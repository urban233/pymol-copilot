# cBioMOL - open C++ and Python platform for BioMOLecular visualization and analysis
# -------------------------------------------------------------------
# This file contains source code for the cBioMOL computer program
# Copyright (C) 2026 Hannah Kullik, Martin Urban (hannah.kullik@studmail.w-hs.de, martin.urban@studmail.w-hs.de)
# Source code is available at <https://github.com/urban233/cBioMOL>
# -------------------------------------------------------------------
# It is unlawful to modify or remove this copyright notice.
# -------------------------------------------------------------------
# Please see the accompanying LICENSE file for further information.
# -------------------------------------------------------------------
# Primary author of this source file:
#
# -------------------------------------------------------------------
# Additional authors of this source file include:
#
# ==============================================================================

"""Session and plan step domain models for the task-workflow UI."""

from __future__ import annotations

import dataclasses
import enum
import re
import uuid


class TaskState(enum.Enum):
    """Lifecycle states for an assistant task session."""

    IDLE = "idle"
    GENERATING = "generating"
    PLAN_READY = "plan_ready"
    EXECUTING = "executing"
    EXECUTED = "executed"
    EXECUTION_FAILED = "execution_failed"
    DONE = "done"
    CANCELLED = "cancelled"


class StepState(enum.Enum):
    """Progress state for a single plan step row."""

    PENDING = "pending"
    ACTIVE = "active"
    DONE = "done"
    SKIPPED = "skipped"


@dataclasses.dataclass
class PlanStep:
    """One parsed tool call displayed in the plan checklist."""

    index: int
    name: str
    arguments: dict
    state: StepState = StepState.PENDING
    warning: str = ""
    display_label: str = ""
    error: str = ""

    def compact_label(self) -> str:
        """Return a single-line label for UI display.

        Returns:
          Tool name followed by compact argument summary.
        """
        if not self.arguments:
            return self.name
        parts = [
            f'{key}="{value}"' if isinstance(value, str) else f"{key}={value}"
            for key, value in self.arguments.items()
        ]
        joined = ", ".join(parts)
        return f"{self.name}({joined})"


@dataclasses.dataclass
class Session:
    """In-memory record of one user task and its generated plan."""

    prompt: str
    mode: str = "visualize"
    dry_run: bool = False
    id: str = dataclasses.field(default_factory=lambda: str(uuid.uuid4()))
    steps: list[PlanStep] = dataclasses.field(default_factory=list)
    summary_prose: str = ""
    raw_assistant_output: str = ""
    state: TaskState = TaskState.IDLE
    execution_log: list[str] = dataclasses.field(default_factory=list)
    saved_session_path: str = ""

    @staticmethod
    def default_pse_filename(prompt: str) -> str:
        """Derive a filesystem-safe default .pse name from the task prompt.

        Args:
          prompt: Full user prompt text.

        Returns:
          Sanitized filename ending with ``.pse``.
        """
        title = Session.title_from_prompt(prompt, max_len=40)
        sanitized = re.sub(r"[^\w\-]+", "_", title, flags=re.UNICODE).strip("_")
        if not sanitized or sanitized == "Task":
            return "pymol_copilot_session.pse"
        return f"{sanitized}.pse"

    @staticmethod
    def title_from_prompt(prompt: str, max_len: int = 60) -> str:
        """Derive a short task title from the first prompt line.

        Args:
          prompt: Full user prompt text.
          max_len: Maximum returned title length.

        Returns:
          Truncated first-line title.
        """
        first_line = (
            prompt.strip().splitlines()[0] if prompt.strip() else "Task"
        )
        if len(first_line) <= max_len:
            return first_line
        return first_line[: max_len - 1] + "…"
