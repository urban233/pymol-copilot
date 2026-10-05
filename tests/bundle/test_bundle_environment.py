# Copyright 2026 PyMOL Copilot contributors.
"""The bundle's lock is the runtime, plus what the notebook's cells need.

docs/master_plan.md item 20. The portable Windows bundle runs the
notebook from its own Python (`requirements-bundle.txt`). It must run
the same runtime packages the evaluation measured, the tokenizer stack
at the notebook's own versions, and nothing of the training stack, which
only the notebook's flags that stay off would reach.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BUNDLE_LOCK = ROOT / "requirements-bundle.txt"
RUNTIME_LOCK = ROOT / "requirements_lock.txt"
NOTEBOOK_LOCK = ROOT / "requirements-notebook.txt"

#: What the notebook's own cells import, pinned as the notebook ran them.
NOTEBOOK_PACKAGES = {
    "transformers",
    "tokenizers",
    "huggingface-hub",
    "matplotlib",
    "ipykernel",
    "nbclient",
    "nbformat",
}

#: The training stack, which the bundle leaves out.
TRAINING_PACKAGES = {
    "torch",
    "triton",
    "unsloth",
    "unsloth-zoo",
    "peft",
    "trl",
    "bitsandbytes",
    "xformers",
}


def _pins(lock: Path) -> dict[str, str]:
    """Read every `name==version` pin out of a lock.

    Args:
        lock: The lock file.

    Returns:
        The locked version of each package, by lower-cased name.
    """
    pins: dict[str, str] = {}
    for line in lock.read_text(encoding="utf-8").splitlines():
        if "==" in line and not line.startswith((" ", "#")):
            name, version = line.split(" ", 1)[0].split("==")
            pins[name.lower()] = version
    return pins


def test_the_lock_is_compiled_for_windows() -> None:
    """The bundle installs on Windows x64 from wheels only."""
    header = BUNDLE_LOCK.read_text(encoding="utf-8").splitlines()[1]

    assert "--python-platform x86_64-pc-windows-msvc" in header
    assert "--python-version 3.13.13" in header
    assert "--only-binary :all:" in header


def test_the_bundle_runs_the_runtimes_packages() -> None:
    """Every package both locks pin is pinned identically."""
    bundle, runtime = _pins(BUNDLE_LOCK), _pins(RUNTIME_LOCK)

    shared = set(bundle) & set(runtime)
    assert shared >= {"pymol-open-source-whl", "numpy", "langgraph", "httpx"}
    assert {name: bundle[name] for name in shared} == {
        name: runtime[name] for name in shared
    }


def test_the_notebooks_packages_are_the_notebooks_versions() -> None:
    """The tokenizer and the plot run as they did in the committed run."""
    bundle, notebook = _pins(BUNDLE_LOCK), _pins(NOTEBOOK_LOCK)

    assert {name: bundle[name] for name in NOTEBOOK_PACKAGES} == {
        name: notebook[name] for name in NOTEBOOK_PACKAGES
    }


def test_the_training_stack_is_left_out() -> None:
    """No CUDA wheel, and nothing only training needs."""
    assert not TRAINING_PACKAGES & set(_pins(BUNDLE_LOCK))


def test_every_pin_is_hashed() -> None:
    """The lock installs with `--require-hashes`."""
    text = BUNDLE_LOCK.read_text(encoding="utf-8")

    assert text.count("--hash=sha256:") >= len(_pins(BUNDLE_LOCK))


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
