# Copyright 2026 PyMOL Copilot contributors.
"""The runtime can send the prompt the local model was fine-tuned on.

`pmc_agent.prompt.build_training_prompt` is the prompt builder that
`pmc_server.main --prompt training` selects (master plan item 18). It
must be, byte for byte, the `prompt_text` every dataset sample holds and
the fine-tune learned from, and a repair must be worded as the graph's
own placeholder words it.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import pytest

from pmc_agent.prompt import AttemptFailure
from pmc_agent.prompt import PromptInputs
from pmc_agent.prompt import _error_line
from pmc_agent.prompt import build_training_prompt
from pmc_core.protocol import CURRENT_CONTRACT_MANIFEST
from pmc_data.gold_set import DEFAULT_GOLD_SAMPLES_PATH
from pmc_data.sample import read_samples
from pmc_data.structures import StructureSpec
from pmc_data.structures import build_structure

SAMPLES = read_samples(DEFAULT_GOLD_SAMPLES_PATH)

FAILURES = (
    AttemptFailure(
        source="parser",
        category="unknown_verb",
        message="make is not a supported verb",
        command_index=0,
    ),
    AttemptFailure(
        source="sidecar",
        category="empty_selection",
        message="no atoms matched",
        command_index=None,
    ),
)


def _inputs(
    index: int, errors: tuple[AttemptFailure, ...] = ()
) -> PromptInputs:
    """Build the prompt inputs for one gold sample.

    Args:
        index: The gold sample's position.
        errors: Earlier failures to report.

    Returns:
        The inputs the graph would assemble for it.
    """
    sample = SAMPLES[index]
    return PromptInputs(
        intent=sample.intent,
        snapshot=build_structure(
            StructureSpec.from_dict(sample.structure.spec)
        ),
        contract_manifest=CURRENT_CONTRACT_MANIFEST,
        errors=errors,
    )


@pytest.mark.parametrize("index", [0, 27, 60])
def test_a_first_attempt_is_the_training_prompt(index: int) -> None:
    """With no earlier failure, the prompt is the sample's own prompt."""
    assert build_training_prompt(_inputs(index)) == SAMPLES[index].prompt_text


def test_a_repair_appends_the_graphs_own_failure_lines() -> None:
    """Earlier failures follow the intent, oldest first, as the graph words them."""
    first = build_training_prompt(_inputs(0))
    repaired = build_training_prompt(_inputs(0, FAILURES))
    assert repaired.startswith(first)
    assert repaired[len(first) :] == "".join(_error_line(e) for e in FAILURES)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
