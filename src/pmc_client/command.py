# Copyright 2026 PyMOL Copilot contributors.
"""Non-mutating ``copilot`` command seam for the initial V1 fixture."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from datetime import timezone
import uuid
from typing import Protocol

from pmc_core.protocol import ContractManifestV1
from pmc_core.protocol import FailedPlanResponseV1
from pmc_core.protocol import PlanRequestV1
from pmc_core.protocol import StructureSnapshotV1
from pmc_core.protocol import ValidatedPlanResponseV1
from pmc_client.transport import LoopbackPlanClient

FIXTURE_INTENT = "Select chain A and color it red."
FIXTURE_MANIFEST = ContractManifestV1("1", "1", "1")
FIXTURE_SNAPSHOT = StructureSnapshotV1(
    "1", "sha256:example-chain-a-digest", "one-object-chain-a-v1"
)


class CmdExtension(Protocol):
    """Small subset of the PyMOL command API required for registration."""

    def extend(self, name: str, callback: Callable[[str], None]) -> None:
        """Register a command callback."""


class PlanTransport(Protocol):
    """Transport boundary used by the non-mutating command client."""

    def submit(
        self, request: PlanRequestV1
    ) -> ValidatedPlanResponseV1 | FailedPlanResponseV1:
        """Submit one typed plan request."""


def _utc_timestamp() -> str:
    """Return the current time in the protocol's RFC3339 UTC form."""
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


class CopilotCommandClient:
    """Submit and render fixture-backed plans without mutating PyMOL."""

    def __init__(
        self,
        transport: PlanTransport,
        output: Callable[[str], None],
        *,
        uuid_factory: Callable[[], uuid.UUID] = uuid.uuid4,
        timestamp_factory: Callable[[], str] = _utc_timestamp,
    ) -> None:
        """Create a command client with one session identity.

        Args:
            transport: Existing authenticated plan transport.
            output: Callable receiving command-console text.
            uuid_factory: UUID source, injectable for deterministic tests.
            timestamp_factory: RFC3339 UTC timestamp source.
        """
        self._transport = transport
        self._output = output
        self._uuid_factory = uuid_factory
        self._timestamp_factory = timestamp_factory
        self._session_id = str(uuid_factory())

    @property
    def session_id(self) -> str:
        """Return the UUIDv4 session identity reused by this client."""
        return self._session_id

    def register(self, cmd: CmdExtension) -> None:
        """Register the non-mutating command with a PyMOL-like object."""
        cmd.extend("copilot", self.copilot)

    def copilot(self, intent: str) -> None:
        """Submit one intent and report its typed result without execution."""
        request = PlanRequestV1(
            request_id=str(self._uuid_factory()),
            session_id=self._session_id,
            created_at=self._timestamp_factory(),
            contract_manifest=FIXTURE_MANIFEST,
            intent=intent,
            snapshot=FIXTURE_SNAPSHOT,
        )
        response = self._transport.submit(request)
        match response:
            case FailedPlanResponseV1():
                self._report_failure(response)
            case ValidatedPlanResponseV1():
                self._report_validated(response)

    def _report_failure(self, response: FailedPlanResponseV1) -> None:
        """Report a typed failure without attempting to render a plan."""
        failure = response.failure
        retryability = "retryable" if failure.retryable else "not retryable"
        self._output(
            f"copilot failed ({failure.category}; {retryability}): "
            f"{failure.message}"
        )

    def _report_validated(self, response: ValidatedPlanResponseV1) -> None:
        """Report only a passing typed plan and its canonical PML text."""
        if response.validation.status != "passed":
            self._output(
                "copilot validation failed: "
                f"status={response.validation.status}; "
                f"snapshot={response.validation.snapshot_digest}"
            )
            return
        self._output(f"copilot validation: {response.validation.status}")
        self._output(response.action_plan.render_pml())


def register_copilot(
    cmd: CmdExtension,
    transport: LoopbackPlanClient,
    output: Callable[[str], None],
) -> CopilotCommandClient:
    """Register ``copilot`` and return its client for the owning session."""
    client = CopilotCommandClient(transport, output)
    client.register(cmd)
    return client
