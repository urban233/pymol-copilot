# Copyright 2026 PyMOL Copilot contributors.
"""Contract tests for strict V1 client-server protocol codecs."""

import json
from dataclasses import replace

import pytest  # noqa: I001, RUF100  # Keep imports split for Google style.

from pmc_core.plan import MAX_COMMANDS
from pmc_core.plan import ActionPlan
from pmc_core.plan import AndClause
from pmc_core.plan import ChainTerm
from pmc_core.plan import ColorOperation
from pmc_core.plan import Factor
from pmc_core.plan import NamedSelection
from pmc_core.plan import SelectOperation
from pmc_core.plan import SelectionExpression
from pmc_core.plan import ShowOperation
from pmc_core.plan import HideOperation
from pmc_core.plan import OrientOperation
from pmc_core.errors import CATEGORY_UNKNOWN
from pmc_core.errors import ERROR_ENVELOPE_VERSION
from pmc_core.errors import ExecutionErrorV1
from pmc_core.executor import REASON_OK
from pmc_core.protocol import PROTOCOL_VERSION
from pmc_core.protocol import FIDELITY_EXACT
from pmc_core.protocol import FIDELITY_NOT_EXACT
from pmc_core.protocol import FIDELITY_UNAVAILABLE
from pmc_core.protocol import MAX_FIDELITY_MISMATCH_BYTES
from pmc_core.protocol import MAX_FIDELITY_MISMATCHES
from pmc_core.protocol import CommandOutcomeV1
from pmc_core.protocol import ContractManifestV1
from pmc_core.protocol import ExecutionReportV1
from pmc_core.protocol import FailedPlanResponseV1
from pmc_core.protocol import FailureEnvelopeV1
from pmc_core.protocol import FidelityOutcomeV1
from pmc_core.protocol import CancelRequestV1
from pmc_core.protocol import ApplyOutcomeRequestV1
from pmc_core.protocol import ApplyRequestV1
from pmc_core.protocol import APPLY_OUTCOME_APPLIED
from pmc_core.protocol import APPLY_OUTCOME_RESTORED
from pmc_core.protocol import APPLY_OUTCOME_ROLLED_BACK
from pmc_core.protocol import PlanRequestV1
from pmc_core.protocol import ProtocolDecodeError
from pmc_core.protocol import RejectRequestV1
from pmc_core.protocol import SelectionCountV1
from pmc_core.protocol import StructureSnapshotV1
from pmc_core.protocol import ValidatedPlanResponseV1
from pmc_core.protocol import ValidationReportV1
from pmc_core.protocol import decode_cancel_request_json
from pmc_core.protocol import decode_apply_outcome_request_json
from pmc_core.protocol import decode_apply_request_json
from pmc_core.protocol import decode_execution_error
from pmc_core.protocol import decode_json
from pmc_core.protocol import decode_plan
from pmc_core.protocol import decode_reject_request_json
from pmc_core.protocol import encode_json
from pmc_core.protocol import encode_plan

REQUEST_IDS = {
    "requestId": "11111111-1111-4111-8111-111111111111",
    "sessionId": "22222222-2222-4222-8222-222222222222",
}

PLAN_ID = "33333333-3333-4333-8333-333333333333"


def fixture_plan() -> ActionPlan:
    """Build the two-command plan these protocol fixtures carry.

    pmc_core no longer ships a fixture plan of its own, and this module
    must not reach into pmc_data or pmc_server for one, so it builds the
    plan from the typed values directly.

    Returns:
        select copilot_selection, chain A followed by
        color red, copilot_selection.
    """
    return ActionPlan(
        operations=(
            SelectOperation(
                selection_name="copilot_selection",
                expression=SelectionExpression(
                    clauses=(AndClause(factors=(Factor(ChainTerm("A")),)),)
                ),
            ),
            ColorOperation(
                color="red", target=NamedSelection("copilot_selection")
            ),
        )
    )


def request() -> PlanRequestV1:
    """Build the accepted request fixture.

    Returns:
        The accepted plan request.
    """
    return PlanRequestV1(
        request_id=REQUEST_IDS["requestId"],
        session_id=REQUEST_IDS["sessionId"],
        created_at="2026-08-26T14:22:03.123Z",
        contract_manifest=ContractManifestV1("1", "1", "1"),
        intent="Select chain A and color it red.",
        snapshot=StructureSnapshotV1(
            schema_version="1",
            digest="sha256:example-chain-a-digest",
            object_name="one-object-chain-a-v1",
            atom_count=2,
            state_count=1,
        ),
        snapshot_json="{}",
        fidelity=FidelityOutcomeV1(
            status=FIDELITY_EXACT,
            reason=REASON_OK,
            mismatch_count=0,
            mismatches=(),
        ),
    )


def reject_request() -> RejectRequestV1:
    """Build the accepted reject-request fixture.

    Returns:
        The accepted reject request.
    """
    return RejectRequestV1(
        request_id=REQUEST_IDS["requestId"],
        session_id=REQUEST_IDS["sessionId"],
        plan_id=PLAN_ID,
    )


def cancel_request() -> CancelRequestV1:
    """Build the accepted cancel-request fixture.

    Returns:
        The accepted cancel request.
    """
    return CancelRequestV1(
        request_id=REQUEST_IDS["requestId"],
        session_id=REQUEST_IDS["sessionId"],
    )


def apply_request() -> ApplyRequestV1:
    """Build the accepted apply-request fixture."""
    return ApplyRequestV1(
        request_id=REQUEST_IDS["requestId"],
        session_id=REQUEST_IDS["sessionId"],
        plan_id=PLAN_ID,
    )


def apply_outcome_request(
    outcome: str = APPLY_OUTCOME_APPLIED,
) -> ApplyOutcomeRequestV1:
    """Build the accepted apply-outcome fixture."""
    return ApplyOutcomeRequestV1(
        request_id=REQUEST_IDS["requestId"],
        session_id=REQUEST_IDS["sessionId"],
        plan_id=PLAN_ID,
        outcome=outcome,
    )


def response() -> ValidatedPlanResponseV1:
    """Build the accepted validated response fixture.

    Returns:
        The accepted validated plan response.
    """
    return ValidatedPlanResponseV1(
        request_id=REQUEST_IDS["requestId"],
        session_id=REQUEST_IDS["sessionId"],
        received_at="2026-08-26T14:22:03.124Z",
        validated_at="2026-08-26T14:22:03.220Z",
        action_plan=fixture_plan(),
        validation=ValidationReportV1(
            "passed",
            "sha256:example-chain-a-digest",
            True,
            (),
            (SelectionCountV1("copilot_selection", 1020),),
            0,
        ),
        plan_id="33333333-3333-4333-8333-333333333333",
        snapshot_digest="sha256:example-chain-a-digest",
        expires_at="2026-08-26T14:27:03.220Z",
        model_identity="test-model@test-checkpoint",
        target_object="one-object-chain-a-v1",
    )


def test_request_fixture_round_trips_as_strict_json() -> None:
    """The accepted request survives JSON encoding and decoding."""
    assert decode_json(encode_json(request())) == request()


def test_request_rejects_unknown_fields() -> None:
    """Requests with unknown fields are rejected."""
    payload = request().to_dict()
    payload["unexpected"] = True

    with pytest.raises(ProtocolDecodeError):
        PlanRequestV1.from_dict(payload)


@pytest.mark.parametrize("field", ["requestId", "sessionId"])
def test_request_rejects_non_v4_identifiers(field: str) -> None:
    """Requests with non-v4 identifiers are rejected.

    Args:
        field: Identifier field to replace with an invalid value.
    """
    payload = request().to_dict()
    payload[field] = "11111111-1111-3111-8111-111111111111"

    with pytest.raises(ProtocolDecodeError, match="UUIDv4"):
        PlanRequestV1.from_dict(payload)


def test_request_rejects_non_utc_timestamp() -> None:
    """Requests with non-UTC timestamps are rejected."""
    payload = request().to_dict()
    payload["createdAt"] = "2026-08-26T14:22:03.123+01:00"

    with pytest.raises(ProtocolDecodeError, match="RFC 3339 UTC"):
        PlanRequestV1.from_dict(payload)


def test_request_rejects_timestamp_with_space_separator() -> None:
    """Requests reject timestamps with a space instead of uppercase T."""
    payload = request().to_dict()
    payload["createdAt"] = "2026-08-26 14:22:03.123Z"

    with pytest.raises(ProtocolDecodeError, match="RFC 3339 UTC"):
        PlanRequestV1.from_dict(payload)


def test_request_rejects_timestamp_without_seconds() -> None:
    """Requests reject timestamps that omit seconds precision."""
    payload = request().to_dict()
    payload["createdAt"] = "2026-08-26T14:22Z"

    with pytest.raises(ProtocolDecodeError, match="RFC 3339 UTC"):
        PlanRequestV1.from_dict(payload)


def test_request_rejects_unsupported_protocol_version() -> None:
    """Requests for unsupported protocol versions are rejected."""
    payload = request().to_dict()
    payload["protocolVersion"] = "2"

    with pytest.raises(ProtocolDecodeError, match="unsupported protocol"):
        PlanRequestV1.from_dict(payload)


def test_validated_response_round_trips_typed_action_plan() -> None:
    """A validated response decodes into the immutable typed plan."""
    decoded = decode_json(encode_json(response()), response=True)

    assert isinstance(decoded, ValidatedPlanResponseV1)
    assert decoded == response()
    assert decoded.action_plan.render_pml() == (
        "select copilot_selection, chain A\ncolor red, copilot_selection\n"
    )


def test_validated_response_rejects_unknown_fields() -> None:
    """Validated responses with unknown fields are rejected."""
    payload = response().to_dict()
    payload["unexpected"] = True

    with pytest.raises(ProtocolDecodeError):
        ValidatedPlanResponseV1.from_dict(payload)


def test_validated_response_rejects_malformed_identifier() -> None:
    """Validated responses require UUIDv4 correlation identifiers."""
    payload = response().to_dict()
    payload["requestId"] = "not-a-uuid"

    with pytest.raises(ProtocolDecodeError, match="UUIDv4"):
        ValidatedPlanResponseV1.from_dict(payload)


def test_validated_response_rejects_malformed_timestamp() -> None:
    """Validated responses require RFC 3339 UTC timestamps."""
    payload = response().to_dict()
    payload["validatedAt"] = "yesterday"

    with pytest.raises(ProtocolDecodeError, match="RFC 3339 UTC"):
        ValidatedPlanResponseV1.from_dict(payload)


def test_validated_response_rejects_unsupported_protocol_version() -> None:
    """Validated responses for unsupported protocol versions are rejected."""
    payload = response().to_dict()
    payload["protocolVersion"] = "2"

    with pytest.raises(ProtocolDecodeError, match="unsupported protocol"):
        ValidatedPlanResponseV1.from_dict(payload)


def test_validated_response_rejects_missing_action_plan() -> None:
    """A malformed validated response without its typed plan is rejected."""
    payload = response().to_dict()
    del payload["actionPlan"]

    with pytest.raises(ProtocolDecodeError):
        ValidatedPlanResponseV1.from_dict(payload)


def test_validated_response_rejects_mismatched_snapshot_digests() -> None:
    """A response whose plan and report digests disagree is rejected."""
    payload = response().to_dict()
    payload["validation"] = ValidationReportV1(
        "passed", "sha256:different-digest", True, (), (), 0
    ).to_dict()

    with pytest.raises(ProtocolDecodeError, match="snapshot digests"):
        ValidatedPlanResponseV1.from_dict(payload)


def test_validated_response_accepts_matching_snapshot_digests_from_another_request() -> (
    None
):
    """A differently-keyed response still decodes when its digests agree."""
    fixture = response()
    another_request_response = ValidatedPlanResponseV1(
        request_id=fixture.request_id,
        session_id=fixture.session_id,
        received_at=fixture.received_at,
        validated_at=fixture.validated_at,
        action_plan=fixture.action_plan,
        validation=ValidationReportV1(
            "passed", "sha256:another-request-digest", True, (), (), 0
        ),
        plan_id=fixture.plan_id,
        snapshot_digest="sha256:another-request-digest",
        expires_at=fixture.expires_at,
        model_identity=fixture.model_identity,
        target_object=fixture.target_object,
    )

    decoded = ValidatedPlanResponseV1.from_dict(
        another_request_response.to_dict()
    )

    assert decoded.snapshot_digest == "sha256:another-request-digest"
    assert decoded.validation.snapshot_digest == "sha256:another-request-digest"


def _response_payload_with_command(
    index: int, field: str, value: str
) -> dict[str, object]:
    """Build a full V1 response payload with one command field overridden.

    Args:
        index: Index of the command to modify (0 for select, 1 for color).
        field: Command field name to override.
        value: Replacement value, expected to be outside the fixture.

    Returns:
        A complete V1 response payload dict with the overridden command.
    """
    commands: list[dict[str, object]] = [
        {
            "verb": "select",
            "name": "copilot_selection",
            "expression": "chain A",
        },
        {
            "verb": "color",
            "color": "red",
            "target": {"kind": "name", "value": "copilot_selection"},
        },
    ]
    commands[index] = {**commands[index], field: value}
    return {
        "protocolVersion": "1",
        "requestId": REQUEST_IDS["requestId"],
        "sessionId": REQUEST_IDS["sessionId"],
        "receivedAt": "2026-08-26T14:22:03.124Z",
        "validatedAt": "2026-08-26T14:22:03.220Z",
        "status": "validated",
        "actionPlan": {
            "planId": "33333333-3333-4333-8333-333333333333",
            "planVersion": "1",
            "snapshotDigest": "sha256:example-chain-a-digest",
            "expiresAt": "2026-08-26T14:27:03.220Z",
            "modelIdentity": "test-model@test-checkpoint",
            "targetObject": "one-object-chain-a-v1",
            "commands": commands,
        },
        "validation": {
            "status": "passed",
            "snapshotDigest": "sha256:example-chain-a-digest",
            "applicable": True,
            "warnings": [],
            "selectionCounts": [],
            "repairAttempts": 0,
        },
    }


def wire_plan(payload: dict[str, object]) -> dict[str, object]:
    """Reach the actionPlan object inside a decoded response payload.

    Args:
        payload: A full response payload.

    Returns:
        The payload's actionPlan object, narrowed so its commands list can
        be replaced in place.
    """
    action_plan = payload["actionPlan"]

    assert isinstance(action_plan, dict)
    return action_plan


def test_validated_response_rejects_a_denied_expression_as_decode_error() -> (
    None
):
    """An expression the parser refuses raises ProtocolDecodeError."""
    payload = _response_payload_with_command(0, "expression", "__import__(os)")

    with pytest.raises(ProtocolDecodeError, match="unsupported select"):
        ValidatedPlanResponseV1.from_dict(payload)


def test_validated_response_rejects_a_denied_color_as_decode_error() -> None:
    """A color outside the allowlist raises ProtocolDecodeError."""
    payload = _response_payload_with_command(1, "color", "blurple")

    with pytest.raises(ProtocolDecodeError, match="unsupported color"):
        ValidatedPlanResponseV1.from_dict(payload)


def test_the_wire_cannot_express_a_plan_the_parser_would_refuse() -> None:
    """Expression text on the wire is re-parsed, not trusted.

    This is the property that keeps the protocol from becoming a second way
    to build a typed plan. The expression below is well-formed JSON and the
    right type; it is refused because the parser refuses it.
    """
    payload = _response_payload_with_command(
        0, "expression", "chain A or (chain B and polymer)"
    )

    with pytest.raises(ProtocolDecodeError, match="unsupported select"):
        ValidatedPlanResponseV1.from_dict(payload)


def test_every_verb_round_trips_across_the_wire() -> None:
    """A plan using all five verbs encodes and decodes unchanged."""
    expression = SelectionExpression(
        clauses=(AndClause(factors=(Factor(ChainTerm("A")),)),)
    )
    plan = ActionPlan(
        operations=(
            SelectOperation(
                selection_name="copilot_core", expression=expression
            ),
            ColorOperation(
                color="marine", target=NamedSelection("copilot_core")
            ),
            ShowOperation(representation="cartoon", target=expression),
            HideOperation(
                representation="nb_spheres",
                target=NamedSelection("copilot_core"),
            ),
            OrientOperation(target=expression),
        )
    )
    payload = replace(response(), action_plan=plan).to_dict()

    decoded = ValidatedPlanResponseV1.from_dict(payload)

    assert decoded.action_plan == plan
    assert decoded.action_plan.render_pml() == plan.render_pml()


def test_a_single_command_plan_round_trips_across_the_wire() -> None:
    """The wire no longer requires exactly two commands."""
    plan = ActionPlan(
        operations=(
            OrientOperation(
                target=SelectionExpression(
                    clauses=(AndClause(factors=(Factor(ChainTerm("A")),)),)
                )
            ),
        )
    )
    payload = replace(response(), action_plan=plan).to_dict()

    assert ValidatedPlanResponseV1.from_dict(payload).action_plan == plan


def test_wire_plan_past_the_command_limit_is_rejected() -> None:
    """The wire enforces the same finite command bound as the parser."""
    payload = response().to_dict()
    command = {
        "verb": "orient",
        "target": {"kind": "expression", "value": "chain A"},
    }
    wire_plan(payload)["commands"] = [command] * (MAX_COMMANDS + 1)

    with pytest.raises(ProtocolDecodeError, match="length is outside"):
        ValidatedPlanResponseV1.from_dict(payload)


def test_wire_plan_with_no_commands_is_rejected() -> None:
    """An empty command list is refused rather than decoded as a no-op."""
    payload = response().to_dict()
    wire_plan(payload)["commands"] = []

    with pytest.raises(ProtocolDecodeError, match="length is outside"):
        ValidatedPlanResponseV1.from_dict(payload)


def test_wire_plan_with_an_unknown_verb_is_rejected() -> None:
    """A verb outside the allowlist cannot arrive over the wire either."""
    payload = response().to_dict()
    wire_plan(payload)["commands"] = [
        {"verb": "delete", "target": {"kind": "name", "value": "copilot_a"}}
    ]

    with pytest.raises(ProtocolDecodeError, match="unsupported action plan"):
        ValidatedPlanResponseV1.from_dict(payload)


def test_wire_plan_referencing_an_uncreated_selection_is_rejected() -> None:
    """The plan-shape rule is enforced on decode, not only on parse."""
    payload = response().to_dict()
    wire_plan(payload)["commands"] = [
        {
            "verb": "color",
            "color": "red",
            "target": {"kind": "name", "value": "copilot_missing"},
        }
    ]

    with pytest.raises(ProtocolDecodeError, match="wrong shape"):
        ValidatedPlanResponseV1.from_dict(payload)


@pytest.mark.parametrize(
    "target",
    [
        {"kind": "name", "value": "sele"},
        {"kind": "expression", "value": "chain A; rm -rf /"},
        {"kind": "object", "value": "chain A"},
        {"kind": "name"},
        {"kind": "expression", "value": "chain A", "extra": 1},
    ],
    ids=[
        "unprefixed_name",
        "denied_expression",
        "unknown_kind",
        "missing_value",
        "unknown_field",
    ],
)
def test_malformed_wire_targets_are_rejected(
    target: dict[str, object],
) -> None:
    """A target that is not one of the two tagged forms is refused.

    Args:
        target: The malformed wire target under test.
    """
    payload = response().to_dict()
    wire_plan(payload)["commands"] = [{"verb": "orient", "target": target}]

    with pytest.raises(ProtocolDecodeError):
        ValidatedPlanResponseV1.from_dict(payload)


@pytest.mark.parametrize(
    "command",
    [
        {"verb": "orient"},
        {"verb": "select", "name": "copilot_a"},
        {
            "verb": "show",
            "target": {"kind": "expression", "value": "chain A"},
        },
        {
            "verb": "orient",
            "target": {"kind": "expression", "value": "chain A"},
            "extra": 1,
        },
    ],
    ids=[
        "orient_without_target",
        "select_without_expression",
        "show_without_representation",
        "orient_with_unknown_field",
    ],
)
def test_wire_commands_with_wrong_field_sets_are_rejected(
    command: dict[str, object],
) -> None:
    """Each verb declares an exact field set on the wire.

    Args:
        command: The malformed wire command under test.
    """
    payload = response().to_dict()
    wire_plan(payload)["commands"] = [command]

    with pytest.raises(ProtocolDecodeError):
        ValidatedPlanResponseV1.from_dict(payload)


def test_validation_rejects_unknown_status() -> None:
    """Validation reports accept only the successful passed status."""
    payload = response().validation.to_dict()
    payload["status"] = "unknown"

    with pytest.raises(ProtocolDecodeError, match="status is not passed"):
        ValidationReportV1.from_dict(payload)


def test_failure_response_has_no_partial_action_plan() -> None:
    """A failure response cannot carry a partial action plan."""
    failure = FailedPlanResponseV1(
        request_id=REQUEST_IDS["requestId"],
        session_id=REQUEST_IDS["sessionId"],
        failure=FailureEnvelopeV1("invalid_request", "bad request", False),
    )

    payload = failure.to_dict()
    assert "actionPlan" not in payload
    assert decode_json(encode_json(failure), response=True) == failure


def test_failure_response_rejects_partial_action_plan() -> None:
    """A failed response containing a partial action plan is rejected."""
    failure = FailedPlanResponseV1(
        request_id=REQUEST_IDS["requestId"],
        session_id=REQUEST_IDS["sessionId"],
        failure=FailureEnvelopeV1("invalid_request", "bad request", False),
    )
    payload = failure.to_dict()
    payload["actionPlan"] = response().to_dict()["actionPlan"]

    with pytest.raises(ProtocolDecodeError):
        FailedPlanResponseV1.from_dict(payload)


@pytest.mark.parametrize(
    "command",
    [
        {
            "verb": "select",
            "name": "copilot_a",
            "expression": "chain A",
            "onSuccess": "delete all",
        },
        {
            "verb": "color",
            "color": "red",
            "target": {"kind": "expression", "value": "chain A"},
            "onSuccess": "delete all",
        },
        {
            "verb": "show",
            "representation": "cartoon",
            "target": {"kind": "expression", "value": "chain A"},
            "onSuccess": "delete all",
        },
        {
            "verb": "hide",
            "representation": "cartoon",
            "target": {"kind": "expression", "value": "chain A"},
            "onSuccess": "delete all",
        },
    ],
    ids=["select", "color", "show", "hide"],
)
def test_a_smuggled_extra_field_is_rejected_for_every_verb(
    command: dict[str, object],
) -> None:
    """Each verb declares an exact field set, so nothing rides along.

    Every command here is otherwise valid; only the extra field makes it
    invalid. A subset check rather than an exact one would let the field
    through unnoticed.

    Args:
        command: An otherwise valid command carrying one extra field.
    """
    payload = response().to_dict()
    wire_plan(payload)["commands"] = [command]

    with pytest.raises(ProtocolDecodeError):
        ValidatedPlanResponseV1.from_dict(payload)


def test_an_unsupported_plan_version_is_rejected() -> None:
    """actionPlan.planVersion is checked, not only the envelope version."""
    payload = response().to_dict()
    wire_plan(payload)["planVersion"] = "9"

    with pytest.raises(ProtocolDecodeError, match="unsupported plan version"):
        ValidatedPlanResponseV1.from_dict(payload)


@pytest.mark.parametrize(
    "verb",
    [[], {}, ["select"]],
    ids=["list", "dict", "list_containing_a_verb"],
)
def test_an_unhashable_wire_verb_is_a_decode_error_not_a_crash(
    verb: object,
) -> None:
    """A non-string verb must not escape as TypeError.

    `verb in {"show", "hide"}` raises TypeError for an unhashable JSON
    value, and the client transport catches only ProtocolDecodeError, so it
    would surface as an unhandled crash rather than a bounded failure.

    Args:
        verb: The unhashable value sent as a command verb.
    """
    payload = response().to_dict()
    wire_plan(payload)["commands"] = [{"verb": verb}]

    with pytest.raises(ProtocolDecodeError):
        ValidatedPlanResponseV1.from_dict(payload)


@pytest.mark.parametrize(
    "raw",
    [
        "[" * 12000 + "]" * 12000,
        '{"protocolVersion":' + "9" * 5000 + "}",
    ],
    ids=["deeply_nested_arrays", "integer_past_the_digit_limit"],
)
def test_hostile_json_is_a_decode_error_not_a_crash(raw: str) -> None:
    """json.loads raises more than JSONDecodeError on hostile input.

    Deep nesting raises RecursionError and an over-long integer literal
    raises a plain ValueError. Both fit well inside the transport's payload
    bound, and the loopback server catches only ProtocolDecodeError -- so
    unhandled, they drop the connection with no response at all.

    Args:
        raw: The hostile JSON text.
    """
    with pytest.raises(ProtocolDecodeError):
        decode_json(raw, response=True)


# --- executor wire types (docs/master_plan.md item 4) ---------------------


def five_verb_plan() -> ActionPlan:
    """Build a plan exercising all five allowlisted verbs.

    Returns:
        select, color, show, hide, orient, in that order.
    """
    expression = SelectionExpression(
        clauses=(AndClause(factors=(Factor(ChainTerm("A")),)),)
    )
    return ActionPlan(
        operations=(
            SelectOperation(
                selection_name="copilot_selection", expression=expression
            ),
            ColorOperation(
                color="red", target=NamedSelection("copilot_selection")
            ),
            ShowOperation(
                representation="spheres",
                target=NamedSelection("copilot_selection"),
            ),
            HideOperation(
                representation="sticks",
                target=NamedSelection("copilot_selection"),
            ),
            OrientOperation(target=NamedSelection("copilot_selection")),
        )
    )


def test_encode_plan_decode_plan_round_trips_every_verb() -> None:
    """encode_plan/decode_plan round-trip a plan covering every verb."""
    plan = five_verb_plan()
    envelope = {
        "planId": REQUEST_IDS["requestId"],
        "planVersion": PROTOCOL_VERSION,
        "snapshotDigest": "sha256:example-digest",
        "commands": encode_plan(plan),
    }

    assert decode_plan(envelope) == plan


def sample_execution_report() -> ExecutionReportV1:
    """Build a fully populated, successful execution report fixture.

    Returns:
        An accepted execution report exercising every field.
    """
    return ExecutionReportV1(
        executor_version=1,
        status="ok",
        reason="ok",
        input_digest="sha256:example-digest",
        resulting_fingerprint="sha256:" + "1" * 64,
        selection_counts=(SelectionCountV1("copilot_selection", 4),),
        command_outcomes=(
            CommandOutcomeV1(0, "select", "ok", None),
            CommandOutcomeV1(1, "color", "ok", None),
        ),
        elapsed_seconds=0.125,
        warnings=("a bounded diagnostic",),
    )


def test_execution_report_round_trips() -> None:
    """A fully populated execution report survives to_dict/from_dict."""
    report = sample_execution_report()

    assert ExecutionReportV1.from_dict(report.to_dict()) == report


@pytest.mark.parametrize(
    "status,reason",
    [
        ("rejected", "oversized_input"),
        ("rejected", "malformed_input"),
        ("rejected", "unsupported_schema_version"),
        ("rejected", "policy_denied"),
        ("failed", "spawn_or_load_failure"),
        ("failed", "timeout"),
        ("failed", "child_crash"),
        ("failed", "command_failure"),
        ("failed", "fidelity_mismatch"),
    ],
)
def test_execution_report_round_trips_every_fail_closed_reason(
    status: str, reason: str
) -> None:
    """Unlike ValidationReportV1, this report can represent any failure.

    Args:
        status: The report status under test.
        reason: The report reason under test.
    """
    report = ExecutionReportV1(
        executor_version=1,
        status=status,
        reason=reason,
        input_digest=None,
        resulting_fingerprint=None,
        selection_counts=(),
        command_outcomes=(),
        elapsed_seconds=0.01,
        warnings=(),
    )

    assert ExecutionReportV1.from_dict(report.to_dict()) == report


def test_execution_report_rejects_unknown_fields() -> None:
    """Execution reports with unknown fields are rejected."""
    payload = sample_execution_report().to_dict()
    payload["unexpected"] = True

    with pytest.raises(ProtocolDecodeError):
        ExecutionReportV1.from_dict(payload)


def test_execution_report_rejects_a_missing_field() -> None:
    """Execution reports missing a required field are rejected."""
    payload = sample_execution_report().to_dict()
    del payload["resultingFingerprint"]

    with pytest.raises(ProtocolDecodeError):
        ExecutionReportV1.from_dict(payload)


def test_command_outcome_round_trips_including_none_error() -> None:
    """A successful command outcome's error field round-trips as None."""
    outcome = CommandOutcomeV1(0, "orient", "ok", None)

    assert CommandOutcomeV1.from_dict(outcome.to_dict()) == outcome
    assert outcome.error_envelope is None


def sample_execution_error() -> ExecutionErrorV1:
    """Build a fully populated error envelope.

    Returns:
        An accepted envelope exercising every field.
    """
    return ExecutionErrorV1(
        envelope_version=ERROR_ENVELOPE_VERSION,
        command_index=1,
        verb="color",
        category=CATEGORY_UNKNOWN,
        message="a bounded diagnostic",
    )


def test_execution_error_round_trips() -> None:
    """A fully populated error envelope survives to_dict/decode."""
    envelope = sample_execution_error()

    assert decode_execution_error(envelope.to_dict()) == envelope


def test_execution_error_rejects_unknown_fields() -> None:
    """An error envelope carrying an unknown field is rejected."""
    payload = sample_execution_error().to_dict()
    payload["unexpected"] = True

    with pytest.raises(ProtocolDecodeError):
        decode_execution_error(payload)


def test_execution_error_rejects_a_missing_field() -> None:
    """An error envelope missing a required field is rejected."""
    payload = sample_execution_error().to_dict()
    del payload["message"]

    with pytest.raises(ProtocolDecodeError):
        decode_execution_error(payload)


def test_execution_error_rejects_a_value_its_own_constructor_refuses() -> None:
    """A field violating ExecutionErrorV1's own invariants is rejected.

    `decode_execution_error` re-raises `ExecutionErrorV1.__post_init__`'s
    `ValueError` as a `ProtocolDecodeError`, so a value that is
    structurally a valid envelope but semantically wrong -- a verb outside
    the command allowlist, here -- fails the same way every other decoder
    in this module does.
    """
    payload = sample_execution_error().to_dict()
    payload["verb"] = "fetch"

    with pytest.raises(ProtocolDecodeError):
        decode_execution_error(payload)


def test_command_outcome_round_trips_with_an_error_envelope() -> None:
    """A failed command outcome's envelope round-trips with it."""
    outcome = CommandOutcomeV1(
        1, "color", "error", "a bounded diagnostic", sample_execution_error()
    )

    assert CommandOutcomeV1.from_dict(outcome.to_dict()) == outcome
    assert (
        outcome.to_dict()["errorEnvelope"] == sample_execution_error().to_dict()
    )


def test_command_outcome_rejects_a_missing_error_envelope_field() -> None:
    """A command outcome missing errorEnvelope entirely is rejected.

    The field is optional in value (it may be null) but not optional in
    presence -- `_strict_object` requires an exact field set, matching
    every other wire type in this module.
    """
    payload = CommandOutcomeV1(0, "orient", "ok", None).to_dict()
    del payload["errorEnvelope"]

    with pytest.raises(ProtocolDecodeError):
        CommandOutcomeV1.from_dict(payload)


def test_selection_count_round_trips_a_zero_count() -> None:
    """A selection matching zero atoms round-trips, not an error."""
    count = SelectionCountV1("copilot_empty", 0)

    assert SelectionCountV1.from_dict(count.to_dict()) == count


@pytest.mark.parametrize(
    ("status", "mismatch_count", "mismatches"),
    [
        (FIDELITY_EXACT, 0, ()),
        (FIDELITY_NOT_EXACT, 2, ("state0.atom0.q expected=1.0 actual=0.5",)),
        (FIDELITY_UNAVAILABLE, 0, ()),
    ],
)
def test_fidelity_outcome_round_trips_every_status(
    status: str, mismatch_count: int, mismatches: tuple[str, ...]
) -> None:
    """Each of the three fidelity statuses round-trips through JSON.

    Args:
        status: The fidelity status under test.
        mismatch_count: The declared mismatch count.
        mismatches: The carried mismatch strings.
    """
    outcome = FidelityOutcomeV1(
        status=status,
        reason=REASON_OK,
        mismatch_count=mismatch_count,
        mismatches=mismatches,
    )

    assert FidelityOutcomeV1.from_dict(outcome.to_dict()) == outcome


def test_fidelity_outcome_rejects_an_unrecognized_status() -> None:
    """A fidelity status outside the three recognized values is rejected."""
    payload = FidelityOutcomeV1(FIDELITY_EXACT, REASON_OK, 0, ()).to_dict()
    payload["status"] = "somewhat_exact"

    with pytest.raises(ProtocolDecodeError, match="recognized value"):
        FidelityOutcomeV1.from_dict(payload)


def test_fidelity_outcome_rejects_exact_status_carrying_a_mismatch() -> None:
    """An exact status may never carry a nonzero mismatch count."""
    payload = FidelityOutcomeV1(FIDELITY_EXACT, REASON_OK, 0, ()).to_dict()
    payload["mismatchCount"] = 1

    with pytest.raises(ProtocolDecodeError, match="exact"):
        FidelityOutcomeV1.from_dict(payload)


def test_fidelity_outcome_rejects_more_mismatches_than_the_declared_count() -> (
    None
):
    """A carried mismatch list may never outnumber its own declared count."""
    payload = FidelityOutcomeV1(
        FIDELITY_NOT_EXACT, "child_crash", 1, ("one mismatch",)
    ).to_dict()
    payload["mismatchCount"] = 0

    with pytest.raises(ProtocolDecodeError, match="mismatchCount"):
        FidelityOutcomeV1.from_dict(payload)


def test_fidelity_outcome_rejects_more_than_the_maximum_mismatches() -> None:
    """A mismatch list longer than MAX_FIDELITY_MISMATCHES is rejected."""
    payload = FidelityOutcomeV1(
        FIDELITY_NOT_EXACT,
        "child_crash",
        MAX_FIDELITY_MISMATCHES + 1,
        tuple(f"mismatch {i}" for i in range(MAX_FIDELITY_MISMATCHES + 1)),
    ).to_dict()

    with pytest.raises(ProtocolDecodeError, match="exceeds the V1 limit"):
        FidelityOutcomeV1.from_dict(payload)


def test_fidelity_outcome_rejects_unknown_fields() -> None:
    """Fidelity outcomes with unknown fields are rejected."""
    payload = FidelityOutcomeV1(FIDELITY_EXACT, REASON_OK, 0, ()).to_dict()
    payload["unexpected"] = True

    with pytest.raises(ProtocolDecodeError):
        FidelityOutcomeV1.from_dict(payload)


def test_structure_snapshot_round_trips_its_computed_identity() -> None:
    """A real computed snapshot identity round-trips through JSON."""
    snapshot = StructureSnapshotV1(
        schema_version="1",
        digest="sha256:a-real-computed-digest",
        object_name="fx",
        atom_count=13,
        state_count=2,
    )

    assert StructureSnapshotV1.from_dict(snapshot.to_dict()) == snapshot


def test_validation_report_round_trips_applicable_both_ways() -> None:
    """`applicable` round-trips true and false independently of status."""
    applicable_report = ValidationReportV1(
        "passed", "sha256:digest", True, (), (), 0
    )
    non_applicable_report = ValidationReportV1(
        "passed", "sha256:digest", False, (), (), 0
    )

    assert (
        ValidationReportV1.from_dict(applicable_report.to_dict())
        == applicable_report
    )
    assert (
        ValidationReportV1.from_dict(non_applicable_report.to_dict())
        == non_applicable_report
    )


def test_validation_report_rejects_a_non_boolean_applicable() -> None:
    """A non-boolean applicable value is rejected, not coerced."""
    payload = ValidationReportV1(
        "passed", "sha256:digest", True, (), (), 0
    ).to_dict()
    payload["applicable"] = "true"

    with pytest.raises(ProtocolDecodeError, match="applicable"):
        ValidationReportV1.from_dict(payload)


def test_request_with_a_full_mismatch_list_stays_well_under_the_transport_cap() -> (
    None
):
    """A ten-mismatch fidelity outcome leaves the 64 KiB request cap intact.

    Mirrors pmc_client.transport.MAX_MESSAGE_BYTES without importing
    pmc_client from a pmc_core-only contract test: this is evidence about
    the protocol's own encoded size, not about the transport itself.
    """
    max_message_bytes = 64 * 1024
    full_request = replace(
        request(),
        fidelity=FidelityOutcomeV1(
            status=FIDELITY_NOT_EXACT,
            reason="child_crash",
            mismatch_count=MAX_FIDELITY_MISMATCHES,
            mismatches=tuple(
                "x" * MAX_FIDELITY_MISMATCH_BYTES
                for _ in range(MAX_FIDELITY_MISMATCHES)
            ),
        ),
    )

    encoded = encode_json(full_request).encode("utf-8")

    assert len(encoded) < max_message_bytes


def test_reject_request_fixture_round_trips_as_strict_json() -> None:
    """The accepted reject request survives JSON encoding and decoding."""
    encoded = json.dumps(reject_request().to_dict())
    assert decode_reject_request_json(encoded) == reject_request()


def test_reject_request_rejects_unknown_fields() -> None:
    """Reject requests with unknown fields are rejected."""
    payload = reject_request().to_dict()
    payload["unexpected"] = True

    with pytest.raises(ProtocolDecodeError):
        RejectRequestV1.from_dict(payload)


@pytest.mark.parametrize("field", ["requestId", "sessionId", "planId"])
def test_reject_request_rejects_non_v4_identifiers(field: str) -> None:
    """Reject requests with non-v4 identifiers are rejected.

    Args:
        field: Identifier field to replace with an invalid value.
    """
    payload = reject_request().to_dict()
    payload[field] = "11111111-1111-3111-8111-111111111111"

    with pytest.raises(ProtocolDecodeError, match="UUIDv4"):
        RejectRequestV1.from_dict(payload)


def test_reject_request_json_rejects_invalid_json() -> None:
    """Hostile, non-JSON reject request bodies fail closed."""
    with pytest.raises(ProtocolDecodeError):
        decode_reject_request_json("{not valid json")


def test_cancel_request_fixture_round_trips_as_strict_json() -> None:
    """The accepted cancel request survives JSON encoding and decoding."""
    encoded = json.dumps(cancel_request().to_dict())
    assert decode_cancel_request_json(encoded) == cancel_request()


def test_cancel_request_rejects_unknown_fields() -> None:
    """Cancel requests with unknown fields are rejected."""
    payload = cancel_request().to_dict()
    payload["unexpected"] = True

    with pytest.raises(ProtocolDecodeError):
        CancelRequestV1.from_dict(payload)


@pytest.mark.parametrize("field", ["requestId", "sessionId"])
def test_cancel_request_rejects_non_v4_identifiers(field: str) -> None:
    """Cancel requests with non-v4 identifiers are rejected.

    Args:
        field: Identifier field to replace with an invalid value.
    """
    payload = cancel_request().to_dict()
    payload[field] = "11111111-1111-3111-8111-111111111111"

    with pytest.raises(ProtocolDecodeError, match="UUIDv4"):
        CancelRequestV1.from_dict(payload)


def test_cancel_request_json_rejects_invalid_json() -> None:
    """Hostile, non-JSON cancel request bodies fail closed."""
    with pytest.raises(ProtocolDecodeError):
        decode_cancel_request_json("{not valid json")


def test_apply_request_round_trips_and_requires_v4_identifiers() -> None:
    """Approval requests use the same strict correlation boundary as reject."""
    assert (
        decode_apply_request_json(encode_json(apply_request()))
        == apply_request()
    )
    payload = apply_request().to_dict()
    payload["planId"] = "11111111-1111-3111-8111-111111111111"
    with pytest.raises(ProtocolDecodeError, match="UUIDv4"):
        ApplyRequestV1.from_dict(payload)


@pytest.mark.parametrize(
    "outcome",
    [
        APPLY_OUTCOME_APPLIED,
        APPLY_OUTCOME_RESTORED,
        APPLY_OUTCOME_ROLLED_BACK,
    ],
)
def test_apply_outcome_request_round_trips(outcome: str) -> None:
    """Each allowed terminal apply outcome has one strict wire form."""
    request = apply_outcome_request(outcome)
    assert decode_apply_outcome_request_json(encode_json(request)) == request


def test_apply_outcome_request_rejects_unknown_outcome() -> None:
    """An apply outcome cannot create a new graph terminal by spelling."""
    payload = apply_outcome_request().to_dict()
    payload["outcome"] = "unexpected"
    with pytest.raises(ProtocolDecodeError, match="unsupported apply outcome"):
        ApplyOutcomeRequestV1.from_dict(payload)


@pytest.mark.parametrize("field", ["expiresAt", "modelIdentity"])
def test_validated_response_requires_approval_reverification_fields(
    field: str,
) -> None:
    """Older peers missing approval-critical values fail closed."""
    payload = response().to_dict()
    action_plan = wire_plan(payload)
    del action_plan[field]
    with pytest.raises(ProtocolDecodeError):
        ValidatedPlanResponseV1.from_dict(payload)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
