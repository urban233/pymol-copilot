# Copyright 2026 PyMOL Copilot contributors.
"""Strict codecs for the initial client-server protocol fixture."""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime

from pmc_core.plan import ActionPlan
from pmc_core.plan import ColorOperation
from pmc_core.plan import SelectOperation

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


def _plan_commands(plan: ActionPlan) -> list[dict[str, str]]:
    """Convert a typed action plan to its wire command objects.

    Args:
        plan: Action plan to encode.

    Returns:
        The command objects for the plan.

    Raises:
        ProtocolDecodeError: If the plan contains an unsupported operation.
    """
    commands: list[dict[str, str]] = []
    for operation in plan.operations:
        match operation:
            case SelectOperation():
                commands.append(
                    {
                        "verb": "select",
                        "name": operation.selection_name,
                        "expression": operation.expression,
                    }
                )
            case ColorOperation():
                commands.append(
                    {
                        "verb": "color",
                        "color": operation.color,
                        "target": operation.selection_name,
                    }
                )
            case _:
                raise ProtocolDecodeError("unsupported action plan operation")
    return commands


def _decode_plan(value: object) -> ActionPlan:
    """Decode a strictly shaped action plan.

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
        case list() as command_list if len(command_list) == 2:
            pass
        case _:
            raise ProtocolDecodeError(
                "actionPlan.commands must contain two items"
            )
    decoded = tuple(_decode_command(command) for command in command_list)
    match decoded:
        case (SelectOperation() as select, ColorOperation() as color):
            return ActionPlan(operations=(select, color))
        case _:
            raise ProtocolDecodeError("action plan commands have wrong shape")


def _decode_command(value: object) -> SelectOperation | ColorOperation:
    """Decode one strictly shaped action-plan command.

    Args:
        value: JSON-like value containing an action-plan command.

    Returns:
        The decoded select or color operation.

    Raises:
        ProtocolDecodeError: If value does not match a supported command shape.
    """
    item = _object(value, name="actionPlan command")
    verb = item.get("verb")
    if verb == "select":
        if set(item) != {"verb", "name", "expression"}:
            raise ProtocolDecodeError("invalid select command fields")
        try:
            return SelectOperation(
                selection_name=_string(item["name"], name="name"),
                expression=_string(item["expression"], name="expression"),
            )
        except ValueError as error:
            raise ProtocolDecodeError(
                "unsupported select command values"
            ) from error
    if verb == "color":
        if set(item) != {"verb", "color", "target"}:
            raise ProtocolDecodeError("invalid color command fields")
        try:
            return ColorOperation(
                color=_string(item["color"], name="color"),
                selection_name=_string(item["target"], name="target"),
            )
        except ValueError as error:
            raise ProtocolDecodeError(
                "unsupported color command values"
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
                "commands": _plan_commands(self.action_plan),
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
        plan = _decode_plan(action_plan_data)
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
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError as error:
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
