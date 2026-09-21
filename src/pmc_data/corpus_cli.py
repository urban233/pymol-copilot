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

Output goes to a content-addressed directory under `--out`, whose
contents `.gitignore` excludes. Three files, because a summary alone
would let a rejection disappear:

- `samples.jsonl` -- verified samples only.
- `rejections.jsonl` -- every attempt that did not become one, with
  the reason the executor actually gave.
- `report.json` -- the per-category rejection rate.

The run is deterministic in its seed: the structures, the plans, the
subset chosen when a budget is set, and the sample identities all
derive from it, and nothing nondeterministic is recorded. Two runs at
the same seed produce byte-identical files, which is what makes the
recorded seed worth anything.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from pmc_core.snapshot import ObjectSnapshot
from pmc_data.generate import Rejection
from pmc_data.generate import verify_sample
from pmc_data.report import build_report
from pmc_data.report import render_table
from pmc_data.report import write_rejections
from pmc_data.report import write_report
from pmc_data.sample import Sample
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


def _has_unobservable_representation(attempt: Attempt) -> bool:
    """Whether an attempt shows a representation the snapshot cannot see.

    Args:
        attempt: The attempt to inspect.

    Returns:
        True when the plan names one of those four representations.
    """
    return any(
        line.startswith(f"show {rep},") or line.startswith(f"hide {rep},")
        for line in attempt.candidate.plan.render_pml().splitlines()
        for rep in UNOBSERVABLE_REPRESENTATIONS
    )


def conformance_slice(attempts: Sequence[Attempt]) -> tuple[Attempt, ...]:
    """Pick the smallest slice that still covers the whole surface.

    A run of a few thousand samples cannot live in `bazel test`, but
    contract drift -- a bumped card version, a changed colour index, an
    altered snapshot field -- breaks every sample at once, so a small
    slice catches it just as well. What the slice must not miss is a
    *kind* of thing: every verb set, every term keyword, every boolean
    shape, and every controlled structure, so a structure that stopped
    reconstructing faithfully is caught here too.

    Plans naming the polymer flag are skipped while covering those
    axes and added once at the end. They are ungradable, so letting one
    stand in for a term axis would spend the axis on a sample that can
    never be verified -- which is how `hetatm` first went uncovered,
    swallowed by a two-selection plan that paired it with `polymer`.

    Args:
        attempts: Every attempt the full run would make.

    Returns:
        The chosen attempts, in the input order.
    """
    chosen: dict[str, Attempt] = {}
    seen_verbs: set[str] = set()
    seen_terms: set[str] = set()
    seen_shapes: set[str] = set()
    seen_specs: set[str] = set()

    for attempt in attempts:
        category = attempt.candidate.category
        if "polymer" in category:
            continue
        verbs, terms, shape = category.split("/")
        keywords = set(terms.split("+"))
        if (
            verbs in seen_verbs
            and keywords <= seen_terms
            and shape in seen_shapes
            and attempt.spec.spec_id in seen_specs
        ):
            continue
        seen_verbs.add(verbs)
        seen_terms |= keywords
        seen_shapes.add(shape)
        seen_specs.add(attempt.spec.spec_id)
        chosen.setdefault(attempt.candidate.plan.render_pml(), attempt)

    # One plan of each ungradable kind, so the slice exercises the
    # unsupported path rather than only the happy one.
    if not any(_has_unobservable_representation(a) for a in chosen.values()):
        for attempt in attempts:
            if _has_unobservable_representation(attempt):
                chosen.setdefault(attempt.candidate.plan.render_pml(), attempt)
                break
    for attempt in attempts:
        if "polymer" in attempt.candidate.category:
            chosen.setdefault(attempt.candidate.plan.render_pml(), attempt)
            break

    order = {
        attempt.candidate.plan.render_pml(): index
        for index, attempt in enumerate(attempts)
    }
    return tuple(
        sorted(
            chosen.values(),
            key=lambda a: order[a.candidate.plan.render_pml()],
        )
    )


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
    parser.add_argument("--target", type=int, default=None)
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
    return parser.parse_args(argv)


def run(argv: list[str]) -> int:
    """Generate the corpus and write it with its report.

    Args:
        argv: The arguments after the program name.

    Returns:
        The process exit code. Zero whenever the run completed, even
        with rejections: a rejection is a measurement, not an error.
        Non-zero only when the run produced no verified sample at all,
        which means something is broken rather than merely hard.
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

    attempts = plan_attempts(seed, None if args.slice else target)
    if args.slice:
        attempts = conformance_slice(attempts)
    print(
        f"seed={seed} attempts={len(attempts)} "
        f"categories={len({a.candidate.category for a in attempts})} "
        f"workers={args.workers}",
        flush=True,
    )

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        # map preserves input order, so the written corpus does not
        # depend on which worker finished first.
        results = list(pool.map(_verify, enumerate(attempts)))

    samples = [r for r in results if isinstance(r, Sample)]
    rejections = [r for r in results if isinstance(r, Rejection)]

    if args.slice:
        run_dir = REPO_ROOT / "src" / "pmc_data" / "conformance"
    else:
        out_dir = args.out if args.out.is_absolute() else REPO_ROOT / args.out
        run_dir = out_dir / f"seed-{seed}"
    run_dir.mkdir(parents=True, exist_ok=True)

    write_samples(run_dir / "samples.jsonl", samples)
    report = build_report(samples, rejections, seed=seed)
    if not args.slice:
        write_rejections(run_dir / "rejections.jsonl", rejections)
        write_report(run_dir / "report.json", report)

    print(render_table(report), end="", flush=True)
    print(f"WROTE {run_dir}", flush=True)
    return 0 if samples else 1


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
