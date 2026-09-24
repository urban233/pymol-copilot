# Copyright 2026 PyMOL Copilot contributors.
"""Authenticated, bounded HTTP/JSON loopback client transport."""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

from http import HTTPStatus
from http.client import HTTPConnection
from http.client import HTTPException
from http.client import HTTPResponse

from pmc_core.executor import MAX_EXECUTION_REQUEST_BYTES
from pmc_core.protocol import CancelRequestV1
from pmc_core.protocol import ApplyOutcomeRequestV1
from pmc_core.protocol import ApplyRequestV1
from pmc_core.protocol import FailedPlanResponseV1
from pmc_core.protocol import PlanRequestV1
from pmc_core.protocol import ProtocolDecodeError
from pmc_core.protocol import RejectRequestV1
from pmc_core.protocol import ValidatedPlanResponseV1
from pmc_core.protocol import decode_json
from pmc_core.protocol import encode_json

LOOPBACK_HOST = "127.0.0.1"
PLAN_PATH = "/v1/plan"
#: docs/master_plan.md item 8's own request-graph endpoints
#: (`pmc_server.transport.REJECT_PATH`/`CANCEL_PATH`), redefined here with
#: matching literal values: `pmc_client` cannot depend on `pmc_server`
#: (tools/bazel/check_dependency_boundaries.py), so every endpoint path
#: this client uses is its own copy of the server's own constant, exactly
#: as `PLAN_PATH` already is.
REJECT_PATH = "/v1/reject"
CANCEL_PATH = "/v1/cancel"
APPLY_PATH = "/v1/apply"
APPLY_OUTCOME_PATH = "/v1/apply-outcome"
CREDENTIAL_HEADER = "X-PyMOL-Copilot-Credential"
MAX_MESSAGE_BYTES = 64 * 1024
#: `PlanRequestV1` now carries the full canonical snapshot JSON, not
#: merely its identity (docs/master_plan.md item 8), so the request side
#: of this transport needs the same wider bound
#: `pmc_server.transport`'s own `/v1/plan` handler enforces --
#: `pmc_core.executor.MAX_EXECUTION_REQUEST_BYTES`, imported directly
#: rather than recomputed: unlike `REJECT_PATH` above, `pmc_client` already
#: depends on `pmc_core` for other reasons, so there is no dependency-
#: boundary reason to keep a second, independently-computed copy of this
#: one. Every response this transport reads stays bounded at
#: MAX_MESSAGE_BYTES: no response ever carries a snapshot.
MAX_REQUEST_BYTES = MAX_EXECUTION_REQUEST_BYTES

type PLAN_RESPONSE = ValidatedPlanResponseV1 | FailedPlanResponseV1

# Preserve the original public type-alias name.
globals()["PlanResponse"] = PLAN_RESPONSE


class TransportError(RuntimeError):
    """Raised when the local server transport cannot be trusted."""


#: `/v1/plan` now answers synchronously from inside the request graph
#: (docs/master_plan.md item 8), not a fixture echo: `pmc_server.lifecycle
#: .RequestGraphLifecycle` can drive up to three full generate-then-validate
#: attempts (one initial plus two repairs) before the HTTP response is ever
#: written, each bounded by the graph's own 30-second generation deadline
#: and 30-second sidecar-validation deadline. `pmc_client` cannot import
#: those bounds directly (`pmc_agent` is off limits for code running inside
#: PyMOL's interpreter), so this default is that worst case -- 3 * (30 + 30)
#: = 180 seconds -- with headroom, computed here rather than left at a
#: value sized for the old fixture echo. `/v1/reject` and `/v1/cancel`
#: resume a single already-parked attempt and return far sooner, but share
#: this same generous bound rather than a second, separately-tuned one.
DEFAULT_TIMEOUT_SECONDS = 200.0


class LoopbackPlanClient:
    """Send one strict V1 plan request to the local loopback server."""

    def __init__(
        self,
        port: int,
        credential: str,
        *,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        """Configure a finite-timeout client for one server endpoint.

        Args:
            port: The server's ephemeral loopback port.
            credential: The ephemeral credential sent as an HTTP header.
            timeout_seconds: The finite request and response timeout.
                Defaults to a bound above the request graph's own worst-case
                generate-then-validate duration; a caller talking to a
                server it knows answers faster (or that has no request
                graph behind it at all, as in a transport-only test) may
                still pass a smaller value.

        Raises:
            ValueError: If an argument cannot form a bounded local connection.
        """
        if not 1 <= port <= 65535:
            raise ValueError("port must be between 1 and 65535")
        if not credential:
            raise ValueError("credential must not be empty")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._port = port
        self._credential = credential
        self._timeout_seconds = timeout_seconds

    def submit(self, request: PlanRequestV1) -> PLAN_RESPONSE:
        """Submit a request and verify its typed correlated response.

        Args:
            request: Typed request to send to the loopback server.

        Returns:
            The validated plan or typed failure returned by the server.

        Raises:
            TransportError: If HTTP or protocol validation fails.
        """
        decoded = self._send(request, PLAN_PATH)
        match decoded:
            case ValidatedPlanResponseV1() as response:
                self._validate_correlation(request, response)
                if (
                    response.snapshot_digest != request.snapshot.digest
                    or response.validation.snapshot_digest
                    != request.snapshot.digest
                ):
                    raise TransportError(
                        "server response does not match request snapshot identity"
                    )
                return response
            case FailedPlanResponseV1() as response:
                self._validate_correlation(request, response)
                return response

    def reject(self, request: RejectRequestV1) -> FailedPlanResponseV1:
        """Submit a reject request and verify its typed correlated response.

        Args:
            request: Typed reject request to send to the loopback server.

        Returns:
            The typed failure response returned by the server, whose
            `failure.category` names whichever terminal the graph reached
            (`rejected` on an ordinary success, `expired` if the plan's
            TTL had already passed).

        Raises:
            TransportError: If HTTP or protocol validation fails.
        """
        decoded = self._send(request, REJECT_PATH)
        match decoded:
            case FailedPlanResponseV1() as response:
                self._validate_correlation(request, response)
                return response
            case _:
                raise TransportError(
                    "server response has an unsupported V1 shape for /v1/reject"
                )

    def cancel(self, request: CancelRequestV1) -> FailedPlanResponseV1:
        """Submit a cancel request and verify its typed correlated response.

        Args:
            request: Typed cancel request to send to the loopback server.

        Returns:
            The typed failure response returned by the server, whose
            `failure.category` names whichever terminal the graph reached.

        Raises:
            TransportError: If HTTP or protocol validation fails.
        """
        decoded = self._send(request, CANCEL_PATH)
        match decoded:
            case FailedPlanResponseV1() as response:
                self._validate_correlation(request, response)
                return response
            case _:
                raise TransportError(
                    "server response has an unsupported V1 shape for /v1/cancel"
                )

    def apply(self, request: ApplyRequestV1) -> PLAN_RESPONSE:
        """Submit one approval request and receive the canonical plan."""
        decoded = self._send(request, APPLY_PATH)
        self._validate_correlation(request, decoded)
        return decoded

    def report_apply_outcome(
        self, request: ApplyOutcomeRequestV1
    ) -> FailedPlanResponseV1:
        """Report a terminal live-apply outcome after recovery is complete."""
        decoded = self._send(request, APPLY_OUTCOME_PATH)
        if not isinstance(decoded, FailedPlanResponseV1):
            raise TransportError(
                "server response has an unsupported V1 shape for /v1/apply-outcome"
            )
        self._validate_correlation(request, decoded)
        return decoded

    def _send(
        self,
        request: PlanRequestV1
        | RejectRequestV1
        | CancelRequestV1
        | ApplyRequestV1
        | ApplyOutcomeRequestV1,
        path: str,
    ) -> PLAN_RESPONSE:
        """POST one typed request and decode its typed response.

        Shared by `submit`, `reject`, and `cancel`: the connection,
        timeout, and error handling are identical regardless of which
        endpoint or request shape is involved. Each caller still runs its
        own correlation check afterward, since what "belongs to this
        request" means is the same test for all three but must be checked
        against each one's own identifiers.

        Args:
            request: The typed request to encode and send.
            path: The server path to POST to.

        Returns:
            The decoded typed response.

        Raises:
            TransportError: If HTTP or protocol validation fails, or the
                response is not one of this protocol's two response
                shapes.
        """
        payload = encode_json(request).encode("utf-8")
        if len(payload) > MAX_REQUEST_BYTES:
            raise TransportError("request exceeds the V1 transport limit")
        connection = HTTPConnection(
            LOOPBACK_HOST, self._port, timeout=self._timeout_seconds
        )
        try:
            connection.request(
                "POST",
                path,
                body=payload,
                headers={
                    "Content-Type": "application/json",
                    "Content-Length": str(len(payload)),
                    CREDENTIAL_HEADER: self._credential,
                },
            )
            response = connection.getresponse()
            if response.status != HTTPStatus.OK:
                raise TransportError(
                    f"server rejected request with HTTP {response.status}"
                )
            response_payload = self._read_response(response)
        except (HTTPException, OSError, TimeoutError) as error:
            raise TransportError("loopback request failed") from error
        finally:
            connection.close()
        try:
            decoded = decode_json(
                response_payload.decode("utf-8"), response=True
            )
        except (ProtocolDecodeError, UnicodeDecodeError) as error:
            raise TransportError(
                "server response does not match V1 protocol"
            ) from error
        match decoded:
            case ValidatedPlanResponseV1() | FailedPlanResponseV1():
                return decoded
            case _:
                raise TransportError(
                    "server response has an unsupported V1 shape"
                )

    def _validate_correlation(
        self,
        request: PlanRequestV1
        | RejectRequestV1
        | CancelRequestV1
        | ApplyRequestV1
        | ApplyOutcomeRequestV1,
        response: PLAN_RESPONSE,
    ) -> None:
        """Verify that a response belongs to the submitted request.

        Args:
            request: Request whose identifiers must match.
            response: Response to validate.

        Raises:
            TransportError: If request and response identifiers differ.
        """
        if (
            response.request_id != request.request_id
            or response.session_id != request.session_id
        ):
            raise TransportError(
                "server response does not match request correlation"
            )

    def _read_response(self, response: HTTPResponse) -> bytes:
        """Read and validate a bounded JSON response body.

        Args:
            response: HTTP response whose body should be read.

        Returns:
            The response body bytes.

        Raises:
            TransportError: If response metadata or length is invalid.
        """
        content_type = response.getheader("Content-Type")
        if content_type != "application/json":
            raise TransportError("server response is not JSON")
        content_length = response.getheader("Content-Length")
        if content_length is None or not content_length.isdigit():
            raise TransportError("server response has no valid content length")
        expected_length = int(content_length)
        if expected_length > MAX_MESSAGE_BYTES:
            raise TransportError(
                "server response exceeds the V1 transport limit"
            )
        payload = response.read(expected_length)
        if len(payload) != expected_length:
            raise TransportError(
                "server response ended before its declared length"
            )
        return payload
