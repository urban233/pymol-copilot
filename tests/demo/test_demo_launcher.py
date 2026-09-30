# Copyright 2026 PyMOL Copilot contributors.
"""The demo's two beats end as the demo needs them to.

docs/master_plan.md item 19. The real server runs in this process with a
scripted engine that answers the demo's gold plan, and the launcher's
own rehearsal drives real headless PyMOL through the real client: the
first beat applies and rolls back, the second fails one verb on purpose
and is restored. The failure proxy fails only the verb it names.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import winstage

import copilot_demo
from pmc_agent.inference.base import STOP_END
from pmc_agent.inference.fake import FakeEngine
from pmc_agent.inference.base import CompletionResult
from pmc_server.main import serve


@pytest.fixture(scope="module")
def cmd() -> Iterator[Any]:
    """Launch real headless PyMOL once for this module.

    Yields:
        PyMOL's `cmd`.
    """
    winstage.ensure_importable()
    import pymol  # pyrefly: ignore[missing-import]
    from pymol import cmd as real_cmd  # pyrefly: ignore[missing-import]

    pymol.finish_launching(["pymol", "-qc"])
    yield real_cmd


@pytest.fixture
def handoff(tmp_path: Path) -> Iterator[Path]:
    """Serve the demo's gold plan from the real server, in this process.

    Args:
        tmp_path: Where the handoff is written.

    Yields:
        The handoff file.
    """
    plan = copilot_demo.demo_sample().plan_pml
    engine = FakeEngine([CompletionResult(plan, "demo@gold", STOP_END)] * 8)
    stop, ready = threading.Event(), threading.Event()
    path = tmp_path / "session.json"
    thread = threading.Thread(
        target=serve,
        kwargs={
            "handoff_path": path,
            "engine": engine,
            "ready": lambda _port: ready.set(),
            "stop": stop,
        },
        daemon=True,
    )
    thread.start()
    assert ready.wait(60)
    try:
        yield path
    finally:
        stop.set()
        thread.join(timeout=30)


def test_the_first_beat_applies_and_rolls_back(
    cmd: Any, handoff: Path, tmp_path: Path
) -> None:
    """Preview changes nothing, apply changes it, rollback restores it."""
    result = copilot_demo.rehearse(
        cmd,
        handoff=handoff,
        recovery_root=tmp_path,
        fail_on=None,
        sample=copilot_demo.demo_sample(),
    )

    assert result.passed, (result.problems, result.transcript)
    assert "DEMO:" not in result.transcript
    assert "rolled back" in result.transcript


def test_the_second_beat_fails_on_purpose_and_is_restored(
    cmd: Any, handoff: Path, tmp_path: Path
) -> None:
    """The staged failure is announced, and the session comes back whole."""
    result = copilot_demo.rehearse(
        cmd,
        handoff=handoff,
        recovery_root=tmp_path,
        fail_on="color",
        sample=copilot_demo.demo_sample(),
    )

    assert result.passed, (result.problems, result.transcript)
    assert result.transcript.startswith(copilot_demo.banner("color"))
    assert "restored cleanly" in result.transcript


class _Recorder:
    """A stand-in `cmd` that records which verbs were called."""

    def __init__(self) -> None:
        """Start with no calls."""
        self.calls: list[str] = []

    def __getattr__(self, name: str) -> Any:
        """Record a call to any verb.

        Args:
            name: The verb.

        Returns:
            A function that records it.
        """
        return lambda *_args, **_kwargs: self.calls.append(name)


def test_the_proxy_fails_only_the_named_verb() -> None:
    """Every other verb reaches PyMOL unchanged."""
    recorder = _Recorder()
    proxy = copilot_demo.FailOnVerbProxy(recorder, "color")

    for verb in ("select", "show", "hide", "orient", "extend", "do"):
        getattr(proxy, verb)("x")
    with pytest.raises(RuntimeError, match="on purpose"):
        proxy.color("red", "chain A")

    assert recorder.calls == [
        "select",
        "show",
        "hide",
        "orient",
        "extend",
        "do",
    ]


def test_the_proxy_refuses_a_verb_the_demo_does_not_name() -> None:
    """Only the command language's verbs can be failed."""
    with pytest.raises(ValueError, match="cannot fail"):
        copilot_demo.FailOnVerbProxy(_Recorder(), "delete")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
