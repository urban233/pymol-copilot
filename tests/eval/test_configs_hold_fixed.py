# Copyright 2026 PyMOL Copilot contributors.
"""Every evaluation config differs from the baseline's only in its model.

Item 17 compares a fine-tuned model with the untuned baseline, and
that comparison holds everything but the weights fixed
(docs/evaluation/README.md, PREREGISTRATION.md). So each config beside
`baseline.json` may name another model and pin another GGUF, and a
CPU config may name another backend and host, but nothing else: not
the generation bounds, the context, the sets, the conditions, the
engine release or the chat template's pinned date.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import json
from pathlib import Path

import pytest

from pmc_eval.compare import ALLOWED_CONFIG_KEYS
from pmc_eval.compare import config_differences
from pmc_eval.config import load_config

ROOT = Path(__file__).resolve().parents[2]
CONFIGS = ROOT / "configs" / "evaluation"
BASELINE = CONFIGS / "baseline.json"

#: What any item 17 config may change: the model under evaluation, the
#: same leaves `eval_cli compare` lets two compared configs differ in.
MODEL_KEYS = ALLOWED_CONFIG_KEYS

#: What a config for a CPU engine may change besides: where it runs.
#: Its llama.cpp build is the CPU backend's own, reported as found.
CPU_KEYS = frozenset(
    {
        ("engine", "backend"),
        ("engine_provenance", "host"),
        ("engine_provenance", "llama_cpp_build"),
        ("engine_provenance", "emulation"),
    }
)

OTHERS = sorted(path for path in CONFIGS.glob("*.json") if path != BASELINE)


def _differences(path: Path) -> set[tuple[str, ...]]:
    """Name the leaves a config changes relative to the baseline's.

    Args:
        path: The config.

    Returns:
        The paths of every leaf added, removed or changed.
    """
    return config_differences(
        json.loads(path.read_text(encoding="utf-8")),
        json.loads(BASELINE.read_text(encoding="utf-8")),
    )


def test_item_17_configs_exist() -> None:
    """The export-pipeline control's config is committed."""
    assert CONFIGS / "export_control.json" in OTHERS


@pytest.mark.parametrize("path", OTHERS, ids=lambda path: path.stem)
def test_config_changes_only_the_model(path: Path) -> None:
    """A GPU config changes the model; a CPU one, also where it runs."""
    load_config(path)
    allowed = MODEL_KEYS | (CPU_KEYS if path.stem.endswith("_cpu") else set())
    changed = _differences(path)
    assert changed <= allowed, sorted(changed - allowed)
    assert {("engine", "model_name"), ("engine", "checkpoint")} <= changed


@pytest.mark.parametrize("path", OTHERS, ids=lambda path: path.stem)
def test_local_checkpoint_is_the_mounted_file(path: Path) -> None:
    """A locally exported model is served from the read-only mount."""
    engine = json.loads(path.read_text(encoding="utf-8"))["engine"]
    checkpoint = engine["checkpoint"]
    assert checkpoint.startswith("/models/")
    assert Path(checkpoint).name == f"{engine['model_name']}.gguf"


def test_the_check_catches_a_changed_bound(tmp_path: Path) -> None:
    """Changing a generation bound would be caught."""
    data = json.loads((CONFIGS / "export_control.json").read_text("utf-8"))
    data["generation"]["max_tokens"] = 512
    changed = tmp_path / "changed.json"
    changed.write_text(json.dumps(data), encoding="utf-8")
    assert ("generation", "max_tokens") in _differences(changed)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
