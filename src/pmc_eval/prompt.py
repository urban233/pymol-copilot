# Copyright 2026 PyMOL Copilot contributors.
"""The prompt the harness sends: the training prompt, plus repair lines.

`pmc_agent.graph` builds every prompt through an injected
`PROMPT_BUILDER`, and its own default (`pmc_agent.prompt.
build_default_prompt`) is a placeholder whose bytes differ from the
prompt every dataset sample records. An evaluation that used it would
measure a model on a prompt it was never trained on. `contract_prompt`
is the builder the harness injects instead: a first attempt's prompt is
`pmc_core.prompt.build_for_runtime`'s, byte for byte the
`Sample.prompt_text` item 17 trains on, and each repair appends one line
per earlier failure, in the graph's own wording, after the intent. After
rather than before: the card is by far the longest part of the prompt
and is shared by every sample on the same structure, so keeping it a
prefix lets the engine's prompt cache reuse it across repairs.

Since item 18, `contract_prompt` delegates to the runtime's own
`pmc_agent.prompt.build_training_prompt`, so the lines it sends are
`pmc_agent.prompt._error_line`'s. `repair_line` stays here as the
versioned statement of that wording (`REPAIR_PROMPT_VERSION`):
`tests/eval/test_prompt.py` fails if the runtime's wording drifts from
it, and a deliberate change updates both and bumps the version.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import hashlib

from pmc_agent.prompt import AttemptFailure
from pmc_agent.prompt import PromptInputs
from pmc_agent.prompt import build_training_prompt
from pmc_core.snapshot import ObjectSnapshot
from pmc_core.snapshot import structure_digest
from pmc_core.snapshot import to_json
from pmc_data.sample import Sample
from pmc_data.structures import StructureSpec
from pmc_data.structures import build_structure

#: The version of the repair-prompt form `contract_prompt` renders: where
#: the failure lines go and how each is worded. A first attempt's prompt
#: is versioned by `pmc_core.prompt.PROMPT_VERSION` instead, since it is
#: exactly that module's output. Any change to `repair_line` or to where
#: its lines are placed is a bump here.
REPAIR_PROMPT_VERSION = 1


class BrokenLineageError(ValueError):
    """A sample's structure no longer rebuilds to what it was verified on."""


def repair_line(failure: AttemptFailure) -> str:
    """Render one earlier failure as one prompt line.

    Worded exactly as `pmc_agent.prompt._error_line` words it. It is not
    what `contract_prompt` sends (that is `_error_line` itself); it is the
    wording `REPAIR_PROMPT_VERSION` versions, which the tests hold the
    runtime to.

    Args:
        failure: The earlier attempt's failure evidence.

    Returns:
        One newline-terminated line naming the source, the command index
        when there is one, the category and the message.
    """
    where = (
        f"command {failure.command_index}"
        if failure.command_index is not None
        else "the whole plan"
    )
    return (
        f"previous attempt failed ({failure.source}, {where}): "
        f"{failure.category}: {failure.message}\n"
    )


def contract_prompt(inputs: PromptInputs) -> str:
    """Build the prompt for one attempt, a `PROMPT_BUILDER`.

    `inputs.contract_manifest` is not rendered: `build_for_runtime`
    stamps the prompt's own contract versions, and the graph's
    `preparing` node has already refused any request whose manifest is
    not the current one before this is ever called.

    Args:
        inputs: The request's prompt inputs, as the graph assembles them.

    Returns:
        The training prompt, followed by one `repair_line` per earlier
        failure, oldest first.
    """
    # The runtime's own builder since item 18; `repair_line` is kept here,
    # worded identically, because REPAIR_PROMPT_VERSION versions it.
    return build_training_prompt(inputs)


def snapshot_for(sample: Sample) -> ObjectSnapshot:
    """Rebuild the structure a sample was verified on, and prove it.

    Args:
        sample: The stored sample whose structure to rebuild.

    Returns:
        The rebuilt canonical snapshot.

    Raises:
        BrokenLineageError: If the rebuilt snapshot's SHA-256 or
            structure digest differs from what the sample recorded. A
            model graded against a different structure than the one its
            assertions were computed on would be graded against the
            wrong answer.
    """
    snapshot = build_structure(StructureSpec.from_dict(sample.structure.spec))
    sha256 = hashlib.sha256(to_json(snapshot).encode("utf-8")).hexdigest()
    if sha256 != sample.structure.snapshot_sha256:
        raise BrokenLineageError(
            f"{sample.sample_id}: rebuilt snapshot SHA-256 {sha256} is not "
            f"the recorded {sample.structure.snapshot_sha256}"
        )
    digest = structure_digest(snapshot)
    if digest != sample.structure.structure_digest:
        raise BrokenLineageError(
            f"{sample.sample_id}: rebuilt structure digest {digest} is not "
            f"the recorded {sample.structure.structure_digest}"
        )
    return snapshot
