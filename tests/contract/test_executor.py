# Copyright 2026 PyMOL Copilot contributors.
"""Contract tests for the executor's parent-side validation: no PyMOL.

Covers every failure mode `pmc_core.executor.execute()` rejects before any
process is spawned: an unsupported executor version, an oversized or
malformed snapshot, an incompatible snapshot schema version, and a plan the
default-deny policy denies. Each case asserts a typed `reason` (never a raw
exception string), that no child-process evidence is ever produced for a
rejected request, and that no scratch directory this module's own executor
would create ever appears -- trivially true today since no such code exists
yet, and still asserted so the property is pinned before the spawn path
(added in a later step of this promotion) can regress it.

The real-PyMOL spawn, deadline, kill, and reap evidence lives in
tests/integration/test_executor_boundary.py, since it needs a real PyMOL
child process to produce anything to observe.
"""

import json
import tempfile
from pathlib import Path
from typing import Any

import pytest  # noqa: I001, RUF100  # Keep imports split for Google style.

import pmc_core.executor as executor
from pmc_core.plan import ActionPlan
from pmc_core.plan import ChainTerm
from pmc_core.plan import ColorOperation
from pmc_core.plan import AndClause
from pmc_core.plan import Factor
from pmc_core.plan import OrientOperation
from pmc_core.plan import SelectionExpression
from pmc_core.snapshot import DECLARED_UNSUPPORTED
from pmc_core.snapshot import SNAPSHOT_VERSION
from pmc_core.snapshot import ObjectSnapshot
from pmc_core.snapshot import to_json


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
    technique tests/contract/test_policy.py uses to reach the policy's own
    default-deny path.

    Args:
        operation_type: The frozen dataclass to assemble.
        **fields: The field values to install directly.

    Returns:
        The assembled value, with no validation performed. Typed Any so the
        deliberately invalid value below reaches the executor under test
        rather than being refused by the type checker first.
    """
    value = object.__new__(operation_type)
    for name, field_value in fields.items():
        object.__setattr__(value, name, field_value)
    return value


def _valid_plan() -> ActionPlan:
    """Build a plan that the default-deny policy allows.

    Returns:
        A one-command plan every field of which is within its allowlist.
    """
    return ActionPlan(operations=(OrientOperation(target=chain_a()),))


def _denied_plan() -> ActionPlan:
    """Build a plan the default-deny policy denies.

    Returns:
        A one-command plan wrapping an off-allowlist color, assembled by
        bypassing ColorOperation's own construction-time check so the
        plan-level ActionPlan constructor itself still accepts it -- only
        pmc_core.policy.evaluate_plan re-derives the denial.
    """
    return ActionPlan(
        operations=(
            _bypass(
                ColorOperation,
                color="not_a_real_color_zzz",
                target=chain_a(),
            ),
        )
    )


def _minimal_snapshot() -> ObjectSnapshot:
    """Build the smallest well-formed snapshot.

    Returns:
        An empty-state ObjectSnapshot, sufficient for every executor test
        below that never reaches a real reconstruction.
    """
    return ObjectSnapshot(
        schema_version=SNAPSHOT_VERSION,
        name="fx",
        enabled=True,
        states=(),
        bonds=(),
        view=(),
        settings=(),
        unsupported=DECLARED_UNSUPPORTED,
    )


def _base_request(**overrides: Any) -> executor.ExecutionRequest:
    """Build a well-formed ExecutionRequest, with fields overridden.

    Args:
        **overrides: Fields to override on the well-formed default.

    Returns:
        The constructed ExecutionRequest.
    """
    fields: dict[str, Any] = {
        "executor_version": executor.EXECUTOR_VERSION,
        "plan": _valid_plan(),
        "snapshot_json": to_json(_minimal_snapshot()),
    }
    fields.update(overrides)
    return executor.ExecutionRequest(**fields)


def _scratch_dirs() -> set[Path]:
    """Every executor scratch directory currently on disk.

    Returns:
        The set of matching paths under the system temp directory.
    """
    return set(Path(tempfile.gettempdir()).glob("pmc-executor-*"))


def _assert_rejected(report: executor.ExecutionReport, reason: str) -> None:
    """Assert the four properties every rejected report must have.

    Args:
        report: The report execute() returned.
        reason: The expected typed rejection reason.
    """
    assert report.status == executor.STATUS_REJECTED
    assert report.reason == reason
    assert report.child_pid is None
    assert report.child_terminated is None
    assert report.command_outcomes == ()
    assert report.selection_counts == ()
    assert report.resulting_fingerprint is None


def test_unsupported_executor_version_is_rejected() -> None:
    """A request whose executor_version this module does not know fails."""
    scratch_before = _scratch_dirs()

    report = executor.execute(
        _base_request(executor_version=executor.EXECUTOR_VERSION + 1)
    )

    _assert_rejected(report, executor.REASON_UNSUPPORTED_SCHEMA_VERSION)
    assert report.input_digest is None
    assert _scratch_dirs() == scratch_before


def test_oversized_snapshot_is_rejected() -> None:
    """A snapshot larger than the declared limit fails closed."""
    scratch_before = _scratch_dirs()

    report = executor.execute(_base_request(max_snapshot_bytes=10))

    _assert_rejected(report, executor.REASON_OVERSIZED_INPUT)
    assert report.input_digest is None
    assert _scratch_dirs() == scratch_before


def test_malformed_snapshot_json_is_rejected() -> None:
    """Snapshot JSON that does not even parse fails closed."""
    scratch_before = _scratch_dirs()

    report = executor.execute(_base_request(snapshot_json="{not valid json"))

    _assert_rejected(report, executor.REASON_MALFORMED_INPUT)
    assert report.input_digest is None
    assert _scratch_dirs() == scratch_before


@pytest.mark.parametrize("scalar_json", ["42", "null", "[]", '"hello"', "true"])
def test_non_object_snapshot_json_is_rejected(scalar_json: str) -> None:
    """Syntactically valid JSON that is not an object fails closed.

    `from_json` parses these fine, but then calls
    `.get("schema_version")` on the result, which raises `AttributeError`
    for a scalar, string, or list.

    Args:
        scalar_json: JSON text that parses to a non-object value.
    """
    scratch_before = _scratch_dirs()

    report = executor.execute(_base_request(snapshot_json=scalar_json))

    _assert_rejected(report, executor.REASON_MALFORMED_INPUT)
    assert report.input_digest is None
    assert _scratch_dirs() == scratch_before


def test_snapshot_missing_a_key_is_rejected() -> None:
    """A snapshot JSON object missing a required key fails closed."""
    payload = json.loads(to_json(_minimal_snapshot()))
    del payload["name"]
    scratch_before = _scratch_dirs()

    report = executor.execute(_base_request(snapshot_json=json.dumps(payload)))

    _assert_rejected(report, executor.REASON_MALFORMED_INPUT)
    assert report.input_digest is None
    assert _scratch_dirs() == scratch_before


def test_incompatible_snapshot_schema_version_is_rejected() -> None:
    """A snapshot declaring an unrecognized schema version fails closed."""
    payload = json.loads(to_json(_minimal_snapshot()))
    payload["schema_version"] = SNAPSHOT_VERSION + 1
    scratch_before = _scratch_dirs()

    report = executor.execute(_base_request(snapshot_json=json.dumps(payload)))

    _assert_rejected(report, executor.REASON_UNSUPPORTED_SCHEMA_VERSION)
    assert report.input_digest is None
    assert _scratch_dirs() == scratch_before


def test_policy_denied_plan_is_rejected() -> None:
    """A plan the default-deny policy denies fails closed, unspawned.

    Unlike the six cases above, the snapshot itself parses successfully
    here, so input_digest is populated (H02-S3-F8: the ported prototype
    hardcoded None on every rejection, even after a successful parse).
    """
    scratch_before = _scratch_dirs()

    report = executor.execute(_base_request(plan=_denied_plan()))

    _assert_rejected(report, executor.REASON_POLICY_DENIED)
    assert report.input_digest is not None
    assert report.input_digest.startswith("sha256:")
    assert _scratch_dirs() == scratch_before


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
