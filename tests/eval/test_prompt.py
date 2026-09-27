# Copyright 2026 PyMOL Copilot contributors.
"""The harness prompts a model exactly as it was trained to be prompted.

Item 17 trains on `Sample.prompt_text`. If the evaluation sent anything
else on a first attempt, the baseline and the fine-tune would both be
measured on a prompt neither was built for, and the comparison between
them would say nothing about the fine-tune.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import dataclasses

import pytest

from pmc_agent.prompt import AttemptFailure
from pmc_agent.prompt import PromptInputs
from pmc_agent.prompt import build_default_prompt
from pmc_core.protocol import CURRENT_CONTRACT_MANIFEST
from pmc_core.snapshot import from_json
from pmc_core.snapshot import to_json
from pmc_data.gold_set import DEFAULT_GOLD_SAMPLES_PATH
from pmc_data.sample import Sample
from pmc_data.sample import read_samples
from pmc_eval.prompt import BrokenLineageError
from pmc_eval.prompt import contract_prompt
from pmc_eval.prompt import repair_line
from pmc_eval.prompt import snapshot_for

SAMPLES = read_samples(DEFAULT_GOLD_SAMPLES_PATH)

#: One failure of each shape a repair prompt must carry: one naming a
#: command and one naming the whole plan.
FAILURES = (
    AttemptFailure(
        source="parse",
        category="unknown_verb",
        command_index=0,
        message="verb is not in the command allowlist",
    ),
    AttemptFailure(
        source="parse",
        category="alternate_whitespace",
        command_index=None,
        message="blank command lines are not accepted",
    ),
)


def _inputs(
    sample: Sample, errors: tuple[AttemptFailure, ...] = ()
) -> PromptInputs:
    """Assemble prompt inputs the way the request graph does.

    The graph hands its builder `from_json(state["snapshot_json"])`, not
    the snapshot the data pipeline held, so the round trip is part of
    what is being proved.

    Args:
        sample: The stored sample to prompt for.
        errors: Earlier failures to feed back, if any.

    Returns:
        The graph-shaped prompt inputs.
    """
    return PromptInputs(
        intent=sample.intent,
        snapshot=from_json(to_json(snapshot_for(sample))),
        contract_manifest=CURRENT_CONTRACT_MANIFEST,
        errors=errors,
    )


@pytest.mark.parametrize(
    "sample", SAMPLES, ids=[sample.sample_id for sample in SAMPLES]
)
def test_first_attempt_prompt_is_the_training_prompt(sample: Sample) -> None:
    """A first attempt sends the sample's own recorded prompt, byte for byte.

    Args:
        sample: The committed gold sample being prompted for.
    """
    assert contract_prompt(_inputs(sample)) == sample.prompt_text


def test_repair_lines_match_the_graphs_wording() -> None:
    """The failure lines are the ones the runtime's own builder renders.

    The placeholder builder puts its failure lines between the card and
    its intent line, so they are exactly what adding failures inserts.
    """
    sample = SAMPLES[0]
    without = build_default_prompt(_inputs(sample))
    with_errors = build_default_prompt(_inputs(sample, FAILURES))
    intent_line = f"intent: {sample.intent}\n"
    assert without.endswith(intent_line)
    prefix = without[: -len(intent_line)]
    assert with_errors.startswith(prefix)
    assert with_errors.endswith(intent_line)

    inserted = with_errors[len(prefix) : -len(intent_line)]

    assert inserted == "".join(repair_line(error) for error in FAILURES)


def test_repair_lines_follow_the_intent_and_keep_the_prefix() -> None:
    """A repair prompt is the first prompt with failure lines appended."""
    sample = SAMPLES[0]
    first = contract_prompt(_inputs(sample))

    repair = contract_prompt(_inputs(sample, FAILURES))

    assert first.splitlines()[-1].startswith("intent=")
    assert repair.startswith(first)
    assert repair[len(first) :] == "".join(
        repair_line(error) for error in FAILURES
    )


def test_a_changed_snapshot_is_refused() -> None:
    """A structure whose snapshot bytes no longer match is refused."""
    sample = SAMPLES[0]
    structure = dataclasses.replace(sample.structure, snapshot_sha256="0" * 64)

    with pytest.raises(BrokenLineageError, match="SHA-256"):
        snapshot_for(dataclasses.replace(sample, structure=structure))


def test_a_changed_structure_digest_is_refused() -> None:
    """A structure whose digest no longer matches is refused."""
    sample = SAMPLES[0]
    structure = dataclasses.replace(
        sample.structure, structure_digest="sha256:" + "0" * 64
    )

    with pytest.raises(BrokenLineageError, match="structure digest"):
        snapshot_for(dataclasses.replace(sample, structure=structure))


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
