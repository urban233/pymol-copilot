# Copyright 2026 PyMOL Copilot contributors.
"""The split build: no leak, no loss, and a refusal for every bad input.

Driven end to end through `split_cli.run` on the synthetic repository
`split_fixture` writes, so what is tested is the binary a person runs,
not a helper beside it. No PyMOL child is spawned.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import dataclasses
import filecmp
import json
from pathlib import Path

import pytest

from split_fixture import GIT_CLEAN
from split_fixture import HELD_OUT_SPECS
from split_fixture import Repo
from split_fixture import make_repo
from pmc_data import split_cli
from pmc_data.gold_set import load_gold_items
from pmc_data.gold_set import write_gold_items
from pmc_data.manifest import DATA_FILES
from pmc_data.sample import read_samples
from pmc_data.split import HELD_OUT_SPEC_IDS
from pmc_data.split import uses_representation


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Repo:
    """Write a synthetic repository and point the binary at it.

    Args:
        tmp_path: Scratch directory.
        monkeypatch: Re-roots the binary.

    Returns:
        The fixture repository.
    """
    made = make_repo(tmp_path)
    monkeypatch.setattr(split_cli, "REPO_ROOT", tmp_path)
    return made


def _build(repo: Repo, *extra: str, git: tuple[str, bool] = GIT_CLEAN) -> int:
    """Run `split_cli build` against the fixture corpus.

    Args:
        repo: The fixture repository.
        *extra: Further arguments.
        git: The commit and dirty flag to record.

    Returns:
        The exit code.
    """
    return split_cli.run(
        ["build", "--corpus", str(repo.corpus), *extra], git=git
    )


def _only_split(out: Path) -> Path:
    """Find the one split directory a build wrote.

    Args:
        out: The splits directory.

    Returns:
        The split directory.
    """
    (found,) = [p for p in out.iterdir() if p.name.startswith("split-")]
    return found


def test_no_test_structure_reaches_train(repo: Repo) -> None:
    """Training holds no held-out spec, structure hash or digest."""
    assert _build(repo) == 0
    split = _only_split(repo.out)
    train = read_samples(split / "train.jsonl")
    held = read_samples(split / "heldout_synthetic.jsonl") + read_samples(
        split / "test_gold.jsonl"
    )

    assert train
    assert not {s.structure.spec_id for s in train} & HELD_OUT_SPEC_IDS
    assert not {s.structure.snapshot_sha256 for s in train} & {
        s.structure.snapshot_sha256 for s in held
    }
    assert not {s.structure.structure_digest for s in train} & {
        s.structure.structure_digest for s in held
    }
    assert {s.structure.spec_id for s in held} == set(HELD_OUT_SPECS)


def test_every_corpus_sample_lands_exactly_once(repo: Repo) -> None:
    """Train, held-out and dropped partition the corpus: nothing lost or doubled."""
    assert _build(repo) == 0
    split = _only_split(repo.out)
    corpus = [s.sample_id for s in read_samples(repo.corpus / "samples.jsonl")]
    dropped = [
        json.loads(line)["sample"]["sample_id"]
        for line in (split / "decontam_dropped.jsonl")
        .read_text("utf-8")
        .splitlines()
    ]
    placed = (
        [s.sample_id for s in read_samples(split / "train.jsonl")]
        + [s.sample_id for s in read_samples(split / "heldout_synthetic.jsonl")]
        + [s.sample_id for s in read_samples(split / "excluded.jsonl")]
        + dropped
    )

    assert sorted(placed) == sorted(corpus)


def test_a_near_duplicate_is_dropped_with_its_match(repo: Repo) -> None:
    """The training sample the gold set restates is dropped and says why.

    Its `Select ... and color it ...` sibling template, which names the
    same chain and colour, may be dropped beside it; every drop has to
    name the gold item it matched.
    """
    assert _build(repo) == 0
    split = _only_split(repo.out)
    dropped = {
        record["sample"]["sample_id"]: record
        for record in (
            json.loads(line)
            for line in (split / "decontam_dropped.jsonl")
            .read_text("utf-8")
            .splitlines()
        )
    }

    assert dropped[repo.duplicated_train_id]["score"] == 1.0
    assert {record["gold_id"] for record in dropped.values()} == {"gold_001"}
    assert all(record["score"] >= 0.5 for record in dropped.values())


def test_excluded_representations_are_dropped_from_both_sides(
    repo: Repo,
) -> None:
    """No slice sample survives anywhere; each is recorded as excluded."""
    assert _build(repo) == 0
    split = _only_split(repo.out)
    slice_only = frozenset(("slice",))

    for name in ("train.jsonl", "heldout_synthetic.jsonl"):
        assert not [
            s.sample_id
            for s in read_samples(split / name)
            if uses_representation(s, slice_only)
        ], name
    excluded = read_samples(split / "excluded.jsonl")
    assert {s.structure.spec_id for s in excluded} == {
        "minimal_single_chain",
        "two_chains_hetatm",
    }
    manifest = json.loads((split / "manifest.json").read_text("utf-8"))
    assert manifest["counts"]["excluded"] == len(excluded)
    assert manifest["provenance"]["exclusions"]["representations"] == ["slice"]


def test_refuses_gold_using_an_excluded_representation(repo: Repo) -> None:
    """The test split is edited by hand, never silently filtered."""
    config = repo.root / "configs" / "generation" / "split.json"
    data = json.loads(config.read_text("utf-8"))
    data["exclude"]["representations"] = ["slice", "sticks"]
    config.write_text(json.dumps(data), encoding="utf-8")

    assert _build(repo) == 1


def test_refuses_unreviewed_gold(repo: Repo) -> None:
    """A split is never frozen over a label nobody signed off."""
    path = repo.root / "src" / "pmc_data" / "gold" / "gold_items.jsonl"
    items = load_gold_items(path)
    first = items[0]
    write_gold_items(
        path,
        (
            dataclasses.replace(first, reviewed=False, reviewed_by=None),
            *items[1:],
        ),
    )

    assert _build(repo) == 1
    assert not repo.out.exists() or not list(repo.out.glob("split-*"))


def test_refuses_stale_gold_samples(repo: Repo) -> None:
    """Gold samples that no longer match their items must be regenerated."""
    path = repo.root / "src" / "pmc_data" / "gold" / "gold_items.jsonl"
    items = load_gold_items(path)
    first = items[0]
    write_gold_items(
        path,
        (
            dataclasses.replace(first, intent="recoloured"),
            *items[1:],
        ),
    )

    assert _build(repo) == 1


def test_refuses_incomplete_corpus(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A partial corpus run is not split.

    Args:
        tmp_path: Scratch directory.
        monkeypatch: Re-roots the binary.
    """
    repo = make_repo(tmp_path, complete=False)
    monkeypatch.setattr(split_cli, "REPO_ROOT", tmp_path)

    assert _build(repo) == 1


def test_refuses_broken_lineage(repo: Repo) -> None:
    """A sample whose recorded structure is not what its spec builds is refused."""
    path = repo.corpus / "samples.jsonl"
    lines = path.read_text("utf-8").splitlines()
    record = json.loads(lines[0])
    record["structure"]["snapshot_sha256"] = "0" * 64
    lines[0] = json.dumps(record, sort_keys=True, separators=(",", ":"))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    assert _build(repo) == 1


def test_refuses_a_dirty_tree(repo: Repo) -> None:
    """A dirty tree is refused, unless explicitly allowed and then recorded."""
    assert _build(repo, git=("f" * 40, True)) == 1
    assert _build(repo, "--allow-dirty", git=("f" * 40, True)) == 0

    manifest = json.loads(
        (_only_split(repo.out) / "manifest.json").read_text("utf-8")
    )
    assert manifest["provenance"]["git_dirty"] is True


def test_rerun_is_byte_identical(repo: Repo) -> None:
    """The same inputs give the same split, and an existing one is kept."""
    assert _build(repo) == 0
    first = _only_split(repo.out)
    other = repo.root / "elsewhere"

    assert _build(repo, "--out", str(other)) == 0
    second = _only_split(other)
    assert first.name == second.name
    for name in DATA_FILES:
        assert filecmp.cmp(first / name, second / name, shallow=False), name

    before = (first / "manifest.json").read_bytes()
    assert _build(repo, git=("e" * 40, False)) == 0
    assert (first / "manifest.json").read_bytes() == before


def test_the_manifest_and_datasheet_are_published(repo: Repo) -> None:
    """The committed copies land in docs and match the split's own."""
    assert _build(repo) == 0
    split = _only_split(repo.out)

    for name in ("manifest.json", "DATASHEET.md"):
        assert filecmp.cmp(split / name, repo.docs / name, shallow=False)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
