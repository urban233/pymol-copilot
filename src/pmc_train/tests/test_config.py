# Copyright 2026 PyMOL Copilot contributors.
"""The training config is read strictly and identifies its run.

A config field nobody reads, or a default nobody wrote down, would let
a run train on settings its committed file does not show. So every
field is required, every unknown field is refused, and the file's
exact bytes name the run.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from pmc_train.config import DEFAULT_CONFIG
from pmc_train.config import InvalidConfigError
from pmc_train.config import config_sha256
from pmc_train.config import load_config
from pmc_train.config import parse_config
from pmc_train.config import run_id

ROOT = Path(__file__).resolve().parents[3]
COMMITTED = ROOT / DEFAULT_CONFIG


def _raw() -> dict[str, Any]:
    """Decode the committed config.

    Returns:
        Its JSON object.
    """
    return json.loads(COMMITTED.read_text(encoding="utf-8"))


def test_committed_config_loads() -> None:
    """The committed config parses, with the settings the plan fixed."""
    config = load_config(COMMITTED)
    assert config.max_seq_length == 16384
    assert config.chat_template_date == "26 Jul 2024"
    assert config.export.quantization == "Q4_K_M"
    assert config.export.llama_cpp_tag == "b10707"
    assert config.seed != config.data_seed


def test_split_is_the_committed_one() -> None:
    """The config trains on the split the dataset manifest froze."""
    manifest = json.loads(
        (ROOT / "docs" / "dataset" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    config = load_config(COMMITTED)
    assert config.split.split_id == manifest["split_id"]
    assert config.split.dir.name == f"split-{manifest['split_id']}"


def test_base_gguf_is_the_baseline_one() -> None:
    """The export is checked against the GGUF the baseline ran."""
    baseline = json.loads(
        (ROOT / "configs" / "evaluation" / "baseline.json").read_text(
            encoding="utf-8"
        )
    )
    gguf = load_config(COMMITTED).export.base_gguf
    provenance = baseline["engine_provenance"]
    assert gguf.sha256 == provenance["gguf_sha256"]
    assert gguf.revision == provenance["hf_revision"]
    assert f"{gguf.repo}:{gguf.file}" == baseline["engine"]["checkpoint"]


@pytest.mark.parametrize(
    "path",
    [
        ("seed",),
        ("lora", "r"),
        ("optimizer", "epochs"),
        ("export", "base_gguf"),
    ],
)
def test_missing_field_is_refused(path: tuple[str, ...]) -> None:
    """Removing any field, at any level, is refused."""
    data = _raw()
    parent = data
    for key in path[:-1]:
        parent = parent[key]
    del parent[path[-1]]
    with pytest.raises(InvalidConfigError, match="missing"):
        parse_config(data)


@pytest.mark.parametrize("where", [(), ("lora",), ("export", "base_gguf")])
def test_unknown_field_is_refused(where: tuple[str, ...]) -> None:
    """An unknown field, at any level, is refused."""
    data = _raw()
    parent = data
    for key in where:
        parent = parent[key]
    parent["packing"] = True
    with pytest.raises(InvalidConfigError, match="unknown"):
        parse_config(data)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("seed",), "1"),
        (("max_seq_length",), 16384.0),
        (("lora", "dropout"), None),
        (("optimizer", "epochs"), True),
        (("lora", "target_modules"), []),
        (("max_seq_length",), 0),
        (("precision",), "fp16"),
        (("optimizer", "warmup_ratio"), 1.0),
        (("optimizer", "warmup_ratio"), -0.1),
        (("lora", "dropout"), 1.0),
        (("optimizer", "weight_decay"), -0.01),
    ],
)
def test_bad_value_is_refused(path: tuple[str, ...], value: object) -> None:
    """A wrong type or an out-of-range value is refused."""
    data = copy.deepcopy(_raw())
    parent = data
    for key in path[:-1]:
        parent = parent[key]
    parent[path[-1]] = value
    with pytest.raises(InvalidConfigError):
        parse_config(data)


def test_hash_is_stable_and_byte_sensitive(tmp_path: Path) -> None:
    """The config hash is the file's bytes; one byte changes it."""
    copy_path = tmp_path / "config.json"
    copy_path.write_bytes(COMMITTED.read_bytes())
    assert config_sha256(copy_path) == config_sha256(COMMITTED)
    copy_path.write_bytes(COMMITTED.read_bytes() + b"\n")
    assert config_sha256(copy_path) != config_sha256(COMMITTED)


def test_run_id_depends_on_every_input() -> None:
    """Changing the config, the split or the commit changes the run id."""
    base = run_id("a" * 64, "e4599620801af592", "c" * 40)
    assert len(base) == 16
    assert base == run_id("a" * 64, "e4599620801af592", "c" * 40)
    assert base != run_id("b" * 64, "e4599620801af592", "c" * 40)
    assert base != run_id("a" * 64, "f6c24e0f8463359c", "c" * 40)
    assert base != run_id("a" * 64, "e4599620801af592", "d" * 40)
