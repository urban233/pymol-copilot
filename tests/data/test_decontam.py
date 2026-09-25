# Copyright 2026 PyMOL Copilot contributors.
"""The near-duplicate rule, pinned against hand-labelled pairs.

`testdata/near_duplicate_pairs.jsonl` records, for each pair of
intents, whether they are near-duplicates and why. It is reviewed by a
person together with the gold set, because it is the definition of the
rule in examples: a change to the normalizer, the stopwords or the
threshold that flips a label fails here, and has to be argued for.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import json
from pathlib import Path

import pytest

from pmc_data.decontam import METHOD
from pmc_data.decontam import find_near_duplicates
from pmc_data.decontam import normalize_intent
from pmc_data.decontam import sensitivity
from pmc_data.decontam import similarity
from pmc_data.decontam import split_intent
from pmc_data.decontam import structure_vocabulary
from pmc_data.split import InvalidSplitConfigError
from pmc_data.split import load_split_config
from pmc_data.structures import build_structure
from pmc_data.structures import enumerate_structures

HERE = Path(__file__).resolve().parent
PAIRS_PATH = HERE / "testdata" / "near_duplicate_pairs.jsonl"
CONFIG_PATH = (
    Path(__file__).resolve().parents[2]
    / "configs"
    / "generation"
    / "split.json"
)

CONFIG = load_split_config(CONFIG_PATH)
VOCABULARY = structure_vocabulary(
    build_structure(spec) for spec in enumerate_structures(CONFIG.seed)
)
PAIRS = tuple(
    json.loads(line)
    for line in PAIRS_PATH.read_text(encoding="utf-8").splitlines()
    if line
)


@pytest.mark.parametrize(
    "pair", PAIRS, ids=[f"{i:02d}" for i in range(len(PAIRS))]
)
def test_labelled_pairs(pair: dict[str, object]) -> None:
    """Each labelled pair is judged the way its label says, both ways round.

    Args:
        pair: One labelled pair from the fixture.
    """
    left = split_intent(str(pair["left"]), VOCABULARY)
    right = split_intent(str(pair["right"]), VOCABULARY)
    threshold = CONFIG.decontam_threshold

    assert (similarity(left, right) >= threshold) is pair["duplicate"], pair[
        "why"
    ]
    assert similarity(left, right) == similarity(right, left)


@pytest.mark.parametrize(
    ("plain", "padded"),
    [
        ("Show chain A as cartoon.", "Please show chain A as the cartoon now."),
        ("color chain B red", "could you color all of chain B in red for me"),
    ],
)
def test_filler_words_leave_the_frame_unchanged(
    plain: str, padded: str
) -> None:
    """Stopwords are removed exactly, not merely diluted below the threshold.

    Args:
        plain: An intent without filler.
        padded: The same intent with only stopwords added.
    """
    assert split_intent(plain, VOCABULARY) == split_intent(padded, VOCABULARY)


def test_the_fixture_holds_both_labels() -> None:
    """A fixture of one label could not catch a rule that flipped the other."""
    labels = [pair["duplicate"] for pair in PAIRS]

    assert labels.count(True) >= 5
    assert labels.count(False) >= 5


def test_threshold_is_read_from_config() -> None:
    """The threshold in force is the frozen one, under the implemented method."""
    assert CONFIG.decontam_method == METHOD
    assert CONFIG.decontam_threshold == 0.5


def test_an_unknown_method_is_refused(tmp_path: Path) -> None:
    """A config naming a rule this code does not implement is not read as this one."""
    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    data["decontam"]["method"] = "char-shingle-jaccard"
    path = tmp_path / "split.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(InvalidSplitConfigError, match="unknown"):
        load_split_config(path)


def test_the_frozen_config_excludes_slice() -> None:
    """Every slice sample is dropped, and the config says why."""
    assert CONFIG.excluded_representations == ("slice",)
    assert CONFIG.exclusion_reason


@pytest.mark.parametrize(
    ("exclude", "match"),
    [
        ({"representations": ["splice"], "reason": "x"}, "unknown"),
        ({"representations": ["slice"]}, "reason"),
        ({"representations": "slice", "reason": "x"}, "list"),
    ],
)
def test_a_malformed_exclusion_is_refused(
    tmp_path: Path, exclude: dict[str, object], match: str
) -> None:
    """An exclusion must name real representations and give its reason.

    Args:
        tmp_path: Scratch directory.
        exclude: The malformed exclude section.
        match: What the refusal must mention.
    """
    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    data["exclude"] = exclude
    path = tmp_path / "split.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(InvalidSplitConfigError, match=match):
        load_split_config(path)


def test_normalization_folds_only_what_it_claims() -> None:
    """Case, punctuation, spacing and British spelling fold; nothing else."""
    assert normalize_intent("  Colour Chain-A, RED!  ") == "color chain a red"
    assert normalize_intent("show nb_spheres") == "show nb_spheres"
    assert normalize_intent("grey") != normalize_intent("gray")


def test_chain_a_is_an_entity_but_the_article_is_not() -> None:
    """A lone `a` is a chain letter after `chain`, and an article otherwise."""
    assert split_intent("colour chain a red", VOCABULARY).entities == (
        "a",
        "red",
    )
    assert split_intent("make a sphere of it", VOCABULARY).entities == ()


def test_find_keeps_the_best_match_and_names_it() -> None:
    """A dropped sample records which gold item it duplicated, and how closely."""
    found = find_near_duplicates(
        [("train_1", "Color chain A red."), ("train_2", "Color chain B red.")],
        [
            ("gold_b", "colour chain A red please"),
            ("gold_a", "Color chain A red"),
        ],
        threshold=0.5,
        vocabulary=VOCABULARY,
    )

    assert set(found) == {"train_1"}
    assert found["train_1"].gold_id == "gold_a"
    assert found["train_1"].score == 1.0


def test_sensitivity_is_monotone() -> None:
    """A stricter threshold never drops more."""
    train = [(f"t{i}", pair["left"]) for i, pair in enumerate(PAIRS)]
    gold = [(f"g{i}", pair["right"]) for i, pair in enumerate(PAIRS)]

    counts = sensitivity(
        train, gold, thresholds=(0.3, 0.5, 0.7, 1.0), vocabulary=VOCABULARY
    )

    assert counts["0.30"] >= counts["0.50"] >= counts["0.70"] >= counts["1.00"]


def test_a_threshold_outside_the_unit_interval_is_refused() -> None:
    """Zero would match every pair with equal entities; above one, none."""
    with pytest.raises(ValueError, match="threshold"):
        find_near_duplicates([], [], threshold=0.0, vocabulary=VOCABULARY)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
