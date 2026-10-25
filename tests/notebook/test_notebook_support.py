# Copyright 2026 PyMOL Copilot contributors.
"""The notebook's helpers find and check the engine section 9 serves from.

In the portable Windows bundle the
notebook starts its own Lemonade on the CPU; on the development machine
it uses the Docker engine already running. These tests cover the parts
that decide what is started and what is accepted, without starting
anything: `notebook_support` imports only the standard library.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]

#: The evaluated CPU engine's llama.cpp arguments.
LLAMACPP_ARGS = json.loads(
    (ROOT / "configs" / "evaluation" / "finetuned_cpu.json").read_text(
        encoding="utf-8"
    )
)["engine_provenance"]["llamacpp_args"]

#: The launch command Lemonade 11.9.0 reported on Windows (docs/bundle.md).
WINDOWS_LAUNCH = [
    "C:\\pmc-spike\\cache\\bin\\llamacpp\\cpu\\llama-server.exe",
    "-m",
    "C:\\pmc-spike\\model-ascii\\model.gguf",
    "--ctx-size",
    "16384",
    "--port",
    "8001",
    "--jinja",
    "--metrics",
    "--chat-template-kwargs",
    '{"date_string":"26 Jul 2024"}',
    "--parallel",
    "1",
]


def _support() -> Any:
    """Import `notebooks/notebook_support.py` as a module.

    Returns:
        The module.
    """
    spec = importlib.util.spec_from_file_location(
        "notebook_support", ROOT / "notebooks" / "notebook_support.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Its dataclass looks its own module up while it is being defined.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


support = _support()


def test_the_launch_on_windows_carries_the_evaluated_arguments() -> None:
    """The chat template's date reached llama.cpp as one argument."""
    assert support.launched_with(WINDOWS_LAUNCH, LLAMACPP_ARGS)


@pytest.mark.parametrize(
    "mangled",
    [
        # The JSON lost its quotes on the way.
        "{date_string:26 Jul 2024}",
        # The single quotes were passed through.
        '\'{"date_string":"26 Jul 2024"}\'',
    ],
)
def test_a_mangled_template_date_is_refused(mangled: str) -> None:
    """Any other spelling would print today's date into the prompt."""
    command = [
        mangled if part.startswith("{") else part for part in WINDOWS_LAUNCH
    ]

    assert not support.launched_with(command, LLAMACPP_ARGS)


def test_a_launch_without_the_arguments_is_refused() -> None:
    """Lemonade launched with its defaults is not the evaluated engine."""
    command = WINDOWS_LAUNCH[: WINDOWS_LAUNCH.index("--chat-template-kwargs")]

    assert not support.launched_with(command, LLAMACPP_ARGS)


def test_the_engine_config_serves_only_the_local_model_offline() -> None:
    """Lemonade fetches nothing, announces nothing, and uses the CPU."""
    config = support.engine_config(
        models_dir="C:\\pmc\\model",
        log_file="C:\\pmc\\lemonade\\lemonade.log",
        llamacpp_args=LLAMACPP_ARGS,
    )

    assert config["extra_models_dir"] == "C:\\pmc\\model"
    assert config["llamacpp"] == {
        "args": LLAMACPP_ARGS,
        "backend": "cpu",
        "prefer_system": False,
    }
    assert config["offline"] is True
    assert config["no_fetch_executables"] is True
    assert config["broadcast"] is False
    assert config["auto_check_model_updates"] is False


def test_an_ascii_path_is_kept() -> None:
    """Most paths need no short form."""
    path = Path("C:/Users/anna/Downloads/pymol-copilot/lemonade")

    assert support.ascii_path(path, lambda _path: None) == str(path)


def test_a_non_ascii_path_uses_its_short_form() -> None:
    """Lemonade exits on `ü`; the 8.3 short name is ASCII."""
    path = Path("C:/Users/jürgen/Downloads/pymol-copilot/lemonade")

    assert (
        support.ascii_path(path, lambda _path: "C:\\Users\\JRGEN~1\\x")
        == "C:\\Users\\JRGEN~1\\x"
    )


@pytest.mark.parametrize("short", [None, "C:\\Users\\jürgen\\x"])
def test_a_non_ascii_path_without_an_ascii_short_form_is_none(
    short: str | None,
) -> None:
    """The caller then stages the engine instead."""
    path = Path("C:/Users/jürgen/Downloads/pymol-copilot/lemonade")

    assert support.ascii_path(path, lambda _path: short) is None


def test_the_plan_id_is_read_from_a_preview() -> None:
    """The id the preview offers is the one to apply."""
    preview = (
        "copilot plan p-31cc1fc1-8496-473f-b660-932a5f67b376 "
        "(expires 2026-10-05T18:11:51.371Z, in 5 min)\n"
        "  object:    pmc_structure (36 atoms, 1 state)"
    )

    assert support.plan_id(preview) == "p-31cc1fc1-8496-473f-b660-932a5f67b376"


@pytest.mark.parametrize("preview", ["", "copilot: the model abstained."])
def test_a_preview_without_a_plan_has_no_id(preview: str) -> None:
    """Nothing is applied when the copilot offered nothing."""
    assert support.plan_id(preview) is None


def test_outside_the_bundle_the_docker_engine_serves_on_the_gpu(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Nothing is started; the server is pointed at the Docker engine."""
    monkeypatch.delenv(support.BUNDLE_VARIABLE, raising=False)
    monkeypatch.delenv(support.BACKEND_VARIABLE, raising=False)

    engine = support.start_engine("model", 16384)

    assert engine.process is None
    assert engine.flags == (
        "--checkpoint",
        support.DOCKER_CHECKPOINT,
        "--backend",
        "cuda",
    )


def test_outside_the_bundle_the_backend_can_be_the_cpu(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The committed notebook is re-executed against the CPU engine."""
    monkeypatch.delenv(support.BUNDLE_VARIABLE, raising=False)
    monkeypatch.setenv(support.BACKEND_VARIABLE, "cpu")

    assert support.start_engine("model", 16384).flags[-1] == "cpu"


def test_the_bundle_is_found_by_its_variable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The launcher names the folder the bundle was extracted to."""
    monkeypatch.delenv(support.BUNDLE_VARIABLE, raising=False)
    assert support.bundle_root() is None

    monkeypatch.setenv(support.BUNDLE_VARIABLE, str(tmp_path))
    assert support.bundle_root() == tmp_path


def test_a_package_that_is_not_installed_has_no_licence() -> None:
    """The bundle has no training stack; its licence row says so."""
    assert support.package_licence("pmc-not-a-package") == "not installed"


def test_the_host_is_described_on_any_platform() -> None:
    """Windows has no /etc/os-release; the row is never empty."""
    host = support.host_description()

    assert set(host) == {"os", "kernel", "architecture", "python"}
    assert host["os"] != "unknown" or Path("/etc/os-release").is_file()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
