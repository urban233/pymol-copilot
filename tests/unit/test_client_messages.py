# Copyright 2026 PyMOL Copilot contributors.
"""Behavior tests for `pmc_client.messages`."""

from __future__ import annotations

import pytest

from pmc_client.messages import ACTIONS
from pmc_client.messages import MAX_LINE_BYTES
from pmc_client.messages import HTTP_ACTIONS
from pmc_client.messages import bounded
from pmc_client.messages import describe_failure
from pmc_client.messages import describe_transport
from pmc_client.messages import describe_unexpected
from pmc_client.transport import TransportError
from pmc_core.protocol import FAILURE_CATEGORIES
from pmc_core.protocol import FailureEnvelopeV1


def test_actions_covers_every_failure_category() -> None:
    """Every category the server may emit has a registered next step.

    Proven by hand for this item by deleting one entry from `ACTIONS` (for
    example `"hostile_output"`) and confirming this assertion names it,
    then restoring it.
    """
    missing = FAILURE_CATEGORIES - set(ACTIONS)
    assert not missing, f"ACTIONS has no entry for: {sorted(missing)}"


@pytest.mark.parametrize("category", sorted(FAILURE_CATEGORIES))
def test_every_action_is_a_non_empty_bounded_sentence(category: str) -> None:
    """Every action itself is short enough to fit inside one line."""
    action = ACTIONS[category]
    assert action
    assert len(action.encode("utf-8")) < MAX_LINE_BYTES


@pytest.mark.parametrize(
    "message",
    [
        "x" * (1024 * 1024),
        "\x00\x01control chars\x1b",
        "nön-ascii téxt",
        "",
    ],
    ids=["one_megabyte", "control_chars", "non_ascii", "empty"],
)
def test_describe_failure_stays_within_bounds_for_any_message(
    message: str,
) -> None:
    """A described failure line is always bounded and printable."""
    envelope = FailureEnvelopeV1("repair_exhausted", bounded(message), True)

    line = describe_failure("copilot", envelope)

    assert len(line.encode("utf-8")) <= MAX_LINE_BYTES
    assert line.isascii() and line.isprintable()


def test_describe_failure_names_the_categorys_own_action() -> None:
    """The category, not just the message, decides the printed action."""
    envelope = FailureEnvelopeV1(
        "expired", "the plan's TTL had already passed", True
    )

    line = describe_failure("copilot_apply", envelope)

    assert line.startswith("copilot_apply: the plan's TTL had already passed")
    assert "Run copilot again for a fresh plan" in line


def test_describe_failure_falls_back_for_an_unrecognized_category() -> None:
    """A category from a newer or older server still gets an action."""
    envelope = FailureEnvelopeV1("some_future_category", "unrecognized", True)

    line = describe_failure("copilot", envelope)

    assert "copilot_health" in line


@pytest.mark.parametrize("status", sorted(HTTP_ACTIONS))
def test_describe_transport_recognizes_every_registered_http_status(
    status: int,
) -> None:
    """Each registered HTTP status gets its own, not the generic, action."""
    error = TransportError(f"server rejected request with HTTP {status}")

    line = describe_transport("copilot", error)

    assert HTTP_ACTIONS[status] in line


def test_describe_transport_falls_back_for_a_connection_level_failure() -> None:
    """A failure naming no HTTP status gets the generic transport action."""
    error = TransportError("loopback request failed")

    line = describe_transport("copilot", error)

    assert "copilot_health" in line
    assert len(line.encode("utf-8")) <= MAX_LINE_BYTES


def test_describe_unexpected_never_contains_the_raw_exception_text() -> None:
    """An exception's own message never reaches the printed line.

    `select chain A` is plan-shaped text; if it ever leaked through, this
    is exactly the kind of fragment SPECIFICATION.md:503-511 requires stay
    confined to the printed plan block, never an error.
    """
    sentinel = "LEAK select chain A"
    error = RuntimeError(sentinel)

    line = describe_unexpected("copilot", error, mutated_possible=False)

    assert sentinel not in line
    assert "RuntimeError" in line
    assert "nothing was applied" in line.lower()


def test_describe_unexpected_names_uncertain_mutation() -> None:
    """A failure after mutation began is reported as uncertain, not clean."""
    line = describe_unexpected(
        "copilot_apply", RuntimeError("boom"), mutated_possible=True
    )

    assert "may have been partially changed" in line


def test_bounded_never_raises_for_hostile_input() -> None:
    """bounded() is total: nothing it can be given makes it raise."""
    for value in ("", "x" * 100_000, "\x00" * 10, "\U0001f600" * 50):
        result = bounded(value)
        assert result.isascii() and result.isprintable()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
