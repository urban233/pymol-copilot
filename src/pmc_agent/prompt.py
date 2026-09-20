# Copyright 2026 PyMOL Copilot contributors.
"""The prompt-builder seam: a placeholder default, not a real prompt.

docs/master_plan.md item 13 (Martin's, ~2 days, blocked on item 5) owns
the real prompt builder: "turns a structure card plus a user intent into
the model prompt, and emits the grammar for the engine," stamping "card
version, grammar version and policy version into every prompt," with a
parity test asserting the dataset generator and the runtime call the same
code. None of that exists yet.

This module exists only so the request graph (`pmc_agent.graph`) has
something to call today: a `PROMPT_BUILDER` seam -- one callable taking a
frozen `PromptInputs` and returning a prompt string -- and a minimal
default implementation that stamps `pmc_core.card.CARD_VERSION`, the
request's own contract manifest, and the literal intent into a bounded
prompt. Building item 13's real prompt or grammar here would be work item
13 deletes; this module's only job is to give the graph a seam item 13 can
be dropped into without a graph change.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

from collections.abc import Callable
from dataclasses import dataclass

from pmc_core.card import CARD_VERSION
from pmc_core.card import render_for_runtime
from pmc_core.protocol import ContractManifestV1
from pmc_core.snapshot import ObjectSnapshot


@dataclass(frozen=True)
class PromptInputs:
    """Everything a prompt builder needs, computed once per request.

    Attributes:
        intent: The user's literal, immutable request text.
        snapshot: The canonical snapshot the structure card is rendered
            from.
        contract_manifest: The contract versions this request declared,
            stamped into the prompt so a captured prompt is reproducible
            against the exact contracts that produced it.
    """

    intent: str
    snapshot: ObjectSnapshot
    contract_manifest: ContractManifestV1


#: The prompt-builder seam `pmc_agent.graph` depends on. item 13 supplies
#: its own implementation of this same signature; the graph never changes.
type PROMPT_BUILDER = Callable[[PromptInputs], str]


def build_default_prompt(inputs: PromptInputs) -> str:
    """Build a minimal placeholder prompt: card, manifest, and intent.

    Args:
        inputs: The request's own prompt inputs.

    Returns:
        A bounded prompt string. Not the real prompt item 13 will emit --
        no grammar, no few-shot structure, no task framing -- only enough
        for the fake engine in this item's own tests to have something to
        record, and for a real engine to have something to complete
        against before item 13 lands.
    """
    manifest = inputs.contract_manifest
    return (
        f"card-version={CARD_VERSION}\n"
        f"plan-version={manifest.plan_version}\n"
        f"policy-version={manifest.policy_version}\n"
        f"snapshot-version={manifest.snapshot_version}\n"
        f"{render_for_runtime(inputs.snapshot)}"
        f"intent: {inputs.intent}\n"
    )
