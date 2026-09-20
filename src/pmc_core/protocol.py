# Copyright 2026 PyMOL Copilot contributors.
"""Strict codecs for the client-server protocol.

A plan crosses the wire as one object per command, carrying the same five
verbs the command allowlist names. A command's target crosses as a tagged
value: either the name of a selection an earlier command created, or the
canonical text of a selection expression.

That expression text is decoded by handing it back to pmc_core.parser rather
than by rebuilding the term tree from JSON. Rebuilding it here would be a
second, unaudited way to construct a typed plan, and the wire is the one
place untrusted bytes arrive already shaped like a plan. Routing it through
the same total parser means the wire cannot express an operation the parser
would have refused.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime

from pmc_core.parser import ParseRejection
from pmc_core.parser import parse_selection_expression
from pmc_core.plan import MAX_COMMANDS
from pmc_core.plan import OPERATION
from pmc_core.plan import ActionPlan
from pmc_core.plan import ColorOperation
from pmc_core.plan import HideOperation
from pmc_core.plan import NamedSelection
from pmc_core.plan import OrientOperation
from pmc_core.plan import SelectOperation
from pmc_core.plan import SelectionExpression
from pmc_core.plan import ShowOperation

PROTOCOL_VERSION = "1"


class ProtocolDecodeError(ValueError):
    """Raised when a protocol value does not match its V1 schema."""


def _object(value: object, *, name: str) -> dict[str, object]:
    """Require a protocol value to be a JSON object.

    Args:
        value: Value to validate.
        name: Field name used in the error message.

    Returns:
        The value narrowed to a JSON object.

    Raises:
        ProtocolDecodeError: If value is not a JSON object.
    """
    match value:
        case dict() as result:
            return result
        case _:
            raise ProtocolDecodeError(f"{name} must be an object")


def _strict_object(
    value: object, *, name: str, required: set[str]
) -> dict[str, object]:
    """Require a JSON object to contain exactly the required fields.

    Args:
        value: Value to validate.
        name: Object name used in the error message.
        required: Exact set of accepted field names.

    Returns:
        The validated JSON object.

    Raises:
        ProtocolDecodeError: If the value or its fields are invalid.
    """
    result = _object(value, name=name)
    if set(result) != required:
        raise ProtocolDecodeError(f"{name} fields do not match V1 schema")
    return result


def _string(value: object, *, name: str) -> str:
    """Require a protocol value to be a string.

    Args:
        value: Value to validate.
        name: Field name used in the error message.

    Returns:
        The value narrowed to a string.

    Raises:
        ProtocolDecodeError: If value is not a string.
    """
    match value:
        case str() as result:
            return result
        case _:
            raise ProtocolDecodeError(f"{name} must be a string")


def _uuid4(value: object, *, name: str) -> str:
    """Require a protocol value to be a canonical UUIDv4 string.

    Args:
        value: Value to validate.
        name: Field name used in the error message.

    Returns:
        The validated UUIDv4 string.

    Raises:
        ProtocolDecodeError: If value is not a canonical UUIDv4 string.
    """
    text = _string(value, name=name)
    try:
        parsed = uuid.UUID(text)
    except ValueError as error:
        raise ProtocolDecodeError(f"{name} must be a UUIDv4") from error
    if str(parsed) != text or parsed.version != 4:
        raise ProtocolDecodeError(f"{name} must be a UUIDv4")
    return text


def _timestamp(value: object, *, name: str) -> str:
    """Require a protocol value to be an RFC3339 UTC timestamp.

    Args:
        value: Value to validate.
        name: Field name used in the error message.

    Returns:
        The validated timestamp string.

    Raises:
        ProtocolDecodeError: If value is not a valid UTC timestamp.
    """
    text = _string(value, name=name)
    # fromisoformat() accepts variants such as a space separator or omitted.
    # seconds, so enforce the V1 wire shape before checking calendar validity.
    if (
        re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z", text)
        is None
    ):
        raise ProtocolDecodeError(f"{name} must be an RFC 3339 UTC timestamp")
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as error:
        raise ProtocolDecodeError(
            f"{name} must be an RFC 3339 UTC timestamp"
        ) from error
    if parsed.tzinfo is None:
        raise ProtocolDecodeError(f"{name} must be an RFC 3339 UTC timestamp")
    return text


def _int(value: object, *, name: str) -> int:
    """Require a protocol value to be an integer, not a bool.

    Args:
        value: Value to validate.
        name: Field name used in the error message.

    Returns:
        The value narrowed to an int.

    Raises:
        ProtocolDecodeError: If value is not an int, or is a bool (JSON's
            true/false decode to Python's bool, itself an int subclass).
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise ProtocolDecodeError(f"{name} must be an integer")
    return value


def _float(value: object, *, name: str) -> float:
    """Require a protocol value to be a real number.

    Args:
        value: Value to validate.
        name: Field name used in the error message.

    Returns:
        The value narrowed to a float. An int value is accepted and
        widened, since JSON has no separate integer/float wire types.

    Raises:
        ProtocolDecodeError: If value is not a real number, or is a bool.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProtocolDecodeError(f"{name} must be a number")
    return float(value)


def _optional_string(value: object, *, name: str) -> str | None:
    """Require a protocol value to be a string or JSON null.

    Args:
        value: Value to validate.
        name: Field name used in the error message.

    Returns:
        The value narrowed to a string, or None for JSON null.

    Raises:
        ProtocolDecodeError: If value is neither a string nor None.
    """
    if value is None:
        return None
    return _string(value, name=name)


@dataclass(frozen=True)
class ContractManifestV1:
    """Versions of the shared contracts used by a request."""

    plan_version: str
    policy_version: str
    snapshot_version: str

    def to_dict(self) -> dict[str, str]:
        """Encode the manifest using its V1 wire-field names.

        Returns:
            The manifest represented with wire-field names.
        """
        return {
            "planVersion": self.plan_version,
            "policyVersion": self.policy_version,
            "snapshotVersion": self.snapshot_version,
        }

    @classmethod
    def from_dict(cls, value: object) -> ContractManifestV1:
        """Decode and validate a V1 contract manifest.

        Args:
            value: JSON-like value containing a contract manifest.

        Returns:
            The validated contract manifest.

        Raises:
            ProtocolDecodeError: If value does not match the manifest schema.
        """
        data = _strict_object(
            value,
            name="contractManifest",
            required={"planVersion", "policyVersion", "snapshotVersion"},
        )
        return cls(
            plan_version=_string(data["planVersion"], name="planVersion"),
            policy_version=_string(data["policyVersion"], name="policyVersion"),
            snapshot_version=_string(
                data["snapshotVersion"], name="snapshotVersion"
            ),
        )


@dataclass(frozen=True)
class StructureSnapshotV1:
    """The canonical snapshot identity used by the initial fixture."""

    schema_version: str
    digest: str
    fixture_id: str

    def to_dict(self) -> dict[str, str]:
        """Encode the snapshot identity using its V1 wire-field names.

        Returns:
            The snapshot represented with wire-field names.
        """
        return {
            "schemaVersion": self.schema_version,
            "digest": self.digest,
            "fixtureId": self.fixture_id,
        }

    @classmethod
    def from_dict(cls, value: object) -> StructureSnapshotV1:
        """Decode and validate a V1 structure snapshot identity.

        Args:
            value: JSON-like value containing a structure snapshot.

        Returns:
            The validated structure snapshot.

        Raises:
            ProtocolDecodeError: If value does not match the snapshot schema.
        """
        data = _strict_object(
            value,
            name="snapshot",
            required={"schemaVersion", "digest", "fixtureId"},
        )
        return cls(
            schema_version=_string(data["schemaVersion"], name="schemaVersion"),
            digest=_string(data["digest"], name="digest"),
            fixture_id=_string(data["fixtureId"], name="fixtureId"),
        )


@dataclass(frozen=True)
class PlanRequestV1:
    """A strictly decoded request sent from client to server."""

    request_id: str
    session_id: str
    created_at: str
    contract_manifest: ContractManifestV1
    intent: str
    snapshot: StructureSnapshotV1
    protocol_version: str = PROTOCOL_VERSION

    def to_dict(self) -> dict[str, object]:
        """Encode the request using its V1 wire-field names.

        Returns:
            The request represented with wire-field names.
        """
        return {
            "protocolVersion": self.protocol_version,
            "requestId": self.request_id,
            "sessionId": self.session_id,
            "createdAt": self.created_at,
            "contractManifest": self.contract_manifest.to_dict(),
            "intent": self.intent,
            "snapshot": self.snapshot.to_dict(),
        }

    @classmethod
    def from_dict(cls, value: object) -> PlanRequestV1:
        """Decode and validate a V1 plan request.

        Args:
            value: JSON-like value containing a plan request.

        Returns:
            The validated plan request.

        Raises:
            ProtocolDecodeError: If value does not match the request schema.
        """
        data = _strict_object(
            value,
            name="PlanRequestV1",
            required={
                "protocolVersion",
                "requestId",
                "sessionId",
                "createdAt",
                "contractManifest",
                "intent",
                "snapshot",
            },
        )
        if data["protocolVersion"] != PROTOCOL_VERSION:
            raise ProtocolDecodeError("unsupported protocol version")
        intent = _string(data["intent"], name="intent")
        if not 1 <= len(intent) <= 4096:
            raise ProtocolDecodeError("intent length is outside the V1 limit")
        return cls(
            request_id=_uuid4(data["requestId"], name="requestId"),
            session_id=_uuid4(data["sessionId"], name="sessionId"),
            created_at=_timestamp(data["createdAt"], name="createdAt"),
            contract_manifest=ContractManifestV1.from_dict(
                data["contractManifest"]
            ),
            intent=intent,
            snapshot=StructureSnapshotV1.from_dict(data["snapshot"]),
        )


def _encode_target(target: object) -> dict[str, str]:
    """Convert a command target to its tagged wire value.

    Args:
        target: The typed target to encode.

    Returns:
        The wire object for the target.

    Raises:
        ProtocolDecodeError: If target is not an accepted target value.
    """
    match target:
        case NamedSelection():
            return {"kind": "name", "value": target.name}
        case SelectionExpression():
            return {"kind": "expression", "value": target.render()}
        case _:
            raise ProtocolDecodeError("unsupported action plan target")


def encode_plan(plan: ActionPlan) -> list[dict[str, object]]:
    """Convert a typed action plan to its wire command objects.

    Promoted from the module-private `_plan_commands` (docs/master_plan.md
    item 4, the sidecar executor) so `src/pmc_sidecar/child.py` can reuse
    this exact encoding to cross its own parent-child process boundary,
    rather than inventing a second plan wire format.

    Args:
        plan: Action plan to encode.

    Returns:
        The command objects for the plan.

    Raises:
        ProtocolDecodeError: If the plan contains an unsupported operation.
    """
    commands: list[dict[str, object]] = []
    for operation in plan.operations:
        match operation:
            case SelectOperation():
                commands.append(
                    {
                        "verb": "select",
                        "name": operation.selection_name,
                        "expression": operation.expression.render(),
                    }
                )
            case ColorOperation():
                commands.append(
                    {
                        "verb": "color",
                        "color": operation.color,
                        "target": _encode_target(operation.target),
                    }
                )
            case ShowOperation():
                commands.append(
                    {
                        "verb": "show",
                        "representation": operation.representation,
                        "target": _encode_target(operation.target),
                    }
                )
            case HideOperation():
                commands.append(
                    {
                        "verb": "hide",
                        "representation": operation.representation,
                        "target": _encode_target(operation.target),
                    }
                )
            case OrientOperation():
                commands.append(
                    {
                        "verb": "orient",
                        "target": _encode_target(operation.target),
                    }
                )
            case _:
                raise ProtocolDecodeError("unsupported action plan operation")
    return commands


def decode_plan(value: object) -> ActionPlan:
    """Decode a strictly shaped action plan.

    Promoted from the module-private `_decode_plan` (docs/master_plan.md
    item 4, the sidecar executor) so `src/pmc_sidecar/child.py` can reuse
    this exact decoding to cross its own parent-child process boundary,
    rather than inventing a second plan wire format.

    Args:
        value: JSON-like value containing an action plan.

    Returns:
        The decoded action plan.

    Raises:
        ProtocolDecodeError: If value does not match the action-plan schema.
    """
    data = _strict_object(
        value,
        name="actionPlan",
        required={"planId", "planVersion", "snapshotDigest", "commands"},
    )
    _uuid4(data["planId"], name="planId")
    if data["planVersion"] != PROTOCOL_VERSION:
        raise ProtocolDecodeError("unsupported plan version")
    _string(data["snapshotDigest"], name="snapshotDigest")
    commands = data["commands"]
    match commands:
        case list() as command_list if 1 <= len(command_list) <= MAX_COMMANDS:
            pass
        case _:
            raise ProtocolDecodeError(
                "actionPlan.commands length is outside the V1 limit"
            )
    decoded = tuple(_decode_command(command) for command in command_list)
    try:
        return ActionPlan(operations=decoded)
    except ValueError as error:
        raise ProtocolDecodeError(
            "action plan commands have wrong shape"
        ) from error


def _decode_target(value: object) -> NamedSelection | SelectionExpression:
    """Decode a strictly shaped command target.

    Args:
        value: JSON-like value containing a tagged target.

    Returns:
        The decoded named selection or selection expression.

    Raises:
        ProtocolDecodeError: If value is not an accepted target.
    """
    item = _strict_object(
        value, name="command target", required={"kind", "value"}
    )
    text = _string(item["value"], name="target value")
    if item["kind"] == "name":
        try:
            return NamedSelection(text)
        except ValueError as error:
            raise ProtocolDecodeError(
                "unsupported target selection name"
            ) from error
    if item["kind"] == "expression":
        expression = parse_selection_expression(text)
        if isinstance(expression, ParseRejection):
            raise ProtocolDecodeError("unsupported target selection expression")
        return expression
    raise ProtocolDecodeError("unsupported action plan target")


def _decode_command(value: object) -> OPERATION:
    """Decode one strictly shaped action-plan command.

    Args:
        value: JSON-like value containing an action-plan command.

    Returns:
        The decoded operation.

    Raises:
        ProtocolDecodeError: If value does not match a supported command
            shape, or carries a value the typed contract refuses.
    """
    item = _object(value, name="actionPlan command")
    verb = item.get("verb")
    # Checked before any comparison: `verb in {"show", "hide"}` raises
    # TypeError for an unhashable JSON value such as a list or object, and
    # that would escape this function rather than becoming a decode error.
    if not isinstance(verb, str):
        raise ProtocolDecodeError("action plan command verb must be a string")
    try:
        if verb == "select":
            if set(item) != {"verb", "name", "expression"}:
                raise ProtocolDecodeError("invalid select command fields")
            expression = parse_selection_expression(
                _string(item["expression"], name="expression")
            )
            if isinstance(expression, ParseRejection):
                raise ProtocolDecodeError("unsupported select command values")
            return SelectOperation(
                selection_name=_string(item["name"], name="name"),
                expression=expression,
            )
        if verb == "color":
            if set(item) != {"verb", "color", "target"}:
                raise ProtocolDecodeError("invalid color command fields")
            return ColorOperation(
                color=_string(item["color"], name="color"),
                target=_decode_target(item["target"]),
            )
        if verb in {"show", "hide"}:
            if set(item) != {"verb", "representation", "target"}:
                raise ProtocolDecodeError(f"invalid {verb} command fields")
            operation_type = ShowOperation if verb == "show" else HideOperation
            return operation_type(
                representation=_string(
                    item["representation"], name="representation"
                ),
                target=_decode_target(item["target"]),
            )
        if verb == "orient":
            if set(item) != {"verb", "target"}:
                raise ProtocolDecodeError("invalid orient command fields")
            return OrientOperation(target=_decode_target(item["target"]))
    except ValueError as error:
        if isinstance(error, ProtocolDecodeError):
            raise
        raise ProtocolDecodeError(
            f"unsupported {verb} command values"
        ) from error
    raise ProtocolDecodeError("unsupported action plan command")


@dataclass(frozen=True)
class ValidationReportV1:
    """The validation result accompanying a typed action plan."""

    status: str
    snapshot_digest: str
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Encode the validation report using its V1 wire-field names.

        Returns:
            The validation report represented with wire-field names.
        """
        return {
            "status": self.status,
            "snapshotDigest": self.snapshot_digest,
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_dict(cls, value: object) -> ValidationReportV1:
        """Decode and validate a V1 validation report.

        Args:
            value: JSON-like value containing a validation report.

        Returns:
            The validated validation report.

        Raises:
            ProtocolDecodeError: If value does not match the report schema.
        """
        data = _strict_object(
            value,
            name="validation",
            required={"status", "snapshotDigest", "warnings"},
        )
        match data["warnings"]:
            case list() as warning_values:
                warnings = tuple(
                    _string(item, name="warning") for item in warning_values
                )
            case _:
                raise ProtocolDecodeError("validation.warnings must be strings")
        status = _string(data["status"], name="status")
        if status != "passed":
            raise ProtocolDecodeError("validation status is not passed")
        return cls(
            status=status,
            snapshot_digest=_string(
                data["snapshotDigest"], name="snapshotDigest"
            ),
            warnings=warnings,
        )


@dataclass(frozen=True)
class ValidatedPlanResponseV1:
    """A strictly decoded successful server response."""

    request_id: str
    session_id: str
    received_at: str
    validated_at: str
    action_plan: ActionPlan
    validation: ValidationReportV1
    plan_id: str
    snapshot_digest: str
    protocol_version: str = PROTOCOL_VERSION

    def to_dict(self) -> dict[str, object]:
        """Encode the validated response using its V1 wire shape.

        Returns:
            The response represented with wire-field names.
        """
        return {
            "protocolVersion": self.protocol_version,
            "requestId": self.request_id,
            "sessionId": self.session_id,
            "receivedAt": self.received_at,
            "validatedAt": self.validated_at,
            "status": "validated",
            "actionPlan": {
                "planId": self.plan_id,
                "planVersion": self.protocol_version,
                "snapshotDigest": self.snapshot_digest,
                "commands": encode_plan(self.action_plan),
            },
            "validation": self.validation.to_dict(),
        }

    @classmethod
    def from_dict(cls, value: object) -> ValidatedPlanResponseV1:
        """Decode and validate a successful V1 response.

        Args:
            value: JSON-like value containing a validated response.

        Returns:
            The validated response.

        Raises:
            ProtocolDecodeError: If value does not match the response schema.
        """
        data = _strict_object(
            value,
            name="ValidatedPlanResponseV1",
            required={
                "protocolVersion",
                "requestId",
                "sessionId",
                "receivedAt",
                "validatedAt",
                "status",
                "actionPlan",
                "validation",
            },
        )
        if data["protocolVersion"] != PROTOCOL_VERSION:
            raise ProtocolDecodeError("unsupported protocol version")
        if data["status"] != "validated":
            raise ProtocolDecodeError("response status is not validated")
        action_plan_data = _object(data["actionPlan"], name="actionPlan")
        plan = decode_plan(action_plan_data)
        validation = ValidationReportV1.from_dict(data["validation"])
        snapshot_digest = _string(
            action_plan_data["snapshotDigest"], name="snapshotDigest"
        )
        if snapshot_digest != validation.snapshot_digest:
            raise ProtocolDecodeError(
                "actionPlan and validation snapshot digests do not match"
            )
        return cls(
            request_id=_uuid4(data["requestId"], name="requestId"),
            session_id=_uuid4(data["sessionId"], name="sessionId"),
            received_at=_timestamp(data["receivedAt"], name="receivedAt"),
            validated_at=_timestamp(data["validatedAt"], name="validatedAt"),
            action_plan=plan,
            validation=validation,
            plan_id=_uuid4(action_plan_data["planId"], name="planId"),
            snapshot_digest=snapshot_digest,
        )


@dataclass(frozen=True)
class FailureEnvelopeV1:
    """A bounded, typed failure that carries no executable plan."""

    category: str
    message: str
    retryable: bool

    def to_dict(self) -> dict[str, object]:
        """Encode the bounded failure envelope.

        Returns:
            The failure envelope represented with wire-field names.
        """
        return {
            "category": self.category,
            "message": self.message,
            "retryable": self.retryable,
        }

    @classmethod
    def from_dict(cls, value: object) -> FailureEnvelopeV1:
        """Decode and validate a bounded failure envelope.

        Args:
            value: JSON-like value containing a failure envelope.

        Returns:
            The validated failure envelope.

        Raises:
            ProtocolDecodeError: If value does not match the envelope schema.
        """
        data = _strict_object(
            value,
            name="failure",
            required={"category", "message", "retryable"},
        )
        match data["retryable"]:
            case bool() as retryable:
                pass
            case _:
                raise ProtocolDecodeError("failure.retryable must be a boolean")
        return cls(
            category=_string(data["category"], name="category"),
            message=_string(data["message"], name="message"),
            retryable=retryable,
        )


@dataclass(frozen=True)
class FailedPlanResponseV1:
    """A correlated V1 failure response with no partial action plan."""

    request_id: str
    session_id: str
    failure: FailureEnvelopeV1
    protocol_version: str = PROTOCOL_VERSION

    def to_dict(self) -> dict[str, object]:
        """Encode the failed response without an action plan.

        Returns:
            The response represented with wire-field names.
        """
        return {
            "protocolVersion": self.protocol_version,
            "requestId": self.request_id,
            "sessionId": self.session_id,
            "status": "failed",
            "failure": self.failure.to_dict(),
        }

    @classmethod
    def from_dict(cls, value: object) -> FailedPlanResponseV1:
        """Decode and validate a failed V1 response.

        Args:
            value: JSON-like value containing a failed response.

        Returns:
            The validated failed response.

        Raises:
            ProtocolDecodeError: If value does not match the response schema.
        """
        data = _strict_object(
            value,
            name="FailedPlanResponseV1",
            required={
                "protocolVersion",
                "requestId",
                "sessionId",
                "status",
                "failure",
            },
        )
        if data["protocolVersion"] != PROTOCOL_VERSION:
            raise ProtocolDecodeError("unsupported protocol version")
        if data["status"] != "failed":
            raise ProtocolDecodeError("response status is not failed")
        return cls(
            request_id=_uuid4(data["requestId"], name="requestId"),
            session_id=_uuid4(data["sessionId"], name="sessionId"),
            failure=FailureEnvelopeV1.from_dict(data["failure"]),
        )


@dataclass(frozen=True)
class CommandOutcomeV1:
    """One command's observed outcome, indexed by its plan position."""

    index: int
    verb: str
    status: str
    error: str | None

    def to_dict(self) -> dict[str, object]:
        """Encode this outcome using its V1 wire-field names.

        Returns:
            The outcome represented with wire-field names.
        """
        return {
            "index": self.index,
            "verb": self.verb,
            "status": self.status,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, value: object) -> CommandOutcomeV1:
        """Decode and validate a V1 command outcome.

        Args:
            value: JSON-like value containing a command outcome.

        Returns:
            The validated command outcome.

        Raises:
            ProtocolDecodeError: If value does not match the outcome schema.
        """
        data = _strict_object(
            value,
            name="commandOutcome",
            required={"index", "verb", "status", "error"},
        )
        return cls(
            index=_int(data["index"], name="index"),
            verb=_string(data["verb"], name="verb"),
            status=_string(data["status"], name="status"),
            error=_optional_string(data["error"], name="error"),
        )


@dataclass(frozen=True)
class SelectionCountV1:
    """One selection's atom count after a plan executed."""

    name: str
    atom_count: int

    def to_dict(self) -> dict[str, object]:
        """Encode this selection count using its V1 wire-field names.

        Returns:
            The selection count represented with wire-field names.
        """
        return {"name": self.name, "atomCount": self.atom_count}

    @classmethod
    def from_dict(cls, value: object) -> SelectionCountV1:
        """Decode and validate a V1 selection count.

        Args:
            value: JSON-like value containing a selection count.

        Returns:
            The validated selection count.

        Raises:
            ProtocolDecodeError: If value does not match the schema.
        """
        data = _strict_object(
            value, name="selectionCount", required={"name", "atomCount"}
        )
        return cls(
            name=_string(data["name"], name="name"),
            atom_count=_int(data["atomCount"], name="atomCount"),
        )


@dataclass(frozen=True)
class ExecutionReportV1:
    """The sidecar executor's report, on the wire.

    Unlike ValidationReportV1, this type's status and reason can represent
    any of pmc_core.executor's STATUS_*/REASON_* values, including a
    failure -- a report that can only represent success is not a
    fail-closed contract. See docs/master_plan.md item 4, the sidecar
    executor.
    """

    executor_version: int
    status: str
    reason: str
    input_digest: str | None
    resulting_fingerprint: str | None
    selection_counts: tuple[SelectionCountV1, ...]
    command_outcomes: tuple[CommandOutcomeV1, ...]
    elapsed_seconds: float
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Encode this report using its V1 wire-field names.

        Returns:
            The report represented with wire-field names.
        """
        return {
            "executorVersion": self.executor_version,
            "status": self.status,
            "reason": self.reason,
            "inputDigest": self.input_digest,
            "resultingFingerprint": self.resulting_fingerprint,
            "selectionCounts": [
                item.to_dict() for item in self.selection_counts
            ],
            "commandOutcomes": [
                item.to_dict() for item in self.command_outcomes
            ],
            "elapsedSeconds": self.elapsed_seconds,
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_dict(cls, value: object) -> ExecutionReportV1:
        """Decode and validate a V1 execution report.

        Args:
            value: JSON-like value containing an execution report.

        Returns:
            The validated execution report.

        Raises:
            ProtocolDecodeError: If value does not match the report schema.
        """
        data = _strict_object(
            value,
            name="executionReport",
            required={
                "executorVersion",
                "status",
                "reason",
                "inputDigest",
                "resultingFingerprint",
                "selectionCounts",
                "commandOutcomes",
                "elapsedSeconds",
                "warnings",
            },
        )
        match data["selectionCounts"]:
            case list() as items:
                selection_counts = tuple(
                    SelectionCountV1.from_dict(item) for item in items
                )
            case _:
                raise ProtocolDecodeError(
                    "executionReport.selectionCounts must be a list"
                )
        match data["commandOutcomes"]:
            case list() as items:
                command_outcomes = tuple(
                    CommandOutcomeV1.from_dict(item) for item in items
                )
            case _:
                raise ProtocolDecodeError(
                    "executionReport.commandOutcomes must be a list"
                )
        match data["warnings"]:
            case list() as items:
                warnings = tuple(
                    _string(item, name="warning") for item in items
                )
            case _:
                raise ProtocolDecodeError(
                    "executionReport.warnings must be strings"
                )
        return cls(
            executor_version=_int(
                data["executorVersion"], name="executorVersion"
            ),
            status=_string(data["status"], name="status"),
            reason=_string(data["reason"], name="reason"),
            input_digest=_optional_string(
                data["inputDigest"], name="inputDigest"
            ),
            resulting_fingerprint=_optional_string(
                data["resultingFingerprint"], name="resultingFingerprint"
            ),
            selection_counts=selection_counts,
            command_outcomes=command_outcomes,
            elapsed_seconds=_float(
                data["elapsedSeconds"], name="elapsedSeconds"
            ),
            warnings=warnings,
        )


@dataclass(frozen=True)
class ExecutionRequestV1:
    """A request to execute one typed plan against one canonical snapshot.

    On the wire, this reuses the same tagged `actionPlan` object
    `ValidatedPlanResponseV1` carries (`planId`/`planVersion`/
    `snapshotDigest`/`commands`), so there is exactly one plan wire shape
    in the repository -- the sidecar executor's own request/report
    contract is otherwise unrelated to that response type. `planId` exists
    only to satisfy that shared envelope's own schema. The action-plan-level
    `snapshotDigest`, however, is enforced by the executor against the
    structural digest it computes from `snapshotJson`, so a plan cannot be
    silently executed against a different snapshot.
    """

    plan: ActionPlan
    plan_id: str
    snapshot_digest: str
    snapshot_json: str
    expected_resulting_fingerprint: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Encode this request using its V1 wire-field names.

        Returns:
            The request represented with wire-field names.
        """
        return {
            "actionPlan": {
                "planId": self.plan_id,
                "planVersion": PROTOCOL_VERSION,
                "snapshotDigest": self.snapshot_digest,
                "commands": encode_plan(self.plan),
            },
            "snapshotJson": self.snapshot_json,
            "expectedResultingFingerprint": (
                self.expected_resulting_fingerprint
            ),
        }

    @classmethod
    def from_dict(cls, value: object) -> ExecutionRequestV1:
        """Decode and validate a V1 execution request.

        Args:
            value: JSON-like value containing an execution request.

        Returns:
            The validated execution request.

        Raises:
            ProtocolDecodeError: If value does not match the request schema.
        """
        data = _strict_object(
            value,
            name="executionRequest",
            required={
                "actionPlan",
                "snapshotJson",
                "expectedResultingFingerprint",
            },
        )
        action_plan_data = _object(data["actionPlan"], name="actionPlan")
        plan = decode_plan(action_plan_data)
        return cls(
            plan=plan,
            plan_id=_uuid4(action_plan_data["planId"], name="planId"),
            snapshot_digest=_string(
                action_plan_data["snapshotDigest"], name="snapshotDigest"
            ),
            snapshot_json=_string(data["snapshotJson"], name="snapshotJson"),
            expected_resulting_fingerprint=_optional_string(
                data["expectedResultingFingerprint"],
                name="expectedResultingFingerprint",
            ),
        )


def encode_json(
    value: PlanRequestV1 | ValidatedPlanResponseV1 | FailedPlanResponseV1,
) -> str:
    """Encode a supported protocol value as compact JSON.

    Args:
        value: Supported protocol value to encode.

    Returns:
        The compact JSON representation.
    """
    return json.dumps(value.to_dict(), separators=(",", ":"))


def decode_json(
    value: str, *, response: bool = False
) -> PlanRequestV1 | ValidatedPlanResponseV1 | FailedPlanResponseV1:
    """Decode JSON strictly as a V1 request or validated response.

    Args:
        value: JSON text to decode.
        response: Whether to decode a response instead of a request.

    Returns:
        The decoded typed protocol value.

    Raises:
        ProtocolDecodeError: If the JSON or protocol value is invalid.
    """
    # json.loads raises more than JSONDecodeError on hostile input: deeply
    # nested arrays raise RecursionError, and an integer literal past
    # CPython's digit limit raises a plain ValueError. Both arrive well
    # inside the transport's payload bound, and both would otherwise escape
    # as unhandled exceptions -- the loopback server catches only
    # ProtocolDecodeError, so the connection would drop with no response.
    try:
        decoded = json.loads(value)
    except (ValueError, RecursionError) as error:
        raise ProtocolDecodeError("invalid JSON") from error
    match decoded:
        case dict():
            pass
        case _:
            raise ProtocolDecodeError("protocol message must be an object")
    if not response:
        return PlanRequestV1.from_dict(decoded)
    if decoded.get("status") == "failed":
        return FailedPlanResponseV1.from_dict(decoded)
    return ValidatedPlanResponseV1.from_dict(decoded)


def encode_execution_response_json(value: ExecutionReportV1) -> str:
    """Encode an execution report as compact JSON.

    Args:
        value: Execution report to encode.

    Returns:
        The compact JSON representation.
    """
    return json.dumps(
        value.to_dict(), separators=(",", ":"), ensure_ascii=False
    )


def decode_execution_request_json(value: str) -> ExecutionRequestV1:
    """Decode JSON strictly as a V1 execution request.

    Args:
        value: JSON text to decode.

    Returns:
        The decoded typed execution request.

    Raises:
        ProtocolDecodeError: If the JSON or protocol value is invalid.
    """
    # Same hostile-JSON handling as decode_json: deeply nested arrays raise
    # RecursionError and an over-long integer literal raises a plain
    # ValueError, neither of which is ProtocolDecodeError on its own.
    try:
        decoded = json.loads(value)
    except (ValueError, RecursionError) as error:
        raise ProtocolDecodeError("invalid JSON") from error
    return ExecutionRequestV1.from_dict(decoded)
