# Copyright 2026 PyMOL Copilot contributors.
"""Comparable live-session evidence for recovery and refusal tests.

The product's extraction boundary is deliberately reused here.  It records
coordinates, colors, supported representations, labels, the view, and the
tracked object settings; the complete name list catches selections and other
objects which a replacement-session restore must not leave behind.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pmc_core.snapshot import ObjectSnapshot
from pmc_core.snapshot import extract


@dataclass(frozen=True)
class SessionFingerprint:
    """The V1-observable state of a live session and its target object."""

    snapshot: ObjectSnapshot
    names: tuple[str, ...]


def capture_session_fingerprint(
    cmd: Any, object_name: str
) -> SessionFingerprint:
    """Capture every V1-observable field before or after one command path."""
    return SessionFingerprint(
        snapshot=extract(cmd, object_name),
        names=tuple(sorted(cmd.get_names("all"))),
    )


def assert_session_unchanged(
    before: SessionFingerprint, after: SessionFingerprint
) -> None:
    """Fail when a supposedly read-only command path changed the session."""
    assert before == after
