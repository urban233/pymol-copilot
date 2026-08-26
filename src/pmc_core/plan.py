# Copyright 2026 PyMOL Copilot contributors.
"""Immutable typed plan and operation contracts for the V1 fixture.

This module defines the frozen domain values that represent the initial
accepted native .pml fixture -- one select operation that creates the
selection copilot_selection from the expression chain A, followed by one
color operation that applies red to that selection. It also defines the
canonical, idempotent rendering of that plan back to native .pml text.

No parser or policy lives here. Construction is restricted to the recorded
fixture values so that only the accepted operations can exist as typed
values; broadening those values requires an accepted fixture and security
evidence in the owning design.
"""

from __future__ import annotations

from dataclasses import dataclass

#: The only selection name accepted by the initial fixture.
FIXTURE_SELECTION_NAME = "copilot_selection"

#: The only selection expression accepted by the initial fixture.
FIXTURE_SELECTION_EXPRESSION = "chain A"

#: The only color value accepted by the initial fixture.
FIXTURE_COLOR_VALUE = "red"


@dataclass(frozen=True)
class SelectOperation:
    """A typed select operation for the initial fixture.

    Attributes:
        selection_name: The name of the selection created by this operation.
        expression: The selection expression assigned to selection_name.
    """

    selection_name: str
    expression: str

    def __post_init__(self) -> None:
        """Reject any value outside the recorded fixture.

        Raises:
            ValueError: If selection_name or expression is not the
                exact recorded fixture value.
        """
        if self.selection_name != FIXTURE_SELECTION_NAME:
            raise ValueError(
                f"unsupported selection name: {self.selection_name!r}"
            )
        if self.expression != FIXTURE_SELECTION_EXPRESSION:
            raise ValueError(
                f"unsupported selection expression: {self.expression!r}"
            )

    def render(self) -> str:
        """Render this operation as one canonical native .pml line.

        Returns:
            The canonical select command text without a trailing newline.
        """
        return f"select {self.selection_name}, {self.expression}"


@dataclass(frozen=True)
class ColorOperation:
    """A typed color operation for the initial fixture.

    Attributes:
        color: The color value applied to selection_name.
        selection_name: The name of the selection this operation colors.
    """

    color: str
    selection_name: str

    def __post_init__(self) -> None:
        """Reject any value outside the recorded fixture.

        Raises:
            ValueError: If color or selection_name is not the exact
                recorded fixture value.
        """
        if self.color != FIXTURE_COLOR_VALUE:
            raise ValueError(f"unsupported color value: {self.color!r}")
        if self.selection_name != FIXTURE_SELECTION_NAME:
            raise ValueError(
                f"unsupported selection name: {self.selection_name!r}"
            )

    def render(self) -> str:
        """Render this operation as one canonical native .pml line.

        Returns:
            The canonical color command text without a trailing newline.
        """
        return f"color {self.color}, {self.selection_name}"


#: The ordered operation types accepted in an ActionPlan.
type OPERATION = SelectOperation | ColorOperation
# Preserve the original runtime name for callers importing this type alias.
globals()["Operation"] = OPERATION


@dataclass(frozen=True)
class ActionPlan:
    """An immutable, ordered plan over the initial fixture operations.

    Attributes:
        operations: The ordered operations that make up this plan. The
            initial fixture requires exactly one SelectOperation followed by
            one ColorOperation that colors the selection created by that
            SelectOperation.
    """

    operations: tuple[OPERATION, ...]

    def __post_init__(self) -> None:
        """Reject any operation sequence outside the recorded fixture.

        Raises:
            ValueError: If operations is not exactly the recorded select-then-
                color fixture sequence.
        """
        if len(self.operations) != 2:
            raise ValueError(
                "plan must contain exactly the select-then-color fixture"
            )
        select_op, color_op = self.operations
        if not isinstance(select_op, SelectOperation):
            raise ValueError("first operation must be a select operation")
        if not isinstance(color_op, ColorOperation):
            raise ValueError("second operation must be a color operation")
        if color_op.selection_name != select_op.selection_name:
            raise ValueError(
                "color operation must reference the selection created by "
                "the preceding select operation"
            )

    def render_pml(self) -> str:
        """Render this plan as canonical native .pml text.

        Rendering is idempotent: rendering the same plan value always
        produces the same bytes, and those bytes describe exactly the
        commands that will execute in order.

        Returns:
            The canonical .pml text, one command per line, terminated by
            a single trailing newline.
        """
        lines = (operation.render() for operation in self.operations)
        return "\n".join(lines) + "\n"


def initial_fixture_plan() -> ActionPlan:
    """Build the accepted initial fixture plan.

    Returns:
        The immutable ActionPlan for the recorded fixture: select
        copilot_selection, chain A followed by color red, copilot_selection.
    """
    return ActionPlan(
        operations=(
            SelectOperation(
                selection_name=FIXTURE_SELECTION_NAME,
                expression=FIXTURE_SELECTION_EXPRESSION,
            ),
            ColorOperation(
                color=FIXTURE_COLOR_VALUE,
                selection_name=FIXTURE_SELECTION_NAME,
            ),
        )
    )
