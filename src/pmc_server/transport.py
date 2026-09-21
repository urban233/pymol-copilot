# Copyright 2026 PyMOL Copilot contributors.
"""Authenticated, bounded HTTP/JSON loopback server transport."""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import logging
from collections.abc import Callable
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer
from threading import Thread

from pmc_core.executor import DEFAULT_MAX_SNAPSHOT_BYTES
from pmc_core.protocol import CancelRequestV1
from pmc_core.protocol import ExecutionReportV1
from pmc_core.protocol import ExecutionRequestV1
from pmc_core.protocol import FailedPlanResponseV1
from pmc_core.protocol import PlanRequestV1
from pmc_core.protocol import ProtocolDecodeError
from pmc_core.protocol import RejectRequestV1
from pmc_core.protocol import ValidatedPlanResponseV1
from pmc_core.protocol import decode_cancel_request_json
from pmc_core.protocol import decode_execution_request_json
from pmc_core.protocol import decode_json
from pmc_core.protocol import decode_reject_request_json
from pmc_core.protocol import encode_execution_response_json
from pmc_core.protocol import encode_json

LOOPBACK_HOST = "127.0.0.1"
PLAN_PATH = "/v1/plan"
#: docs/master_plan.md item 8: reach `pmc_agent.session.RequestGraphSession
#: .reject`/`.cancel` through `pmc_server.lifecycle.RequestGraphLifecycle`.
#: Routed only when a server is constructed with the matching handler,
#: exactly like VALIDATE_PATH below -- a server built without one (every
#: transport-layer test that only cares about PLAN_PATH) returns 404 here,
#: exactly as it did when these paths were not routed at all.
REJECT_PATH = "/v1/reject"
CANCEL_PATH = "/v1/cancel"
#: The sidecar executor's endpoint (docs/master_plan.md item 4). Routed
#: only when a server is constructed with an execution_handler; a server
#: with none (every caller before this endpoint existed) returns 404 here,
#: exactly as it did when this path was not routed at all.
VALIDATE_PATH = "/v1/validate"
CREDENTIAL_HEADER = "X-PyMOL-Copilot-Credential"
MAX_MESSAGE_BYTES = 64 * 1024
#: `/v1/validate` carries a snapshot JSON document inside a JSON string. In
#: the worst case each byte of the canonical inner document needs one extra
#: escape byte, with the ordinary 64 KiB budget left for the action-plan
#: envelope. Responses stay on the shared 64 KiB bound.
MAX_EXECUTION_REQUEST_BYTES = 2 * DEFAULT_MAX_SNAPSHOT_BYTES + MAX_MESSAGE_BYTES
REQUEST_TIMEOUT_SECONDS = 5.0

LOGGER = logging.getLogger(__name__)

type PLAN_RESPONSE = ValidatedPlanResponseV1 | FailedPlanResponseV1
type PLAN_HANDLER = Callable[[PlanRequestV1], PLAN_RESPONSE]
type EXECUTION_HANDLER = Callable[[ExecutionRequestV1], ExecutionReportV1]
type REJECT_HANDLER = Callable[[RejectRequestV1], FailedPlanResponseV1]
type CANCEL_HANDLER = Callable[[CancelRequestV1], FailedPlanResponseV1]

# Preserve the original public type-alias names.
globals()["PlanResponse"] = PLAN_RESPONSE
globals()["PlanHandler"] = PLAN_HANDLER
globals()["ExecutionHandler"] = EXECUTION_HANDLER


class LoopbackPlanServer:
    """Serve authenticated V1 plan requests on an ephemeral loopback port."""

    def __init__(
        self,
        credential: str,
        handler: PLAN_HANDLER,
        *,
        execution_handler: EXECUTION_HANDLER | None = None,
        reject_handler: REJECT_HANDLER | None = None,
        cancel_handler: CANCEL_HANDLER | None = None,
    ) -> None:
        """Create a server that authenticates requests before decoding JSON.

        Args:
            credential: The ephemeral credential expected in every request.
            handler: The server request lifecycle invoked after strict
                decoding of a PLAN_PATH request.
            execution_handler: The sidecar executor's own request lifecycle
                (docs/master_plan.md item 4), invoked after strict decoding
                of a VALIDATE_PATH request. None -- the default, and every
                caller before this endpoint existed -- routes VALIDATE_PATH
                to 404, exactly as an unrouted path already does.
            reject_handler: docs/master_plan.md item 8's own request-graph
                lifecycle, invoked after strict decoding of a REJECT_PATH
                request. None -- the default -- routes REJECT_PATH to 404,
                exactly as an unrouted path already does.
            cancel_handler: The same lifecycle's cancel entry point,
                invoked after strict decoding of a CANCEL_PATH request.
                None -- the default -- routes CANCEL_PATH to 404.

        Raises:
            ValueError: If credential is empty.
        """
        if not credential:
            raise ValueError("credential must not be empty")
        self._credential = credential
        self._handler = handler
        self._execution_handler = execution_handler
        self._reject_handler = reject_handler
        self._cancel_handler = cancel_handler
        self._httpd = ThreadingHTTPServer(
            (LOOPBACK_HOST, 0), self._make_request_handler()
        )
        self._thread: Thread | None = None
        self._closed = False

    @property
    def port(self) -> int:
        """Return the ephemeral port allocated by the operating system.

        Returns:
            The server's allocated TCP port.
        """
        return self._httpd.server_port

    @property
    def host(self) -> str:
        """Return the only address on which this server accepts requests.

        Returns:
            The loopback host address.
        """
        return LOOPBACK_HOST

    def start(self) -> None:
        """Start accepting requests in a daemon thread.

        Raises:
            RuntimeError: If the server has already started or closed.
        """
        if self._closed:
            raise RuntimeError("loopback server is closed")
        if self._thread is not None:
            raise RuntimeError("loopback server has already started")
        self._thread = Thread(
            target=self._httpd.serve_forever,
            name="pymol-copilot-loopback-server",
            daemon=True,
        )
        self._thread.start()

    def close(self) -> None:
        """Stop serving requests and release the loopback socket."""
        if self._closed:
            return
        self._closed = True
        if self._thread is None:
            self._httpd.server_close()
            return
        self._httpd.shutdown()
        self._thread.join()
        self._httpd.server_close()
        self._thread = None

    def __enter__(self) -> LoopbackPlanServer:
        """Start the server for a context-managed transport fixture.

        Returns:
            This started server.
        """
        self.start()
        return self

    def __exit__(
        self,
        _exception_type: type[BaseException] | None,
        _exception: BaseException | None,
        _traceback: object | None,
    ) -> None:
        """Stop the server when a context-managed fixture exits.

        Args:
            _exception_type: Exception type raised inside the context, if any.
            _exception: Exception raised inside the context, if any.
            _traceback: Traceback for an exception raised inside the context.
        """
        self.close()

    def _make_request_handler(self) -> type[BaseHTTPRequestHandler]:
        """Create the request handler bound to this server instance.

        Returns:
            The configured HTTP request-handler class.
        """
        server = self

        class RequestHandler(BaseHTTPRequestHandler):
            """Handle one authenticated plan request."""

            def do_post(self) -> None:
                """Route by path to the plan or the execution endpoint.

                Returns:
                    None. The response is written to the client connection.
                """
                if self.path == PLAN_PATH:
                    self._handle_plan()
                    return
                if (
                    self.path == VALIDATE_PATH
                    and server._execution_handler is not None
                ):
                    self._handle_validate()
                    return
                if (
                    self.path == REJECT_PATH
                    and server._reject_handler is not None
                ):
                    self._handle_reject()
                    return
                if (
                    self.path == CANCEL_PATH
                    and server._cancel_handler is not None
                ):
                    self._handle_cancel()
                    return
                self._send_empty(HTTPStatus.NOT_FOUND)

            def _handle_plan(self) -> None:
                """Decode, dispatch, and answer one PLAN_PATH request."""
                # docs/master_plan.md item 8: the request now carries the
                # full canonical snapshot JSON (PlanRequestV1.snapshot_json),
                # not merely its identity, so this path shares VALIDATE_PATH's
                # own wider body cap rather than the plain message bound.
                payload = self._authorized_json_body(
                    MAX_EXECUTION_REQUEST_BYTES
                )
                if payload is None:
                    return
                try:
                    request = decode_json(payload.decode("utf-8"))
                except (ProtocolDecodeError, UnicodeDecodeError):
                    self._send_empty(HTTPStatus.BAD_REQUEST)
                    return
                if not isinstance(request, PlanRequestV1):
                    self._send_empty(HTTPStatus.BAD_REQUEST)
                    return
                try:
                    response = server._handler(request)
                    response_payload = encode_json(response).encode("utf-8")
                except (ProtocolDecodeError, ValueError):
                    self._send_empty(HTTPStatus.INTERNAL_SERVER_ERROR)
                    return
                self._send_json(response_payload)

            def _handle_validate(self) -> None:
                """Decode, dispatch, and answer one VALIDATE_PATH request."""
                payload = self._authorized_json_body(
                    MAX_EXECUTION_REQUEST_BYTES
                )
                if payload is None:
                    return
                try:
                    request = decode_execution_request_json(
                        payload.decode("utf-8")
                    )
                except (ProtocolDecodeError, UnicodeDecodeError):
                    self._send_empty(HTTPStatus.BAD_REQUEST)
                    return
                try:
                    execution_handler = server._execution_handler
                    assert execution_handler is not None
                    response = execution_handler(request)
                    response_payload = encode_execution_response_json(
                        response
                    ).encode("utf-8")
                except (ProtocolDecodeError, ValueError):
                    self._send_empty(HTTPStatus.INTERNAL_SERVER_ERROR)
                    return
                self._send_json(response_payload)

            def _handle_reject(self) -> None:
                """Decode, dispatch, and answer one REJECT_PATH request."""
                payload = self._authorized_json_body(MAX_MESSAGE_BYTES)
                if payload is None:
                    return
                try:
                    request = decode_reject_request_json(
                        payload.decode("utf-8")
                    )
                except (ProtocolDecodeError, UnicodeDecodeError):
                    self._send_empty(HTTPStatus.BAD_REQUEST)
                    return
                try:
                    reject_handler = server._reject_handler
                    assert reject_handler is not None
                    response = reject_handler(request)
                    response_payload = encode_json(response).encode("utf-8")
                except (ProtocolDecodeError, ValueError):
                    self._send_empty(HTTPStatus.INTERNAL_SERVER_ERROR)
                    return
                self._send_json(response_payload)

            def _handle_cancel(self) -> None:
                """Decode, dispatch, and answer one CANCEL_PATH request."""
                payload = self._authorized_json_body(MAX_MESSAGE_BYTES)
                if payload is None:
                    return
                try:
                    request = decode_cancel_request_json(
                        payload.decode("utf-8")
                    )
                except (ProtocolDecodeError, UnicodeDecodeError):
                    self._send_empty(HTTPStatus.BAD_REQUEST)
                    return
                try:
                    cancel_handler = server._cancel_handler
                    assert cancel_handler is not None
                    response = cancel_handler(request)
                    response_payload = encode_json(response).encode("utf-8")
                except (ProtocolDecodeError, ValueError):
                    self._send_empty(HTTPStatus.INTERNAL_SERVER_ERROR)
                    return
                self._send_json(response_payload)

            def _authorized_json_body(self, maximum_bytes: int) -> bytes | None:
                """Authenticate a request and read its bounded JSON body.

                Shared by every endpoint this handler serves: the
                credential, content-type, and content-length checks, and
                the bounded read itself, are identical regardless of which
                endpoint's own decode/encode runs afterward. The caller
                supplies the endpoint-specific request bound.

                Args:
                    maximum_bytes: Largest accepted request body.

                Returns:
                    The request body, or None after sending an error.
                """
                if self.headers.get(CREDENTIAL_HEADER) != server._credential:
                    self._send_empty(HTTPStatus.UNAUTHORIZED)
                    return None
                if self.headers.get("Content-Type") != "application/json":
                    self._send_empty(HTTPStatus.UNSUPPORTED_MEDIA_TYPE)
                    return None
                content_length = self._content_length(maximum_bytes)
                if content_length is None:
                    return None
                try:
                    payload = self.rfile.read(content_length)
                except TimeoutError:
                    self._send_empty(HTTPStatus.REQUEST_TIMEOUT)
                    return None
                if len(payload) != content_length:
                    self._send_empty(HTTPStatus.BAD_REQUEST)
                    return None
                return payload

            def _send_json(self, payload: bytes) -> None:
                """Send a successful bounded JSON response.

                Args:
                    payload: The encoded response body.
                """
                if len(payload) > MAX_MESSAGE_BYTES:
                    self._send_empty(HTTPStatus.INTERNAL_SERVER_ERROR)
                    return
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def _content_length(self, maximum_bytes: int) -> int | None:
                """Read and validate the request content length.

                Args:
                    maximum_bytes: Largest accepted request body.

                Returns:
                    The bounded content length, or None after sending an error.

                """
                values = self.headers.get_all("Content-Length")
                if values is None:
                    self._send_empty(HTTPStatus.LENGTH_REQUIRED)
                    return None
                if len(values) != 1 or not values[0].isdigit():
                    self._send_empty(HTTPStatus.BAD_REQUEST)
                    return None
                content_length = int(values[0])
                if content_length > maximum_bytes:
                    self._send_empty(HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
                    return None
                return content_length

            def _send_empty(self, status: HTTPStatus) -> None:
                """Send an empty response with the given HTTP status.

                Args:
                    status: HTTP status to send to the client.
                """
                self.send_response(status)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def setup(self) -> None:
                """Bound a connected client's time to provide its payload."""
                super().setup()
                self.connection.settimeout(REQUEST_TIMEOUT_SECONDS)

            def log_request(
                self, code: int | str = "-", size: int | str = "-"
            ) -> None:
                """Log response metadata without exposing request content.

                Args:
                    code: HTTP response status code.
                    size: Response body size.
                """
                LOGGER.info(
                    "loopback HTTP response completed: method=%s status=%s bytes=%s",
                    self.command,
                    code,
                    size,
                )

            def log_message(self, _message: str, *_args: object) -> None:
                """Log handler errors without forwarding untrusted request text.

                Args:
                    _message: Untrusted handler message, intentionally ignored.
                    _args: Untrusted message arguments, intentionally ignored.
                """
                LOGGER.warning("loopback HTTP handler error")

        RequestHandler.do_POST = RequestHandler.do_post
        return RequestHandler
