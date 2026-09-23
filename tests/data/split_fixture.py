# Copyright 2026 PyMOL Copilot contributors.
"""A small synthetic repository for driving `split_cli` without PyMOL.

`make_repo` writes, under a temporary root, everything a split build
reads: a completed corpus run on a few training and held-out
structures, a reviewed gold set with its verified samples, the two
generation configs and a LICENSE. Every sample is produced by the real
`pmc_data.generate.verify_sample` against the real structure matrix,
with `oracle_executor.oracle_report` standing in for the PyMOL child,
so lineage checks see exactly what a real run would record.

One gold intent is deliberately a near-duplicate of one training
intent, so decontamination has something to drop.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import json
from dataclasses import dataclass
from pathlib import Path

from oracle_executor import oracle_report
from pmc_data.generate import verify_sample
from pmc_data.gold_set import GoldItem
from pmc_data.gold_set import verify_gold
from pmc_data.gold_set import write_gold_items
from pmc_data.sample import Sample
from pmc_data.sample import write_samples
from pmc_data.structures import build_structure
from pmc_data.structures import enumerate_structures
from pmc_data.taxonomy import enumerate_plans

SEED = 20260921

#: A fake commit to record, so no test depends on the real repository.
GIT_CLEAN = ("0" * 40, False)

#: Structures the fixture corpus is generated on: three training, two
#: held out.
TRAIN_SPECS = ("minimal_single_chain", "two_chains", "single_chain_hetatm")
HELD_OUT_SPECS = ("two_chains_hetatm", "three_states")

#: Samples generated per structure.
PER_SPEC = 8

#: The audit size the fixture config asks for; small, so tests are fast.
AUDIT_SIZE = 5


@dataclass(frozen=True)
class Repo:
    """Where the fixture put everything.

    Attributes:
        root: The fake repository root.
        corpus: The corpus run directory.
        out: Where splits are written.
        docs: Where the committed dataset docs go.
        duplicated_train_id: The training sample the gold set duplicates.
    """

    root: Path
    corpus: Path
    out: Path
    docs: Path
    duplicated_train_id: str


def _corpus() -> list[Sample]:
    """Generate the fixture corpus.

    Returns:
        Verified samples, PER_SPEC per structure, in a stable order.
    """
    specs = {spec.spec_id: spec for spec in enumerate_structures(SEED)}
    samples: list[Sample] = []
    for spec_id in (*TRAIN_SPECS, *HELD_OUT_SPECS):
        spec = specs[spec_id]
        snapshot = build_structure(spec)
        kept = 0
        for candidate in enumerate_plans(snapshot, seed=spec.seed):
            if kept == PER_SPEC:
                break
            result = verify_sample(
                snapshot,
                spec,
                candidate,
                sample_id=f"{spec_id}_{kept:03d}",
                executor=oracle_report,
            )
            if isinstance(result, Sample):
                samples.append(result)
                kept += 1
    return samples


def _gold(duplicate_of: Sample) -> list[GoldItem]:
    """Author the fixture gold set.

    Args:
        duplicate_of: The training sample one gold intent restates.

    Returns:
        Reviewed gold records on held-out structures.
    """

    def item(gold_id: str, spec_id: str, intent: str, pml: str) -> GoldItem:
        return GoldItem(
            gold_id=gold_id,
            spec_id=spec_id,
            intent=intent,
            reference_pml=pml,
            concept=None,
            drafted_by="claude-opus-5-5",
            reviewed_by="martin",
            reviewed=True,
        )

    return [
        item(
            "gold_001",
            "two_chains_hetatm",
            duplicate_of.intent.lower().rstrip(".") + " please",
            duplicate_of.plan_pml,
        ),
        item(
            "gold_002",
            "two_chains_hetatm",
            "make the zinc ions magenta",
            "color magenta, resn ZN\n",
        ),
        item(
            "gold_003",
            "three_states",
            "show residues 2 through 3 as sticks",
            "show sticks, resi 2-3\n",
        ),
    ]


def make_repo(root: Path, *, complete: bool = True) -> Repo:
    """Write a whole synthetic repository a split can be built from.

    Args:
        root: An empty directory to use as the repository root.
        complete: What the corpus report says about its run.

    Returns:
        Where everything was written.
    """
    corpus = _corpus()
    duplicate_of = next(
        s
        for s in corpus
        if s.structure.spec_id == TRAIN_SPECS[0]
        and s.category == "color/chain/single"
    )

    (root / "LICENSE").write_text(
        "BSD 3-Clause License\n\nCopyright (c) 2026, Test Fixture\n",
        encoding="utf-8",
    )
    configs = root / "configs" / "generation"
    configs.mkdir(parents=True)
    (configs / "corpus.json").write_text(
        json.dumps({"seed": SEED, "samples_target": 40}), encoding="utf-8"
    )
    (configs / "split.json").write_text(
        json.dumps(
            {
                "seed": SEED,
                "decontam": {
                    "method": "entity-gated-token-jaccard",
                    "threshold": 0.5,
                    "sensitivity": [0.3, 0.5, 0.7],
                },
                "audit": {"sample_size": AUDIT_SIZE, "seed": 7},
            }
        ),
        encoding="utf-8",
    )

    run = root / "data" / "samples" / f"seed-{SEED}-fixture"
    run.mkdir(parents=True)
    write_samples(run / "samples.jsonl", corpus)
    (run / "report.json").write_text(
        json.dumps(
            {
                "seed": SEED,
                "complete": complete,
                "attempted": len(corpus),
                "kept": len(corpus),
            }
        ),
        encoding="utf-8",
    )

    gold_dir = root / "src" / "pmc_data" / "gold"
    gold_dir.mkdir(parents=True)
    items = _gold(duplicate_of)
    write_gold_items(gold_dir / "gold_items.jsonl", items)
    write_samples(
        gold_dir / "gold_samples.jsonl",
        verify_gold(items, seed=SEED, executor=oracle_report),
    )
    return Repo(
        root=root,
        corpus=run,
        out=root / "data" / "splits",
        docs=root / "docs" / "dataset",
        duplicated_train_id=duplicate_of.sample_id,
    )
