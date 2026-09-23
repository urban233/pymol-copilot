# Copyright 2026 PyMOL Copilot contributors.
"""Verify the reviewed gold set and write its committed samples.

Run it with:

    bazel run //src/pmc_data:gold_cli

Every record in `src/pmc_data/gold/gold_items.jsonl` is verified
through `pmc_data.gold_set.verify_gold` -- the oracle predicts the
result, and real headless PyMOL in a fresh `pmc_sidecar.child` has to
agree -- and the verified samples are written to
`src/pmc_data/gold/gold_samples.jsonl`, which is committed and replayed
by `tests/data/test_gold_set_real_pymol.py`.

The structures come from the corpus's own configuration
(`configs/generation/corpus.json`), so a gold sample and a generated
sample on the same spec are graded against the same bytes.

The binary refuses to run while any record is unreviewed: a gold sample
exists only for a label a person has signed off. It writes nothing
unless every record verifies. A partial gold set would pass its own
replay test while covering less than the set it claims to be.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import argparse
import json
import os
import sys
from pathlib import Path

from pmc_data.gold_set import GoldVerificationError
from pmc_data.gold_set import load_gold_items
from pmc_data.gold_set import verify_gold
from pmc_data.sample import write_samples

#: The repository root, resolved the way Bazel's own `bazel run`
#: convention expects so output lands in the real source tree.
REPO_ROOT = Path(
    os.environ.get(
        "BUILD_WORKSPACE_DIRECTORY", Path(__file__).resolve().parents[2]
    )
)

DEFAULT_ITEMS = Path("src") / "pmc_data" / "gold" / "gold_items.jsonl"
DEFAULT_OUT = Path("src") / "pmc_data" / "gold" / "gold_samples.jsonl"
DEFAULT_CORPUS_CONFIG = Path("configs") / "generation" / "corpus.json"


def _resolve(path: Path) -> Path:
    """Resolve a command-line path against the repository root.

    Args:
        path: The path as given.

    Returns:
        The path itself if absolute, else under REPO_ROOT.
    """
    return path if path.is_absolute() else REPO_ROOT / path


def _parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse this binary's command line.

    Args:
        argv: The arguments after the program name.

    Returns:
        The parsed arguments.
    """
    parser = argparse.ArgumentParser(
        description="Verify the reviewed gold set and write its samples."
    )
    parser.add_argument("--items", type=Path, default=DEFAULT_ITEMS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--corpus-config", type=Path, default=DEFAULT_CORPUS_CONFIG
    )
    parser.add_argument(
        "--workers", type=int, default=min(8, (os.cpu_count() or 2))
    )
    args = parser.parse_args(argv)
    if args.workers < 1:
        parser.error(f"--workers must be at least 1, not {args.workers}")
    return args


def run(argv: list[str]) -> int:
    """Verify the gold set and write it, or refuse and say why.

    Args:
        argv: The arguments after the program name.

    Returns:
        Zero when every record verified and was written; non-zero when
        any record is unreviewed or failed verification, in which case
        nothing is written.
    """
    args = _parse_args(argv)
    items = load_gold_items(_resolve(args.items))
    unreviewed = [item.gold_id for item in items if not item.reviewed]
    if unreviewed:
        print(
            f"REFUSED: {len(unreviewed)} of {len(items)} gold items are not "
            f"reviewed: {', '.join(unreviewed)}",
            file=sys.stderr,
        )
        return 1

    config = json.loads(
        _resolve(args.corpus_config).read_text(encoding="utf-8")
    )
    seed = int(config["seed"])
    try:
        samples = verify_gold(items, seed=seed, workers=args.workers)
    except GoldVerificationError as error:
        print(f"REFUSED: {error}", file=sys.stderr)
        return 1

    out = _resolve(args.out)
    # Written beside the destination and moved in whole, so a failure
    # partway through never leaves a truncated gold set in place.
    staging = out.with_name(f".{out.name}.incomplete")
    written = write_samples(staging, samples)
    staging.replace(out)
    print(f"WROTE {written} gold samples to {out} (seed={seed})")
    return 0


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
