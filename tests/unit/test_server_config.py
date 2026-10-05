# Copyright 2026 PyMOL Copilot contributors.
"""The server reads an evaluation config exactly as the evaluation does.

docs/master_plan.md item 19. `pmc_server.config` reads the committed
evaluation configs itself, since nothing in `src` may import
`pmc_eval`. These tests prove the two readers agree on every committed
config, that the server refuses what it would otherwise ignore, and
that the server's defaults are the fine-tuned model's evaluated ones.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from pmc_agent.inference.lemonade import loaded_llamacpp_args
from pmc_eval.config import load_config
from pmc_server.config import EngineOptions
from pmc_server.config import GenerationOptions
from pmc_server.config import InvalidRuntimeConfigError
from pmc_server.config import engine_mismatch
from pmc_server.config import load_runtime_config

CONFIGS = Path(__file__).resolve().parents[2] / "configs" / "evaluation"
FINETUNED = CONFIGS / "finetuned.json"
CONFIG_FILES = sorted(CONFIGS.glob("*.json"))


def test_every_committed_config_is_found() -> None:
    """The parity check below is not vacuous."""
    assert {path.name for path in CONFIG_FILES} >= {
        "baseline.json",
        "finetuned.json",
    }


@pytest.mark.parametrize("path", CONFIG_FILES, ids=lambda path: path.name)
def test_the_server_reads_what_the_evaluation_reads(path: Path) -> None:
    """Every field the server takes is the evaluation's own value."""
    evaluated = load_config(path)
    served = load_runtime_config(path)

    assert served.base_url == evaluated.engine.base_url
    assert served.engine == EngineOptions(
        model_name=evaluated.engine.model_name,
        checkpoint=evaluated.engine.checkpoint,
        backend=evaluated.engine.backend,
        context_size=evaluated.engine.context_size,
        read_timeout_seconds=evaluated.engine.read_timeout_seconds,
        connect_timeout_seconds=evaluated.engine.connect_timeout_seconds,
    )
    assert served.engine.model_identity == evaluated.engine.model_identity
    assert served.max_tokens == evaluated.max_tokens
    assert served.deadline_seconds == evaluated.generation_deadline_seconds
    for name, value in served.provenance.items():
        assert value == evaluated.engine_provenance[name]
    for condition in evaluated.conditions:
        bounds = evaluated.condition(condition)
        generation = served.generation(
            prompt="training", grammar=bounds.grammar
        )
        assert generation.max_tokens == bounds.max_tokens
        assert generation.deadline_seconds == bounds.deadline_seconds


def test_the_defaults_are_the_fine_tuned_models_evaluated_ones() -> None:
    """A server started without a config serves the evaluated way."""
    served = load_runtime_config(FINETUNED)
    defaults = EngineOptions()

    assert defaults.context_size == served.engine.context_size
    assert defaults.read_timeout_seconds == served.engine.read_timeout_seconds
    assert GenerationOptions() == served.generation(
        prompt="training", grammar=True
    )


def _write(tmp_path: Path, edit: dict[str, Any]) -> Path:
    """Write the fine-tuned config with one block's fields changed.

    Args:
        tmp_path: Where to write it.
        edit: `{block: {field: value}}`; a value of None removes the
            field.

    Returns:
        The written file.
    """
    data = json.loads(FINETUNED.read_text(encoding="utf-8"))
    for block, fields in edit.items():
        for field, value in fields.items():
            if value is None:
                data[block].pop(field)
            else:
                data[block][field] = value
    path = tmp_path / "edited.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    "edit",
    [
        {"engine": {"grammar_mode": "lazy"}},
        {"generation": {"temperature": 0.7}},
        {"engine": {"context_size": None}},
        {"engine": {"context_size": "16384"}},
        {"engine": {"context_size": 0}},
        {"generation": {"max_tokens": 0}},
        {"generation": {"deadline_seconds": -1}},
        {"engine_provenance": {"llamacpp_args": None}},
    ],
    ids=json.dumps,
)
def test_a_config_the_server_cannot_serve_exactly_is_refused(
    tmp_path: Path, edit: dict[str, Any]
) -> None:
    """A field it would ignore, lack, or refuse later stops it now."""
    with pytest.raises(InvalidRuntimeConfigError):
        load_runtime_config(_write(tmp_path, edit))


def test_a_relative_config_path_is_the_workspaces_under_bazel_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`bazel run` starts in the runfiles tree; the path is the user's."""
    target = tmp_path / "configs" / "evaluation"
    target.mkdir(parents=True)
    (target / "finetuned.json").write_bytes(FINETUNED.read_bytes())
    monkeypatch.setenv("BUILD_WORKSPACE_DIRECTORY", str(tmp_path))

    served = load_runtime_config(Path("configs/evaluation/finetuned.json"))

    assert served.path == target / "finetuned.json"


def test_engine_mismatch_is_none_for_the_recorded_engine() -> None:
    """The engine the config records matches it."""
    config = load_runtime_config(FINETUNED)

    assert (
        engine_mismatch(
            config,
            model_identity=config.engine.model_identity,
            lemonade_version=config.provenance["lemonade_version"],
            llamacpp_args=config.provenance["llamacpp_args"],
        )
        is None
    )


def test_an_unreported_chat_template_date_is_a_mismatch() -> None:
    """A Lemonade that does not report the arguments cannot prove the date."""
    config = load_runtime_config(FINETUNED)

    mismatch = engine_mismatch(
        config,
        model_identity=config.engine.model_identity,
        lemonade_version=config.provenance["lemonade_version"],
        llamacpp_args=None,
    )

    assert mismatch is not None
    assert "llamacpp_args" in mismatch


def _health_client(health: object) -> httpx.Client:
    """Build a client whose health endpoint answers `health`.

    Args:
        health: The JSON body to answer.

    Returns:
        A hermetic client.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/health"
        return httpx.Response(200, json=health)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_loaded_llamacpp_args_reads_the_named_models_arguments() -> None:
    """The arguments come from the loaded model the config names."""
    client = _health_client(
        {
            "all_models_loaded": [
                {
                    "model_name": "other",
                    "recipe_options": {"llamacpp_args": "--other"},
                },
                {
                    "model_name": "tuned",
                    "recipe_options": {"llamacpp_args": "--pinned"},
                },
            ]
        }
    )

    assert (
        loaded_llamacpp_args(
            base_url="http://127.0.0.1:13305", model_name="tuned", client=client
        )
        == "--pinned"
    )


@pytest.mark.parametrize(
    "health",
    [
        {},
        [],
        {"all_models_loaded": "no"},
        {"all_models_loaded": [{"model_name": "tuned"}]},
        {
            "all_models_loaded": [
                {"model_name": "tuned", "recipe_options": {"llamacpp_args": 1}}
            ]
        },
    ],
)
def test_loaded_llamacpp_args_is_none_when_health_does_not_say(
    health: object,
) -> None:
    """Anything but a string for the named model is no answer."""
    assert (
        loaded_llamacpp_args(
            base_url="http://127.0.0.1:13305",
            model_name="tuned",
            client=_health_client(health),
        )
        is None
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
