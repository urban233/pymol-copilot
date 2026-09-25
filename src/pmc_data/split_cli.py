# Copyright 2026 PyMOL Copilot contributors.
"""Build the held-out split, its manifest and datasheet, and the audit.

Three subcommands:

    bazel run //src/pmc_data:split_cli -- build \\
        --corpus data/samples/seed-20260921-<identity>
    bazel run //src/pmc_data:split_cli -- audit draw \\
        --split data/splits/split-<id>
    bazel run //src/pmc_data:split_cli -- audit score \\
        --split data/splits/split-<id> --auditor martin

`build` divides a completed corpus run and the committed gold set into
`train`, `test_gold`, `heldout_synthetic`, `decontam_dropped` and
`excluded`, and
writes them under `data/splits/split-<id>/` with `manifest.json` and
`DATASHEET.md`. The id is a digest of the data files, so the same inputs
land in the same directory; an existing split is never overwritten.
The manifest and datasheet are also copied to `docs/dataset/`, which is
committed -- the split itself is not.

`audit draw` writes the audit sheet a person fills in; `audit score`
turns the filled sheet into the observed error rate, records it in the
manifest and datasheet, and copies the sheet and result to
`docs/dataset/audit/`.

The build refuses a dirty working tree unless `--allow-dirty` is given,
and then records that it was dirty: a split whose recorded commit does
not contain its inputs cannot be regenerated from that record.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import argparse
import json
import os
import secrets
import shutil
import subprocess
import sys
from collections import Counter
from collections.abc import Sequence
from importlib import metadata
from pathlib import Path
from typing import Any

from pmc_data.audit import InvalidAuditError
from pmc_data.audit import draw
from pmc_data.audit import read_sheet
from pmc_data.audit import score
from pmc_data.audit import sheet_rows
from pmc_data.audit import write_sheet
from pmc_data.gold_set import GoldItem
from pmc_data.gold_set import load_gold_items
from pmc_data.manifest import DATA_FILES
from pmc_data.manifest import MANIFEST_VERSION
from pmc_data.manifest import compute_split_id
from pmc_data.manifest import file_record
from pmc_data.manifest import render_datasheet
from pmc_data.manifest import sha256_of
from pmc_data.manifest import validate_manifest
from pmc_data.manifest import write_json
from pmc_data.sample import PINNED_PYMOL_WHEEL
from pmc_data.sample import Sample
from pmc_data.sample import read_samples
from pmc_data.sample import to_json_line
from pmc_data.sample import write_samples
from pmc_data.split import HELD_OUT_SPEC_IDS
from pmc_data.split import SPLIT_VERSION
from pmc_data.split import InvalidSplitError
from pmc_data.split import SplitConfig
from pmc_data.split import SplitResult
from pmc_data.split import build_split
from pmc_data.split import load_split_config
from pmc_data.structures import enumerate_structures

#: The repository root, resolved the way Bazel's own `bazel run`
#: convention expects so output lands in the real source tree.
REPO_ROOT = Path(
    os.environ.get(
        "BUILD_WORKSPACE_DIRECTORY", Path(__file__).resolve().parents[2]
    )
)

DEFAULT_OUT = Path("data") / "splits"
DEFAULT_DOCS = Path("docs") / "dataset"
DEFAULT_CONFIG = Path("configs") / "generation" / "split.json"
DEFAULT_CORPUS_CONFIG = Path("configs") / "generation" / "corpus.json"
DEFAULT_GOLD_ITEMS = Path("src") / "pmc_data" / "gold" / "gold_items.jsonl"
DEFAULT_GOLD_SAMPLES = Path("src") / "pmc_data" / "gold" / "gold_samples.jsonl"

#: The distribution whose license the manifest records.
PYMOL_DISTRIBUTION = "pymol-open-source-whl"

#: The exit code for a refusal: the inputs were not trustworthy, so
#: nothing was written.
_EXIT_REFUSED = 1


def _resolve(path: Path) -> Path:
    """Resolve a command-line path against the repository root.

    Args:
        path: The path as given.

    Returns:
        The path itself if absolute, else under REPO_ROOT.
    """
    return path if path.is_absolute() else REPO_ROOT / path


def _relative(path: Path) -> str:
    """Render a path relative to the repository root when it is inside it.

    Args:
        path: The path.

    Returns:
        A repository-relative POSIX path, or the path unchanged.
    """
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def git_state(root: Path) -> tuple[str, bool]:
    """Read the commit and whether the working tree is dirty.

    Args:
        root: The repository root.

    Returns:
        The HEAD commit and True when `git status` reports anything.
    """
    commit = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return commit, bool(status.strip())


def pymol_license() -> str:
    """Record PyMOL's license as its installed wheel states it.

    Read from the distribution's own metadata rather than written here,
    so the record cannot drift from what was actually installed.

    Returns:
        The distribution, version, license field and license
        classifiers, or a plain statement that none could be read.
    """
    try:
        info = metadata.metadata(PYMOL_DISTRIBUTION)
    except metadata.PackageNotFoundError:
        return (
            f"unrecorded: {PYMOL_DISTRIBUTION} metadata was not found in "
            "the environment that built this split"
        )
    stated = info.get("License-Expression") or info.get("License") or "none"
    classifiers = [
        value
        for value in info.get_all("Classifier") or []
        if value.startswith("License")
    ]
    return (
        f"{PYMOL_DISTRIBUTION} {info.get('Version')}, as its wheel metadata "
        f"states: License: {stated}; classifiers: "
        f"{'; '.join(classifiers) or 'none'}"
    )


def code_license(root: Path) -> str:
    """Record the repository's own license from its LICENSE file.

    Args:
        root: The repository root.

    Returns:
        The license name and copyright line.
    """
    lines = [
        line.strip()
        for line in (root / "LICENSE").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return f"{lines[0]}; {lines[1]} (LICENSE)"


def _counts(samples: Sequence[Sample]) -> dict[str, Any]:
    """Count one split part by category and difficulty.

    Args:
        samples: The part's samples.

    Returns:
        The total, distinct category count and both breakdowns.
    """
    categories = Counter(sample.category for sample in samples)
    return {
        "total": len(samples),
        "categories": len(categories),
        "by_category": dict(sorted(categories.items())),
        "by_difficulty": dict(
            sorted(Counter(sample.difficulty for sample in samples).items())
        ),
    }


def _single_versions(samples: Sequence[Sample]) -> dict[str, Any]:
    """Read the one set of contract versions every sample shares.

    Args:
        samples: Every sample in the split.

    Returns:
        The shared versions.

    Raises:
        InvalidSplitError: If the samples were made under more than one
            set of contracts, which would make every downstream number
            a blend of incompatible prompts.
    """
    found = {
        json.dumps(sample.versions.to_dict(), sort_keys=True)
        for sample in samples
    }
    if len(found) != 1:
        raise InvalidSplitError(
            f"samples carry {len(found)} different contract version sets"
        )
    return json.loads(found.pop())


def previous_audits(docs: Path) -> list[dict[str, Any]]:
    """Collect the audits of earlier split versions kept in history.

    Args:
        docs: The committed dataset documentation directory.

    Returns:
        One record per earlier version, ordered by split version.
    """
    records: list[dict[str, Any]] = []
    for path in sorted((docs / "history").glob("*/manifest.json")):
        earlier = json.loads(path.read_text(encoding="utf-8"))
        records.append(
            {
                "split_id": earlier["split_id"],
                "split_version": earlier["split_version"],
                "audit": earlier["audit"],
            }
        )
    return sorted(records, key=lambda record: record["split_version"])


def build_manifest(
    *,
    result: SplitResult,
    files: dict[str, dict[str, Any]],
    config: SplitConfig,
    config_path: Path,
    corpus_dir: Path,
    corpus_report: dict[str, Any],
    gold_items: Sequence[GoldItem],
    gold_items_path: Path,
    gold_samples_path: Path,
    git: tuple[str, bool],
    root: Path,
    previous: list[dict[str, Any]],
) -> dict[str, Any]:
    """Assemble the manifest for one built split.

    Args:
        result: The split.
        files: The per-file records.
        config: The split settings.
        config_path: Where they were read from.
        corpus_dir: The corpus run directory.
        corpus_report: That run's report.json.
        gold_items: The gold records.
        gold_items_path: Where they were read from.
        gold_samples_path: Where the gold samples were read from.
        git: The commit and whether the tree was dirty.
        root: The repository root, for the license file.
        previous: The audits of earlier split versions.

    Returns:
        The manifest, with no audit yet.
    """
    commit, dirty = git
    everything = (
        *result.train,
        *result.test_gold,
        *result.heldout_synthetic,
        *(sample for sample, _ in result.dropped),
        *result.excluded,
    )
    drafters = Counter(item.drafted_by for item in gold_items)
    reviewers = Counter(
        item.reviewed_by for item in gold_items if item.reviewed_by
    )
    corpus_config = _resolve(DEFAULT_CORPUS_CONFIG)
    return {
        "manifest_version": MANIFEST_VERSION,
        "split_id": compute_split_id(files),
        "split_version": SPLIT_VERSION,
        "files": files,
        "provenance": {
            "git_commit": commit,
            "git_dirty": dirty,
            "corpus": {
                "directory": corpus_dir.name,
                "report_sha256": sha256_of(corpus_dir / "report.json"),
                "samples_sha256": sha256_of(corpus_dir / "samples.jsonl"),
                "seed": corpus_report["seed"],
                "attempted": corpus_report["attempted"],
                "kept": corpus_report["kept"],
                "structure_count": len(enumerate_structures(config.seed)),
            },
            "gold_items_sha256": sha256_of(gold_items_path),
            "gold_samples_sha256": sha256_of(gold_samples_path),
            "gold_authorship": {
                "drafted_by": dict(sorted(drafters.items())),
                "reviewed_by": dict(sorted(reviewers.items())),
            },
            "versions": _single_versions(everything),
            "pymol_wheel": PINNED_PYMOL_WHEEL,
            "seed": config.seed,
            "held_out_spec_ids": sorted(HELD_OUT_SPEC_IDS),
            "decontam": {
                "method": config.decontam_method,
                "threshold": config.decontam_threshold,
                "sensitivity": dict(result.sensitivity),
            },
            "exclusions": {
                "representations": list(config.excluded_representations),
                "reason": config.exclusion_reason or "none",
            },
        },
        "counts": {
            "train": _counts(result.train),
            "test_gold": _counts(result.test_gold),
            "heldout_synthetic": _counts(result.heldout_synthetic),
            "decontam_dropped": len(result.dropped),
            "excluded": len(result.excluded),
            "train_candidates": len(result.train) + len(result.dropped),
            "template_overlap": result.template_overlap,
        },
        "license": {
            "code": code_license(root),
            "structures": (
                "authored synthetically in this repository by "
                "pmc_data.structures; no PDB or wwPDB-derived data"
            ),
            "pymol": pymol_license(),
            "gold_intents": (
                "written for this repository: drafted by "
                + ", ".join(sorted(drafters))
                + " and reviewed and edited by "
                + (", ".join(sorted(reviewers)) or "nobody")
            ),
            "teacher_outputs": (
                "none; training intents are templated by pmc_data.taxonomy"
            ),
            "publication": (
                "none planned; SPECIFICATION.md records that no publication "
                "is planned for this deliverable"
            ),
        },
        "regeneration": {
            "commands": [
                "bazel run //src/pmc_data:corpus_cli -- --config "
                f"{_relative(corpus_config)}",
                "bazel run //src/pmc_data:gold_cli",
                "bazel run //src/pmc_data:split_cli -- build --corpus "
                f"{_relative(corpus_dir)}",
            ],
            "configs": {
                _relative(corpus_config): sha256_of(corpus_config),
                _relative(config_path): sha256_of(config_path),
            },
        },
        "audit_plan": {
            "sample_size": config.audit_sample_size,
            "seed": config.audit_seed,
        },
        "audit": None,
        "previous_audits": previous,
    }


def _write_parts(directory: Path, result: SplitResult) -> None:
    """Write the four data files of a split.

    Args:
        directory: The directory to write into.
        result: The split.
    """
    write_samples(directory / "train.jsonl", result.train)
    write_samples(directory / "test_gold.jsonl", result.test_gold)
    write_samples(
        directory / "heldout_synthetic.jsonl", result.heldout_synthetic
    )
    write_samples(directory / "excluded.jsonl", result.excluded)
    with (directory / "decontam_dropped.jsonl").open(
        "w", encoding="utf-8", newline="\n"
    ) as handle:
        for sample, match in result.dropped:
            line = {
                "gold_id": match.gold_id,
                "score": match.score,
                "sample": json.loads(to_json_line(sample)),
            }
            handle.write(
                json.dumps(line, sort_keys=True, separators=(",", ":")) + "\n"
            )


def _publish(directory: Path, docs: Path) -> None:
    """Copy the committed parts of a split directory into docs.

    Args:
        directory: The split directory.
        docs: The committed dataset documentation directory.
    """
    docs.mkdir(parents=True, exist_ok=True)
    for name in ("manifest.json", "DATASHEET.md"):
        shutil.copyfile(directory / name, docs / name)
    audit = directory / "audit"
    if (audit / "result.json").is_file():
        (docs / "audit").mkdir(exist_ok=True)
        for name in ("sheet.jsonl", "sheet.md", "result.json"):
            shutil.copyfile(audit / name, docs / "audit" / name)


def run_build(args: argparse.Namespace, git: tuple[str, bool]) -> int:
    """Build a split and its manifest.

    Args:
        args: The parsed build arguments.
        git: The commit and whether the tree is dirty.

    Returns:
        The process exit code.
    """
    if git[1] and not args.allow_dirty:
        print(
            "REFUSED: the working tree is dirty; commit first, or pass "
            "--allow-dirty to build a split the manifest marks as dirty",
            file=sys.stderr,
        )
        return _EXIT_REFUSED
    config_path = _resolve(args.config)
    config = load_split_config(config_path)
    corpus_dir = _resolve(args.corpus)
    report = json.loads((corpus_dir / "report.json").read_text("utf-8"))
    if report.get("seed") != config.seed:
        print(
            f"REFUSED: the corpus seed {report.get('seed')} is not the "
            f"split's seed {config.seed}",
            file=sys.stderr,
        )
        return _EXIT_REFUSED
    gold_items_path = _resolve(args.gold_items)
    gold_samples_path = _resolve(args.gold_samples)
    gold_items = load_gold_items(gold_items_path)
    try:
        result = build_split(
            corpus=read_samples(corpus_dir / "samples.jsonl"),
            corpus_complete=bool(report.get("complete")),
            gold_items=gold_items,
            gold_samples=read_samples(gold_samples_path),
            config=config,
        )
    except InvalidSplitError as error:
        print(f"REFUSED: {error}", file=sys.stderr)
        return _EXIT_REFUSED

    out = _resolve(args.out)
    out.mkdir(parents=True, exist_ok=True)
    staging = out / f".split.{secrets.token_hex(4)}.incomplete"
    staging.mkdir()
    _write_parts(staging, result)
    files = {name: file_record(staging / name) for name in DATA_FILES}
    manifest = build_manifest(
        result=result,
        files=files,
        config=config,
        config_path=config_path,
        corpus_dir=corpus_dir,
        corpus_report=report,
        gold_items=gold_items,
        gold_items_path=gold_items_path,
        gold_samples_path=gold_samples_path,
        git=git,
        root=REPO_ROOT,
        previous=previous_audits(_resolve(args.docs)),
    )
    write_json(staging / "manifest.json", manifest)
    (staging / "DATASHEET.md").write_text(
        render_datasheet(manifest), encoding="utf-8", newline="\n"
    )
    validate_manifest(staging)

    final = out / f"split-{manifest['split_id']}"
    if final.exists():
        # The id is a digest of the data files, so an existing directory
        # of the same name holds the same data. It is kept, with the
        # manifest it was first frozen with, and nothing is replaced.
        shutil.rmtree(staging)
        validate_manifest(final)
        print(f"UNCHANGED {final}: this split already exists")
        return 0
    staging.replace(final)
    _publish(final, _resolve(args.docs))
    counts = manifest["counts"]
    print(
        f"train={counts['train']['total']} "
        f"test_gold={counts['test_gold']['total']} "
        f"heldout_synthetic={counts['heldout_synthetic']['total']} "
        f"decontam_dropped={counts['decontam_dropped']} "
        f"excluded={counts['excluded']}"
    )
    print(f"WROTE {final}")
    return 0


def _drawn(split: Path, manifest: dict[str, Any]) -> tuple[Sample, ...]:
    """Re-derive the audit draw from the split and its recorded plan.

    Args:
        split: The split directory.
        manifest: Its manifest.

    Returns:
        The drawn samples.
    """
    plan = manifest["audit_plan"]
    return draw(
        read_samples(split / "train.jsonl"),
        size=plan["sample_size"],
        seed=plan["seed"],
    )


def run_audit_draw(args: argparse.Namespace) -> int:
    """Write the audit sheet for a split.

    Args:
        args: The parsed arguments.

    Returns:
        The process exit code.
    """
    split = _resolve(args.split)
    manifest = validate_manifest(split)
    sheet = split / "audit" / "sheet.jsonl"
    if sheet.exists():
        print(
            f"REFUSED: {sheet} already exists; it may hold verdicts",
            file=sys.stderr,
        )
        return _EXIT_REFUSED
    write_sheet(split / "audit", sheet_rows(_drawn(split, manifest)))
    print(f"WROTE {sheet} and {sheet.with_suffix('.md')}")
    return 0


def run_audit_score(args: argparse.Namespace) -> int:
    """Score a filled audit sheet and record the result.

    Args:
        args: The parsed arguments.

    Returns:
        The process exit code.
    """
    split = _resolve(args.split)
    manifest = validate_manifest(split)
    sheet = split / "audit" / "sheet.jsonl"
    try:
        result = score(
            read_sheet(sheet),
            drawn_ids=[s.sample_id for s in _drawn(split, manifest)],
        )
    except InvalidAuditError as error:
        print(f"REFUSED: {error}", file=sys.stderr)
        return _EXIT_REFUSED
    record = {
        **result.to_dict(),
        "seed": manifest["audit_plan"]["seed"],
        "auditor": args.auditor,
        "sheet_sha256": sha256_of(sheet),
    }
    write_json(split / "audit" / "result.json", record)
    manifest["audit"] = record
    write_json(split / "manifest.json", manifest)
    (split / "DATASHEET.md").write_text(
        render_datasheet(manifest), encoding="utf-8", newline="\n"
    )
    validate_manifest(split)
    _publish(split, _resolve(args.docs))
    print(
        f"error rate {result.wrong}/{result.judged} = {result.error_rate:.3f} "
        f"(Wilson 95% {result.wilson_low:.3f}-{result.wilson_high:.3f}); "
        f"unsure {result.unsure}"
    )
    return 0


def _parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse this binary's command line.

    Args:
        argv: The arguments after the program name.

    Returns:
        The parsed arguments.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)

    build = commands.add_parser("build", help="build a split")
    build.add_argument("--corpus", type=Path, required=True)
    build.add_argument("--out", type=Path, default=DEFAULT_OUT)
    build.add_argument("--docs", type=Path, default=DEFAULT_DOCS)
    build.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    build.add_argument("--gold-items", type=Path, default=DEFAULT_GOLD_ITEMS)
    build.add_argument(
        "--gold-samples", type=Path, default=DEFAULT_GOLD_SAMPLES
    )
    build.add_argument("--allow-dirty", action="store_true")

    audit = commands.add_parser("audit", help="draw or score the audit")
    steps = audit.add_subparsers(dest="step", required=True)
    audit_draw = steps.add_parser("draw", help="write the audit sheet")
    audit_draw.add_argument("--split", type=Path, required=True)
    audit_score = steps.add_parser("score", help="score the filled sheet")
    audit_score.add_argument("--split", type=Path, required=True)
    audit_score.add_argument("--auditor", required=True)
    audit_score.add_argument("--docs", type=Path, default=DEFAULT_DOCS)
    return parser.parse_args(argv)


def run(argv: list[str], *, git: tuple[str, bool] | None = None) -> int:
    """Dispatch one subcommand.

    Args:
        argv: The arguments after the program name.
        git: The commit and dirty flag to record; read from the
            repository when None.

    Returns:
        The process exit code.
    """
    args = _parse_args(argv)
    if args.command == "build":
        return run_build(args, git if git is not None else git_state(REPO_ROOT))
    if args.step == "draw":
        return run_audit_draw(args)
    return run_audit_score(args)


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
