# Copyright 2026 PyMOL Copilot contributors.
"""The end-to-end scenarios against the fine-tuned model, opt-in.

docs/master_plan.md item 19: "Pair one trained model artifact with the
runtime and run the end-to-end suite against it." Every other module in
this package scripts the engine; this one starts the production server
(`python -m pmc_server.main --config configs/evaluation/finetuned.json`)
against the local fine-tuned model, exactly as a user would, and drives
it from real headless PyMOL through the handoff file and the real
client.

It runs only when `PMC_LEMONADE_BASE_URL` names the running engine's
loopback origin, the same opt-in `//tests/integration:lemonade_real`
uses, so CI stays scripted. Bring the engine up first with the same
config (configs/evaluation/engine/README.md); the server refuses any
other engine.

The intent is gold item `gold_056` on its own held-out structure, which
the fine-tuned model got right offline under the grammar; the engine
answers deterministically (temperature 0), so each scenario asserts on
the resulting state, not on the plan's text. The scenarios that need a
completion no real model can be made to produce on demand -- a denied
command (`test_denied_command_real_pymol.py`), a hostile completion,
and an unavailable engine (`test_server_unavailable_real_pymol.py`) --
stay scripted, where they are.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import hashlib
import json
import os
import stat
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest

import scenario_support
from pmc_agent.inference.lemonade import _local_origin
from pmc_client.bootstrap import connect_from_handoff
from pmc_client.recovery import RecoveryStore
from pmc_core.snapshot import extract
from pmc_core.snapshot import reconstruct
from pmc_core.snapshot import to_json
from pmc_data.gold_set import DEFAULT_GOLD_SAMPLES_PATH
from pmc_data.sample import Sample
from pmc_data.sample import read_samples
from pmc_eval.prompt import snapshot_for
from scenario_support import ConsoleDriver
from scenario_support import FailColorProxy

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs" / "evaluation" / "finetuned.json"
SAMPLE_ID = "gold_056"

#: A real model answers slower than the scripted engine the rest of this
#: package uses: this raises every console invocation's deadline.
REAL_ENGINE_DEADLINE_SECONDS = 600.0

#: How long the server may take to load the model and write its handoff.
SERVER_START_SECONDS = 600.0


def _sample() -> Sample:
    """Read gold item `SAMPLE_ID`.

    Returns:
        The sample.
    """
    return next(
        s
        for s in read_samples(DEFAULT_GOLD_SAMPLES_PATH)
        if s.sample_id == SAMPLE_ID
    )


@pytest.fixture(scope="module")
def handoff(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    """Start the production server against the fine-tuned model.

    Args:
        tmp_path_factory: Pytest's temporary-directory factory.

    Yields:
        The server's handoff file.
    """
    base_url = os.environ.get("PMC_LEMONADE_BASE_URL")
    if base_url is None:
        pytest.skip(
            "PMC_LEMONADE_BASE_URL is unset; the real-engine scenarios are "
            "opt-in"
        )
    _local_origin(base_url)
    configured = json.loads(CONFIG.read_text(encoding="utf-8"))["engine"]
    if urlsplit(base_url).port != urlsplit(configured["base_url"]).port:
        pytest.fail(
            f"the server serves from {CONFIG.name}, whose engine is at "
            f"{configured['base_url']}; PMC_LEMONADE_BASE_URL names "
            f"{base_url}"
        )
    directory = tmp_path_factory.mktemp("server")
    path = directory / "session.json"
    log_path = directory / "server.log"
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "pmc_server.main",
                "--config",
                str(CONFIG),
                "--handoff",
                str(path),
            ],
            stdout=log,
            stderr=subprocess.STDOUT,
            env=os.environ.copy(),
        )
    try:
        deadline = time.monotonic() + SERVER_START_SECONDS
        while not path.exists():
            if process.poll() is not None or time.monotonic() > deadline:
                pytest.fail(
                    "the server did not start:\n" + log_path.read_text()
                )
            time.sleep(0.5)
        yield path
    finally:
        process.terminate()
        try:
            process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def _fingerprint(cmd: Any, name: str) -> str:
    """Fingerprint one live object the way the sidecar does.

    Args:
        cmd: PyMOL's `cmd`.
        name: The object.

    Returns:
        `sha256:<hex>` of its canonical snapshot.
    """
    text = to_json(extract(cmd, name))
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


class _Session:
    """One connected client on the rebuilt gold structure."""

    def __init__(self, cmd: Any, driver: ConsoleDriver, root: Path) -> None:
        """Hold what a scenario drives.

        Args:
            cmd: The real PyMOL `cmd`.
            driver: The console driver the client is registered on.
            root: The recovery store's root.
        """
        self.cmd = cmd
        self.driver = driver
        self.root = root
        self.output: list[str] = []
        self.name = snapshot_for(_sample()).name

    def run(self, command_line: str) -> str:
        """Run one console command and return what it printed.

        Args:
            command_line: What a user types.

        Returns:
            The client's output.
        """
        self.output.clear()
        self.driver.run(command_line)
        text = "\n".join(self.output)
        self.output.clear()
        return text

    def preview(self) -> str:
        """Ask for gold item `SAMPLE_ID`'s intent and return its plan id.

        Returns:
            The previewed, approvable plan's identifier.
        """
        text = self.run(f"copilot {_sample().intent}")
        first = next(
            line
            for line in text.splitlines()
            if line.startswith("copilot plan ")
        )
        assert "apply:     copilot_apply" in text, text
        return first.removeprefix("copilot plan ").split(" ", 1)[0]

    def fingerprint(self) -> str:
        """Fingerprint the gold structure now.

        Returns:
            Its fingerprint.
        """
        return _fingerprint(self.cmd, self.name)


def _connect(
    real_pymol: Any,
    handoff: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    wrap: bool = False,
) -> _Session:
    """Rebuild the gold structure and connect a client to the server.

    Args:
        real_pymol: The real PyMOL `cmd`.
        handoff: The server's handoff file.
        tmp_path: The recovery store's root.
        monkeypatch: Pytest's monkeypatch fixture.
        wrap: Whether the client drives PyMOL through `FailColorProxy`,
            whose `color` fails after the plan's `select` has run.

    Returns:
        The connected session.
    """
    monkeypatch.setattr(
        scenario_support,
        "INVOCATION_DEADLINE_SECONDS",
        REAL_ENGINE_DEADLINE_SECONDS,
    )
    real_pymol.delete("all")
    reconstruct(real_pymol, snapshot_for(_sample()))
    target = FailColorProxy(real_pymol) if wrap else real_pymol
    session = _Session(real_pymol, ConsoleDriver(target), tmp_path)
    client = connect_from_handoff(
        # pyrefly: ignore.  __getattr__ delegates the query surface at
        # runtime, but pyrefly cannot verify that structurally.
        session.driver,
        session.output.append,
        path=handoff,
        recovery_store=RecoveryStore(tmp_path),
    )
    assert client is not None, session.output
    session.output.clear()
    return session


@pytest.fixture
def session(
    real_pymol: Any,
    handoff: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[_Session]:
    """A client connected on a freshly rebuilt gold structure.

    Args:
        real_pymol: The real PyMOL `cmd`.
        handoff: The server's handoff file.
        tmp_path: The recovery store's root.
        monkeypatch: Pytest's monkeypatch fixture.

    Yields:
        The session.
    """
    yield _connect(real_pymol, handoff, tmp_path, monkeypatch)
    real_pymol.delete("all")


def test_health_names_the_fine_tuned_model_with_every_contract_matching(
    session: _Session,
) -> None:
    """The client talks to the evaluated model, on matching contracts."""
    configured = json.loads(CONFIG.read_text(encoding="utf-8"))["engine"]

    text = session.run("copilot_health")

    assert "engine:    ready" in text, text
    assert (
        f"model:     {configured['model_name']}@{configured['checkpoint']}"
        in text
    ), text
    assert "all match this client" in text, text


def test_a_preview_changes_nothing(session: _Session) -> None:
    """The model's plan is shown, and the session is untouched."""
    before = session.fingerprint()
    names = session.cmd.get_names("all")

    session.preview()

    assert session.fingerprint() == before
    assert session.cmd.get_names("all") == names


def test_apply_reaches_the_offline_result_with_a_private_recovery_point(
    session: _Session,
) -> None:
    """The applied state is the gold plan's, and `.pse` is user-only."""
    plan_id = session.preview()

    text = session.run(f"copilot_apply {plan_id}")

    assert f"copilot_apply: plan {plan_id} applied." in text, text
    assert session.fingerprint() == _sample().verification.resulting_fingerprint
    (point,) = (session.root / ".pymol-copilot" / "recovery").glob("*.pse")
    if sys.platform != "win32":
        assert stat.S_IMODE(point.stat().st_mode) == 0o600


def test_rollback_restores_the_session_from_before_apply(
    session: _Session,
) -> None:
    """One-level rollback returns the whole session to its pre-apply state."""
    before = session.fingerprint()
    plan_id = session.preview()
    session.run(f"copilot_apply {plan_id}")
    assert session.fingerprint() != before

    text = session.run(f"copilot_rollback {plan_id}")

    assert f"plan {plan_id} rolled back" in text, text
    assert session.fingerprint() == before


def test_a_mid_apply_failure_is_restored_automatically(
    real_pymol: Any,
    handoff: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A command that fails mid-plan leaves the pre-apply session."""
    session = _connect(real_pymol, handoff, tmp_path, monkeypatch, wrap=True)
    try:
        before = session.fingerprint()
        names = session.cmd.get_names("all")
        plan_id = session.preview()

        text = session.run(f"copilot_apply {plan_id}")

        assert (
            f"copilot_apply: plan {plan_id} failed and the complete session "
            "was restored cleanly." in text
        ), text
        assert session.fingerprint() == before
        assert session.cmd.get_names("all") == names
    finally:
        real_pymol.delete("all")


def test_a_change_after_preview_refuses_apply(session: _Session) -> None:
    """A plan bound to a session that changed is never applied."""
    plan_id = session.preview()
    session.cmd.color("red", "chain B")
    changed = session.fingerprint()

    text = session.run(f"copilot_apply {plan_id}")

    assert "Nothing was applied." in text, text
    assert session.fingerprint() == changed


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
