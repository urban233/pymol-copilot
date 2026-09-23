# Copyright 2026 PyMOL Copilot contributors.
"""Generate and verify the dataset corpus, then report it honestly.

Run it with:

    bazel run //src/pmc_data:corpus_cli -- \\
        --config configs/generation/corpus.json --workers 8

Every sample is verified through the real `pmc_core.executor`, which
spawns a real `pmc_sidecar.child` process running real headless
PyMOL. This binary therefore never imports PyMOL itself -- the child
is the only thing that does, which is why the whole run stays outside
`bazel test`: a few thousand samples is a few thousand processes.

Output goes to `seed-<seed>-<identity>/` under `--out`, whose contents
`.gitignore` excludes. The identity digests the budget, every contract
version and the structures and plans the generator produced, as well
as the seed, because those decide the content too: naming the
directory for the seed alone let a `--target 100` run overwrite a
four-thousand-attempt corpus in place. A run is written beside its
destination, under a name of its own that no concurrent run can be
holding, and moved in only once it is complete, so a failed run leaves
a `.partial` directory rather than something that looks like the
corpus and is not. The move never deletes what is already there: an
identity that already has a corpus keeps it, and a rerun that produced
something different is kept beside it and reported instead of replacing
it. Three files, because a summary alone would let a rejection
disappear:

- `samples.jsonl` -- verified samples only.
- `rejections.jsonl` -- every attempt that did not become one, with
  the reason the executor actually gave.
- `report.json` -- the per-category rejection rate, and how much of
  the kept set could actually have failed.

`--slice` writes the first two into the committed conformance
directory instead, and no report: the slice's report would restate
what the samples beside it already say. A slice run that fails partway
writes nothing at all -- with no report beside them there is nowhere
to record that the tracked files were replaced by something
incomplete, so they are left exactly as they were.

The run is deterministic in its seed: the structures, the plans, the
subset chosen when a budget is set, and the sample identities all
derive from it, and nothing nondeterministic is recorded. Two runs at
the same seed produce byte-identical files, which is what makes the
recorded seed worth anything.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import argparse
import filecmp
import hashlib
import json
import os
import secrets
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from pmc_core.card import CARD_VERSION
from pmc_core.plan import HideOperation
from pmc_core.plan import ShowOperation
from pmc_core.prompt import PROMPT_VERSION
from pmc_core.snapshot import ObjectSnapshot
from pmc_core.snapshot import to_json
from pmc_data.generate import verify_sample
from pmc_data.report import CorpusReport
from pmc_data.report import build_report
from pmc_data.report import render_table
from pmc_data.report import write_rejections
from pmc_data.report import write_report
from pmc_data.sample import Rejection
from pmc_data.sample import Sample
from pmc_data.sample import current_versions
from pmc_data.sample import write_samples
from pmc_data.structures import StructureSpec
from pmc_data.structures import build_structure
from pmc_data.structures import enumerate_structures
from pmc_data.taxonomy import PlanCandidate
from pmc_data.taxonomy import UNOBSERVABLE_REPRESENTATIONS
from pmc_data.taxonomy import enumerate_plans
from pmc_data.taxonomy import stratified_subset

#: The repository root, resolved the way Bazel's own `bazel run`
#: convention expects so output lands in the real source tree.
REPO_ROOT = Path(
    os.environ.get(
        "BUILD_WORKSPACE_DIRECTORY", Path(__file__).resolve().parents[2]
    )
)

#: Where a run writes when --out is not given.
DEFAULT_OUT = Path("data") / "samples"

#: Where the run's declared configuration lives by default.
DEFAULT_CONFIG = Path("configs") / "generation" / "corpus.json"


@dataclass(frozen=True)
class Attempt:
    """One planned attempt, before it is verified.

    Attributes:
        spec: The structure spec the plan runs against.
        snapshot: That structure, already built.
        candidate: The plan, category, difficulty and intent.
    """

    spec: StructureSpec
    snapshot: ObjectSnapshot
    candidate: PlanCandidate


def plan_attempts(seed: int, budget: int | None) -> tuple[Attempt, ...]:
    """Enumerate every attempt a run will make, deterministically.

    Args:
        seed: The run's seed; structures and plans derive from it.
        budget: The most attempts to make, or None for all of them.

    Returns:
        The attempts, in a stable order.
    """
    attempts: list[Attempt] = []
    for spec in enumerate_structures(seed):
        snapshot = build_structure(spec)
        for candidate in enumerate_plans(snapshot, seed=spec.seed):
            attempts.append(
                Attempt(spec=spec, snapshot=snapshot, candidate=candidate)
            )
    if budget is None:
        return tuple(attempts)
    return stratified_subset(
        attempts,
        category_of=lambda attempt: attempt.candidate.category,
        budget=budget,
        seed=seed,
    )


def _verify(numbered: tuple[int, Attempt]) -> Sample | Rejection:
    """Verify one attempt, naming it from its position in the run.

    Args:
        numbered: The attempt and its zero-based position.

    Returns:
        The verified sample, or the rejection explaining why not.
    """
    index, attempt = numbered
    return verify_sample(
        attempt.snapshot,
        attempt.spec,
        attempt.candidate,
        sample_id=f"{attempt.spec.spec_id}_{index:05d}",
    )


def _representations(attempt: Attempt) -> frozenset[str]:
    """Report which representations an attempt's plan names.

    Read off the typed operations rather than matched against rendered
    .pml text: a change to `ShowOperation.render()`'s spacing would
    silently turn a text match into "no such attempt exists", and this
    is the only thing that keeps the committed slice covering the
    representation surface at all.

    Args:
        attempt: The attempt to inspect.

    Returns:
        Every representation its `show` and `hide` operations name,
        which is empty for a plan that only selects, colors or orients.
    """
    return frozenset(
        operation.representation
        for operation in attempt.candidate.plan.operations
        if isinstance(operation, ShowOperation | HideOperation)
    )


def conformance_slice(attempts: Sequence[Attempt]) -> tuple[Attempt, ...]:
    """Pick the smallest slice that still covers the whole surface.

    A run of a few thousand samples cannot live in `bazel test`, but
    contract drift -- a bumped card version, a changed colour index, an
    altered snapshot field -- breaks every sample at once, so a small
    slice catches it just as well. What the slice must not miss is a
    *kind* of thing: every verb set, every term keyword, every boolean
    shape, every controlled structure, and every representation, so a
    structure that stopped reconstructing faithfully is caught here
    too.

    Representation is an axis in its own right because the others do
    not imply it. `show` and `hide` are one verb set each, so four
    representations covered the whole verb axis while `labels`,
    `ribbon`, `surface` and `mesh` went into the corpus by the
    hundred with nothing in `bazel test` replaying them: a PyMOL
    upgrade that changed what `cmd.iterate` reports for one of them
    would have left every test green and surfaced only as a wall of
    fidelity mismatches partway through the next corpus run.

    Plans naming the polymer flag are skipped while covering those
    axes and added once at the end. They are ungradable, so letting one
    stand in for a term axis would spend the axis on a sample that can
    never be verified -- which is how `hetatm` first went uncovered,
    swallowed by a two-selection plan that paired it with `polymer`.
    That polymer attempt never reaches `samples.jsonl`, because it is
    not a sample; it is written to the committed `rejections.jsonl`
    alongside the direct-`orient` attempt the loop above already
    covers, so the slice carries evidence of both ungradable paths
    rather than only of the happy one.

    An attempt is identified by its structure *and* its plan text, not
    by the plan text alone: two structures with the same shape can draw
    the same colour and emit byte-identical .pml, and keying on the
    text alone would mark the second structure covered while silently
    keeping only the first structure's attempt.

    Args:
        attempts: Every attempt the full run would make.

    Returns:
        The chosen attempts, in the input order.
    """

    def identity(attempt: Attempt) -> tuple[str, str]:
        """Identify one attempt by its structure and its plan text.

        Args:
            attempt: The attempt to identify.

        Returns:
            The structure's spec id paired with the canonical .pml.
        """
        return (attempt.spec.spec_id, attempt.candidate.plan.render_pml())

    chosen: dict[tuple[str, str], Attempt] = {}
    seen_verbs: set[str] = set()
    seen_terms: set[str] = set()
    seen_shapes: set[str] = set()
    seen_specs: set[str] = set()
    seen_reps: set[str] = set()

    for attempt in attempts:
        category = attempt.candidate.category
        if "polymer" in category:
            continue
        verbs, terms, shape = category.split("/")
        keywords = set(terms.split("+"))
        representations = _representations(attempt)
        if (
            verbs in seen_verbs
            and keywords <= seen_terms
            and shape in seen_shapes
            and attempt.spec.spec_id in seen_specs
            and representations <= seen_reps
        ):
            continue
        seen_verbs.add(verbs)
        seen_terms |= keywords
        seen_shapes.add(shape)
        seen_specs.add(attempt.spec.spec_id)
        seen_reps |= representations
        chosen.setdefault(identity(attempt), attempt)

    # One plan of each ungradable kind, so the slice exercises the
    # unsupported path rather than only the happy one. The
    # representation axis above already reaches every unobservable
    # name the enumeration emits outside a polymer plan, so today this
    # adds nothing; it stays because the loop skips polymer plans, and
    # an unobservable representation that came to be emitted only
    # inside one would otherwise drop out of the slice in silence.
    unobservable = frozenset(UNOBSERVABLE_REPRESENTATIONS)
    if not any(_representations(a) & unobservable for a in chosen.values()):
        for attempt in attempts:
            if _representations(attempt) & unobservable:
                chosen.setdefault(identity(attempt), attempt)
                break
    for attempt in attempts:
        if "polymer" in attempt.candidate.category:
            chosen.setdefault(identity(attempt), attempt)
            break

    order = {identity(attempt): index for index, attempt in enumerate(attempts)}
    return tuple(sorted(chosen.values(), key=lambda a: order[identity(a)]))


def run_identity(
    seed: int, target: int | None, attempts: Sequence[Attempt]
) -> str:
    """Digest everything that decides what a run's content will be.

    The output directory was named for the seed alone, which is a
    claim the seed cannot support. `--target 100` and the configured
    four-thousand budget produce different corpora from the same seed,
    and so does the same budget under a changed contract; all of them
    landed in one directory, where each silently replaced the last. A
    measured 3,695-sample corpus was reduced to 53 that way, with
    nothing but `report.json`'s own `attempted` count to show for it.

    The attempts themselves are digested, not only the seed and the
    budget that select them. `pmc_data.structures` and
    `pmc_data.taxonomy` are inputs to a run exactly as much as the seed
    is, and neither moves a contract version when it changes: the
    commit that added the missing verb and target forms took the
    enumeration from 9,594 plans to 11,274 without altering one value
    `current_versions()` returns, so the old corpus and the new one
    would have been the same directory.

    What is digested is what those two modules actually produced --
    every structure this run built, by its spec and the bytes of the
    structure itself, and every plan, by its canonical .pml together
    with the labels its sample will carry. That is stronger than a
    hand-maintained schema version, which records that someone
    remembered to bump it: a structure whose atoms change while its
    spec stays put moves this digest, and a version constant would not
    have noticed.

    The labels are digested because they are output bytes, not
    commentary on them. A `Sample` records `intent`, `category` and
    `difficulty` verbatim, and `prompt_text` is built from the intent,
    so rewording one intent template rewrites `samples.jsonl` while
    leaving every plan, structure and contract version where it was --
    two different corpora in one directory again, by the same route
    the enumeration change took. The plan alone is not a proxy for
    them: a candidate is a plan *plus* the labels, and only the plan
    was ever hashed.

    Args:
        seed: The run's seed.
        target: The attempt budget, or None for the whole enumeration.
        attempts: The attempts this run will make, in order.

    Returns:
        A short hex digest over the seed, the budget, every contract
        version a sample records, and the structures, plans and
        sample labels the enumeration produced.
    """
    structures: dict[str, dict[str, str]] = {}
    plans: list[list[str]] = []
    for attempt in attempts:
        spec_id = attempt.spec.spec_id
        if spec_id not in structures:
            # Hashed once per structure rather than once per attempt:
            # the whole enumeration is thousands of plans over a dozen
            # or so structures, all of which are already built and in
            # memory by the time this is called.
            structures[spec_id] = {
                "spec": json.dumps(attempt.spec.to_dict(), sort_keys=True),
                "snapshot_sha256": hashlib.sha256(
                    to_json(attempt.snapshot).encode("utf-8")
                ).hexdigest(),
            }
        candidate = attempt.candidate
        plans.append(
            [
                spec_id,
                candidate.plan.render_pml(),
                candidate.intent,
                candidate.category,
                candidate.difficulty,
            ]
        )
    material = json.dumps(
        {
            "seed": seed,
            "target": target,
            "versions": current_versions(
                card_version=CARD_VERSION, prompt_version=PROMPT_VERSION
            ).to_dict(),
            "structures": structures,
            "plans": plans,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:12]


def _parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse this binary's command line.

    Args:
        argv: The arguments after the program name.

    Returns:
        The parsed arguments.
    """
    parser = argparse.ArgumentParser(
        description="Generate and verify the dataset corpus."
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument(
        "--target",
        type=int,
        default=None,
        help=(
            "The most attempts to make, not the number of samples to "
            "keep: an attempt the oracle cannot grade is reported "
            "rather than kept, so the corpus is smaller than this."
        ),
    )
    parser.add_argument(
        "--workers", type=int, default=min(8, (os.cpu_count() or 2))
    )
    parser.add_argument(
        "--slice",
        action="store_true",
        help=(
            "Generate the small committed conformance slice instead "
            "of the corpus, and write it next to the package."
        ),
    )
    args = parser.parse_args(argv)
    # Checked here rather than left to ThreadPoolExecutor and
    # stratified_subset: both raise, but only after this binary has
    # enumerated every attempt and printed its banner, which reads
    # like the run started and then broke.
    if args.workers < 1:
        parser.error(f"--workers must be at least 1, not {args.workers}")
    if args.target is not None and args.target < 1:
        parser.error(f"--target must be at least 1, not {args.target}")
    return args


def _write_run(
    run_dir: Path,
    results: Sequence[Sample | Rejection],
    *,
    seed: int,
    slice_only: bool,
    complete: bool,
) -> CorpusReport:
    """Write everything one run produced, and return its report.

    Args:
        run_dir: The directory to write into; it must already exist.
        results: Every attempt's outcome, in attempt order.
        seed: The seed the run used.
        slice_only: Whether this is the committed conformance slice.
            The slice's report is not written: it is derived entirely
            from the samples beside it, and a tracked file that
            restates them would only be one more thing to keep in
            step. Its rejections are written, because those are the
            slice's only record of the ungradable path.
        complete: Whether every planned attempt was made.

    Returns:
        The report for what was written.
    """
    samples = [result for result in results if isinstance(result, Sample)]
    rejections = [result for result in results if isinstance(result, Rejection)]
    write_samples(run_dir / "samples.jsonl", samples)
    write_rejections(run_dir / "rejections.jsonl", rejections)
    report = build_report(samples, rejections, seed=seed, complete=complete)
    if not slice_only:
        write_report(run_dir / "report.json", report)
    return report


def _same_corpus(left: Path, right: Path) -> bool:
    """Compare two corpus directories file by file.

    Args:
        left: One directory.
        right: The other.

    Returns:
        True when both hold the same file names and the same bytes.
    """
    names = {
        path.relative_to(left) for path in left.rglob("*") if path.is_file()
    }
    if names != {
        path.relative_to(right) for path in right.rglob("*") if path.is_file()
    }:
        return False
    # shallow=False: equal size and mtime is not equal content, and a
    # regenerated corpus carries whatever mtime the run gave it.
    return all(
        filecmp.cmp(left / name, right / name, shallow=False) for name in names
    )


def _promote(write_dir: Path, run_dir: Path, kept_dir: Path) -> Path:
    """Move a completed run into place without deleting a corpus.

    The move used to be `rmtree(run_dir)` followed by a rename, which
    deletes a known-good corpus first and loses it outright if anything
    goes wrong in between. It is a rename onto a name nothing holds
    instead, which either happens or does not; the destination is never
    removed, and a rerun that disagrees with what is already there is
    kept beside it rather than allowed to overwrite it. An identity is
    a promise that the content is the same, so a rerun that breaks the
    promise is a finding, and this is the one place that could destroy
    the evidence for it.

    Args:
        write_dir: The staging directory holding the completed run.
        run_dir: The destination this identity names.
        kept_dir: Where to keep the run if the destination is occupied
            by something else.

    Returns:
        The directory that now holds this run's output: `run_dir` when
        the run was promoted or an identical corpus was already there,
        and `kept_dir` when it was not.
    """
    try:
        # Not shutil.move: that copies into an existing destination
        # directory, which is exactly the overwrite this refuses. A
        # rename fails instead, and both directories are siblings, so
        # it cannot fail for being across devices either.
        os.replace(write_dir, run_dir)
    except OSError:
        if not run_dir.exists():
            raise
    else:
        return run_dir
    if _same_corpus(write_dir, run_dir):
        # The identity held: what is there is what this run produced,
        # so there is nothing to promote and nothing to report.
        shutil.rmtree(write_dir)
        return run_dir
    write_dir.replace(kept_dir)
    return kept_dir


def run(argv: list[str]) -> int:
    """Generate the corpus and write it with its report.

    Args:
        argv: The arguments after the program name.

    Returns:
        The process exit code. Zero whenever the run completed and
        landed, even with rejections: a rejection is a measurement, not
        an error. Non-zero when the run produced no verified sample at
        all, or when a corpus of the same identity was already in place
        and disagreed with this one -- both mean something is broken
        rather than merely hard.
    """
    args = _parse_args(argv)
    config_path = (
        args.config if args.config.is_absolute() else REPO_ROOT / args.config
    )
    config = json.loads(config_path.read_text(encoding="utf-8"))
    seed = args.seed if args.seed is not None else int(config["seed"])
    target = (
        args.target if args.target is not None else config.get("samples_target")
    )
    # The same floor --target is held to. Without this a configured 0 or
    # a negative budget produces an empty attempt set, an empty corpus
    # and a bare non-zero exit, which reads like the pipeline broke.
    if target is not None and target < 1:
        raise SystemExit(
            f"{config_path}: samples_target must be at least 1, not {target}"
        )

    attempts = plan_attempts(seed, None if args.slice else target)
    if args.slice:
        attempts = conformance_slice(attempts)
    print(
        f"seed={seed} attempts={len(attempts)} "
        f"categories={len({a.candidate.category for a in attempts})} "
        f"workers={args.workers}",
        flush=True,
    )

    if args.slice:
        # The slice is a single tracked artifact with one identity, and
        # it is written in place: its guard against a partial run is to
        # write nothing at all, below.
        run_dir = write_dir = kept_dir = partial_dir = (
            REPO_ROOT / "src" / "pmc_data" / "conformance"
        )
        write_dir.mkdir(parents=True, exist_ok=True)
    else:
        out_dir = args.out if args.out.is_absolute() else REPO_ROOT / args.out
        run_dir = (
            out_dir / f"seed-{seed}-{run_identity(seed, target, attempts)}"
        )
        # Written beside the destination rather than into it, so a run
        # that dies partway cannot leave a half-corpus sitting where a
        # complete one is expected. The completed run is moved into
        # place in one step at the end.
        #
        # The staging name carries a token of this run's own, because a
        # fixed one is shared by every run of the same identity: two
        # such runs at once wrote into one directory and deleted each
        # other's output, and the second to fail replaced the first's
        # `.partial` as well. Nothing downstream reads these names --
        # the token only has to differ.
        token = secrets.token_hex(4)
        write_dir = out_dir / f".{run_dir.name}.{token}.incomplete"
        partial_dir = out_dir / f"{run_dir.name}.{token}.partial"
        kept_dir = out_dir / f"{run_dir.name}.{token}.rerun"
        out_dir.mkdir(parents=True, exist_ok=True)
        # Not exist_ok: the token makes this name this run's alone, so
        # finding it taken means the assumption is wrong and the run
        # should say so rather than write into someone else's staging.
        write_dir.mkdir()

    results: list[Sample | Rejection] = []
    # Not a `with` block: on the way out through an exception that
    # would wait for every attempt already queued behind the failure,
    # which for a four-thousand-attempt run means a Ctrl-C taking
    # another ten minutes or so to be honoured.
    pool = ThreadPoolExecutor(max_workers=args.workers)
    try:
        # map preserves input order, so the written corpus does not
        # depend on which worker finished first. Collected one at a
        # time rather than with list(), so the ones already yielded
        # survive a failure further down the sequence.
        for result in pool.map(_verify, enumerate(attempts)):
            results.append(result)
    except BaseException:
        pool.shutdown(wait=True, cancel_futures=True)
        if args.slice:
            # The slice is a committed, tracked artifact and writes no
            # report, so there is nowhere beside it to record that what
            # replaced it was incomplete. Truncating it in place would
            # leave a smaller slice that still passes its own replay
            # test while covering less than its name claims, so it is
            # left exactly as it was.
            print(
                f"PARTIAL: failed after {len(results)} of "
                f"{len(attempts)} attempts; {run_dir} left unchanged",
                file=sys.stderr,
                flush=True,
            )
            raise
        # A full run is thousands of spawned PyMOL processes: measured
        # across eight workers at ten and a half minutes for the
        # configured four thousand, and roughly half an hour for the
        # whole enumeration. An unexpected failure at attempt
        # 3,500 has still measured 3,499 attempts, and throwing those
        # away would turn one failure into a much larger one. Nothing
        # is swallowed:
        # what finished is written, its report says plainly that it is
        # incomplete, and the exception carries on out of here to end
        # the process non-zero with its traceback intact.
        _write_run(
            write_dir,
            results,
            seed=seed,
            slice_only=False,
            complete=False,
        )
        # Kept under its own name. A partial run is worth keeping, but
        # it is not this identity's corpus, and putting it there would
        # leave the next reader holding something narrower than the
        # directory name promises. Nothing is removed to make room:
        # the name is this run's, so an earlier partial run of the same
        # identity keeps its own evidence.
        write_dir.replace(partial_dir)
        print(
            f"PARTIAL {partial_dir}: wrote {len(results)} of "
            f"{len(attempts)} attempts before failing; "
            f"{run_dir} left unchanged",
            file=sys.stderr,
            flush=True,
        )
        raise
    else:
        pool.shutdown(wait=True)

    report = _write_run(
        write_dir, results, seed=seed, slice_only=args.slice, complete=True
    )
    if write_dir != run_dir:
        landed = _promote(write_dir, run_dir, kept_dir)
        if landed != run_dir:
            # The identity promised that a rerun reproduces the corpus
            # already sitting there, and it did not. Both are kept and
            # the run ends non-zero: quietly replacing one with the
            # other would destroy the only evidence of a generator that
            # no longer reproduces its own output.
            print(render_table(report), end="", flush=True)
            print(
                f"REFUSED {run_dir}: a different corpus of the same "
                f"identity is already there; this run was kept at "
                f"{landed} and nothing was replaced",
                file=sys.stderr,
                flush=True,
            )
            return 1
    print(render_table(report), end="", flush=True)
    print(f"WROTE {run_dir}", flush=True)
    return 0 if report.kept else 1


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
