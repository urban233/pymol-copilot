# Copyright 2026 PyMOL Copilot contributors.
"""Authenticated, bounded HTTP/JSON loopback server transport."""

from __future__ import annotations

from collections.abc import Callable
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer
import logging
from threading import Thread

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
REQUEST_TIMEOUT_SECONDS = 5.0

LOGGER = logging.getLogger(__name__)

type PlanResponse = ValidatedPlanResponseV1 | FailedPlanResponseV1
type PlanHandler = Callable[[PlanRequestV1], PlanResponse]


class LoopbackPlanServer:
    """Serve authenticated V1 plan requests on an ephemeral loopback port."""

    def __init__(self, credential: str, handler: PlanHandler) -> None:
        """Create a server that authenticates requests before decoding JSON.

        Args:
            credential: The ephemeral credential expected in every request.
            handler: The server request lifecycle invoked after strict decoding.

        Raises:
            ValueError: If credential is empty.
        """
        if not credential:
            raise ValueError("credential must not be empty")
        self._credential = credential
        self._handler = handler
        self._httpd = ThreadingHTTPServer(
            (LOOPBACK_HOST, 0), self._make_request_handler()
        )
        self._thread: Thread | None = None
        self._closed = False

    @property
    def port(self) -> int:
        """Return the ephemeral port allocated by the operating system."""
        return self._httpd.server_port

    @property
    def host(self) -> str:
        """Return the only address on which this server accepts requests."""
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
        """Start the server for a context-managed transport fixture."""
        self.start()
        return self

    def __exit__(
        self,
        _exception_type: type[BaseException] | None,
        _exception: BaseException | None,
        _traceback: object | None,
    ) -> None:
        """Stop the server when a context-managed fixture exits."""
        self.close()

    def _make_request_handler(self) -> type[BaseHTTPRequestHandler]:
        server = self

        class RequestHandler(BaseHTTPRequestHandler):
            """Handle one authenticated plan request."""

            def do_POST(self) -> None:
                """Decode and dispatch the sole V1 endpoint."""
                if self.path != PLAN_PATH:
                    self._send_empty(HTTPStatus.NOT_FOUND)
                    return
                if self.headers.get(CREDENTIAL_HEADER) != server._credential:
                    self._send_empty(HTTPStatus.UNAUTHORIZED)
                    return
                if self.headers.get("Content-Type") != "application/json":
                    self._send_empty(HTTPStatus.UNSUPPORTED_MEDIA_TYPE)
                    return
                content_length = self._content_length()
                if content_length is None:
                    return
                try:
                    payload = self.rfile.read(content_length)
                except TimeoutError:
                    self._send_empty(HTTPStatus.REQUEST_TIMEOUT)
                    return
                if len(payload) != content_length:
                    self._send_empty(HTTPStatus.BAD_REQUEST)
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
                if len(response_payload) > MAX_MESSAGE_BYTES:
                    self._send_empty(HTTPStatus.INTERNAL_SERVER_ERROR)
                    return
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(response_payload)))
                self.end_headers()
                self.wfile.write(response_payload)

            def _content_length(self) -> int | None:
                values = self.headers.get_all("Content-Length")
                if values is None:
                    self._send_empty(HTTPStatus.LENGTH_REQUIRED)
                    return None
                if len(values) != 1 or not values[0].isdigit():
                    self._send_empty(HTTPStatus.BAD_REQUEST)
                    return None
                content_length = int(values[0])
                if content_length > MAX_MESSAGE_BYTES:
                    self._send_empty(HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
                    return None
                return content_length

            def _send_empty(self, status: HTTPStatus) -> None:
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
                """Log response metadata without exposing request content."""
                LOGGER.info(
                    "loopback HTTP response completed: method=%s status=%s bytes=%s",
                    self.command,
                    code,
                    size,
                )

            def log_message(self, _message: str, *_args: object) -> None:
                """Log handler errors without forwarding untrusted request text."""
                LOGGER.warning("loopback HTTP handler error")

        return RequestHandler
