# Copyright 2026 PyMOL Copilot contributors.
"""The gold record schema, and the gold set committed against it.

The schema half is settled on synthetic records: a record round-trips,
an incomplete one is refused, and a reference plan the parser or the
policy rejects never becomes a candidate. The committed half checks the
real `gold/gold_items.jsonl`: that it covers the whole supported
surface, sits only on held-out structures, and never asks for a
selection that matches nothing.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import json
from pathlib import Path

import pytest

from oracle_executor import mismatch_report
from oracle_executor import oracle_report
from pmc_core.executor import REASON_FIDELITY_MISMATCH
from pmc_core.plan import ActionPlan
from pmc_core.plan import SelectionExpression
from pmc_core.plan import SelectOperation
from pmc_core.policy import PlanDecision
from pmc_core.policy import PolicyDecision
from pmc_data import gold_cli
from pmc_data import gold_set
from pmc_data.gold_set import DEFAULT_GOLD_ITEMS_PATH
from pmc_data.gold_set import GoldItem
from pmc_data.gold_set import GoldVerificationError
from pmc_data.gold_set import InvalidGoldItemError
from pmc_data.gold_set import load_gold_items
from pmc_data.gold_set import coverage_gaps
from pmc_data.gold_set import to_candidate
from pmc_data.gold_set import verify_gold
from pmc_data.gold_set import write_gold_items
from pmc_data.oracle import UNSUPPORTED_CAMERA_VIEW
from pmc_data.oracle import apply_plan
from pmc_data.oracle import selected_serials
from pmc_data.sample import read_samples
from pmc_data.split import HELD_OUT_SPEC_IDS
from pmc_data.structures import build_structure
from pmc_data.structures import enumerate_structures

#: The corpus seed, from configs/generation/corpus.json.
SEED = 20260921

SPECS = {spec.spec_id: spec for spec in enumerate_structures(SEED)}


def _item(**overrides: object) -> GoldItem:
    """Build a valid unreviewed gold record, with fields overridden.

    Args:
        **overrides: Fields to replace.

    Returns:
        The record.
    """
    fields: dict[str, object] = {
        "gold_id": "gold_probe",
        "spec_id": "two_chains_hetatm",
        "intent": "make the zinc ions magenta",
        "reference_pml": "color magenta, resn ZN\n",
        "concept": "zinc ions = resn ZN",
        "drafted_by": "claude-opus-5-5",
        "reviewed_by": None,
        "reviewed": False,
    }
    fields.update(overrides)
    return GoldItem(**fields)  # pyrefly: ignore[bad-argument-type]


REQUIRED_KEYS = tuple(_item().to_dict())


def test_round_trip_preserves_every_field(tmp_path: Path) -> None:
    """A record written and read back is the same record."""
    reviewed = _item(
        gold_id="gold_b",
        intent="show the zinc ions as dots",
        reference_pml="show dots, resn ZN\n",
        concept=None,
        reviewed=True,
        reviewed_by="martin",
    )
    items = (_item(), reviewed)
    path = tmp_path / "gold.jsonl"

    write_gold_items(path, items)

    assert load_gold_items(path) == items


@pytest.mark.parametrize("key", REQUIRED_KEYS)
def test_missing_required_field_is_rejected(key: str) -> None:
    """No field may be left out, not even the ones allowed to be null.

    Args:
        key: The field to drop.
    """
    data = _item().to_dict()
    del data[key]

    with pytest.raises(InvalidGoldItemError):
        GoldItem.from_dict(data)


def test_review_fields_must_agree() -> None:
    """A reviewer without the flag, or the flag without a reviewer, is refused."""
    with pytest.raises(InvalidGoldItemError, match="must name its reviewer"):
        _item(reviewed=True, reviewed_by=None)
    with pytest.raises(InvalidGoldItemError, match="not marked reviewed"):
        _item(reviewed=False, reviewed_by="martin")


def test_duplicate_intents_are_rejected(tmp_path: Path) -> None:
    """Two records differing only in case and spacing are one test item."""
    path = tmp_path / "gold.jsonl"
    write_gold_items(
        path,
        (
            _item(gold_id="gold_a"),
            _item(gold_id="gold_b", intent="Make  the ZINC ions magenta"),
        ),
    )

    with pytest.raises(InvalidGoldItemError, match="duplicates line 1"):
        load_gold_items(path)


def test_duplicate_ids_are_rejected(tmp_path: Path) -> None:
    """A gold_id is an identity, so it may appear once."""
    path = tmp_path / "gold.jsonl"
    write_gold_items(
        path, (_item(), _item(intent="colour the zinc ions magenta"))
    )

    with pytest.raises(InvalidGoldItemError, match="already used"):
        load_gold_items(path)


@pytest.mark.parametrize(
    "text",
    [
        "colour magenta, resn ZN\n",
        "load x.pdb\n",
        "color red\n",
        "color red, copilot_missing\n",
    ],
)
def test_unparseable_reference_is_rejected(text: str) -> None:
    """Text the parser refuses never becomes a candidate.

    Args:
        text: A reference plan outside the restricted language.
    """
    with pytest.raises(InvalidGoldItemError, match="does not parse"):
        to_candidate(_item(reference_pml=text))


def test_denied_reference_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """The policy's verdict is consulted, not assumed from the parse.

    The parser and `ActionPlan` itself already refuse every plan-shape
    violation, so no `.pml` text reaches a policy denial today. The
    policy is the independent second authority all the same, so this
    replaces its verdict with a denial and proves the gold path obeys
    it rather than trusting that parsing was enough.

    Args:
        monkeypatch: Replaces the policy the module calls.
    """
    denial = PlanDecision(
        decisions=(
            PolicyDecision(
                operation_index=0,
                allowed=False,
                reason="unsupported_color_arguments",
            ),
        ),
        allowed=False,
    )
    monkeypatch.setattr(gold_set, "evaluate_plan", lambda _plan: denial)

    with pytest.raises(
        InvalidGoldItemError, match=r"denied by policy.*unsupported_color"
    ):
        to_candidate(_item())


def test_category_is_derived_from_the_plan() -> None:
    """The category comes from the plan, because a record cannot declare one."""
    candidate = to_candidate(
        _item(
            reference_pml=(
                "select copilot_zinc, resn ZN\ncolor magenta, copilot_zinc\n"
            )
        )
    )

    assert "category" not in _item().to_dict()
    assert candidate.category == "color+select/resn/single"
    assert candidate.intent == "make the zinc ions magenta"


def test_a_record_file_line_is_named_in_errors(tmp_path: Path) -> None:
    """A malformed line is reported by file and line."""
    path = tmp_path / "gold.jsonl"
    good = json.dumps(_item().to_dict())
    path.write_text(good + "\n{not json\n", encoding="utf-8")

    with pytest.raises(InvalidGoldItemError, match=r"gold\.jsonl:2"):
        load_gold_items(path)


COMMITTED = load_gold_items(DEFAULT_GOLD_ITEMS_PATH)


def _expressions(plan: ActionPlan) -> tuple[SelectionExpression, ...]:
    """Collect every selection expression a plan evaluates.

    Args:
        plan: The plan to inspect.

    Returns:
        The expressions, in operation order.
    """
    found: list[SelectionExpression] = []
    for operation in plan.operations:
        if isinstance(operation, SelectOperation):
            found.append(operation.expression)
            continue
        target = getattr(operation, "target", None)
        if isinstance(target, SelectionExpression):
            found.append(target)
    return tuple(found)


def test_gold_covers_the_supported_surface() -> None:
    """Every verb set, verb-term pair and shape appears in the gold set."""
    gaps = coverage_gaps(to_candidate(item).category for item in COMMITTED)

    assert gaps == {"verb_sets": (), "pairs": (), "shapes": ()}


def test_coverage_gaps_names_what_is_missing() -> None:
    """The coverage check can fail, and says what failed."""
    gaps = coverage_gaps(["color/chain/single"])

    assert "show" in gaps["verb_sets"]
    assert "hide:resn" in gaps["pairs"]
    assert "and_or" in gaps["shapes"]
    assert "color:chain" not in gaps["pairs"]


def test_gold_is_on_held_out_structures_only() -> None:
    """No gold item is asked about a structure training may see."""
    assert {item.spec_id for item in COMMITTED} <= HELD_OUT_SPEC_IDS


@pytest.mark.parametrize(
    "item", COMMITTED, ids=[item.gold_id for item in COMMITTED]
)
def test_every_reference_resolves(item: GoldItem) -> None:
    """Every reference plan selects something and changes something.

    A selection matching no atom, or a plan whose predicted result is
    the structure it started from, is graded by comparing a structure
    against itself -- which any answer passes. An orienting plan is
    the one exception to the second rule: its effect is on the camera,
    which the oracle declines to predict, and it is graded on its
    selection counts instead.

    Args:
        item: The committed gold record.
    """
    candidate = to_candidate(item)
    snapshot = build_structure(SPECS[item.spec_id])

    for expression in _expressions(candidate.plan):
        assert selected_serials(snapshot, expression), expression.render()

    expected = apply_plan(snapshot, candidate.plan)
    assert set(expected.unsupported) <= {UNSUPPORTED_CAMERA_VIEW}
    if expected.snapshot is None:
        assert expected.selection_counts
    else:
        assert expected.snapshot != snapshot


def test_a_verified_gold_item_keeps_its_gold_id() -> None:
    """A clean run becomes a sample named for the gold item."""
    items = (
        _item(),
        _item(
            gold_id="gold_second",
            intent="colour zinc red",
            reference_pml="color red, resn ZN\n",
        ),
    )

    samples = verify_gold(items, seed=SEED, executor=oracle_report)

    assert [s.sample_id for s in samples] == ["gold_probe", "gold_second"]
    assert samples[0].intent == "make the zinc ions magenta"
    assert samples[0].structure.spec_id == "two_chains_hetatm"


def test_a_rejected_gold_item_is_an_error() -> None:
    """A gold label real PyMOL disagrees with stops the run; it is not dropped."""
    with pytest.raises(GoldVerificationError, match="gold_probe") as raised:
        verify_gold((_item(),), seed=SEED, executor=mismatch_report)

    assert [r.reason for r in raised.value.rejections] == [
        REASON_FIDELITY_MISMATCH
    ]


def test_an_unknown_spec_is_an_error() -> None:
    """A gold item must name a structure the matrix actually builds."""
    with pytest.raises(InvalidGoldItemError, match="unknown structure"):
        verify_gold(
            (_item(spec_id="no_such_spec"),),
            seed=SEED,
            executor=oracle_report,
        )


def test_gold_cli_refuses_an_unreviewed_set(tmp_path: Path) -> None:
    """No gold sample is written for a label nobody signed off."""
    items = tmp_path / "gold_items.jsonl"
    out = tmp_path / "gold_samples.jsonl"
    write_gold_items(items, (_item(),))

    code = gold_cli.run(["--items", str(items), "--out", str(out)])

    assert code == 1
    assert not out.exists()


def test_gold_cli_writes_a_reviewed_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A reviewed set that verifies is written whole.

    Args:
        tmp_path: Scratch directory.
        monkeypatch: Replaces the executor with the oracle stand-in.
    """
    items = tmp_path / "gold_items.jsonl"
    out = tmp_path / "gold_samples.jsonl"
    write_gold_items(items, (_item(reviewed=True, reviewed_by="martin"),))
    real_verify = gold_set.verify_gold
    monkeypatch.setattr(
        gold_cli,
        "verify_gold",
        lambda found, **kwargs: real_verify(
            found, seed=kwargs["seed"], executor=oracle_report
        ),
    )

    code = gold_cli.run(["--items", str(items), "--out", str(out)])

    assert code == 0
    assert [s.sample_id for s in read_samples(out)] == ["gold_probe"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
