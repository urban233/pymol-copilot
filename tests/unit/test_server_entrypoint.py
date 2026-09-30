# Copyright 2026 PyMOL Copilot contributors.
"""Hermetic tests for the production server entrypoint.

docs/master_plan.md item 12: the engine fallback, the handoff file, and
the reader that validates it. No PyMOL, no real Lemonade -- every
Lemonade call goes through `httpx.MockTransport`.
"""

from __future__ import annotations

import inspect
import json
import os
import stat
import subprocess
import sys
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

import pmc_server.main as server_main
from pmc_agent.inference.base import EngineFailure
from pmc_agent.inference.lemonade import DEFAULT_BACKEND
from pmc_agent.inference.lemonade import DEFAULT_CHECKPOINT
from pmc_agent.inference.lemonade import DEFAULT_CONNECT_TIMEOUT_SECONDS
from pmc_agent.inference.lemonade import DEFAULT_MODEL_NAME
from pmc_agent.inference.unavailable import UnavailableEngine
from pmc_client.bootstrap import connect_from_handoff
from pmc_client.command import CopilotCommandClient
from pmc_client.recovery import RecoveryStore
from pmc_client.transport import LoopbackPlanClient
from pmc_agent.prompt import build_training_prompt
from pmc_core.grammar import build_grammar
from pmc_core.protocol import HealthRequestV1
from pmc_server.config import load_runtime_config

_FINETUNED = (
    Path(__file__).resolve().parents[2]
    / "configs"
    / "evaluation"
    / "finetuned.json"
)


class _FakeSession:
    """The minimal live-session surface `register_copilot` needs.

    `keyword` mirrors real PyMOL's own attribute, populated by `extend()`
    exactly as `tests/integration/test_command.py`'s own fake does: the
    same shape `register()`'s `cmd.keyword["copilot"][4] = ...` line needs.
    """

    def __init__(self) -> None:
        """Record every registered command name and its keyword entry."""
        self.registered: list[str] = []
        self.keyword: dict[str, list[Any]] = {}

    def extend(self, name: str, callback: Any) -> None:
        """Record a registered command name and its keyword entry.

        Args:
            name: Command name to register.
            callback: The registered callback.
        """
        self.registered.append(name)
        self.keyword[name] = [callback, 0, 0, ",", 11]

    def __getattr__(self, _name: str) -> Any:
        """Never queried by registration or a bootstrap refusal path."""
        raise AssertionError("unexpected live-session query")


def _refusing_client(status: int) -> httpx.Client:
    """Build a client whose every request fails with one HTTP status.

    Args:
        status: The HTTP status every request receives.

    Returns:
        A hermetic client that never reaches a network.
    """

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status)

    return httpx.Client(
        base_url="http://127.0.0.1", transport=httpx.MockTransport(handler)
    )


def test_build_engine_returns_unavailable_on_a_failed_probe() -> None:
    """A failed capability probe becomes `UnavailableEngine`, not a crash."""
    engine = server_main.build_engine(
        base_url="http://127.0.0.1", client=_refusing_client(503)
    )

    assert isinstance(engine, UnavailableEngine)
    assert engine.health().state != "ready"


def test_build_engine_never_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    """`build_engine` calls `connect_lemonade` exactly once."""
    calls: list[str] = []

    def fake_connect(
        *, base_url: str, client: Any, **options: Any
    ) -> EngineFailure:
        del client, options
        calls.append(base_url)
        return EngineFailure("engine_unavailable", "refused")

    monkeypatch.setattr(server_main, "connect_lemonade", fake_connect)

    server_main.build_engine(base_url="http://127.0.0.1")

    assert len(calls) == 1


def test_build_engine_returns_a_real_engine_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A successful probe returns the connected engine, never wrapped."""
    sentinel = object()

    def fake_connect(*, base_url: str, client: Any, **options: Any) -> Any:
        del base_url, client, options
        return sentinel

    monkeypatch.setattr(server_main, "connect_lemonade", fake_connect)

    engine = server_main.build_engine(base_url="http://127.0.0.1")

    assert engine is sentinel
    assert not isinstance(engine, UnavailableEngine)


def _capture_connect(
    monkeypatch: pytest.MonkeyPatch,
) -> list[dict[str, Any]]:
    """Record every `connect_lemonade` call's arguments; refuse each one.

    Args:
        monkeypatch: Pytest's monkeypatch fixture.

    Returns:
        The list the calls' keyword arguments are appended to.
    """
    calls: list[dict[str, Any]] = []

    def fake_connect(**kwargs: Any) -> EngineFailure:
        calls.append(kwargs)
        return EngineFailure("engine_unavailable", "refused")

    monkeypatch.setattr(server_main, "connect_lemonade", fake_connect)
    return calls


def test_build_engine_defaults_are_the_evaluated_ones(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without options: the adapter's model, loaded the evaluated way."""
    calls = _capture_connect(monkeypatch)

    server_main.build_engine(base_url="http://127.0.0.1")

    assert calls[0]["model_name"] == DEFAULT_MODEL_NAME
    assert calls[0]["checkpoint"] == DEFAULT_CHECKPOINT
    assert calls[0]["backend"] == DEFAULT_BACKEND
    assert calls[0]["context_size"] == 16384
    assert calls[0]["read_timeout_seconds"] == 600.0
    assert (
        calls[0]["connect_timeout_seconds"] == DEFAULT_CONNECT_TIMEOUT_SECONDS
    )


def test_build_engine_passes_the_chosen_model_through(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Engine options reach the adapter's probe unchanged."""
    calls = _capture_connect(monkeypatch)
    options = server_main.EngineOptions(
        model_name="tuned",
        checkpoint="/models/tuned/tuned.gguf",
        backend="cuda",
        context_size=16384,
        read_timeout_seconds=600.0,
    )

    server_main.build_engine(base_url="http://127.0.0.1", options=options)

    assert {k: calls[0][k] for k in _OPTION_KEYS} == {
        "model_name": "tuned",
        "checkpoint": "/models/tuned/tuned.gguf",
        "backend": "cuda",
        "context_size": 16384,
        "read_timeout_seconds": 600.0,
    }


_OPTION_KEYS = (
    "model_name",
    "checkpoint",
    "backend",
    "context_size",
    "read_timeout_seconds",
)


def _captured_serve(
    monkeypatch: pytest.MonkeyPatch, argv: list[str]
) -> dict[str, Any]:
    """Run `main` with `serve` replaced, and return what it was given.

    Args:
        monkeypatch: Pytest's monkeypatch fixture.
        argv: The command line.

    Returns:
        `serve`'s keyword arguments.
    """
    seen: dict[str, Any] = {}
    monkeypatch.setattr(
        server_main, "serve", lambda **kwargs: seen.update(kwargs)
    )
    assert server_main.main([*argv, "--handoff", "unused.json"]) == 0
    return seen


def test_main_defaults_serve_the_way_the_model_was_evaluated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No flags: the training prompt, the grammar, the evaluated bounds."""
    seen = _captured_serve(monkeypatch, [])

    assert seen["engine_options"] == server_main.EngineOptions()
    assert seen["generation"] == server_main.GenerationOptions(
        prompt="training", grammar=True, max_tokens=256, deadline_seconds=600.0
    )
    assert seen["expected"] is None


def test_main_no_grammar_sends_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """`--no-grammar` turns the default grammar off."""
    seen = _captured_serve(monkeypatch, ["--no-grammar"])

    assert seen["generation"].grammar is False


def test_main_config_sets_the_engine_and_the_bounds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`--config` takes the engine and generation from the evaluated file."""
    seen = _captured_serve(
        monkeypatch, ["--config", str(_FINETUNED), "--no-grammar"]
    )
    recorded = json.loads(_FINETUNED.read_text(encoding="utf-8"))
    engine = recorded["engine"]

    assert seen["base_url"] == engine["base_url"]
    assert seen["engine_options"] == server_main.EngineOptions(
        model_name=engine["model_name"],
        checkpoint=engine["checkpoint"],
        backend=engine["backend"],
        context_size=engine["context_size"],
        read_timeout_seconds=engine["read_timeout_seconds"],
        connect_timeout_seconds=engine["connect_timeout_seconds"],
    )
    assert seen["generation"] == server_main.GenerationOptions(
        prompt="training",
        grammar=False,
        max_tokens=recorded["generation"]["max_tokens"],
        deadline_seconds=recorded["generation"]["deadline_seconds"],
    )
    assert seen["expected"].engine == seen["engine_options"]


@pytest.mark.parametrize(
    "flags",
    [
        ["--model-name", "other"],
        ["--context-size", "4096"],
        ["--lemonade-base-url", "http://127.0.0.1:1"],
        ["--max-tokens", "1024"],
    ],
)
def test_main_refuses_a_config_combined_with_a_setting_flag(
    monkeypatch: pytest.MonkeyPatch, flags: list[str]
) -> None:
    """One run has one source of truth for what it loads and sends."""
    started: list[object] = []
    monkeypatch.setattr(
        server_main, "serve", lambda **kwargs: started.append(kwargs)
    )
    with pytest.raises(SystemExit):
        server_main.main(
            ["--config", str(_FINETUNED), *flags, "--handoff", "unused.json"]
        )
    assert started == []


def test_main_refuses_a_missing_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A config that cannot be read stops the server at startup."""
    monkeypatch.setattr(server_main, "serve", lambda **_kwargs: None)
    with pytest.raises(SystemExit):
        server_main.main(
            ["--config", str(tmp_path / "absent.json"), "--handoff", "x"]
        )


class _ConnectedEngine:
    """The part of a proven `LemonadeEngine` the config check reads."""

    def __init__(self, model_identity: str, lemonade_version: str) -> None:
        """Report a fixed identity and Lemonade version.

        Args:
            model_identity: The identity to report.
            lemonade_version: The Lemonade version to report.
        """
        self.model_identity = model_identity
        self.capabilities = SimpleNamespace(lemonade_version=lemonade_version)
        self.closed = False

    def close(self) -> None:
        """Record that the engine was released."""
        self.closed = True


def _check_against_config(
    monkeypatch: pytest.MonkeyPatch,
    *,
    model_identity: str | None = None,
    lemonade_version: str | None = None,
    llamacpp_args: str | None = None,
) -> tuple[Any, _ConnectedEngine]:
    """Connect a fake engine and check it against the fine-tuned config.

    Each value left None is the config's own.

    Args:
        monkeypatch: Pytest's monkeypatch fixture.
        model_identity: The identity the engine reports.
        lemonade_version: The Lemonade version it reports.
        llamacpp_args: The llama.cpp arguments health reports.

    Returns:
        What `build_engine` returned, and the connected fake.
    """
    config = load_runtime_config(_FINETUNED)
    connected = _ConnectedEngine(
        model_identity or config.engine.model_identity,
        lemonade_version or config.provenance["lemonade_version"],
    )
    monkeypatch.setattr(
        server_main, "connect_lemonade", lambda **_kwargs: connected
    )
    monkeypatch.setattr(
        server_main,
        "loaded_llamacpp_args",
        lambda **_kwargs: llamacpp_args or config.provenance["llamacpp_args"],
    )
    engine = server_main.build_engine(
        base_url=config.base_url, options=config.engine, expected=config
    )
    return engine, connected


def test_build_engine_accepts_the_engine_the_config_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The evaluated engine is served."""
    engine, connected = _check_against_config(monkeypatch)

    assert engine is connected
    assert not connected.closed


@pytest.mark.parametrize(
    ("mismatch", "field"),
    [
        ({"model_identity": "other@other.gguf"}, "the engine is"),
        ({"lemonade_version": "11.8.0"}, "lemonade_version"),
        (
            {
                "llamacpp_args": (
                    "--chat-template-kwargs "
                    '\'{"date_string":"30 Sep 2026"}\' --parallel 1'
                )
            },
            "llamacpp_args",
        ),
    ],
)
def test_build_engine_refuses_an_engine_the_config_does_not_record(
    monkeypatch: pytest.MonkeyPatch, mismatch: dict[str, str], field: str
) -> None:
    """Another model, Lemonade or chat-template date is not served."""
    engine, connected = _check_against_config(monkeypatch, **mismatch)

    assert isinstance(engine, UnavailableEngine)
    assert connected.closed
    health = engine.health()
    assert health.failure is not None
    assert field in health.failure.message
    assert "finetuned.json" in health.failure.message


def test_main_flags_select_the_fine_tuned_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The flags configure the model, the prompt, the grammar and bounds."""
    seen = _captured_serve(
        monkeypatch,
        [
            "--model-name",
            "tuned",
            "--checkpoint",
            "/models/tuned/tuned.gguf",
            "--backend",
            "cuda",
            "--context-size",
            "16384",
            "--read-timeout-seconds",
            "600",
            "--prompt",
            "training",
            "--grammar",
            "--max-tokens",
            "256",
            "--generation-deadline-seconds",
            "600",
        ],
    )

    assert seen["engine_options"] == server_main.EngineOptions(
        model_name="tuned",
        checkpoint="/models/tuned/tuned.gguf",
        backend="cuda",
        context_size=16384,
        read_timeout_seconds=600.0,
    )
    assert seen["generation"] == server_main.GenerationOptions(
        prompt="training", grammar=True, max_tokens=256, deadline_seconds=600.0
    )


def test_main_refuses_an_unknown_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only the known prompt builders can be selected."""
    monkeypatch.setattr(server_main, "serve", lambda **_kwargs: None)
    with pytest.raises(SystemExit):
        server_main.main(["--prompt", "few-shot", "--handoff", "unused.json"])


@pytest.mark.parametrize(
    "flags",
    [
        ["--max-tokens", "0"],
        ["--generation-deadline-seconds", "0"],
        ["--generation-deadline-seconds", "nan"],
    ],
)
def test_main_refuses_bounds_no_completion_accepts(
    monkeypatch: pytest.MonkeyPatch, flags: list[str]
) -> None:
    """A bound every request would refuse stops the server at startup."""
    started: list[object] = []
    monkeypatch.setattr(
        server_main, "serve", lambda **kwargs: started.append(kwargs)
    )
    with pytest.raises(SystemExit):
        server_main.main([*flags, "--handoff", "unused.json"])
    assert started == []


def test_serve_gives_the_session_the_chosen_prompt_and_grammar(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The session is built with the selected prompt builder and grammar."""
    _capture_connect(monkeypatch)
    built: list[dict[str, Any]] = []
    real = server_main.RequestGraphSession

    def recording_session(**kwargs: Any) -> Any:
        built.append(kwargs)
        return real(**kwargs)

    monkeypatch.setattr(server_main, "RequestGraphSession", recording_session)
    stop = threading.Event()
    stop.set()
    server_main.serve(
        handoff_path=tmp_path / "session.json",
        generation=server_main.GenerationOptions(
            prompt="training", grammar=True, max_tokens=256
        ),
        stop=stop,
    )

    assert built[0]["prompt_builder"] is build_training_prompt
    assert built[0]["grammar"] == build_grammar()
    assert built[0]["max_tokens"] == 256


def test_write_handoff_is_private_and_names_the_real_port(
    tmp_path: Path,
) -> None:
    """The handoff file is mode 0600, parses, and names the real port."""
    path = tmp_path / "session.json"

    server_main.write_handoff(path, port=54321, credential="c" * 43, pid=1)

    assert path.exists()
    if os.name != "nt":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    payload = json.loads(path.read_text())
    assert payload["port"] == 54321
    assert payload["host"] == "127.0.0.1"
    assert payload["credential"] == "c" * 43


def test_write_handoff_never_chmods_a_pre_existing_directory(
    tmp_path: Path,
) -> None:
    """A directory `--handoff` already points into is left untouched.

    Martin's own scenario: `--handoff session.json` (the current working
    directory), `--handoff ~/session.json` (the home directory), and
    `--handoff /tmp/pmc.json` (a directory the current user does not own)
    must never have their mode changed -- unconditionally chmodding a
    directory this call did not create either mutates a directory it does
    not own, or, when the current user does not own it, raises
    `PermissionError` and crashes the server right after it started.
    """
    directory = tmp_path / "already-exists"
    directory.mkdir()
    if os.name != "nt":
        directory.chmod(0o751)

    server_main.write_handoff(
        directory / "session.json", port=1, credential="c" * 43, pid=1
    )

    if os.name != "nt":
        assert stat.S_IMODE(directory.stat().st_mode) == 0o751


def test_write_handoff_chmods_a_directory_it_creates_itself(
    tmp_path: Path,
) -> None:
    """A directory `write_handoff` creates fresh is still made private.

    `--handoff` can name a path under more than one not-yet-existing
    ancestor (`mkdir(parents=True)` then creates every level in one call),
    so both the leaf directory and the intermediate one it creates along
    the way must end up private, not just the leaf.
    """
    directory = tmp_path / "brand-new" / "nested"

    server_main.write_handoff(
        directory / "session.json", port=1, credential="c" * 43, pid=1
    )

    if os.name != "nt":
        assert stat.S_IMODE(directory.stat().st_mode) == 0o700
        assert stat.S_IMODE(directory.parent.stat().st_mode) == 0o700


def test_write_handoff_creates_the_staged_file_already_restricted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The staged file is created at mode 0600 directly, not chmodded after.

    `Path.write_text` creates a file at the platform's default (typically
    world-readable) mode first, and only a later `os.chmod` narrows it --
    leaving a window in which another local user could read the live
    credential before this process gets to that `chmod` call. `os.open`'s
    own `mode` argument applies atomically at creation, closing that
    window entirely, so nothing calling `os.open` here should ever pass a
    wider mode than `_FILE_MODE`.
    """
    if os.name == "nt":
        pytest.skip("POSIX file mode semantics only")
    seen_modes: list[int] = []
    real_open = os.open

    def recording_open(path: Path, flags: int, mode: int = 0o777) -> int:
        seen_modes.append(mode)
        return real_open(path, flags, mode)

    monkeypatch.setattr(server_main.os, "open", recording_open)

    server_main.write_handoff(
        tmp_path / "session.json", port=1, credential="c" * 43, pid=1
    )

    assert seen_modes == [server_main._FILE_MODE]


def test_remove_handoff_if_own_removes_a_file_this_process_wrote(
    tmp_path: Path,
) -> None:
    """A handoff file naming this process's own pid is removed."""
    path = tmp_path / "session.json"
    server_main.write_handoff(path, port=1, credential="c" * 43, pid=4242)

    server_main.remove_handoff_if_own(path, pid=4242)

    assert not path.exists()


def test_remove_handoff_if_own_never_deletes_a_second_servers_handoff(
    tmp_path: Path,
) -> None:
    """A second server overwriting the same path is never deleted.

    Not by the first server's own shutdown. Martin's own scenario:
    server A is running; server B starts and
    overwrites the same (most often default, unspecified `--handoff`)
    path with its own port and credential; A is then stopped. A's own
    shutdown must not delete B's live handoff, or a client reading it
    afterward finds nothing even though a real server is still up.
    """
    path = tmp_path / "session.json"
    server_main.write_handoff(path, port=1, credential="a" * 43, pid=1111)

    server_main.write_handoff(path, port=2, credential="b" * 43, pid=2222)
    server_main.remove_handoff_if_own(path, pid=1111)

    assert path.exists()
    payload = json.loads(path.read_text())
    assert payload["pid"] == 2222
    assert payload["port"] == 2


def test_remove_handoff_if_own_survives_a_racing_replace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A second server's own handoff, installed mid-removal, is never deleted.

    A tighter form of Martin's own scenario above: instead of server B
    overwriting the path before A's removal even starts, B's own
    `os.replace` lands in the gap a plain read-then-unlink can't close --
    right after A has renamed its own file out of the way (confirming
    ownership) but before A has actually deleted anything. A plain
    `path.unlink()` at that point would delete whatever B just installed;
    the rename-first fix means A only ever deletes the private copy it
    already renamed away and re-confirmed as its own.
    """
    path = tmp_path / "session.json"
    server_main.write_handoff(path, port=1, credential="a" * 43, pid=1111)
    real_replace = os.replace
    raced = False

    def racing_replace(src: Path, dst: Path) -> None:
        nonlocal raced
        real_replace(src, dst)
        if not raced and src == path:
            raced = True
            # Server B installs its own live handoff right here, in the
            # window remove_handoff_if_own's rename-first fix closes.
            path.write_text(
                json.dumps(
                    {
                        "host": "127.0.0.1",
                        "port": 2,
                        "credential": "b" * 43,
                        "pid": 2222,
                    }
                )
            )

    monkeypatch.setattr(server_main.os, "replace", racing_replace)

    server_main.remove_handoff_if_own(path, pid=1111)

    assert raced
    assert path.exists()
    payload = json.loads(path.read_text())
    assert payload["pid"] == 2222


def test_remove_handoff_if_own_never_clobbers_a_third_servers_handoff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A third server's handoff, installed mid-restore, is never overwritten.

    Server A owns `claimed` as B's rescued file (B's own pid mismatches A's,
    so A is about to put B's file back). Right before that restore lands, a
    third server C starts and writes its own live handoff to `path`. The
    restore must not clobber C's fresher handoff with B's stale one.
    """
    path = tmp_path / "session.json"
    server_main.write_handoff(path, port=1, credential="a" * 43, pid=1111)
    server_main.write_handoff(path, port=2, credential="b" * 43, pid=2222)
    real_link = os.link
    raced = False

    def racing_link(src: Path, dst: Path) -> None:
        nonlocal raced
        if not raced and dst == path:
            raced = True
            # Server C installs its own live handoff right here, in the
            # window between A's rename-away and this restore attempt.
            server_main.write_handoff(
                path, port=3, credential="c" * 43, pid=3333
            )
        real_link(src, dst)

    monkeypatch.setattr(server_main.os, "link", racing_link)

    server_main.remove_handoff_if_own(path, pid=1111)

    assert raced
    assert path.exists()
    payload = json.loads(path.read_text())
    assert payload["pid"] == 3333


def test_remove_handoff_if_own_tolerates_a_missing_file(
    tmp_path: Path,
) -> None:
    """No file at the path is not an error -- there is nothing to remove."""
    server_main.remove_handoff_if_own(tmp_path / "missing.json", pid=1)


def test_remove_handoff_if_own_tolerates_a_malformed_file(
    tmp_path: Path,
) -> None:
    """A file that is not valid JSON is left alone, never raised on."""
    path = tmp_path / "session.json"
    path.write_text("not json at all")

    server_main.remove_handoff_if_own(path, pid=1)

    assert path.exists()


def test_serve_installs_signal_handlers_before_starting_the_server() -> None:
    """Signal handlers are installed before `server.start()`, not after.

    A SIGTERM arriving between `server.start()`/`write_handoff` and signal
    registration would use Python's default action and kill the process
    without ever running `serve`'s own `finally`, leaving a handoff file
    behind that names a port and credential nothing is listening on
    anymore. A real race like that can't be exercised deterministically
    without introducing timing-dependent flakiness, so this is checked
    structurally instead: `signal.signal` must appear, in source order,
    before `server.start()`.
    """
    source = inspect.getsource(server_main.serve)
    assert source.index("signal.signal(signal.SIGINT") < source.index(
        "server.start()"
    )


def test_serve_waits_on_a_timed_loop_not_an_untimed_wait() -> None:
    """The stop-wait is a timed loop, not a single untimed `Event.wait()`.

    On Windows (Python 3.13), an untimed `Event.wait()` blocks on a lock
    acquire that cannot be interrupted, so the SIGINT handler installed
    above never actually runs while the main thread is parked there, and
    Ctrl+C cannot stop the server. Checked structurally, for the same
    reason as the signal-ordering test above: this is a platform-specific
    behavior difference a hermetic, single-platform suite cannot reproduce
    directly.
    """
    source = inspect.getsource(server_main.serve)
    assert "own_stop.wait()" not in source
    assert "own_stop.wait(timeout=" in source


def test_serve_starts_and_writes_the_handoff_with_an_unavailable_engine(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The server starts (and answers health) even when Lemonade is down.

    SPECIFICATION.md:609: "Server remains available for diagnostics; no
    unconstrained fallback."
    """
    monkeypatch.setattr(
        server_main,
        "connect_lemonade",
        lambda **_kwargs: EngineFailure("engine_unavailable", "refused"),
    )
    handoff = tmp_path / "session.json"
    stop = threading.Event()
    ready = threading.Event()
    ports: list[int] = []

    thread = threading.Thread(
        target=server_main.serve,
        kwargs={
            "handoff_path": handoff,
            "stop": stop,
            "ready": lambda port: (ports.append(port), ready.set()),
        },
        daemon=True,
    )
    thread.start()
    try:
        assert ready.wait(5.0)
        written = json.loads(handoff.read_text())
        credential = written["credential"]
        assert isinstance(credential, str)
        client = LoopbackPlanClient(ports[0], credential)
        response = client.health(
            HealthRequestV1(
                request_id="11111111-1111-4111-8111-111111111111",
                session_id="22222222-2222-4222-8222-222222222222",
            )
        )
        assert response.engine.state != "ready"
    finally:
        stop.set()
        thread.join(timeout=5.0)
    assert not thread.is_alive()
    assert not handoff.exists()


def test_connect_from_handoff_refuses_a_missing_file(tmp_path: Path) -> None:
    """No handoff file: one bounded line, no registration, `None`."""
    output: list[str] = []
    session = _FakeSession()

    client = connect_from_handoff(
        # pyrefly: ignore.  __getattr__ delegates the query surface at
        # runtime, but pyrefly cannot verify that structurally.
        session,
        output.append,
        path=tmp_path / "missing.json",
    )

    assert client is None
    assert session.registered == []
    assert len(output) == 1
    assert output[0].startswith("copilot:")


_VALID_HANDOFF: dict[str, object] = {
    "host": "127.0.0.1",
    "port": 54321,
    "credential": "c" * 43,
    "pid": os.getpid(),
}

# Each case invalidates exactly one field of an otherwise fully valid
# handoff -- including a live `pid` -- and names the refusal it must hit,
# so a case can only pass because *its own* field's check refused it, not
# because a later check (for instance the missing-pid refusal) happened to
# catch the payload instead.
_INVALID_HANDOFF_CASES: list[tuple[str, dict[str, object], str]] = [
    ("any_host", {"host": "0.0.0.0"}, "non-loopback host"),
    ("routable_host", {"host": "10.0.0.5"}, "non-loopback host"),
    # Loopback names the transport would never actually dial: it always
    # connects to 127.0.0.1, so accepting these would send the credential
    # to whatever listens there instead.
    ("localhost_name", {"host": "localhost"}, "non-loopback host"),
    ("ipv6_loopback", {"host": "::1"}, "non-loopback host"),
    ("other_ipv4_loopback", {"host": "127.0.0.2"}, "non-loopback host"),
    ("port_low", {"port": 0}, "invalid port"),
    ("port_high", {"port": 70000}, "invalid port"),
    ("short_credential", {"credential": "short"}, "invalid credential"),
    # 43 characters -- at least `_MIN_CREDENTIAL_LENGTH` -- so this case
    # actually reaches and exercises the alphabet check; a short string
    # with a space in it (the original form of this case) was rejected by
    # the length check first, and would still pass even if the alphabet
    # check were removed entirely.
    ("bad_alphabet", {"credential": "c" * 42 + "!"}, "invalid credential"),
]


@pytest.mark.parametrize(
    ("override", "refusal"),
    [(override, refusal) for _, override, refusal in _INVALID_HANDOFF_CASES],
    ids=[case_id for case_id, _, _ in _INVALID_HANDOFF_CASES],
)
def test_connect_from_handoff_refuses_every_invalid_field(
    tmp_path: Path, override: dict[str, object], refusal: str
) -> None:
    """Each invalid field is refused, with one bounded line and `None`."""
    path = tmp_path / "session.json"
    path.write_text(json.dumps({**_VALID_HANDOFF, **override}))
    output: list[str] = []
    session = _FakeSession()

    # pyrefly: ignore.  __getattr__ delegates the query surface at
    # runtime, but pyrefly cannot verify that structurally.
    client = connect_from_handoff(session, output.append, path=path)

    assert client is None
    assert session.registered == []
    assert len(output) == 1
    assert refusal in output[0]


def _dead_pid() -> int:
    """Return a pid guaranteed not to name a running process.

    Spawns a trivial child and waits for it: on every platform this repo
    targets, `Popen.wait()` reaps the child before returning, so its pid
    cannot still be running -- and is exceedingly unlikely to have been
    recycled by the time this function returns.
    """
    process = subprocess.Popen([sys.executable, "-c", "pass"])
    process.wait(timeout=10.0)
    return process.pid


def test_connect_from_handoff_refuses_a_handoff_naming_a_dead_process(
    tmp_path: Path,
) -> None:
    """A handoff naming a pid that is no longer running is refused.

    Martin's own scenario: a handoff left behind by a SIGKILLed server, a
    Windows `terminate()`, or a power loss. Accepting it anyway would
    report "connected" to a server that is not there, or, once the same
    ephemeral port has been rebound by an unrelated local process, send
    that process the credential and the session snapshot.
    """
    path = tmp_path / "session.json"
    path.write_text(
        json.dumps(
            {
                "host": "127.0.0.1",
                "port": 54321,
                "credential": "c" * 43,
                "pid": _dead_pid(),
            }
        )
    )
    output: list[str] = []
    session = _FakeSession()

    # pyrefly: ignore.  __getattr__ delegates the query surface at
    # runtime, but pyrefly cannot verify that structurally.
    client = connect_from_handoff(session, output.append, path=path)

    assert client is None
    assert session.registered == []
    assert len(output) == 1
    assert "no longer running" in output[0]


@pytest.mark.parametrize("pid", [0, -1, "54321", 3.5, True])
def test_connect_from_handoff_refuses_a_malformed_pid(
    tmp_path: Path, pid: object
) -> None:
    """A pid that is not a positive int is refused, never probed."""
    path = tmp_path / "session.json"
    path.write_text(
        json.dumps(
            {
                "host": "127.0.0.1",
                "port": 54321,
                "credential": "c" * 43,
                "pid": pid,
            }
        )
    )
    output: list[str] = []
    session = _FakeSession()

    # pyrefly: ignore.  __getattr__ delegates the query surface at
    # runtime, but pyrefly cannot verify that structurally.
    client = connect_from_handoff(session, output.append, path=path)

    assert client is None
    assert session.registered == []
    assert len(output) == 1


def test_connect_from_handoff_refuses_an_out_of_range_pid_without_raising(
    tmp_path: Path,
) -> None:
    """A pid past the platform's pid range is refused, never raised.

    `os.kill(2**40, 0)` raises `OverflowError`, not `OSError`, and
    `OpenProcess`'s `DWORD` argument raises `ctypes.ArgumentError` -- either
    would otherwise escape into PyMOL's own command dispatch.
    """
    path = tmp_path / "session.json"
    path.write_text(json.dumps({**_VALID_HANDOFF, "pid": 2**40}))
    output: list[str] = []
    session = _FakeSession()

    # pyrefly: ignore.  __getattr__ delegates the query surface at
    # runtime, but pyrefly cannot verify that structurally.
    client = connect_from_handoff(session, output.append, path=path)

    assert client is None
    assert session.registered == []
    assert len(output) == 1
    assert "no longer running" in output[0]


def test_connect_from_handoff_refuses_a_handoff_missing_a_pid(
    tmp_path: Path,
) -> None:
    """A handoff with no `pid` field at all is refused, not treated as valid."""
    path = tmp_path / "session.json"
    path.write_text(
        json.dumps({"host": "127.0.0.1", "port": 54321, "credential": "c" * 43})
    )
    output: list[str] = []
    session = _FakeSession()

    # pyrefly: ignore.  __getattr__ delegates the query surface at
    # runtime, but pyrefly cannot verify that structurally.
    client = connect_from_handoff(session, output.append, path=path)

    assert client is None
    assert session.registered == []
    assert len(output) == 1


def test_process_is_running_is_true_for_this_process() -> None:
    """The current process is, trivially, itself running."""
    from pmc_client.bootstrap import _process_is_running

    assert _process_is_running(os.getpid())


def test_process_is_running_is_false_for_a_dead_process() -> None:
    """A pid known to have already exited is reported as not running."""
    from pmc_client.bootstrap import _process_is_running

    assert not _process_is_running(_dead_pid())


def test_windows_process_is_running_is_true_on_access_denied() -> None:
    """A NULL handle from ERROR_ACCESS_DENIED still means "running".

    Martin's own first scenario: the target runs under a different
    account or at a higher integrity level, so `OpenProcess` fails, but
    the process genuinely exists. Treating every `OpenProcess` failure as
    "gone" would refuse a live server with "no longer running".
    """
    from pmc_client.bootstrap import _ERROR_ACCESS_DENIED
    from pmc_client.bootstrap import _windows_process_is_running

    assert _windows_process_is_running(
        4242,
        open_process=lambda _pid: 0,
        get_exit_code_process=lambda _handle: None,
        close_handle=lambda _handle: None,
        get_last_error=lambda: _ERROR_ACCESS_DENIED,
    )


def test_windows_process_is_running_is_false_on_other_open_failures() -> None:
    """A NULL handle from any other error means the process is gone."""
    from pmc_client.bootstrap import _windows_process_is_running

    assert not _windows_process_is_running(
        4242,
        open_process=lambda _pid: 0,
        get_exit_code_process=lambda _handle: None,
        close_handle=lambda _handle: None,
        get_last_error=lambda: 87,  # ERROR_INVALID_PARAMETER
    )


def test_windows_process_is_running_checks_the_exit_code() -> None:
    """A valid handle to an already-exited process is still "not running".

    Martin's own second scenario: the target crashed, but some parent (a
    `Popen` launcher, for instance) still holds its process handle, so
    `OpenProcess` succeeds even though the process itself is gone.
    Treating any returned handle as "running" would accept a stale
    handoff naming a dead port.
    """
    from pmc_client.bootstrap import _windows_process_is_running

    closed: list[int] = []

    assert not _windows_process_is_running(
        4242,
        open_process=lambda _pid: 99,
        get_exit_code_process=lambda _handle: 0,  # exited cleanly
        close_handle=closed.append,
        get_last_error=lambda: 0,
    )
    assert closed == [99]


def test_windows_process_is_running_is_true_for_still_active() -> None:
    """A valid handle whose exit code is STILL_ACTIVE means "running"."""
    from pmc_client.bootstrap import _STILL_ACTIVE
    from pmc_client.bootstrap import _windows_process_is_running

    closed: list[int] = []

    assert _windows_process_is_running(
        4242,
        open_process=lambda _pid: 99,
        get_exit_code_process=lambda _handle: _STILL_ACTIVE,
        close_handle=closed.append,
        get_last_error=lambda: 0,
    )
    assert closed == [99]


def test_windows_process_is_running_is_false_when_exit_code_call_fails() -> (
    None
):
    """A failed `GetExitCodeProcess` call is not treated as "running".

    There is nothing left to trust it on.
    """
    from pmc_client.bootstrap import _windows_process_is_running

    closed: list[int] = []

    assert not _windows_process_is_running(
        4242,
        open_process=lambda _pid: 99,
        get_exit_code_process=lambda _handle: None,
        close_handle=closed.append,
        get_last_error=lambda: 0,
    )
    assert closed == [99]


def test_connect_from_handoff_refuses_a_non_json_file(tmp_path: Path) -> None:
    """A file that is not JSON is refused, not raised."""
    path = tmp_path / "session.json"
    path.write_text("not json at all")
    output: list[str] = []

    # pyrefly: ignore.  __getattr__ delegates the query surface at
    # runtime, but pyrefly cannot verify that structurally.
    client = connect_from_handoff(_FakeSession(), output.append, path=path)

    assert client is None
    assert len(output) == 1


def test_connect_from_handoff_refuses_deeply_nested_json_without_raising(
    tmp_path: Path,
) -> None:
    """Deeply nested JSON is refused, not raised.

    `json.loads`'s own recursive-descent parser raises `RecursionError`
    for input like this -- comfortably under `MAX_HANDOFF_BYTES` -- which
    is not `json.JSONDecodeError` and was not caught here before.
    """
    path = tmp_path / "session.json"
    path.write_text("[" * 3000)
    output: list[str] = []

    # pyrefly: ignore.  __getattr__ delegates the query surface at
    # runtime, but pyrefly cannot verify that structurally.
    client = connect_from_handoff(_FakeSession(), output.append, path=path)

    assert client is None
    assert len(output) == 1


def test_connect_from_handoff_refuses_an_oversized_file(
    tmp_path: Path,
) -> None:
    """A file larger than the small cap is refused before it is parsed."""
    from pmc_client.bootstrap import MAX_HANDOFF_BYTES

    path = tmp_path / "session.json"
    path.write_text(
        json.dumps(
            {
                **_VALID_HANDOFF,
                "padding": "x" * (MAX_HANDOFF_BYTES + 1),
            }
        )
    )
    output: list[str] = []

    # pyrefly: ignore.  __getattr__ delegates the query surface at
    # runtime, but pyrefly cannot verify that structurally.
    client = connect_from_handoff(_FakeSession(), output.append, path=path)

    assert client is None
    assert len(output) == 1
    assert "larger than expected" in output[0]


def test_connect_from_handoff_refuses_a_non_regular_file_without_blocking(
    tmp_path: Path,
) -> None:
    """A FIFO at the handoff path is refused before any read blocks on it."""
    path = tmp_path / "session.json"
    # A decorator skips execution but leaves the body visible to Windows
    # type checking, where os.mkfifo does not exist. Guard it here so both
    # pytest and the type checker recognize the platform restriction.
    if sys.platform != "win32":
        os.mkfifo(path)
    else:
        pytest.skip("named pipes are POSIX-only")
    output: list[str] = []

    # pyrefly: ignore.  __getattr__ delegates the query surface at
    # runtime, but pyrefly cannot verify that structurally.
    client = connect_from_handoff(_FakeSession(), output.append, path=path)

    assert client is None
    assert len(output) == 1


def test_connect_from_handoff_registers_on_a_valid_file(
    tmp_path: Path,
) -> None:
    """A fully valid handoff registers every command and reports success."""
    path = tmp_path / "session.json"
    path.write_text(
        json.dumps(
            {
                "host": "127.0.0.1",
                "port": 54321,
                "credential": "c" * 43,
                "pid": os.getpid(),
            }
        )
    )
    output: list[str] = []
    session = _FakeSession()

    # pyrefly: ignore.  __getattr__ delegates the query surface at
    # runtime, but pyrefly cannot verify that structurally.
    client = connect_from_handoff(session, output.append, path=path)

    assert isinstance(client, CopilotCommandClient)
    assert "copilot" in session.registered
    assert "copilot_apply" in session.registered
    assert "copilot_health" in session.registered
    assert any("connected" in line for line in output)


def test_connect_from_handoff_forwards_an_injected_recovery_store(
    tmp_path: Path,
) -> None:
    """A caller-supplied recovery store reaches the registered client.

    Without this, a test pointed at a real handoff file has no way to
    root recovery points anywhere but the real user's home directory --
    the same gap Martin's own review found: a regression that wrote one
    would land in `~/.pymol-copilot/recovery`, invisible to a test
    watching its own `tmp_path`.
    """
    path = tmp_path / "session.json"
    path.write_text(
        json.dumps(
            {
                "host": "127.0.0.1",
                "port": 54321,
                "credential": "c" * 43,
                "pid": os.getpid(),
            }
        )
    )
    output: list[str] = []
    store = RecoveryStore(tmp_path)

    client = connect_from_handoff(
        # pyrefly: ignore.  __getattr__ delegates the query surface at
        # runtime, but pyrefly cannot verify that structurally.
        _FakeSession(),
        output.append,
        path=path,
        recovery_store=store,
    )

    assert isinstance(client, CopilotCommandClient)
    assert client._recovery_store is store


def test_client_closure_never_reaches_langgraph_or_httpx() -> None:
    """`bootstrap.py` must not widen `pmc_client`'s own forbidden closure.

    Static, not a Bazel query: `pmc_client.bootstrap` imports nothing
    outside `pmc_client`/`pmc_core`, checked directly against its own
    module source rather than trusted by inspection.
    """
    import ast
    import inspect

    import pmc_client.bootstrap as bootstrap_module

    tree = ast.parse(inspect.getsource(bootstrap_module))
    modules = {
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    } | {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert "langgraph" not in modules
    assert "httpx" not in modules
    assert "pmc_agent" not in modules


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
