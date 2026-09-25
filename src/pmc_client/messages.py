# Copyright 2026 PyMOL Copilot contributors.
"""One place every user-facing failure line is built.

docs/master_plan.md item 11: "Every failure path must produce a bounded,
actionable message -- no tracebacks, no plan text leaking through an
error." Before this module, each `pmc_client.command` handler built its own
failure text inline, several of them by interpolating `str(error)` directly
-- a raw PyMOL or Python exception message can carry a selection expression
or another fragment of the plan text SPECIFICATION.md:503-511 already
prints elsewhere, and neither `pmc_core.errors.ExecutionErrorV1` nor
`pmc_core.parser.ParseRejection` ever puts that kind of text in an error for
exactly that reason.

`ACTIONS` is this module's closed-set claim: every category
`pmc_core.protocol.FAILURE_CATEGORIES` names has one bounded, concrete next
step here. `tests/unit/test_client_messages.py` asserts
`ACTIONS.keys() >= FAILURE_CATEGORIES` directly; with
`tests/integration/test_failure_messages.py`'s own server-side assertion
that nothing escapes that set, "actionable" becomes a property two tests
check from both ends, not a claim resting on one file staying in sync with
another by hand.
"""

from __future__ import annotations

from types import MappingProxyType

from pmc_core.errors import CATEGORY_INVALID_SELECTION_NAME
from pmc_core.errors import CATEGORY_SELECTION_SYNTAX
from pmc_core.errors import CATEGORY_UNKNOWN
from pmc_core.errors import CATEGORY_UNKNOWN_COLOR
from pmc_core.errors import CATEGORY_UNKNOWN_REPRESENTATION
from pmc_core.executor import bounded_diagnostic
from pmc_core.protocol import EXECUTION_INFRASTRUCTURE_CATEGORIES
from pmc_core.protocol import FailureEnvelopeV1

#: The default byte bound for a rendered command-console line. Chosen well
#: above `pmc_core.errors.MAX_MESSAGE_BYTES` (256) and
#: `pmc_core.protocol.MAX_FAILURE_MESSAGE_BYTES` (256): a rendered line
#: quotes a bounded server message *and* names an action, so it needs
#: headroom past either bound alone.
MAX_LINE_BYTES = 400


def bounded(text: str, *, max_bytes: int = 256) -> str:
    """Bound arbitrary text to one printable-ASCII line.

    The one place this module (and nothing upstream of it) can still see
    unbounded or unprintable text: a raw `Exception` message, a
    `TransportError` string, or a value some future caller forgot to bound
    first. Never raises, for any input.

    Args:
        text: Text to bound, of any length or content.
        max_bytes: The largest UTF-8 encoding to keep.

    Returns:
        `text`, reduced to one printable-ASCII, length-bounded line.
    """
    single_line = "".join(
        character if 0x20 <= ord(character) < 0x7F else "?"
        for character in text
    )
    return bounded_diagnostic(single_line, maximum_bytes=max_bytes)


#: The shared action for every `pmc_core.protocol
#: .EXECUTION_INFRASTRUCTURE_CATEGORIES` member: each names a sidecar-level
#: problem (an oversized or malformed input, a spawn failure, a timeout, a
#: crash, a digest or schema mismatch) that no rewording of the intent can
#: fix, so one honest action serves all ten.
_EXECUTION_INFRASTRUCTURE_ACTION = (
    "This is a problem in the local validation step, not with your "
    "intent. Run copilot again; if it keeps happening, run copilot_health."
)

#: Every `pmc_core.protocol.FAILURE_CATEGORIES` member's own next step.
#: Built from three groups plus the categories this module and
#: `pmc_server.lifecycle` add on top of the graph's own vocabulary --
#: never a single hand-typed literal dict, so a missing category is a
#: missing dict comprehension member, not a silently absent line.
ACTIONS: MappingProxyType[str, str] = MappingProxyType(
    {
        # pmc_agent.graph's own FAILURE_* categories, and pmc_agent
        # .session's inline ones.
        "contract_mismatch": (
            "Client and server versions differ. Restart PyMOL and the "
            "server, then run copilot_health."
        ),
        "malformed_snapshot": (
            "The server could not read the session snapshot. Restart "
            "PyMOL and run copilot again."
        ),
        "no_target_object": (
            "No single supported object is loaded. Load or select "
            "exactly one object, then run copilot again."
        ),
        "engine_incomplete": (
            "The model's response was cut off before finishing. Run "
            "copilot again with a shorter or simpler intent."
        ),
        "repair_exhausted": (
            "The model could not produce a valid plan after retrying. "
            "Rephrase the intent more specifically and run copilot again."
        ),
        "unrecognized_resume": (
            "The client and server disagree about this request's own "
            "state. Restart PyMOL and the server, then try again."
        ),
        "unrecognized_apply_outcome": (
            "The client and server disagree about this request's own "
            "state. Restart PyMOL and the server, then try again."
        ),
        "apply_outcome_required": (
            "The previous approved plan has not been confirmed with the "
            "server yet. Do not run copilot_apply again; retry once the "
            "server is reachable, or run copilot_health."
        ),
        "not_applicable": (
            "This plan can only be inspected, not applied, because the "
            "session could not be reconstructed exactly. Run copilot "
            "again once the session is unchanged."
        ),
        # pmc_server.lifecycle's own FAILURE_NO_PENDING_PLAN.
        "no_pending_plan": (
            "There is no plan pending for this session. Run copilot "
            "again to create one."
        ),
        # docs/master_plan.md item 11's own additions.
        "hostile_output": (
            "The model produced a forbidden command form; nothing was "
            "run. Rephrase the intent."
        ),
        "server_internal_error": (
            "The server hit an internal error. Retry; if it keeps "
            "happening, restart the server and run copilot_health."
        ),
        # pmc_agent.graph's TERMINAL_* names, used as failure categories
        # by `_to_terminal_response`'s own generic fallback.
        "ask": "Run copilot again with a clarified intent.",
        "rejected": "Nothing was applied. Run copilot again if you would like a new plan.",
        "expired": "The plan's approval window passed. Run copilot again for a fresh plan.",
        "superseded": (
            "A newer request replaced this one. Run copilot_apply on the "
            "plan copilot most recently printed, or run copilot again."
        ),
        "cancelled": (
            "The request was cancelled; nothing was applied. Run "
            "copilot again if you still want a plan."
        ),
        "applied": "The plan was already applied. No further action is needed.",
        "apply_failed_restored": (
            "The apply failed and the session was already restored. No "
            "further action is needed."
        ),
        "rolled_back": "The session was already rolled back. No further action is needed.",
        # pmc_core.errors.CATEGORIES, forwarded unprefixed when a real
        # command failed inside the sidecar.
        CATEGORY_UNKNOWN_COLOR: (
            "The generated command names a color PyMOL does not "
            "recognize. Rephrase the intent naming a standard color."
        ),
        CATEGORY_UNKNOWN_REPRESENTATION: (
            "The generated command names a display style PyMOL does not "
            "recognize. Rephrase the intent naming a standard "
            "representation, such as sticks, cartoon, or surface."
        ),
        CATEGORY_INVALID_SELECTION_NAME: (
            "The generated command referenced a selection name PyMOL "
            "does not recognize. Run copilot again with a clearer intent."
        ),
        CATEGORY_SELECTION_SYNTAX: (
            "The generated selection expression was not valid. Run "
            "copilot again, describing the selection more explicitly."
        ),
        CATEGORY_UNKNOWN: (
            "PyMOL reported an error validating this plan. Run copilot "
            "again with a clearer intent; if it keeps happening, run "
            "copilot_health."
        ),
        # pmc_agent.inference.base.EngineFailure categories.
        "engine_unavailable": (
            "Start Lemonade, then run copilot_health to confirm it is "
            "reachable before trying again."
        ),
        "engine_timeout": (
            "The model took too long to respond. Run copilot again; if "
            "it keeps happening, run copilot_health."
        ),
        "engine_refused_grammar": (
            "The local model server rejected required output "
            "constraints. Run copilot_health; this needs a compatible "
            "engine version, not a different intent."
        ),
        "engine_unknown": (
            "The local inference engine reported an unexpected problem. "
            "Run copilot_health for details, then try again."
        ),
        # pmc_core.executor's REASON_* values, prefixed, other than
        # command_failure (reported through the error-envelope categories
        # above instead).
        **dict.fromkeys(
            EXECUTION_INFRASTRUCTURE_CATEGORIES,
            _EXECUTION_INFRASTRUCTURE_ACTION,
        ),
    }
)

#: `ACTIONS`'s own fallback for a category a newer or older server emits
#: that this build has never heard of -- never reached for any category in
#: `pmc_core.protocol.FAILURE_CATEGORIES` itself, only for a genuine
#: version skew this client cannot otherwise describe.
_DEFAULT_ACTION = (
    "Run copilot_health to check for a version mismatch, then try again."
)

#: The action for each HTTP status this transport's own failures can carry
#: (see `describe_transport`'s docstring for how a status is recognized in
#: a `TransportError`'s message). Every other status falls back to
#: `_DEFAULT_HTTP_ACTION`.
HTTP_ACTIONS: MappingProxyType[int, str] = MappingProxyType(
    {
        401: (
            "The client and server credentials do not match. Restart "
            "PyMOL and the server."
        ),
        404: (
            "The server does not support this operation, likely an old "
            "server. Restart the server, or check for an update."
        ),
        408: "The server took too long to read the request. Try again.",
        411: "The request was missing its content length. Try again.",
        413: (
            "The session is too large to send to the server. This is a "
            "fixed limit; there is no workaround for this session size."
        ),
        415: (
            "The client and server disagree about the request format. "
            "Restart PyMOL and the server."
        ),
        500: (
            "The server hit an internal error. Retry; if it keeps "
            "happening, restart the server and run copilot_health."
        ),
    }
)

#: `HTTP_ACTIONS`'s own fallback for a status code this client has never
#: seen from this server.
_DEFAULT_HTTP_ACTION = "Restart the server, then try again."

#: `describe_transport`'s own fallback for a `TransportError` that names no
#: HTTP status at all -- a refused connection, a timeout, or a malformed
#: reply.
_DEFAULT_TRANSPORT_ACTION = (
    "Check that the server is running, then try again; run copilot_health "
    "for details."
)


def _line(command: str, body: str) -> str:
    """Build one bounded `<command>: <body>` console line.

    Args:
        command: The command reporting this line, e.g. `"copilot_apply"`.
        body: The already-assembled sentence or sentences to report.

    Returns:
        One printable-ASCII line of at most `MAX_LINE_BYTES`.
    """
    return bounded(f"{command}: {body}", max_bytes=MAX_LINE_BYTES)


def describe_failure(command: str, envelope: FailureEnvelopeV1) -> str:
    """Describe a server's typed failure envelope with its own next step.

    Args:
        command: The command reporting this line.
        envelope: The server's own bounded failure. `envelope.category` is
            looked up in `ACTIONS`, falling back to `_DEFAULT_ACTION` for a
            category this build does not recognize -- never reached for a
            category actually in `FAILURE_CATEGORIES`. `envelope.message`
            is already bounded and safe to display as-is.

    Returns:
        One bounded, actionable console line.
    """
    action = ACTIONS.get(envelope.category, _DEFAULT_ACTION)
    return _line(command, f"{envelope.message}. {action}")


def describe_transport(command: str, error: BaseException) -> str:
    """Describe a transport-layer failure with its own next step.

    An HTTP status is recognized the same way `pmc_client.transport
    ._send` reports one: the fixed substring `"HTTP <code>"` inside the
    error's own message (`f"server rejected request with HTTP
    {response.status}"`). Parsing the existing message rather than adding
    a status field to `TransportError` keeps every other transport failure
    (a refused connection, a timeout, a malformed reply) going through the
    exact same call, with `_DEFAULT_TRANSPORT_ACTION` covering all of them.

    Args:
        command: The command reporting this line.
        error: The transport-layer exception (typically
            `pmc_client.transport.TransportError`).

    Returns:
        One bounded, actionable console line.
    """
    text = str(error)
    status = _http_status(text)
    action = (
        HTTP_ACTIONS.get(status, _DEFAULT_HTTP_ACTION)
        if status is not None
        else _DEFAULT_TRANSPORT_ACTION
    )
    return _line(command, f"{bounded(text)}. {action}")


def _http_status(message: str) -> int | None:
    """Extract an HTTP status code from a transport error's own message.

    Args:
        message: A `TransportError`'s own message text.

    Returns:
        The status code, if the message names one in the fixed
        `"HTTP <code>"` form; None otherwise.
    """
    marker = "HTTP "
    index = message.find(marker)
    if index == -1:
        return None
    digits = message[index + len(marker) :].split(maxsplit=1)[0]
    return int(digits) if digits.isdigit() else None


def describe_unexpected(
    command: str, error: BaseException, *, mutated_possible: bool
) -> str:
    """Describe an exception this command never expected, safely.

    Never includes `str(error)`: an exception raised from inside real
    PyMOL query APIs, or from deep inside the request graph, can carry a
    selection expression or another fragment of the plan or the user's own
    intent text -- exactly what SPECIFICATION.md:503-511's printed plan
    already shows through its own dedicated path, never through an error.

    Args:
        command: The command reporting this line.
        error: The unexpected exception. Only its type name is reported.
        mutated_possible: Whether this exception could have been raised
            after a live mutation began, so the live session's state
            cannot be assumed unchanged.

    Returns:
        One bounded, actionable console line.
    """
    state = (
        "the session may have been partially changed"
        if mutated_possible
        else "nothing was applied"
    )
    body = (
        f"internal error ({type(error).__name__}). "
        f"{state[0].upper()}{state[1:]}. "
        "Retry; if it keeps happening, run copilot_health."
    )
    return _line(command, body)
