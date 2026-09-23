# Copyright 2026 PyMOL Copilot contributors.
"""Evidence that a corpus run cannot quietly destroy another one.

The corpus generator is the one binary here that writes thousands of
verified samples and then moves them somewhere. Two ways of losing that
work do not show up in any sample, any report or any other test: a run
whose directory name does not distinguish it from a different corpus,
and a promotion step that deletes the destination before it writes it.
Both have happened -- a 3,695-sample run was cut to 53 by the first --
so both are settled here, against real directories rather than mocks.

The generator itself is not run: a full corpus is a few thousand
spawned PyMOL processes, which is why it lives outside `bazel test` in
the first place. What is exercised is the naming and the promotion,
which is where a corpus is lost.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import dataclasses
import hashlib
from pathlib import Path

import pytest

from pmc_core.snapshot import structure_digest
from pmc_core.snapshot import to_json
from pmc_data import corpus_cli
from pmc_data.corpus_cli import Attempt
from pmc_data.corpus_cli import _promote
from pmc_data.corpus_cli import plan_attempts
from pmc_data.corpus_cli import run_identity
from pmc_data.sample import ASSERTION_COMMANDS_SUCCEEDED
from pmc_data.sample import ASSERTION_RESULTING_SNAPSHOT
from pmc_data.sample import FINGERPRINT_PREFIX
from pmc_data.sample import Assertion
from pmc_data.sample import Rejection
from pmc_data.sample import Sample
from pmc_data.sample import StructureIdentity
from pmc_data.sample import VerificationRecord
from pmc_data.sample import current_versions

SEED = 20260921

#: Small enough to keep the module quick, large enough that a run
#: identity is computed over more than a single structure.
BUDGET = 40


def _write(directory: Path, **files: str) -> Path:
    """Write a corpus-shaped directory.

    Args:
        directory: Where to write; created if absent.
        files: File names mapped to their contents.

    Returns:
        The directory written.
    """
    directory.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (directory / name).write_text(content, encoding="utf-8")
    return directory


def _stand_in_sample(numbered: tuple[int, Attempt]) -> Sample | Rejection:
    """Stand in for `_verify` without spawning PyMOL.

    The run path this module exercises does not care what verified: it
    cares where the results land. Everything a `Sample` insists on is
    real all the same -- the structure identity is the attempt's own,
    and the assertions state what the verification beside them records
    -- so this is a sample the record type accepts rather than a stub
    it was taught to tolerate.

    Args:
        numbered: The attempt and its zero-based position, as
            `pool.map` hands it over.

    Returns:
        A verified sample for that attempt.
    """
    index, attempt = numbered
    snapshot_json = to_json(attempt.snapshot)
    fingerprint = (
        FINGERPRINT_PREFIX
        + hashlib.sha256(snapshot_json.encode("utf-8")).hexdigest()
    )
    return Sample(
        sample_id=f"{attempt.spec.spec_id}_{index:05d}",
        intent=attempt.candidate.intent,
        category=attempt.candidate.category,
        difficulty=attempt.candidate.difficulty,
        structure=StructureIdentity(
            spec_id=attempt.spec.spec_id,
            seed=attempt.spec.seed,
            spec=attempt.spec.to_dict(),
            snapshot_sha256=hashlib.sha256(
                snapshot_json.encode("utf-8")
            ).hexdigest(),
            structure_digest=structure_digest(attempt.snapshot),
        ),
        versions=current_versions(card_version=1, prompt_version=1),
        plan_pml=attempt.candidate.plan.render_pml(),
        plan_json=({"verb": "color"},),
        prompt_text="prompt-version=1\n",
        assertions=(
            Assertion(kind=ASSERTION_RESULTING_SNAPSHOT, detail=fingerprint),
            Assertion(kind=ASSERTION_COMMANDS_SUCCEEDED, detail="1 commands"),
        ),
        unsupported_assertions=(),
        verification=VerificationRecord(
            status="ok",
            reason="ok",
            expected_fingerprint=fingerprint,
            resulting_fingerprint=fingerprint,
            selection_counts=(),
            command_verbs=("color",),
        ),
    )


@pytest.fixture
def without_pymol(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace the verification step for a whole-run test.

    Args:
        monkeypatch: pytest's attribute patcher.
    """
    monkeypatch.setattr(corpus_cli, "_verify", _stand_in_sample)


def test_the_same_inputs_name_the_same_directory() -> None:
    """The identity is what makes a regenerated corpus reproducible."""
    attempts = plan_attempts(SEED, BUDGET)

    assert run_identity(SEED, BUDGET, attempts) == run_identity(
        SEED, BUDGET, attempts
    )


def test_a_changed_enumeration_changes_the_identity() -> None:
    """A generator that plans differently must not reuse the name.

    This is the case a contract version misses: adding plan shapes to
    the enumeration took it from 9,594 plans to 11,274 without moving
    one value `current_versions()` returns, so the old corpus and the
    new one would have been the same directory and the second would
    have replaced the first.
    """
    attempts = plan_attempts(SEED, BUDGET)

    assert run_identity(SEED, BUDGET, attempts[:-1]) != run_identity(
        SEED, BUDGET, attempts
    )


def test_a_changed_structure_changes_the_identity() -> None:
    """A structure is an input to a run exactly as the seed is.

    The spec is unchanged here and so is its id, which is what makes
    this the sharp case: only the atoms the structure was built with
    differ, so a digest over the specs alone would call two different
    corpora one corpus.
    """
    attempts = plan_attempts(SEED, BUDGET)
    first = attempts[0]
    state = first.snapshot.states[0]
    recolored = dataclasses.replace(
        state.atoms[0], color=state.atoms[0].color + 1
    )
    altered = dataclasses.replace(
        first,
        snapshot=dataclasses.replace(
            first.snapshot,
            states=(
                dataclasses.replace(state, atoms=(recolored, *state.atoms[1:])),
                *first.snapshot.states[1:],
            ),
        ),
    )

    assert run_identity(SEED, BUDGET, (altered, *attempts[1:])) != (
        run_identity(SEED, BUDGET, attempts)
    )


def test_changed_sample_labels_change_the_identity() -> None:
    """A label is output, not commentary on it.

    The plan, the structure and every contract version are identical in
    each case here; one label differs. `Sample` records `intent`,
    `category` and `difficulty` verbatim and builds `prompt_text` from
    the intent, so `samples.jsonl` comes out with different bytes --
    which is exactly the collision the identity exists to prevent. A
    digest over the plans alone missed it, because a candidate is a
    plan plus its labels and only the plan was hashed.
    """
    attempts = plan_attempts(SEED, BUDGET)
    candidate = attempts[0].candidate
    # Each label is prefixed rather than given a written-out value, so
    # no case can quietly become a no-op by naming the label this
    # candidate already carries -- `difficulty` is already "advanced".
    relabeled = (
        dataclasses.replace(candidate, intent=f"reworded {candidate.intent}"),
        dataclasses.replace(
            candidate, category=f"reworded {candidate.category}"
        ),
        dataclasses.replace(
            candidate, difficulty=f"reworded {candidate.difficulty}"
        ),
    )
    baseline = run_identity(SEED, BUDGET, attempts)

    for relabeled_candidate in relabeled:
        altered = dataclasses.replace(
            attempts[0], candidate=relabeled_candidate
        )

        assert run_identity(SEED, BUDGET, (altered, *attempts[1:])) != baseline


def test_a_free_destination_is_taken(tmp_path: Path) -> None:
    """The ordinary promotion: a rename onto a name nothing holds.

    Args:
        tmp_path: pytest's per-test temporary directory.
    """
    staged = _write(tmp_path / ".run.incomplete", **{"samples.jsonl": "a\n"})
    run_dir = tmp_path / "run"

    assert _promote(staged, run_dir, tmp_path / "run.rerun") == run_dir
    assert (run_dir / "samples.jsonl").read_text(encoding="utf-8") == "a\n"
    assert not staged.exists()


def test_a_reproduced_corpus_is_left_exactly_as_it_was(
    tmp_path: Path,
) -> None:
    """An identity that already has its corpus keeps the one it has.

    Not "is overwritten with identical bytes": the destination is never
    removed, so a rerun cannot end with the corpus half-deleted because
    something failed between the removal and the rename.

    Args:
        tmp_path: pytest's per-test temporary directory.
    """
    run_dir = _write(tmp_path / "run", **{"samples.jsonl": "a\n"})
    written = (run_dir / "samples.jsonl").stat().st_ino
    staged = _write(tmp_path / ".run.incomplete", **{"samples.jsonl": "a\n"})

    assert _promote(staged, run_dir, tmp_path / "run.rerun") == run_dir
    assert (run_dir / "samples.jsonl").stat().st_ino == written
    assert not staged.exists()


def test_a_corpus_that_disagrees_is_kept_beside_the_one_there(
    tmp_path: Path,
) -> None:
    """A rerun that broke the identity's promise loses nothing.

    Both corpora are evidence at that point -- the difference between
    them is the finding -- so the destination stands and the run that
    disagreed is kept under its own name for the caller to report.

    Args:
        tmp_path: pytest's per-test temporary directory.
    """
    run_dir = _write(tmp_path / "run", **{"samples.jsonl": "a\n"})
    staged = _write(tmp_path / ".run.incomplete", **{"samples.jsonl": "b\n"})
    kept_dir = tmp_path / "run.rerun"

    assert _promote(staged, run_dir, kept_dir) == kept_dir
    assert (run_dir / "samples.jsonl").read_text(encoding="utf-8") == "a\n"
    assert (kept_dir / "samples.jsonl").read_text(encoding="utf-8") == "b\n"
    assert not staged.exists()


def test_a_destination_missing_a_file_is_not_the_same_corpus(
    tmp_path: Path,
) -> None:
    """Equal bytes in the files both hold is not equality.

    A truncated corpus -- one written by an older run that produced no
    report, say -- agrees with a complete one on every file it still
    has, and would be silently kept as if it were the same.

    Args:
        tmp_path: pytest's per-test temporary directory.
    """
    run_dir = _write(tmp_path / "run", **{"samples.jsonl": "a\n"})
    staged = _write(
        tmp_path / ".run.incomplete",
        **{"samples.jsonl": "a\n", "report.json": "{}\n"},
    )
    kept_dir = tmp_path / "run.rerun"

    assert _promote(staged, run_dir, kept_dir) == kept_dir
    assert not (run_dir / "report.json").exists()


def _corpus_dirs(out_dir: Path) -> list[str]:
    """List what a run left under --out, hidden directories included.

    Args:
        out_dir: The directory a run was pointed at.

    Returns:
        The entry names, sorted.
    """
    return sorted(entry.name for entry in out_dir.iterdir())


@pytest.mark.usefixtures("without_pymol")
def test_a_run_leaves_its_corpus_and_nothing_else(tmp_path: Path) -> None:
    """A finished run is one directory: no staging, no partial.

    Args:
        tmp_path: pytest's per-test temporary directory.
    """
    assert corpus_cli.run(["--out", str(tmp_path), "--target", "3"]) == 0

    identity = run_identity(SEED, 3, plan_attempts(SEED, 3))
    assert _corpus_dirs(tmp_path) == [f"seed-{SEED}-{identity}"]
    run_dir = tmp_path / f"seed-{SEED}-{identity}"
    assert (run_dir / "samples.jsonl").exists()
    assert (run_dir / "report.json").exists()


@pytest.mark.usefixtures("without_pymol")
def test_rerunning_the_same_run_changes_nothing(tmp_path: Path) -> None:
    """The second run reproduces the first, so the first one stands.

    Args:
        tmp_path: pytest's per-test temporary directory.
    """
    assert corpus_cli.run(["--out", str(tmp_path), "--target", "3"]) == 0
    before = _corpus_dirs(tmp_path)

    assert corpus_cli.run(["--out", str(tmp_path), "--target", "3"]) == 0

    assert _corpus_dirs(tmp_path) == before


@pytest.mark.usefixtures("without_pymol")
def test_a_run_that_disagrees_refuses_to_replace_the_corpus(
    tmp_path: Path,
) -> None:
    """The corpus already there survives, and the run says so.

    Standing in for a generator that no longer reproduces its own
    output: the directory holds something this run did not produce, and
    the promise the identity makes is broken either way. What must not
    happen is the run deciding on its own which of the two to keep.

    Args:
        tmp_path: pytest's per-test temporary directory.
    """
    assert corpus_cli.run(["--out", str(tmp_path), "--target", "3"]) == 0
    identity = run_identity(SEED, 3, plan_attempts(SEED, 3))
    run_dir = tmp_path / f"seed-{SEED}-{identity}"
    (run_dir / "samples.jsonl").write_text("tampered\n", encoding="utf-8")

    assert corpus_cli.run(["--out", str(tmp_path), "--target", "3"]) == 1

    assert (run_dir / "samples.jsonl").read_text(
        encoding="utf-8"
    ) == "tampered\n"
    kept = [
        tmp_path / name
        for name in _corpus_dirs(tmp_path)
        if name.endswith(".rerun")
    ]
    assert len(kept) == 1
    assert (kept[0] / "samples.jsonl").read_text(encoding="utf-8") != (
        "tampered\n"
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
