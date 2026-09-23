# Copyright 2026 PyMOL Copilot contributors.
"""The manifest checks its own claims, and the datasheet states its limits.

A manifest is a claim about bytes, so the validator is tested by
changing bytes. The datasheet is rendered from the manifest, so it is
tested for the statements the spec requires it to make.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import json
from pathlib import Path

import pytest

from split_fixture import GIT_CLEAN
from split_fixture import make_repo
from pmc_data import manifest as manifest_module
from pmc_data import split_cli
from pmc_data.manifest import REQUIRED_FIELDS
from pmc_data.manifest import REQUIRED_PROVENANCE
from pmc_data.manifest import InvalidManifestError
from pmc_data.manifest import read_manifest
from pmc_data.manifest import validate_manifest


@pytest.fixture
def split(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Build a fixture split and return its directory.

    Args:
        tmp_path: Scratch directory.
        monkeypatch: Re-roots the binary.

    Returns:
        The split directory.
    """
    repo = make_repo(tmp_path)
    monkeypatch.setattr(split_cli, "REPO_ROOT", tmp_path)
    assert (
        split_cli.run(["build", "--corpus", str(repo.corpus)], git=GIT_CLEAN)
        == 0
    )
    (found,) = repo.out.glob("split-*")
    return found


def test_a_fresh_split_validates(split: Path) -> None:
    """What the build wrote is exactly what its manifest claims."""
    manifest = validate_manifest(split)

    assert split.name == f"split-{manifest['split_id']}"


@pytest.mark.parametrize(
    "name", ["train.jsonl", "test_gold.jsonl", "decontam_dropped.jsonl"]
)
def test_validator_catches_a_flipped_byte(split: Path, name: str) -> None:
    """Changing one byte of any data file fails validation.

    Args:
        split: The fixture split.
        name: The file to tamper with.
    """
    path = split / name
    data = bytearray(path.read_bytes())
    data[len(data) // 2] ^= 0x01
    path.write_bytes(bytes(data))

    with pytest.raises(InvalidManifestError, match=name):
        validate_manifest(split)


def test_validator_catches_a_forged_split_id(split: Path) -> None:
    """A split id that does not follow from the files is refused."""
    path = split / "manifest.json"
    manifest = json.loads(path.read_text("utf-8"))
    manifest["split_id"] = "0" * 16
    path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(InvalidManifestError, match="split_id"):
        validate_manifest(split)


def test_every_required_field_is_present(split: Path) -> None:
    """The manifest carries content hash, provenance, license and regeneration."""
    manifest = read_manifest(split / "manifest.json")

    assert set(REQUIRED_FIELDS) <= set(manifest)
    assert set(REQUIRED_PROVENANCE) <= set(manifest["provenance"])
    assert set(manifest["license"]) == {
        "code",
        "structures",
        "pymol",
        "gold_intents",
        "teacher_outputs",
        "publication",
    }
    assert manifest["license"]["code"].startswith("BSD 3-Clause License")
    assert manifest["provenance"]["gold_authorship"] == {
        "drafted_by": {"claude-opus-5-5": 3},
        "reviewed_by": {"martin": 3},
    }
    assert manifest["regeneration"]["commands"]
    assert manifest["regeneration"]["configs"]


@pytest.mark.parametrize("field", REQUIRED_FIELDS)
def test_a_missing_field_is_refused(split: Path, field: str) -> None:
    """A manifest missing any required field is not read.

    Args:
        split: The fixture split.
        field: The field to remove.
    """
    path = split / "manifest.json"
    manifest = json.loads(path.read_text("utf-8"))
    del manifest[field]
    path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(InvalidManifestError, match=field):
        read_manifest(path)


def test_a_multi_line_license_stays_one_list_item() -> None:
    """A license notice spanning lines is shortened, never spliced in raw."""
    assert manifest_module._first_line("Notice\n  line two\n") == (
        "Notice (full text recorded in manifest.json)"
    )
    assert manifest_module._first_line("BSD") == "BSD"


def test_datasheet_states_the_limits(split: Path) -> None:
    """The datasheet says what the split does not establish."""
    text = (split / "DATASHEET.md").read_text("utf-8")

    for phrase in (
        "Training intents are templated",
        "synthetic and backbone-only",
        "by spec, not by sequence cluster",
        "drafted by a model",
        "decontaminated against gold intents only",
        "No PDB or wwPDB-derived data",
        "Not yet performed",
    ):
        assert phrase.lower() in text.lower(), phrase


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
