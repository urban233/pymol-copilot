# Copyright 2026 PyMOL Copilot contributors.
"""docs/master_plan.md item 12, scenario 5: the server is unavailable.

A real `pmc_server.main` process, spawned (`python -m pmc_server.main`,
the same "spawn by module name, real environment inheritance" pattern
`pmc_core.executor._run_child` already uses for the sidecar) and then
killed, covering all three sub-cases the brief names:
never started, died mid-session, and up with the engine down. Nothing
here is faked except the Lemonade origin itself, which deliberately names
a port nothing listens on.

Its own real PyMOL launch, separate from every other module in this
package: it spawns and kills a real server process and must not share a
session with `test_scenarios_real_pymol.py`.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from pmc_client.bootstrap import connect_from_handoff
from pmc_client.recovery import RecoveryStore
from scenario_support import FIXTURE_PATH
from scenario_support import OBJECT_NAME
from scenario_support import ConsoleDriver
from scenario_support import assert_unchanged
from scenario_support import capture_fingerprint

import winstage

#: A port nothing listens on, so the Lemonade probe is refused immediately
#: rather than timing out -- keeps this module fast without needing a
#: real Lemonade server anywhere.
_DEAD_LEMONADE_URL = "http://127.0.0.1:1"

INTENT = "Color chain A red."


def _wait_for_file(path: Path, *, timeout_seconds: float) -> bool:
    """Poll for a file's existence.

    Args:
        path: The file to wait for.
        timeout_seconds: How long to poll before giving up.

    Returns:
        True once the file exists; False if the deadline passed first.
    """
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if path.exists():
            return True
        time.sleep(0.05)
    return path.exists()


def _spawn_server(handoff_path: Path) -> subprocess.Popen[str]:
    """Spawn the real production server entrypoint as its own process.

    Args:
        handoff_path: Where the server should write its handoff file.

    Returns:
        The live subprocess handle.
    """
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "pmc_server.main",
            "--lemonade-base-url",
            _DEAD_LEMONADE_URL,
            "--handoff",
            str(handoff_path),
        ],
        env=os.environ.copy(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


@pytest.fixture(scope="module")
def real_pymol() -> Any:
    """Launch real headless PyMOL exactly once for this test module.

    Yields:
        The real PyMOL `cmd` module.
    """
    winstage.ensure_importable()
    import pymol  # pyrefly: ignore.
    from pymol import cmd  # pyrefly: ignore.

    pymol.finish_launching(["pymol", "-qc"])
    try:
        yield cmd
    finally:
        cmd.do("quit")


@pytest.fixture
def loaded_fixture(real_pymol: Any) -> Any:
    """Load the two-chain fixture fresh for one test and clear it after.

    Args:
        real_pymol: The real PyMOL `cmd` module.

    Yields:
        The real PyMOL `cmd` module with only the fixture object loaded.
    """
    real_pymol.delete("all")
    real_pymol.load(str(FIXTURE_PATH), OBJECT_NAME)
    try:
        yield real_pymol
    finally:
        real_pymol.delete("all")


def test_a_server_that_was_never_started_reports_one_bounded_line(
    loaded_fixture: Any, tmp_path: Path
) -> None:
    """Sub-case 1: no handoff file exists at all."""
    before = capture_fingerprint(loaded_fixture)
    output: list[str] = []
    driver = ConsoleDriver(loaded_fixture)

    client = connect_from_handoff(
        # pyrefly: ignore.  __getattr__ delegates the query surface at
        # runtime, but pyrefly cannot verify that structurally.
        driver,
        output.append,
        path=tmp_path / "session.json",
        # Without this, the recovery-directory assertion below checks a
        # path a real RecoveryStore (rooted at the real Path.home()) would
        # never write to at all -- it would pass whether or not a
        # regression actually created one.
        recovery_store=RecoveryStore(tmp_path),
    )

    after = capture_fingerprint(loaded_fixture)
    assert client is None
    assert len(output) == 1
    assert output[0].startswith("copilot:")
    assert_unchanged(before, after)
    assert not (tmp_path / ".pymol-copilot" / "recovery").exists()


def test_server_up_engine_down_then_killed_mid_session(
    loaded_fixture: Any, tmp_path: Path
) -> None:
    """Sub-cases 2 and 3: a real server process, up then killed."""
    handoff = tmp_path / "session.json"
    process = _spawn_server(handoff)
    output: list[str] = []
    driver = ConsoleDriver(loaded_fixture)
    try:
        if not _wait_for_file(handoff, timeout_seconds=15.0):
            process.kill()
            _, stderr = process.communicate(timeout=10.0)
            raise AssertionError(
                f"server never wrote its handoff file; stderr: {stderr}"
            )

        client = connect_from_handoff(
            # pyrefly: ignore.  __getattr__ delegates the query surface at
            # runtime, but pyrefly cannot verify that structurally.
            driver,
            output.append,
            path=handoff,
            # Same reason as the never-started test above: without this,
            # the recovery-directory assertion at the end of this test
            # checks a path nothing here would ever write to.
            recovery_store=RecoveryStore(tmp_path),
        )
        assert client is not None
        assert any("connected" in line for line in output)

        # Sub-case 3: up, engine down. One bounded, actionable line; no
        # plan id; no fallback of any kind. The engine is asked exactly
        # once (this is the only copilot invocation before the process
        # dies, so a single failure line is itself the count).
        before = capture_fingerprint(loaded_fixture)
        output.clear()
        driver.run(f"copilot {INTENT}")
        assert len(output) == 1
        assert output[0].startswith("copilot:")
        assert "p-" not in output[0]
        assert "Start Lemonade" in output[0]
        after_engine_down = capture_fingerprint(loaded_fixture)
        assert_unchanged(before, after_engine_down)

        output.clear()
        driver.run("copilot_health")
        assert len(output) == 1
        health_lines = output[0].splitlines()
        assert any(
            line.strip().startswith("engine:") and "unavailable" in line
            for line in health_lines
        )
        assert health_lines[-1].strip() == "copilot:   ready"

        # Sub-case 2: died mid-session.
        process.terminate()
        try:
            process.wait(timeout=10.0)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10.0)

        output.clear()
        driver.run(f"copilot {INTENT}")
        assert len(output) == 1
        assert output[0].startswith("copilot: loopback request failed")
        after_dead = capture_fingerprint(loaded_fixture)
        assert_unchanged(before, after_dead)

        output.clear()
        driver.run("copilot_health")
        assert len(output) == 1
        dead_health_lines = output[0].splitlines()
        assert any(
            line.strip().startswith("server:") and "unavailable" in line
            for line in dead_health_lines
        )
        assert dead_health_lines[-1].strip() == "copilot:   ready"
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10.0)
        # Popen's own stdout/stderr pipes are never closed just because
        # the child exited -- they stay open file objects in this
        # process until explicitly closed or garbage-collected. Closing
        # them here, rather than leaving that to GC, avoids a
        # ResourceWarning at an unpredictable later point (observed as a
        # real, intermittent pytest failure on Windows CI, since this
        # repository's own filterwarnings turns every warning into one).
        if process.stdout is not None and not process.stdout.closed:
            process.stdout.close()
        if process.stderr is not None and not process.stderr.closed:
            process.stderr.close()
    assert not (tmp_path / ".pymol-copilot" / "recovery").exists()


if __name__ == "__main__":
    # Real PyMOL's headless launch leaves behind cleanup that can complete
    # after this process would otherwise exit, overriding a genuine pytest
    # failure with process exit code 0 (see the same __main__ block in
    # tests/integration/test_real_pymol_command.py). os._exit bypasses that
    # window, and the explicit flushes keep a real failure's traceback from
    # being lost from the captured test log.
    _exit_code = pytest.main([__file__])
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(_exit_code)
