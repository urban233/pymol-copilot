# Copyright 2026 PyMOL Copilot contributors.
"""Decontamination: drop training samples that restate a gold intent.

The spec requires that training data overlapping near-duplicate test
intents is removed. The gold set is the test split, so a training
sample is dropped when its intent is a near-duplicate of any gold
intent. Samples generated on held-out structures are already excluded
from training by the structure split; this module handles the wording.

**What counts as a near-duplicate.** Two intents are near-duplicates
when they name exactly the same entities and are worded almost the
same way. Both halves matter, and neither alone is the rule:

- The *entity signature* is the multiset of tokens naming something the
  plan acts on or with: digits, colour names, representation names,
  residue and atom names drawn from the structures, chain letters, and
  the words that choose or negate a selection (`het`, `polymer`,
  `water`, `except`, `not`).
  `colour chain A red` and `colour chain B red` differ in an entity, so
  they are different requests however similar they look.
- The *frame* is every remaining token after stopwords are removed.
  With the entities equal, the frames are compared by Jaccard
  similarity against a threshold frozen in `configs/generation/
  split.json`.

A plain character-shingle Jaccard was measured and rejected: it scored
the same `chain A` to `chain B` swap 0.56 on a short intent and 0.95 on
a long one, so no single threshold could treat an entity swap
consistently.

**What it deliberately does not catch.** A differently *worded*
request for the same thing -- `paint chain A grey` against `color chain
A grey` -- is not a near-duplicate. Rewording is what the gold set
exists to test, and a rule that dropped every training sample asking
for the same effect would be a semantic filter, not decontamination.

Every choice leans towards dropping too much rather than too little:
`and` and `or` are stopwords, so an intent differing only in its
boolean word is still a duplicate, and ties keep the first gold match
in sorted order so the record of *why* a sample went is stable.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import re
from collections import Counter
from collections.abc import Iterable
from collections.abc import Mapping
from collections.abc import Sequence
from dataclasses import dataclass

from pmc_core.plan import COLOR_ALLOWLIST
from pmc_core.plan import REPRESENTATION_ALLOWLIST
from pmc_core.snapshot import ObjectSnapshot

#: The method name `configs/generation/split.json` must declare. A
#: config naming anything else is refused rather than silently read as
#: this one.
METHOD = "entity-gated-token-jaccard"

#: British spellings folded to the American ones the templates use, so
#: the spelling of one word cannot hide a duplicate. Only words that
#: are not themselves entities: `grey` and `gray` are distinct colours
#: in PyMOL with different indices, so they are left alone.
_SPELLING = {
    "colour": "color",
    "colours": "colors",
    "coloured": "colored",
    "colouring": "coloring",
    "centre": "center",
    "centred": "centered",
}

#: Words that decide *what* is selected without naming an atom: the
#: selection-kind words and the negations. They are entities, because
#: `show the het atoms` and `show polymer atoms` select disjoint sets,
#: and `colour everything except chain A grey` asks the opposite of
#: `colour chain A grey` -- both pairs scored as duplicates when these
#: were frame words. Plurals fold to the singular.
_CONCEPT_WORDS = {
    "backbone": "backbone",
    "but": "not",
    "except": "not",
    "excluding": "not",
    "het": "het",
    "hetatm": "het",
    "hetatms": "het",
    "hetero": "het",
    "heteroatom": "het",
    "heteroatoms": "het",
    "ion": "ion",
    "ions": "ion",
    "ligand": "ligand",
    "ligands": "ligand",
    "minus": "not",
    "not": "not",
    "polymer": "polymer",
    "protein": "protein",
    "water": "water",
    "waters": "water",
    "without": "not",
}

#: Words that carry no request of their own. `and` and `or` are here on
#: purpose; see the module docstring.
STOPWORDS = frozenset(
    (
        "a",
        "all",
        "also",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "can",
        "could",
        "for",
        "from",
        "in",
        "is",
        "it",
        "its",
        "just",
        "me",
        "my",
        "now",
        "of",
        "on",
        "or",
        "please",
        "that",
        "the",
        "their",
        "them",
        "then",
        "these",
        "this",
        "those",
        "to",
        "with",
        "would",
        "you",
    )
)

#: The words after which a lone `a` is a chain letter, not an article.
_CHAIN_WORDS = frozenset(("chain", "chains"))

#: Single letters that are English words before they are chain IDs.
_WORD_LETTERS = frozenset(("a", "i"))

_COLORS = frozenset(name.casefold() for name in COLOR_ALLOWLIST)
_REPRESENTATIONS = frozenset(
    name.casefold() for name in REPRESENTATION_ALLOWLIST
)

#: Anything that is not a word character or whitespace becomes a
#: space. `\\w` keeps the underscore, so `nb_spheres` and `tv_red` stay
#: one token.
_PUNCTUATION = re.compile(r"[^\w\s]")


def structure_vocabulary(snapshots: Iterable[ObjectSnapshot]) -> frozenset[str]:
    """Collect the residue and atom names the structures actually carry.

    Read off the built structures rather than restated here, so a new
    residue name in `pmc_data.structures` becomes an entity without
    anyone remembering to add it.

    Args:
        snapshots: The structures intents may be asked about.

    Returns:
        Every residue name and atom name, casefolded.
    """
    names: set[str] = set()
    for snapshot in snapshots:
        for state in snapshot.states:
            for atom in state.atoms:
                names.add(atom.resn.casefold())
                names.add(atom.name.casefold())
    return frozenset(names)


def normalize_intent(intent: str) -> str:
    """Fold away differences that do not change what an intent asks.

    Casefolds, turns punctuation into spaces, collapses whitespace and
    folds British spellings.

    Unicode NFKC folding was left out on purpose. The only call that
    performs it is `unicodedata.normalize`, and
    `tests/contract/test_errors.py` forbids a data-pipeline module from
    calling anything named `normalize` other than
    `pmc_core.errors.normalize` -- the guard that keeps the error
    envelope identical in training and at runtime. Casefolding already
    covers what typed intents actually differ by.

    Args:
        intent: The intent text.

    Returns:
        The normalized text.
    """
    tokens = _PUNCTUATION.sub(" ", intent.casefold()).split()
    return " ".join(_SPELLING.get(token, token) for token in tokens)


def _is_entity(
    token: str, previous: str | None, vocabulary: frozenset[str]
) -> bool:
    """Say whether one normalized token names an entity.

    Args:
        token: The token.
        previous: The token before it, or None at the start.
        vocabulary: Residue and atom names, casefolded.

    Returns:
        True for a digit string, a colour, a representation, a residue
        or atom name, or a chain letter.
    """
    if token.isdigit():
        return True
    if token in _COLORS or token in _REPRESENTATIONS or token in vocabulary:
        return True
    if len(token) == 1 and token.isalpha():
        return token not in _WORD_LETTERS or previous in _CHAIN_WORDS
    return False


@dataclass(frozen=True)
class IntentParts:
    """An intent split into what it names and how it is worded.

    Attributes:
        entities: The entity tokens, as a sorted multiset.
        frame: The remaining non-stopword tokens.
    """

    entities: tuple[str, ...]
    frame: frozenset[str]


def split_intent(intent: str, vocabulary: frozenset[str]) -> IntentParts:
    """Split an intent into its entity signature and its frame.

    Args:
        intent: The intent text.
        vocabulary: Residue and atom names, casefolded.

    Returns:
        The two parts.
    """
    tokens = normalize_intent(intent).split()
    entities: list[str] = []
    frame: set[str] = set()
    previous: str | None = None
    for token in tokens:
        if token in _CONCEPT_WORDS:
            entities.append(_CONCEPT_WORDS[token])
        elif _is_entity(token, previous, vocabulary):
            entities.append(token)
        elif token not in STOPWORDS:
            frame.add(token)
        previous = token
    return IntentParts(entities=tuple(sorted(entities)), frame=frozenset(frame))


def similarity(left: IntentParts, right: IntentParts) -> float:
    """Score how nearly two intents duplicate each other.

    Args:
        left: One intent's parts.
        right: The other's.

    Returns:
        0.0 when the entity signatures differ; otherwise the Jaccard
        similarity of the frames, with two empty frames scoring 1.0.
    """
    if Counter(left.entities) != Counter(right.entities):
        return 0.0
    union = left.frame | right.frame
    if not union:
        return 1.0
    return len(left.frame & right.frame) / len(union)


@dataclass(frozen=True)
class NearDuplicate:
    """Why one training sample was dropped.

    Attributes:
        sample_id: The dropped training sample.
        gold_id: The gold item it duplicated.
        score: Their similarity.
    """

    sample_id: str
    gold_id: str
    score: float


def find_near_duplicates(
    train: Iterable[tuple[str, str]],
    gold: Iterable[tuple[str, str]],
    *,
    threshold: float,
    vocabulary: frozenset[str],
) -> dict[str, NearDuplicate]:
    """Find every training intent that near-duplicates a gold intent.

    Args:
        train: (sample_id, intent) pairs for the training candidates.
        gold: (gold_id, intent) pairs for the gold set.
        threshold: The frame similarity at or above which two intents
            with equal entities are duplicates.
        vocabulary: Residue and atom names, casefolded.

    Returns:
        For each duplicated training sample, the best-matching gold
        item. Ties keep the first gold_id in sorted order.

    Raises:
        ValueError: If threshold is outside (0, 1].
    """
    if not 0.0 < threshold <= 1.0:
        raise ValueError(f"threshold must be in (0, 1], not {threshold}")
    by_entities: dict[tuple[str, ...], list[tuple[str, IntentParts]]] = {}
    for gold_id, intent in sorted(gold):
        parts = split_intent(intent, vocabulary)
        by_entities.setdefault(parts.entities, []).append((gold_id, parts))

    found: dict[str, NearDuplicate] = {}
    for sample_id, intent in train:
        parts = split_intent(intent, vocabulary)
        best: NearDuplicate | None = None
        for gold_id, gold_parts in by_entities.get(parts.entities, ()):
            score = similarity(parts, gold_parts)
            if score >= threshold and (best is None or score > best.score):
                best = NearDuplicate(
                    sample_id=sample_id, gold_id=gold_id, score=score
                )
        if best is not None:
            found[sample_id] = best
    return found


def sensitivity(
    train: Sequence[tuple[str, str]],
    gold: Sequence[tuple[str, str]],
    *,
    thresholds: Iterable[float],
    vocabulary: frozenset[str],
) -> Mapping[str, int]:
    """Count how many training samples each threshold would drop.

    Reported beside the frozen threshold, so a reader can see how much
    the result depends on it.

    Args:
        train: (sample_id, intent) pairs for the training candidates.
        gold: (gold_id, intent) pairs for the gold set.
        thresholds: The thresholds to try.
        vocabulary: Residue and atom names, casefolded.

    Returns:
        The drop count keyed by threshold, formatted to two decimals.

    Raises:
        ValueError: If any threshold is outside (0, 1].
    """
    ordered = tuple(thresholds)
    if not ordered:
        return {}
    for threshold in ordered:
        if not 0.0 < threshold <= 1.0:
            raise ValueError(f"threshold must be in (0, 1], not {threshold}")
    # One pass at the lowest threshold records each sample's best score,
    # and a sample drops at any threshold its best score reaches, so the
    # intents are split once rather than once per threshold.
    best = find_near_duplicates(
        train, gold, threshold=min(ordered), vocabulary=vocabulary
    )
    return drop_counts(best, ordered)


def drop_counts(
    matches: Mapping[str, NearDuplicate], thresholds: Iterable[float]
) -> dict[str, int]:
    """Count how many of the matches each threshold would drop.

    Each match is a sample's best score, so a sample drops at any
    threshold its score reaches. The matches must have been found at or
    below the lowest of the thresholds, or the lower counts come out
    short.

    Args:
        matches: Each duplicated sample's best match, as
            `find_near_duplicates` returns them.
        thresholds: The thresholds to count at.

    Returns:
        The drop count keyed by threshold, formatted to two decimals.
    """
    return {
        f"{threshold:.2f}": sum(
            match.score >= threshold for match in matches.values()
        )
        for threshold in thresholds
    }
