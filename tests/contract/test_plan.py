# Copyright 2026 PyMOL Copilot contributors.
"""Contract tests for the immutable plan and canonical rendering.

These tests cover the accepted positive fixture -- `select
copilot_selection, chain A` followed by `color red, copilot_selection` --
and the plan-level guarantees achievable without a parser: canonical
rendering, idempotent rendering, immutability, and rejection of any
operation or sequence outside the recorded fixture.
"""

import pytest

from pmc_core.plan import (
    ActionPlan,
    ColorOperation,
    SelectOperation,
    initial_fixture_plan,
)

FIXTURE_PML = (
    "select copilot_selection, chain A\ncolor red, copilot_selection\n"
)


def test_initial_fixture_plan_renders_canonical_pml() -> None:
    """The accepted fixture renders as the exact canonical `.pml` text."""
    plan = initial_fixture_plan()

    assert plan.render_pml() == FIXTURE_PML


def test_canonical_rendering_is_idempotent() -> None:
    """Rendering the same plan value twice yields identical bytes."""
    plan = initial_fixture_plan()

    assert plan.render_pml() == plan.render_pml()


def test_equivalent_plans_render_identically() -> None:
    """Two separately constructed but equal plans render identically."""
    first = initial_fixture_plan()
    second = ActionPlan(
        operations=(
            SelectOperation(
                selection_name="copilot_selection",
                expression="chain A",
            ),
            ColorOperation(
                color="red",
                selection_name="copilot_selection",
            ),
        )
    )

    assert first == second
    assert first.render_pml() == second.render_pml()


def test_action_plan_is_immutable() -> None:
    """An `ActionPlan` and its operations cannot be mutated after creation."""
    plan = initial_fixture_plan()
    select_op, _color_op = plan.operations

    with pytest.raises(AttributeError):
        plan.operations = ()  # type: ignore[misc]
    with pytest.raises(AttributeError):
        select_op.selection_name = "other"  # type: ignore[misc]


def test_select_operation_rejects_unsupported_selection_name() -> None:
    """A selection name outside the fixture is rejected at construction."""
    with pytest.raises(ValueError, match="unsupported selection name"):
        SelectOperation(selection_name="other_selection", expression="chain A")


def test_select_operation_rejects_unsupported_expression() -> None:
    """A selection expression outside the fixture is rejected."""
    with pytest.raises(ValueError, match="unsupported selection expression"):
        SelectOperation(
            selection_name="copilot_selection", expression="chain B"
        )


def test_color_operation_rejects_unsupported_color() -> None:
    """A color value outside the fixture is rejected at construction."""
    with pytest.raises(ValueError, match="unsupported color value"):
        ColorOperation(color="blue", selection_name="copilot_selection")


def test_color_operation_rejects_unsupported_selection_name() -> None:
    """A selection name outside the fixture is rejected for `color`."""
    with pytest.raises(ValueError, match="unsupported selection name"):
        ColorOperation(color="red", selection_name="other_selection")


def test_action_plan_rejects_wrong_operation_order() -> None:
    """A plan cannot begin with `color` and end with `select`."""
    color_op = ColorOperation(color="red", selection_name="copilot_selection")
    select_op = SelectOperation(
        selection_name="copilot_selection", expression="chain A"
    )

    with pytest.raises(ValueError, match="first operation must be a select"):
        ActionPlan(operations=(color_op, select_op))


def test_action_plan_rejects_wrong_operation_count() -> None:
    """A plan must contain exactly the two-operation fixture sequence."""
    select_op = SelectOperation(
        selection_name="copilot_selection", expression="chain A"
    )

    with pytest.raises(ValueError, match="exactly the select-then-color"):
        ActionPlan(operations=(select_op,))


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
