# Copyright 2026 PyMOL Copilot contributors.
"""The hand-reviewed gold set: the evaluation split's intents and plans.

Master plan item 15 asks for a gold set spanning every supported
category, with natural-language intents a structural biologist would
actually type. This module is that set's record type, its loader and
the bridge that turns one record into something the item 14 pipeline
can verify.

It is not `pmc_data.gold_case`. A `GoldCase` is the legacy
chain-A/red fixture, pinned by its own drift guard to one plan and a
PDB file. A `GoldItem` carries an arbitrary plan against one of the
controlled structures `pmc_data.structures` builds, and it becomes a
`pmc_data.sample.Sample` only by passing the same oracle-and-executor
verification every generated sample passes.

Three properties are enforced here rather than trusted:

- **The category is derived, never declared.** A record has no
  category field. `to_candidate` reads it off the parsed plan with
  `pmc_data.taxonomy.categorize`, so a gold item cannot be filed under
  a category its plan does not exercise.
- **The reference plan is legal.** It must parse with
  `pmc_core.parser.parse_pml` and pass `pmc_core.policy.evaluate_plan`,
  the same two authorities every generated plan answers to.
- **Authorship is recorded.** The spec asks for human-authored domain
  intents. These were drafted by a model and then reviewed by a
  person, and each record says which model drafted it and who reviewed
  it, so the evaluation cannot quietly claim more independence than it
  has. `pmc_data.gold_cli` and `pmc_data.split_cli` refuse to run while
  any record is unreviewed.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import json
from collections.abc import Iterable
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pmc_core.parser import ParseRejection
from pmc_core.parser import parse_pml
from pmc_core.plan import ActionPlan
from pmc_core.policy import evaluate_plan
from pmc_core.prompt import MAX_INTENT_CHARACTERS
from pmc_core.prompt import MIN_INTENT_CHARACTERS
from pmc_data.taxonomy import PlanCandidate
from pmc_data.taxonomy import categorize
from pmc_data.taxonomy import difficulty_of

#: Where the committed gold set lives, beside the package it feeds.
GOLD_DIR = Path(__file__).resolve().parent / "gold"

#: The authored records, which a person edits by hand.
DEFAULT_GOLD_ITEMS_PATH = GOLD_DIR / "gold_items.jsonl"

#: The verified samples `pmc_data.gold_cli` writes from those records.
DEFAULT_GOLD_SAMPLES_PATH = GOLD_DIR / "gold_samples.jsonl"


#: The verb sets the gold set must cover: every one the corpus can
#: grade. A bare `orient` is excluded because nothing about its result
#: is checkable, which `pmc_data.generate` already reports.
REQUIRED_VERB_SETS = frozenset(
    (
        "color",
        "color+select",
        "color+select+show",
        "hide",
        "hide+select",
        "hide+show",
        "orient+select",
        "show",
    )
)

#: The verbs and term keywords whose every pairing must appear. The
#: polymer term is excluded because the snapshot format records no
#: polymer flag, so nothing about it can be graded.
REQUIRED_PAIR_VERBS = frozenset(("select", "color", "show", "hide"))
REQUIRED_PAIR_TERMS = frozenset(("chain", "resi", "resn", "name", "hetatm"))

#: The boolean shapes, as `pmc_data.taxonomy` names them, that must
#: appear.
REQUIRED_SHAPES = frozenset(
    ("single", "and", "or", "and_or", "single+not", "and+not")
)


class InvalidGoldItemError(ValueError):
    """Raised when a gold record is incomplete, illegal or contradictory."""


def _required_string(data: Mapping[str, Any], key: str) -> str:
    """Read a required non-empty string field.

    Args:
        data: The raw mapping being decoded.
        key: The required field name.

    Returns:
        The field's string value.

    Raises:
        InvalidGoldItemError: If key is absent, not a string, or empty.
    """
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise InvalidGoldItemError(f"field {key!r} must be a non-empty string")
    return value


def _optional_string(data: Mapping[str, Any], key: str) -> str | None:
    """Read a field that must be present and either a string or null.

    Present-but-null is required rather than absent-means-null: a
    record missing `reviewed_by` is more likely truncated than
    unreviewed, and the difference decides whether it may be frozen.

    Args:
        data: The raw mapping being decoded.
        key: The field name.

    Returns:
        The field's string value, or None when it is null.

    Raises:
        InvalidGoldItemError: If the field is absent, or present and
            neither a non-empty string nor null.
    """
    if key not in data:
        raise InvalidGoldItemError(f"missing required field: {key!r}")
    value = data[key]
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise InvalidGoldItemError(
            f"field {key!r} must be a non-empty string or null"
        )
    return value


def normalized_intent(intent: str) -> str:
    """Fold an intent to the form two records must not share.

    Only case and whitespace are folded. This is the duplicate check
    within the gold set, which is deliberately narrower than
    `pmc_data.decontam`'s near-duplicate rule between gold and
    training: two gold intents that differ in wording are two test
    items, not one.

    Args:
        intent: The intent text.

    Returns:
        The folded text.
    """
    return " ".join(intent.casefold().split())


@dataclass(frozen=True)
class GoldItem:
    """One authored gold record, before it is verified.

    Attributes:
        gold_id: The stable identity; becomes the verified sample's id.
        spec_id: The controlled structure this intent is asked about.
        intent: The natural-language request, as a user would type it.
        reference_pml: One correct plan for the intent. Grading in item
            16 is on the resulting state, so this is a reference, not
            the only acceptable answer.
        concept: How a domain word maps onto the plan, when it is not
            obvious -- for example "waters = resn HOH". None otherwise.
        drafted_by: Who drafted the record: a model identity or a
            person's name.
        reviewed_by: Who reviewed it, or None before review.
        reviewed: Whether review is complete.
    """

    gold_id: str
    spec_id: str
    intent: str
    reference_pml: str
    concept: str | None
    drafted_by: str
    reviewed_by: str | None
    reviewed: bool

    def __post_init__(self) -> None:
        """Reject a record whose fields contradict each other.

        Raises:
            InvalidGoldItemError: If the intent is outside the prompt's
                accepted length, or the review fields disagree -- a
                reviewed record must name its reviewer and an
                unreviewed one must not.
        """
        if not (
            MIN_INTENT_CHARACTERS <= len(self.intent) <= MAX_INTENT_CHARACTERS
        ):
            raise InvalidGoldItemError(
                f"{self.gold_id!r}: intent length {len(self.intent)} is "
                f"outside {MIN_INTENT_CHARACTERS}..{MAX_INTENT_CHARACTERS}"
            )
        if self.reviewed and self.reviewed_by is None:
            raise InvalidGoldItemError(
                f"{self.gold_id!r}: a reviewed record must name its reviewer"
            )
        if not self.reviewed and self.reviewed_by is not None:
            raise InvalidGoldItemError(
                f"{self.gold_id!r}: names reviewer {self.reviewed_by!r} "
                "but is not marked reviewed"
            )

    def to_dict(self) -> dict[str, Any]:
        """Render this record as a JSON-safe mapping.

        Returns:
            A plain dict with this record's fields.
        """
        return {
            "gold_id": self.gold_id,
            "spec_id": self.spec_id,
            "intent": self.intent,
            "reference_pml": self.reference_pml,
            "concept": self.concept,
            "drafted_by": self.drafted_by,
            "reviewed_by": self.reviewed_by,
            "reviewed": self.reviewed,
        }

    @staticmethod
    def from_dict(data: Mapping[str, Any]) -> GoldItem:
        """Decode a GoldItem, rejecting incomplete input.

        Args:
            data: The raw mapping.

        Returns:
            The decoded record.

        Raises:
            InvalidGoldItemError: If a required field is missing or
                the wrong shape.
        """
        reviewed = data.get("reviewed")
        if not isinstance(reviewed, bool):
            raise InvalidGoldItemError("field 'reviewed' must be a boolean")
        return GoldItem(
            gold_id=_required_string(data, "gold_id"),
            spec_id=_required_string(data, "spec_id"),
            intent=_required_string(data, "intent"),
            reference_pml=_required_string(data, "reference_pml"),
            concept=_optional_string(data, "concept"),
            drafted_by=_required_string(data, "drafted_by"),
            reviewed_by=_optional_string(data, "reviewed_by"),
            reviewed=reviewed,
        )


def load_gold_items(
    path: Path = DEFAULT_GOLD_ITEMS_PATH,
) -> tuple[GoldItem, ...]:
    """Read the gold set, rejecting duplicates and malformed lines.

    Args:
        path: The JSONL file to read.

    Returns:
        The records, in file order.

    Raises:
        InvalidGoldItemError: If a line is not a valid record, or two
            records share a gold_id or a normalized intent.
    """
    items: list[GoldItem] = []
    seen_ids: dict[str, int] = {}
    seen_intents: dict[str, int] = {}
    for number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        try:
            item = GoldItem.from_dict(json.loads(line))
        except json.JSONDecodeError as error:
            raise InvalidGoldItemError(
                f"{path}:{number}: line is not valid JSON"
            ) from error
        except InvalidGoldItemError as error:
            raise InvalidGoldItemError(f"{path}:{number}: {error}") from error
        if item.gold_id in seen_ids:
            raise InvalidGoldItemError(
                f"{path}:{number}: gold_id {item.gold_id!r} already used "
                f"on line {seen_ids[item.gold_id]}"
            )
        folded = normalized_intent(item.intent)
        if folded in seen_intents:
            raise InvalidGoldItemError(
                f"{path}:{number}: intent duplicates line "
                f"{seen_intents[folded]}"
            )
        seen_ids[item.gold_id] = number
        seen_intents[folded] = number
        items.append(item)
    return tuple(items)


def write_gold_items(path: Path, items: Iterable[GoldItem]) -> int:
    """Write gold records as deterministic JSONL, one per line.

    Args:
        path: The file to write.
        items: The records, in order.

    Returns:
        How many records were written.
    """
    written = 0
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for item in items:
            handle.write(
                json.dumps(item.to_dict(), ensure_ascii=False, sort_keys=True)
                + "\n"
            )
            written += 1
    return written


def reference_plan(item: GoldItem) -> ActionPlan:
    """Parse and policy-check a record's reference plan.

    Args:
        item: The gold record.

    Returns:
        The typed plan.

    Raises:
        InvalidGoldItemError: If the parser rejects the text or the
            policy denies the plan.
    """
    parsed = parse_pml(item.reference_pml)
    if isinstance(parsed, ParseRejection):
        raise InvalidGoldItemError(
            f"{item.gold_id!r}: reference plan does not parse "
            f"(command {parsed.command_index}, {parsed.category})"
        )
    decision = evaluate_plan(parsed)
    if not decision.allowed:
        denied = [d.reason for d in decision.decisions if not d.allowed]
        raise InvalidGoldItemError(
            f"{item.gold_id!r}: reference plan is denied by policy "
            f"({', '.join(denied) or 'plan shape'})"
        )
    return parsed


def to_candidate(item: GoldItem) -> PlanCandidate:
    """Turn a gold record into the candidate the pipeline verifies.

    Args:
        item: The gold record.

    Returns:
        The candidate, with its category and difficulty derived from
        the plan rather than taken from the record.

    Raises:
        InvalidGoldItemError: If the reference plan is illegal.
    """
    plan = reference_plan(item)
    return PlanCandidate(
        plan=plan,
        category=categorize(plan),
        difficulty=difficulty_of(plan),
        intent=item.intent,
    )


def coverage_gaps(categories: Iterable[str]) -> dict[str, tuple[str, ...]]:
    """Say which parts of the required surface a set of categories misses.

    A category reads `<verbs>/<terms>/<shape>`. A verb-term pair counts
    as covered when one category holds both, which is how
    `pmc_data.taxonomy.categorize` records a plan: its terms are not
    attributed to one operation, so neither is the coverage.

    Args:
        categories: The derived categories of the gold set.

    Returns:
        The missing verb sets, verb-term pairs and shapes, each sorted;
        all three empty when the surface is covered.
    """
    verb_sets: set[str] = set()
    pairs: set[str] = set()
    shapes: set[str] = set()
    for category in categories:
        verbs, terms, shape = category.split("/")
        verb_sets.add(verbs)
        shapes.add(shape)
        for verb in verbs.split("+"):
            for term in terms.split("+"):
                pairs.add(f"{verb}:{term}")
    required_pairs = {
        f"{verb}:{term}"
        for verb in REQUIRED_PAIR_VERBS
        for term in REQUIRED_PAIR_TERMS
    }
    return {
        "verb_sets": tuple(sorted(REQUIRED_VERB_SETS - verb_sets)),
        "pairs": tuple(sorted(required_pairs - pairs)),
        "shapes": tuple(sorted(REQUIRED_SHAPES - shapes)),
    }
