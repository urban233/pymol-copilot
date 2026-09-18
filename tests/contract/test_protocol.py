# Copyright 2026 PyMOL Copilot contributors.
"""Contract tests for strict V1 client-server protocol codecs."""

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
from pmc_core.protocol import ContractManifestV1
from pmc_core.protocol import FailedPlanResponseV1
from pmc_core.protocol import FailureEnvelopeV1
from pmc_core.protocol import PlanRequestV1
from pmc_core.protocol import ProtocolDecodeError
from pmc_core.protocol import StructureSnapshotV1
from pmc_core.protocol import ValidatedPlanResponseV1
from pmc_core.protocol import ValidationReportV1
from pmc_core.protocol import decode_json
from pmc_core.protocol import encode_json

REQUEST_IDS = {
    "requestId": "11111111-1111-4111-8111-111111111111",
    "sessionId": "22222222-2222-4222-8222-222222222222",
}


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
            "1", "sha256:example-chain-a-digest", "one-object-chain-a-v1"
        ),
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
            "passed", "sha256:example-chain-a-digest", ()
        ),
        plan_id="33333333-3333-4333-8333-333333333333",
        snapshot_digest="sha256:example-chain-a-digest",
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
        "passed", "sha256:different-digest", ()
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
            "passed", "sha256:another-request-digest", ()
        ),
        plan_id=fixture.plan_id,
        snapshot_digest="sha256:another-request-digest",
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
            "commands": commands,
        },
        "validation": {
            "status": "passed",
            "snapshotDigest": "sha256:example-chain-a-digest",
            "warnings": [],
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


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
