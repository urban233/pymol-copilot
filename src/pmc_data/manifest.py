# Copyright 2026 PyMOL Copilot contributors.
"""The split's manifest and datasheet: what it is, where it came from.

The spec requires dataset artifacts to be content-addressed and to
carry a datasheet, manifest, license record, label audit and
regeneration configuration. This module writes and checks the first
four; `pmc_data.audit` fills in the fifth.

**Content addressing.** Every data file is recorded by SHA-256, byte
count and record count, and the split's identity is a digest over the
data files' hashes alone. The manifest itself is not part of that
identity, which is what lets the audit result be added to it later
without the split becoming a different split.

**Validation.** `validate_manifest` recomputes every hash from the
files on disk. A manifest is a claim about bytes, so it is only worth
something when that claim is checked rather than read.

**The datasheet** is rendered from the manifest, never written by hand,
so it cannot say something the manifest does not. Its structure
follows Gebru et al., "Datasheets for Datasets"
(https://arxiv.org/abs/1803.09010), and it states the split's limits
as plainly as its contents.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import hashlib
import json
from collections.abc import Mapping
from collections.abc import Sequence
from pathlib import Path
from typing import Any

#: The manifest schema's own version.
MANIFEST_VERSION = 1

#: The data files a split directory holds, in the order they are listed.
DATA_FILES = (
    "train.jsonl",
    "test_gold.jsonl",
    "heldout_synthetic.jsonl",
    "decontam_dropped.jsonl",
    "excluded.jsonl",
)

#: The top-level fields every manifest must carry.
REQUIRED_FIELDS = (
    "manifest_version",
    "split_id",
    "split_version",
    "files",
    "provenance",
    "counts",
    "license",
    "regeneration",
    "audit_plan",
    "audit",
    "previous_audits",
)

#: The provenance fields every manifest must carry.
REQUIRED_PROVENANCE = (
    "git_commit",
    "git_dirty",
    "corpus",
    "gold_items_sha256",
    "gold_samples_sha256",
    "gold_authorship",
    "versions",
    "pymol_wheel",
    "seed",
    "held_out_spec_ids",
    "decontam",
    "exclusions",
)


class InvalidManifestError(ValueError):
    """Raised when a manifest is incomplete or disagrees with its files."""


def sha256_of(path: Path) -> str:
    """Hash one file's bytes.

    Args:
        path: The file.

    Returns:
        The hex SHA-256 digest.
    """
    return hashlib.sha256(path.read_bytes()).hexdigest()


def file_record(path: Path) -> dict[str, Any]:
    """Describe one data file by its content.

    Args:
        path: The JSONL file.

    Returns:
        Its SHA-256, byte count and number of non-empty lines.
    """
    data = path.read_bytes()
    return {
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
        "records": sum(1 for line in data.splitlines() if line.strip()),
    }


def compute_split_id(files: Mapping[str, Mapping[str, Any]]) -> str:
    """Derive a split's identity from its data files' hashes alone.

    Args:
        files: The per-file records, keyed by file name.

    Returns:
        A short hex digest.
    """
    material = json.dumps(
        sorted((name, record["sha256"]) for name, record in files.items()),
        separators=(",", ":"),
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def write_json(path: Path, data: Mapping[str, Any]) -> None:
    """Write JSON deterministically, with a fixed newline.

    Args:
        path: The file to write.
        data: The mapping to serialize.
    """
    path.write_text(
        json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def read_manifest(path: Path) -> dict[str, Any]:
    """Read a manifest and check it carries every required field.

    Args:
        path: The manifest file.

    Returns:
        The manifest.

    Raises:
        InvalidManifestError: If the file is missing, is not a JSON
            object, or lacks a required field.
    """
    if not path.is_file():
        raise InvalidManifestError(f"{path} does not exist")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise InvalidManifestError(f"{path} is not valid JSON") from error
    if not isinstance(manifest, dict):
        raise InvalidManifestError(f"{path} must hold a JSON object")
    missing = [key for key in REQUIRED_FIELDS if key not in manifest]
    provenance = manifest.get("provenance", {})
    missing += [
        f"provenance.{key}"
        for key in REQUIRED_PROVENANCE
        if key not in provenance
    ]
    if missing:
        raise InvalidManifestError(f"{path}: missing fields: {missing}")
    return manifest


def validate_manifest(directory: Path) -> dict[str, Any]:
    """Recompute every hash a split directory's manifest claims.

    Args:
        directory: The split directory holding manifest.json and the
            data files.

    Returns:
        The manifest, once every claim in it has been checked.

    Raises:
        InvalidManifestError: If a field is missing, a file is missing
            or differs from its record, the split id does not follow
            from the files, or a recorded audit sheet has changed.
    """
    manifest = read_manifest(directory / "manifest.json")
    files = manifest["files"]
    if sorted(files) != sorted(DATA_FILES):
        raise InvalidManifestError(
            f"manifest lists {sorted(files)}, expected {sorted(DATA_FILES)}"
        )
    for name, record in files.items():
        path = directory / name
        if not path.is_file():
            raise InvalidManifestError(f"{name}: listed but missing")
        if file_record(path) != record:
            raise InvalidManifestError(f"{name}: does not match its record")
    if compute_split_id(files) != manifest["split_id"]:
        raise InvalidManifestError("split_id does not follow from the files")
    audit = manifest["audit"]
    if audit is not None:
        sheet = directory / "audit" / "sheet.jsonl"
        if not sheet.is_file() or sha256_of(sheet) != audit["sheet_sha256"]:
            raise InvalidManifestError(
                "the audit sheet is missing or changed since it was scored"
            )
    return manifest


def _table(rows: Sequence[Sequence[object]], header: Sequence[str]) -> str:
    """Render a small Markdown table.

    Args:
        rows: The body rows.
        header: The column names.

    Returns:
        The table text.
    """
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    lines += [
        "| " + " | ".join(str(cell) for cell in row) + " |" for row in rows
    ]
    return "\n".join(lines)


def _audit_section(audit: Mapping[str, Any] | None) -> str:
    """Render the label-audit section.

    Args:
        audit: The manifest's audit record, or None before scoring.

    Returns:
        The section body.
    """
    if audit is None:
        return (
            "Not yet performed. The audit sheet is drawn with "
            "`split_cli audit draw` and scored with `split_cli audit score` "
            "once every verdict is filled in; this section is rewritten "
            "then."
        )
    return (
        f"{audit['sample_size']} training labels were drawn at random "
        f"(seed {audit['seed']}) and judged by {audit['auditor']}.\n\n"
        f"- **Observed error rate: {audit['wrong']}/{audit['judged']} = "
        f"{audit['error_rate']:.3f}** (Wilson 95% interval "
        f"{audit['wilson_low']:.3f}-{audit['wilson_high']:.3f}), over the "
        f"{audit['judged']} labels judged correct or wrong.\n"
        f"- Unsure: {audit['unsure']}, reported separately and not "
        f"counted as either. If every unsure label were wrong, the rate "
        f"would be {audit['worst_case_rate']:.3f}.\n"
        f"- Sheet SHA-256: `{audit['sheet_sha256']}`."
    )


def _previous_section(previous: Sequence[Mapping[str, Any]]) -> str:
    """Render the audits of earlier, superseded split versions.

    Args:
        previous: One record per earlier version, oldest first.

    Returns:
        The subsection, or nothing when there is no earlier version.
    """
    if not previous:
        return ""
    lines = [
        "\n\nEarlier split versions, superseded by this one and kept in "
        "`docs/dataset/history/`:\n"
    ]
    for record in previous:
        audit = record["audit"]
        result = (
            "not audited"
            if audit is None
            else (
                f"{audit['wrong']}/{audit['judged']} wrong = "
                f"{audit['error_rate']:.3f} (Wilson 95% interval "
                f"{audit['wilson_low']:.3f}-{audit['wilson_high']:.3f}), "
                f"judged by {audit['auditor']}"
            )
        )
        lines.append(
            f"- Split version {record['split_version']} "
            f"(`{record['split_id']}`): {result}."
        )
    return "\n".join(lines)


def render_datasheet(manifest: Mapping[str, Any]) -> str:
    """Render the datasheet for one manifest.

    Args:
        manifest: A complete manifest.

    Returns:
        The datasheet, as Markdown.
    """
    provenance = manifest["provenance"]
    counts = manifest["counts"]
    decontam = provenance["decontam"]
    license_record = manifest["license"]
    files = manifest["files"]
    authorship = provenance["gold_authorship"]
    held_out = ", ".join(f"`{s}`" for s in provenance["held_out_spec_ids"])
    earlier = _previous_section(manifest["previous_audits"])
    exclusions = provenance["exclusions"]
    excluded = (
        ", ".join(f"`{name}`" for name in exclusions["representations"])
        or "none"
    )
    split_rows = [
        (
            name,
            files[name]["records"],
            f"`{files[name]['sha256'][:16]}…`",
        )
        for name in DATA_FILES
    ]
    sensitivity = ", ".join(
        f"{threshold}: {dropped}"
        for threshold, dropped in sorted(decontam["sensitivity"].items())
    )
    versions = ", ".join(
        f"{key}={value}"
        for key, value in sorted(provenance["versions"].items())
    )
    commands = "\n".join(manifest["regeneration"]["commands"])
    configs = "\n".join(
        f"- `{path}`: `{digest}`"
        for path, digest in sorted(manifest["regeneration"]["configs"].items())
    )
    dirty = (
        "\n\n> **Built from a dirty working tree.** This split cannot be "
        "reproduced from the recorded commit alone."
        if provenance["git_dirty"]
        else ""
    )
    return f"""# Datasheet: PyMOL-Copilot dataset split `{manifest["split_id"]}`

Rendered from `manifest.json` by `pmc_data.manifest`; do not edit by
hand. Split version {manifest["split_version"]}, built from commit
`{provenance["git_commit"]}`.{dirty}

## Motivation

This split trains and evaluates a small local model that turns a
structural biologist's natural-language intent into a restricted,
verified PyMOL command plan (master plan items 15-17). It exists so
the offline evaluation measures generalization to structures the model
never saw, on intents a person wrote rather than a template.

## Composition

{_table(split_rows, ("File", "Records", "SHA-256"))}

- **`train.jsonl`** -- corpus samples on training structures, after
  decontamination. {counts["train"]["categories"]} categories.
- **`test_gold.jsonl`** -- the test split: {files["test_gold.jsonl"]["records"]}
  hand-reviewed gold items, all on held-out structures, covering every
  supported verb set, verb-term pair and boolean shape.
- **`heldout_synthetic.jsonl`** -- corpus samples on held-out
  structures, with templated intents. A secondary evaluation set:
  structure-held-out, but not intent-held-out.
- **`decontam_dropped.jsonl`** -- training samples removed because their
  intent near-duplicated a gold intent, each with the gold item it
  matched.
- **`excluded.jsonl`** -- corpus samples removed from both sides
  because their plan uses an excluded representation.

Each sample carries its structure identity and checksum, every
contract version, the canonical plan, the prompt as the model sees it,
the assertions evaluated, the assertions that could not be, and the
executor's verification record.

## Collection process

- **Structures** are {provenance["corpus"]["structure_count"]} controlled
  structures authored in code by `pmc_data.structures` at seed
  {provenance["seed"]}. No PDB or wwPDB-derived data is included.
- **Training labels** are program-first: `pmc_data.taxonomy` enumerates
  a plan, the oracle in `pmc_data.oracle` predicts its result without
  PyMOL, and the plan is executed by real headless Open-Source PyMOL
  ({provenance["pymol_wheel"]}) in a fresh sidecar. A sample is kept
  only if PyMOL agrees with the oracle.
- **Training intents are templated** from the plan, not written by a
  person or a teacher model.
- **Gold intents** were drafted by {_authors(authorship["drafted_by"])} and
  reviewed and edited by {_authors(authorship["reviewed_by"])}. Every gold
  reference plan passed the same oracle-and-PyMOL verification.
- Contract versions: {versions}.

## Preprocessing

- **Split by source structure.** Held out: {held_out}. Every
  structural feature appears on both sides. No held-out structure's
  spec, snapshot hash or structure digest appears in training.
- **Excluded representations: {excluded}.** {counts["excluded"]} corpus
  samples whose plan shows or hides one were removed from training and
  from `heldout_synthetic` alike. Reason: {exclusions["reason"]}.
- **Decontamination** (`{decontam["method"]}`, threshold
  {decontam["threshold"]}) dropped {counts["decontam_dropped"]} training
  samples whose intent names the same entities as a gold intent and is
  worded almost the same. Drop counts at other thresholds: {sensitivity}.
- **Training is decontaminated against gold intents only.** The
  templated intents repeat across structures, so counting the
  held-out templated intents as test intents would drop
  {counts["template_overlap"]} of {counts["train_candidates"]} training
  candidates on exact normalized match alone. `heldout_synthetic` is
  therefore reported as structure-held-out only.

## Label audit

{_audit_section(manifest["audit"])}{earlier}

## Uses

Fine-tuning (item 17) trains on `train.jsonl` only. The offline
evaluation (item 16) reports on `test_gold.jsonl`, with
`heldout_synthetic.jsonl` as a secondary structure-generalization
figure. Neither evaluation file may be used for training, prompt
selection or model selection.

## Distribution and license

- Code: {license_record["code"]}
- Structures: {license_record["structures"]}
- PyMOL: {_first_line(license_record["pymol"])}
- Gold intents: {license_record["gold_intents"]}
- Teacher outputs: {license_record["teacher_outputs"]}
- Publication: {license_record["publication"]}

## Maintenance and regeneration

The split is immutable once inspected: changing the held-out set
requires bumping `SPLIT_VERSION`. Regenerate with:

```
{commands}
```

Configuration files, by SHA-256:

{configs}

## Limits

- **Training intents are templated.** A model can learn the templates'
  phrasing; the gold set measures whether it handles anything else.
- **The structures are synthetic and backbone-only.** They share one
  residue vocabulary (ALA, SER, GLY, VAL, LEU, with ZN and HOH), carry
  no side chains, and have no ligand chemistry, so domain words like
  "side chain" or "ligand pocket" cannot be graded.
- **The split is by spec, not by sequence cluster.** It tests
  generalization across feature combinations and coordinates, not to
  new chemistry.
- **Gold intents were drafted by a model** and then reviewed by a
  person, which is weaker independence than intents written from
  scratch by a structural biologist.
"""


def _authors(counts: Mapping[str, int]) -> str:
    """Name who did something, with how many items each did.

    Args:
        counts: Items per person or model.

    Returns:
        The names with their counts, or "nobody".
    """
    if not counts:
        return "nobody"
    return ", ".join(f"`{who}` ({n})" for who, n in sorted(counts.items()))


def _first_line(text: str) -> str:
    """Shorten a multi-line record to its first line for the datasheet.

    PyMOL's wheel states its license as the whole multi-line notice. The
    manifest keeps all of it; the datasheet's list item shows the first
    line and says where the rest is.

    Args:
        text: The recorded text.

    Returns:
        The text itself if it is one line, else its first line and a
        pointer to the full text.
    """
    lines = text.splitlines()
    if len(lines) <= 1:
        return text
    return f"{lines[0].strip()} (full text recorded in manifest.json)"
