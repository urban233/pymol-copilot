# Copyright 2026 PyMOL Copilot contributors.
"""Real-PyMOL evidence for the sidecar child's closed verb dispatch.

Drives `pmc_sidecar.child.run_plan()` directly against the module-scoped
`real_pymol`/`loaded_fixture` fixtures re-exported by this directory's
`conftest.py`, with no subprocess and no second `pymol.finish_launching()`
call: `run_plan()` assumes reconstruction already happened, which for these
tests is `loaded_fixture`'s own real load of the full-V1 discovery fixture,
not `pmc_core.snapshot.reconstruct`. The fresh-process spawn, deadline,
kill, and reap evidence -- and `child.main()`'s own reconstruct-and-dispatch
sequence -- lives in tests/integration/test_executor_boundary.py, since
proving those needs the boundary genuinely spawning this module as a
subprocess.
"""

from dataclasses import dataclass
from typing import Any

import pytest  # noqa: I001, RUF100  # Keep imports split for Google style.

from pmc_core.executor import OUTCOME_ERROR
from pmc_core.executor import OUTCOME_OK
from pmc_core.executor import REASON_COMMAND_FAILURE
from pmc_core.executor import REASON_OK
from pmc_core.executor import STATUS_FAILED
from pmc_core.executor import STATUS_OK
from pmc_core.plan import ActionPlan
from pmc_core.plan import AndClause
from pmc_core.plan import ChainTerm
from pmc_core.plan import ColorOperation
from pmc_core.plan import Factor
from pmc_core.plan import HideOperation
from pmc_core.plan import NamedSelection
from pmc_core.plan import OrientOperation
from pmc_core.plan import SelectOperation
from pmc_core.plan import SelectionExpression
from pmc_core.plan import ShowOperation
from pmc_sidecar.child import run_plan


def chain_a() -> SelectionExpression:
    """Build the expression `chain A`.

    Returns:
        A one-term expression matching chain A.
    """
    return SelectionExpression(
        clauses=(AndClause(factors=(Factor(ChainTerm("A")),)),)
    )


def _bypass(operation_type: type, **fields: object) -> Any:
    """Assemble a frozen dataclass without running its own checks.

    This is how a bug, or a caller reaching past the typed contract, would
    produce a value the constructors would have refused -- the same
    technique tests/contract/test_policy.py uses to reach that module's own
    default-deny path. Here it reaches run_plan()'s own dispatch defense,
    independent of pmc_core.plan's and pmc_core.policy's separate defenses
    against the same kind of value.

    Args:
        operation_type: The frozen dataclass to assemble.
        **fields: The field values to install directly.

    Returns:
        The assembled value, with no validation performed. Typed Any so the
        deliberately invalid value below reaches run_plan() rather than
        being refused by the type checker first.
    """
    value = object.__new__(operation_type)
    for name, field_value in fields.items():
        object.__setattr__(value, name, field_value)
    return value


def _plan(operation_type: type, **fields: object) -> ActionPlan:
    """Wrap one bypass-assembled operation in a plan without validation.

    Args:
        operation_type: The frozen dataclass to assemble.
        **fields: The field values to install on it directly.

    Returns:
        An ActionPlan wrapping the deliberately invalid operation, itself
        assembled by bypass so ActionPlan's own __post_init__ (which would
        otherwise reject an operation type outside its own allowlist) never
        runs either -- run_plan()'s own defense is what this file tests.
    """
    return _bypass(ActionPlan, operations=(_bypass(operation_type, **fields),))


class _CountingCmd:
    """Wrap a real PyMOL `cmd`, counting genuine calls to one method.

    Every other attribute forwards straight to the wrapped `cmd`
    unchanged, so this stands in for `cmd` in `run_plan()` without
    changing any dispatched command's actual behavior -- only the method
    named at construction is ever counted.
    """

    def __init__(self, real_cmd: Any, counted_method: str) -> None:
        """Wrap a real cmd, counting calls to one of its methods.

        Args:
            real_cmd: The real PyMOL `cmd` module to wrap.
            counted_method: The one method name whose genuine invocations
                to record.
        """
        self._real_cmd = real_cmd
        self._counted_method = counted_method
        self.calls: list[str] = []

    def __getattr__(self, name: str) -> Any:
        """Forward an attribute access, counting the target method's calls.

        Args:
            name: The attribute name being accessed.

        Returns:
            The wrapped cmd's own attribute, wrapped to record a call only
            when name is the counted method.
        """
        attribute = getattr(self._real_cmd, name)
        if name != self._counted_method:
            return attribute

        def _counting_call(*args: Any, **kwargs: Any) -> Any:
            """Record one genuine invocation, then call the real method."""
            self.calls.append(name)
            return attribute(*args, **kwargs)

        return _counting_call


@dataclass(frozen=True)
class _UnknownOperation:
    """A synthetic operation type with no dispatch branch in child.py."""


def test_every_verb_produces_the_expected_observable_change(
    loaded_fixture: Any,
) -> None:
    """Each of the five verbs dispatches to its real PyMOL command.

    Args:
        loaded_fixture: The real PyMOL cmd module with "fx" loaded.
    """
    view_before = loaded_fixture.get_view()
    plan = ActionPlan(
        operations=(
            SelectOperation(selection_name="copilot_sel", expression=chain_a()),
            ColorOperation(color="blue", target=NamedSelection("copilot_sel")),
            ShowOperation(
                representation="spheres",
                target=NamedSelection("copilot_sel"),
            ),
            HideOperation(
                representation="sticks",
                target=NamedSelection("copilot_sel"),
            ),
            OrientOperation(target=NamedSelection("copilot_sel")),
        )
    )

    result = run_plan(loaded_fixture, plan)

    assert result.status == STATUS_OK
    assert result.reason == REASON_OK
    assert [outcome.status for outcome in result.command_outcomes] == [
        OUTCOME_OK
    ] * 5
    assert [outcome.verb for outcome in result.command_outcomes] == [
        "select",
        "color",
        "show",
        "hide",
        "orient",
    ]

    blue_index = loaded_fixture.get_color_index("blue")
    colors: list[int] = []
    loaded_fixture.iterate(
        "copilot_sel", "colors.append(color)", space={"colors": colors}
    )
    assert colors and all(color == blue_index for color in colors)
    # Membership per representation, queried the same way
    # pmc_core.snapshot.extract() does: "<selection> and rep <name>".
    assert loaded_fixture.count_atoms("copilot_sel and rep spheres") == len(
        colors
    )
    assert loaded_fixture.count_atoms("copilot_sel and rep sticks") == 0
    assert loaded_fixture.get_view() != view_before


def test_an_unknown_pymol_error_stops_at_that_index(
    loaded_fixture: Any,
) -> None:
    """A genuine PyMOL command failure fails closed with no later command.

    ColorOperation's own construction-time check already refuses an
    off-allowlist color; bypassing it here proves run_plan()'s own dispatch
    fails closed on a real PyMOL error too, one layer below the typed
    contract's own defense.

    Args:
        loaded_fixture: The real PyMOL cmd module with "fx" loaded.
    """
    plan = _bypass(
        ActionPlan,
        operations=(
            SelectOperation(selection_name="copilot_sel", expression=chain_a()),
            _bypass(
                ColorOperation,
                color="not_a_real_color_zzz",
                target=NamedSelection("copilot_sel"),
            ),
            OrientOperation(target=NamedSelection("copilot_sel")),
        ),
    )

    result = run_plan(loaded_fixture, plan)

    assert result.status == STATUS_FAILED
    assert result.reason == REASON_COMMAND_FAILURE
    assert len(result.command_outcomes) == 2
    assert result.command_outcomes[0].status == OUTCOME_OK
    assert result.command_outcomes[1].verb == "color"
    assert result.command_outcomes[1].status == OUTCOME_ERROR
    assert result.command_outcomes[1].error


def test_a_failing_command_is_dispatched_exactly_once_with_no_retry(
    loaded_fixture: Any,
) -> None:
    """run_plan()'s own dispatch loop never retries a failing command.

    Unlike `test_an_unknown_pymol_error_stops_at_that_index` above, which
    only asserts on the recorded `command_outcomes`, this wraps the real
    `cmd.color` call and counts genuine invocations directly. A silent
    retry loop wrapped around `_dispatch`'s own call would still leave
    `command_outcomes` looking identical -- one recorded failure, same
    index, same error text -- while calling `cmd.color` more than once;
    confirmed empirically by temporarily adding exactly such a loop, which
    left every other test in this promotion (including the one above)
    passing. This test's own counted call list is what closes that gap.

    Args:
        loaded_fixture: The real PyMOL cmd module with "fx" loaded.
    """
    counting_cmd = _CountingCmd(loaded_fixture, "color")
    plan = _bypass(
        ActionPlan,
        operations=(
            SelectOperation(selection_name="copilot_sel", expression=chain_a()),
            _bypass(
                ColorOperation,
                color="not_a_real_color_zzz",
                target=NamedSelection("copilot_sel"),
            ),
        ),
    )

    result = run_plan(counting_cmd, plan)

    assert result.status == STATUS_FAILED
    assert result.reason == REASON_COMMAND_FAILURE
    assert counting_cmd.calls == ["color"]


def test_a_synthetic_operation_type_fails_closed(loaded_fixture: Any) -> None:
    """An operation type outside the allowlist fails closed, not silently.

    Args:
        loaded_fixture: The real PyMOL cmd module with "fx" loaded.
    """
    plan = _bypass(ActionPlan, operations=(_UnknownOperation(),))

    result = run_plan(loaded_fixture, plan)

    assert result.status == STATUS_FAILED
    assert result.reason == REASON_COMMAND_FAILURE
    assert len(result.command_outcomes) == 1
    assert result.command_outcomes[0].verb == "__unsupported__"
    assert result.command_outcomes[0].status == OUTCOME_ERROR


if __name__ == "__main__":
    import os
    import sys

    _exit_code = pytest.main([__file__])
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(_exit_code)
