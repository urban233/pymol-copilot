# Copyright 2026 PyMOL Copilot contributors.
"""The label audit: a fair draw, a complete sheet, an honest number.

The draw must be reproducible and must never reach beyond the training
split. The score must refuse a half-filled sheet, keep `unsure` out of
both counts, and get the interval right against values computed
independently of `pmc_data.audit`.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import json
from collections.abc import Sequence
from pathlib import Path

import pytest

from split_fixture import AUDIT_SIZE
from split_fixture import GIT_CLEAN
from split_fixture import Repo
from split_fixture import make_repo
from pmc_data import split_cli
from pmc_data.audit import VERDICT_CORRECT
from pmc_data.audit import VERDICT_UNSURE
from pmc_data.audit import VERDICT_WRONG
from pmc_data.audit import InvalidAuditError
from pmc_data.audit import draw
from pmc_data.audit import score
from pmc_data.audit import wilson_interval
from pmc_data.manifest import InvalidManifestError
from pmc_data.manifest import validate_manifest
from pmc_data.sample import read_samples


@pytest.fixture
def built(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Repo, Path]:
    """Build a fixture split.

    Args:
        tmp_path: Scratch directory.
        monkeypatch: Re-roots the binary.

    Returns:
        The fixture repository and its split directory.
    """
    repo = make_repo(tmp_path)
    monkeypatch.setattr(split_cli, "REPO_ROOT", tmp_path)
    assert (
        split_cli.run(["build", "--corpus", str(repo.corpus)], git=GIT_CLEAN)
        == 0
    )
    (split,) = repo.out.glob("split-*")
    return repo, split


def _fill(split: Path, verdicts: Sequence[str | None]) -> None:
    """Write verdicts into a drawn sheet, in order.

    Args:
        split: The split directory.
        verdicts: One verdict per sheet row.
    """
    path = split / "audit" / "sheet.jsonl"
    rows = [json.loads(line) for line in path.read_text("utf-8").splitlines()]
    for row, verdict in zip(rows, verdicts, strict=True):
        row["verdict"] = verdict
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_draw_is_seeded_and_train_only(built: tuple[Repo, Path]) -> None:
    """The same seed re-draws the same labels, all from training."""
    _, split = built
    train = read_samples(split / "train.jsonl")
    others = {
        s.sample_id
        for name in ("test_gold.jsonl", "heldout_synthetic.jsonl")
        for s in read_samples(split / name)
    }

    first = [s.sample_id for s in draw(train, size=AUDIT_SIZE, seed=7)]
    again = [
        s.sample_id
        for s in draw(tuple(reversed(train)), size=AUDIT_SIZE, seed=7)
    ]
    other = [s.sample_id for s in draw(train, size=AUDIT_SIZE, seed=8)]

    assert first == again
    assert first != other
    assert len(set(first)) == AUDIT_SIZE
    assert set(first) <= {s.sample_id for s in train}
    assert not set(first) & others


def test_the_cli_draws_what_the_manifest_records(
    built: tuple[Repo, Path],
) -> None:
    """`audit draw` writes the draw the manifest's audit plan implies."""
    _, split = built
    assert split_cli.run(["audit", "draw", "--split", str(split)]) == 0

    rows = [
        json.loads(line)
        for line in (split / "audit" / "sheet.jsonl")
        .read_text("utf-8")
        .splitlines()
    ]
    expected = draw(
        read_samples(split / "train.jsonl"), size=AUDIT_SIZE, seed=7
    )

    assert [row["sample_id"] for row in rows] == [s.sample_id for s in expected]
    assert all(row["verdict"] is None for row in rows)
    assert "chain" in rows[0]["structure"]
    assert all(isinstance(row["not_checked"], list) for row in rows)
    assert (split / "audit" / "sheet.md").is_file()


def test_draw_refuses_to_overwrite_a_sheet(built: tuple[Repo, Path]) -> None:
    """A second draw never clobbers verdicts already written."""
    _, split = built
    assert split_cli.run(["audit", "draw", "--split", str(split)]) == 0
    _fill(split, [VERDICT_CORRECT] * AUDIT_SIZE)

    assert split_cli.run(["audit", "draw", "--split", str(split)]) == 1
    assert '"correct"' in (split / "audit" / "sheet.jsonl").read_text("utf-8")


def test_score_refuses_an_incomplete_sheet(built: tuple[Repo, Path]) -> None:
    """A half-judged sheet would silently become a smaller sample."""
    _, split = built
    assert split_cli.run(["audit", "draw", "--split", str(split)]) == 0
    _fill(split, [VERDICT_CORRECT] * (AUDIT_SIZE - 1) + [None])

    assert (
        split_cli.run(
            ["audit", "score", "--split", str(split), "--auditor", "martin"]
        )
        == 1
    )
    assert not (split / "audit" / "result.json").exists()


def test_a_blank_verdict_is_named_as_blank() -> None:
    """A blank is refused as unfinished, not mistaken for a bad verdict."""
    rows = [
        {"sample_id": "a", "verdict": VERDICT_CORRECT},
        {"sample_id": "b", "verdict": None},
    ]

    with pytest.raises(InvalidAuditError, match="1 verdicts are blank: b"):
        score(rows, drawn_ids=["a", "b"])


def test_score_refuses_a_sheet_that_is_not_the_draw() -> None:
    """Swapping a hard label for an easy one is refused, not scored."""
    rows = [{"sample_id": "a", "verdict": VERDICT_CORRECT}]

    with pytest.raises(InvalidAuditError, match="differ from the draw"):
        score(rows, drawn_ids=["b"])


def test_unsure_is_reported_not_counted() -> None:
    """`unsure` is neither correct nor wrong; the worst case is shown beside."""
    rows = [
        {"sample_id": "a", "verdict": VERDICT_WRONG},
        {"sample_id": "b", "verdict": VERDICT_CORRECT},
        {"sample_id": "c", "verdict": VERDICT_CORRECT},
        {"sample_id": "d", "verdict": VERDICT_UNSURE},
    ]

    result = score(rows, drawn_ids=["a", "b", "c", "d"])

    assert (result.wrong, result.correct, result.unsure) == (1, 2, 1)
    assert result.judged == 3
    assert result.error_rate == pytest.approx(1 / 3)
    assert result.worst_case_rate == pytest.approx(2 / 4)


def test_an_unknown_verdict_is_refused() -> None:
    """Only the three verdicts exist."""
    with pytest.raises(InvalidAuditError, match="must be one of"):
        score([{"sample_id": "a", "verdict": "fine"}], drawn_ids=["a"])


@pytest.mark.parametrize(
    ("wrong", "total", "low", "high"),
    [
        # Computed independently with statistics.NormalDist's 97.5% quantile.
        (0, 50, 0.0, 0.0713476),
        (3, 50, 0.0206150, 0.1621709),
        (50, 50, 0.9286524, 1.0),
    ],
)
def test_wilson_interval_known_values(
    wrong: int, total: int, low: float, high: float
) -> None:
    """The interval matches independently computed values.

    Args:
        wrong: Labels judged wrong.
        total: Labels judged.
        low: The expected lower bound.
        high: The expected upper bound.
    """
    assert wilson_interval(wrong, total) == pytest.approx((low, high), abs=1e-6)


def test_score_is_recorded_and_the_sheet_is_pinned(
    built: tuple[Repo, Path],
) -> None:
    """The result lands in the manifest and datasheet; a later edit is caught."""
    repo, split = built
    assert split_cli.run(["audit", "draw", "--split", str(split)]) == 0
    _fill(split, [VERDICT_WRONG] + [VERDICT_CORRECT] * (AUDIT_SIZE - 1))

    assert (
        split_cli.run(
            ["audit", "score", "--split", str(split), "--auditor", "martin"]
        )
        == 0
    )
    manifest = validate_manifest(split)
    assert manifest["audit"]["wrong"] == 1
    assert manifest["audit"]["judged"] == AUDIT_SIZE
    assert manifest["audit"]["auditor"] == "martin"
    datasheet = (repo.docs / "DATASHEET.md").read_text("utf-8")
    assert f"Observed error rate: 1/{AUDIT_SIZE}" in datasheet
    assert (repo.docs / "audit" / "sheet.jsonl").is_file()

    _fill(split, [VERDICT_CORRECT] * AUDIT_SIZE)
    with pytest.raises(InvalidManifestError, match="audit sheet"):
        validate_manifest(split)


def test_score_refuses_without_a_sheet(built: tuple[Repo, Path]) -> None:
    """Scoring before drawing is a refusal, not a traceback."""
    _, split = built

    assert (
        split_cli.run(
            ["audit", "score", "--split", str(split), "--auditor", "martin"]
        )
        == 1
    )


def test_score_refuses_an_already_audited_split(
    built: tuple[Repo, Path],
) -> None:
    """A second score never overwrites the recorded audit."""
    repo, split = built
    assert split_cli.run(["audit", "draw", "--split", str(split)]) == 0
    _fill(split, [VERDICT_CORRECT] * AUDIT_SIZE)
    first = ["audit", "score", "--split", str(split), "--auditor", "martin"]
    assert split_cli.run(first) == 0
    recorded = (split / "audit" / "result.json").read_bytes()

    again = ["audit", "score", "--split", str(split), "--auditor", "other"]
    assert split_cli.run(again) == 1
    assert (split / "audit" / "result.json").read_bytes() == recorded
    assert (repo.docs / "audit" / "result.json").read_bytes() == recorded


def test_score_refuses_to_overwrite_another_splits_record(
    built: tuple[Repo, Path],
) -> None:
    """Scoring a split that docs does not describe leaves docs alone."""
    repo, split = built
    assert split_cli.run(["audit", "draw", "--split", str(split)]) == 0
    _fill(split, [VERDICT_CORRECT] * AUDIT_SIZE)
    published = repo.docs / "manifest.json"
    manifest = json.loads(published.read_text("utf-8"))
    manifest["split_id"] = "0" * 16
    published.write_text(json.dumps(manifest), encoding="utf-8")

    assert (
        split_cli.run(
            ["audit", "score", "--split", str(split), "--auditor", "martin"]
        )
        == 1
    )
    assert not (split / "audit" / "result.json").exists()
    assert not (repo.docs / "audit").exists()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
