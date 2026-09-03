# Copyright 2026 PyMOL Copilot contributors.
"""Authenticated, bounded HTTP/JSON loopback client transport."""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

from http import HTTPStatus
from http.client import HTTPConnection
from http.client import HTTPException
from http.client import HTTPResponse

from pmc_core.protocol import FailedPlanResponseV1
from pmc_core.protocol import PlanRequestV1
from pmc_core.protocol import ProtocolDecodeError
from pmc_core.protocol import ValidatedPlanResponseV1
from pmc_core.protocol import decode_json
from pmc_core.protocol import encode_json

LOOPBACK_HOST = "127.0.0.1"
PLAN_PATH = "/v1/plan"
CREDENTIAL_HEADER = "X-PyMOL-Copilot-Credential"
MAX_MESSAGE_BYTES = 64 * 1024

type PLAN_RESPONSE = ValidatedPlanResponseV1 | FailedPlanResponseV1

# Preserve the original public type-alias name.
globals()["PlanResponse"] = PLAN_RESPONSE


class TransportError(RuntimeError):
    """Raised when the local server transport cannot be trusted."""


class LoopbackPlanClient:
    """Send one strict V1 plan request to the local loopback server."""

    def __init__(
        self, port: int, credential: str, *, timeout_seconds: float = 5.0
    ) -> None:
        """Configure a finite-timeout client for one server endpoint.

        Args:
            port: The server's ephemeral loopback port.
            credential: The ephemeral credential sent as an HTTP header.
            timeout_seconds: The finite request and response timeout.

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
        payload = encode_json(request).encode("utf-8")
        if len(payload) > MAX_MESSAGE_BYTES:
            raise TransportError("request exceeds the V1 transport limit")
        connection = HTTPConnection(
            LOOPBACK_HOST, self._port, timeout=self._timeout_seconds
        )
        try:
            connection.request(
                "POST",
                PLAN_PATH,
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
            case _:
                raise TransportError(
                    "server response has an unsupported V1 shape"
                )

    def _validate_correlation(
        self, request: PlanRequestV1, response: PLAN_RESPONSE
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
