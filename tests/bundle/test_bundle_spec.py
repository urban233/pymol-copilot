# Copyright 2026 PyMOL Copilot contributors.
"""The bundle holds the evaluated engine and model, and starts safely.

docs/master_plan.md item 20. `tools/bundle/bundle_spec.py` decides what
the portable Windows bundle holds and writes its launcher, README and
manifest; `build_bundle.py` only fetches and assembles. These tests hold
the pins to the evaluated CPU engine and the launcher to what a
colleague's machine needs, without building anything.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import json
import re
from pathlib import Path

import pytest

import bundle_spec

ROOT = Path(__file__).resolve().parents[2]
PINS = bundle_spec.load_pins(ROOT)
CPU_ENGINE = json.loads(
    (ROOT / "configs" / "evaluation" / "finetuned_cpu.json").read_text(
        encoding="utf-8"
    )
)


def _pinned_downloads() -> list[dict[str, str]]:
    """Collect every pinned download.

    Returns:
        Each one's URL and SHA-256.
    """
    return [
        PINS["python"],
        PINS["lemonade"],
        *PINS["licences"].values(),
    ]


def test_every_download_is_pinned_by_its_hash() -> None:
    """Nothing is fetched that the build cannot check."""
    for download in _pinned_downloads():
        assert download["url"].startswith("https://")
        assert re.fullmatch(r"[0-9a-f]{64}", download["sha256"])


def test_the_engine_is_the_evaluated_cpu_engine() -> None:
    """Same Lemonade, same llama.cpp build, same model file."""
    provenance = CPU_ENGINE["engine_provenance"]

    assert PINS["lemonade"]["version"] == provenance["lemonade_version"]
    assert (
        PINS["lemonade"]["llamacpp_backend"] == CPU_ENGINE["engine"]["backend"]
    )
    assert PINS["lemonade"]["llamacpp_build"] == provenance["llama_cpp_build"]
    assert PINS["model"]["sha256"] == provenance["gguf_sha256"]
    assert PINS["model"]["file"] == CPU_ENGINE["engine"]["model_name"] + ".gguf"


def test_the_python_is_the_runtimes() -> None:
    """The interpreter Bazel tests the runtime with."""
    assert PINS["python"]["version"] == "3.13.13"
    assert "cpython-3.13.13" in PINS["python"]["url"]
    assert "x86_64-pc-windows-msvc-install_only" in PINS["python"]["url"]


def test_the_notebooks_own_environment_test_is_left_out() -> None:
    """It asserts the Linux training environment, not the bundle's."""
    specs = bundle_spec.archive_pathspecs()

    assert ":(exclude)notebooks/tests" in specs
    assert {"notebooks", "src", "tests/notebook", "tools/winstage"} <= set(
        specs
    )


def test_the_launcher_isolates_the_bundles_python() -> None:
    """Nothing set on the colleague's machine reaches the bundle."""
    text = bundle_spec.launcher_text()

    for name in bundle_spec.CLEARED:
        assert f'set "{name}="\r\n' in text
    assert 'set "PYTHONNOUSERSITE=1"' in text
    assert 'set "HF_HUB_OFFLINE=1"' in text
    assert 'set "PMC_BUNDLE_ROOT=%PMC_ROOT%"' in text


def test_every_set_is_quoted_and_nothing_is_grouped() -> None:
    """A folder named `pymol-copilot (1)` must not break the launcher."""
    lines = bundle_spec.launcher_text().split("\r\n")

    for line in lines:
        if line.startswith("set "):
            assert line.startswith('set "') and line.endswith('"')
        assert not line.rstrip().endswith("(")
        assert line.strip() != ")"


def test_the_launcher_is_a_windows_batch_file() -> None:
    """ASCII with CRLF line endings, as `cmd` reads it."""
    text = bundle_spec.launcher_text()

    text.encode("ascii")
    assert "\n" not in text.replace("\r\n", "")
    assert text.startswith("@echo off\r\n")


def test_the_launcher_opens_the_notebook_in_jupyterlab() -> None:
    """On loopback, rooted at the repository copy."""
    text = bundle_spec.launcher_text()

    assert '"%PMC_ROOT%\\python\\python.exe" -m jupyterlab' in text
    assert "--ServerApp.ip=127.0.0.1" in text
    assert '--ServerApp.root_dir="%PMC_ROOT%\\repo"' in text
    assert '"%PMC_ROOT%\\repo\\notebooks\\pymol_copilot.ipynb"' in text


@pytest.mark.parametrize(("demo", "value"), [(True, "1"), (False, "0")])
def test_the_demo_runs_only_with_the_model(demo: bool, value: str) -> None:
    """A bundle without the model (CI's) runs with the demo off."""
    text = bundle_spec.launcher_text(demo=demo)

    assert f'set "PMC_NOTEBOOK_DEMO={value}"' in text


def test_everything_written_stays_in_the_bundle() -> None:
    """Jupyter, IPython, matplotlib and the tokenizer write inside it."""
    environment = bundle_spec.environment("R")

    for name in (
        "HF_HOME",
        "MPLCONFIGDIR",
        "JUPYTER_CONFIG_DIR",
        "JUPYTER_DATA_DIR",
        "JUPYTER_RUNTIME_DIR",
        "IPYTHONDIR",
    ):
        assert environment[name].startswith("R\\")


def test_built_with_llama_is_shown() -> None:
    """The Llama 3.2 licence requires it, with a copy of the agreement."""
    readme = bundle_spec.readme_text("abc")

    assert "Built with Llama" in readme
    assert "Built with Llama" in bundle_spec.launcher_text()
    for licence in ("llama-3.2-licence", "llama-3.2-use-policy"):
        assert PINS["licences"][licence]["file"] in readme
    readme.encode("ascii")


def test_the_manifest_names_the_model_the_notebook_checks() -> None:
    """`notebook_support` refuses any model file but this one."""
    manifest = bundle_spec.manifest("c" * 40, PINS, model=True, lock_sha256="l")

    assert manifest["commit"] == "c" * 40
    assert manifest["model"]["sha256"] == PINS["model"]["sha256"]
    assert manifest["model"]["file"] == PINS["model"]["file"]


def test_a_bundle_without_the_model_says_so() -> None:
    """CI's bundle holds no model."""
    manifest = bundle_spec.manifest(
        "c" * 40, PINS, model=False, lock_sha256="l"
    )

    assert manifest["model"] is None


def test_paths_longer_than_the_budget_are_found() -> None:
    """Explorer cannot extract them under a deep folder."""
    fits = "pymol-copilot/" + "a" * (bundle_spec.PATH_BUDGET - 14)

    assert bundle_spec.over_budget([fits]) == []
    assert bundle_spec.over_budget([fits + "b"]) == [fits + "b"]


def test_the_zip_is_named_after_its_commit() -> None:
    """Two builds of different commits never share a name."""
    name = bundle_spec.zip_name("0123456789abcdef0123")

    assert name == "pymol-copilot-0123456789ab-win64.zip"


@pytest.mark.parametrize(
    ("metadata", "licence"),
    [
        ({"License-Expression": "MIT", "License": "x"}, "MIT"),
        ({"License": "BSD"}, "BSD"),
        ({"License": "a very long\nlicence text"}, "see its .dist-info folder"),
        ({}, "see its .dist-info folder"),
    ],
)
def test_a_packages_declared_licence_is_read(
    metadata: dict[str, str], licence: str
) -> None:
    """The short form a package declares, never a whole licence text."""
    assert bundle_spec.declared_licence(metadata) == licence


def test_the_package_list_is_sorted_by_name() -> None:
    """Case does not change the order."""
    text = bundle_spec.package_list([("b", "2", "MIT"), ("A", "1", "BSD")])

    assert text.splitlines()[-2:] == ["A 1: BSD", "b 2: MIT"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
