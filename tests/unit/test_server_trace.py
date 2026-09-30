# Copyright 2026 PyMOL Copilot contributors.
"""The server's opt-in trace records what the model wrote, and only then.

docs/master_plan.md item 19: explaining a difference between the
integrated and the offline TaskSuccess needs every attempt's raw
completion, which the client never sees. `pmc_server.trace` appends one
line per completion call to a private file, only when `--trace-file`
asks for it.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import sys
import threading
from pathlib import Path
from typing import Any

import pytest

import pmc_server.main as server_main
from pmc_agent.graph import ACCEPTED_CONTRACT_MANIFEST
from pmc_agent.graph import STATE_PENDING_APPROVAL
from pmc_agent.inference.base import ENGINE_UNAVAILABLE
from pmc_agent.inference.base import STOP_END
from pmc_agent.inference.base import CancelToken
from pmc_agent.inference.base import CompletionRequest
from pmc_agent.inference.base import CompletionResult
from pmc_agent.inference.base import EngineFailure
from pmc_agent.inference.fake import FakeEngine
from pmc_agent.inference.unavailable import UnavailableEngine
from pmc_agent.session import RequestGraphSession
from pmc_core.executor import REASON_OK
from pmc_core.executor import STATUS_OK
from pmc_core.executor import ExecutionReport
from pmc_core.executor import ExecutionRequest
from pmc_core.protocol import FIDELITY_EXACT
from pmc_core.protocol import FidelityOutcomeV1
from pmc_core.protocol import StructureSnapshotV1
from pmc_core.snapshot import DECLARED_UNSUPPORTED
from pmc_core.snapshot import SNAPSHOT_VERSION
from pmc_core.snapshot import ObjectSnapshot
from pmc_core.snapshot import to_json
from pmc_server.trace import TracingEngine
from pmc_server.trace import open_trace

_SESSION_ID = "44444444-4444-4444-8444-444444444444"


def _lines(path: Path) -> list[dict[str, Any]]:
    """Read a trace file.

    Args:
        path: The trace file.

    Returns:
        Its decoded lines.
    """
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
    ]


def _ok_executor(_request: ExecutionRequest) -> ExecutionReport:
    """Report success, spawning nothing.

    Args:
        _request: Ignored.

    Returns:
        A `STATUS_OK` report.
    """
    return ExecutionReport(
        executor_version=1,
        status=STATUS_OK,
        reason=REASON_OK,
        input_digest="sha256:test",
        resulting_fingerprint="sha256:" + "0" * 64,
        selection_counts=(),
        command_outcomes=(),
        child_pid=1234,
        child_terminated=True,
        elapsed_seconds=0.01,
    )


def _submit(session: RequestGraphSession) -> dict[str, Any]:
    """Submit one well-formed request.

    Args:
        session: The session to submit against.

    Returns:
        The session's result mapping.
    """
    snapshot = ObjectSnapshot(
        schema_version=SNAPSHOT_VERSION,
        name="fx",
        enabled=True,
        states=(),
        bonds=(),
        view=(),
        settings=(),
        unsupported=DECLARED_UNSUPPORTED,
    )
    return dict(
        session.submit(
            request_id="r-1",
            session_id=_SESSION_ID,
            created_at="2026-09-30T00:00:00.000Z",
            intent="colour chain A red",
            contract_manifest=ACCEPTED_CONTRACT_MANIFEST,
            snapshot_identity=StructureSnapshotV1(
                schema_version="1",
                digest="sha256:test-digest",
                object_name="fx",
                atom_count=0,
                state_count=0,
            ),
            snapshot_json=to_json(snapshot),
            fidelity=FidelityOutcomeV1(
                status=FIDELITY_EXACT,
                reason=REASON_OK,
                mismatch_count=0,
                mismatches=(),
            ),
        )
    )


def test_a_repaired_request_records_both_attempts_raw(tmp_path: Path) -> None:
    """One line per attempt, with the model's text before normalization."""
    path = tmp_path / "trace.jsonl"
    inner = FakeEngine(
        [
            CompletionResult("colour red, chain A\n", "m-1", STOP_END),
            CompletionResult("color red, chain A", "m-1", STOP_END),
        ]
    )
    engine = TracingEngine(inner, open_trace(path))
    session = RequestGraphSession(
        engine=engine, executor=_ok_executor, grammar="root ::= x"
    )

    result = _submit(session)
    engine.close()

    assert result["status"] == STATE_PENDING_APPROVAL
    lines = _lines(path)
    assert [line["sequence"] for line in lines] == [1, 2]
    assert [line["text"] for line in lines] == [
        "colour red, chain A\n",
        "color red, chain A",
    ]
    assert all(line["outcome"] == "completion" for line in lines)
    assert all(line["stop_reason"] == STOP_END for line in lines)
    assert all(line["grammar"] is True for line in lines)
    assert [line["prompt_sha256"] for line in lines] == [
        hashlib.sha256(call.prompt.encode("utf-8")).hexdigest()
        for call in inner.calls
    ]
    assert all(call.prompt not in path.read_text() for call in inner.calls)


def test_an_engine_failure_is_recorded_with_its_category(
    tmp_path: Path,
) -> None:
    """A failed call is a line too, carrying the typed failure."""
    path = tmp_path / "trace.jsonl"
    engine = TracingEngine(
        UnavailableEngine(EngineFailure(ENGINE_UNAVAILABLE, "down")),
        open_trace(path),
    )

    outcome = engine.complete(
        CompletionRequest(
            prompt="p", grammar=None, max_tokens=8, deadline_seconds=1.0
        ),
        cancel=CancelToken(),
    )
    engine.close()

    assert isinstance(outcome, EngineFailure)
    (line,) = _lines(path)
    assert line["outcome"] == "failure"
    assert line["category"] == ENGINE_UNAVAILABLE
    assert line["grammar"] is False
    assert "text" not in line


@pytest.mark.skipif(
    sys.platform == "win32", reason="POSIX permission bits only"
)
def test_the_trace_file_is_private_even_if_it_existed(tmp_path: Path) -> None:
    """A pre-existing, world-readable file is narrowed to user-only."""
    path = tmp_path / "trace.jsonl"
    path.write_text("")
    path.chmod(0o644)

    open_trace(path).close()

    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX symlinks only")
def test_the_trace_file_is_never_a_symlink(tmp_path: Path) -> None:
    """A link planted at the trace path is refused, not followed."""
    target = tmp_path / "elsewhere"
    target.write_text("")
    link = tmp_path / "trace.jsonl"
    link.symlink_to(target)

    with pytest.raises(OSError):
        open_trace(link)


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


def test_by_default_nothing_is_traced(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without `--trace-file`, the server records no completion."""
    assert _captured_serve(monkeypatch, [])["trace_path"] is None


def test_the_trace_flag_names_the_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`--trace-file` reaches `serve`, checked openable at startup."""
    path = tmp_path / "trace.jsonl"

    seen = _captured_serve(monkeypatch, ["--trace-file", str(path)])

    assert seen["trace_path"] == path
    assert path.is_file()


def test_an_unopenable_trace_file_stops_the_server(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A trace that cannot be written is refused before anything starts."""
    started: list[object] = []
    monkeypatch.setattr(
        server_main, "serve", lambda **kwargs: started.append(kwargs)
    )
    with pytest.raises(SystemExit):
        server_main.main(
            [
                "--trace-file",
                str(tmp_path / "absent" / "trace.jsonl"),
                "--handoff",
                "unused.json",
            ]
        )
    assert started == []


def test_serve_traces_the_engine_it_is_given(tmp_path: Path) -> None:
    """The test-only engine seam and the trace compose, and both close."""
    closed: list[str] = []

    class _ClosingEngine(FakeEngine):
        def close(self) -> None:
            closed.append("engine")

    stop = threading.Event()
    stop.set()
    server_main.serve(
        handoff_path=tmp_path / "session.json",
        trace_path=tmp_path / "trace.jsonl",
        engine=_ClosingEngine([]),
        stop=stop,
    )

    assert closed == ["engine"]
    assert (tmp_path / "trace.jsonl").is_file()
    assert not (tmp_path / "session.json").exists()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
