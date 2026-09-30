# Copyright 2026 PyMOL Copilot contributors.
"""What the server loads and sends, and the evaluation config it can read.

docs/master_plan.md item 19. The offline evaluation's TaskSuccess is
measured under one committed config (`configs/evaluation/*.json`). A
server that is configured by hand, flag by flag, can drift from it
without anyone noticing -- a smaller context, another checkpoint, a
chat-template date that is not the pinned one -- and then the runtime
is not the system that was measured. `load_runtime_config` reads the
engine and generation settings straight from that same file, so the
two cannot differ, and `engine_mismatch` refuses an engine that is not
the one the config records.

This module reads the config itself rather than importing `pmc_eval`:
the evaluation harness sits above the runtime and nothing in `src`
depends on it. `tests/unit/test_server_config.py` proves the two readers
agree on every committed config.
"""

from __future__ import annotations

import json
import math
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pmc_agent.inference.lemonade import DEFAULT_BACKEND
from pmc_agent.inference.lemonade import DEFAULT_CHECKPOINT
from pmc_agent.inference.lemonade import DEFAULT_CONNECT_TIMEOUT_SECONDS
from pmc_agent.inference.lemonade import DEFAULT_MODEL_NAME
from pmc_agent.prompt import PROMPT_BUILDER
from pmc_agent.prompt import build_default_prompt
from pmc_agent.prompt import build_training_prompt

#: The prompt builders `--prompt` can select. `training` is the prompt
#: the local model was fine-tuned on (master plan item 17), which the
#: offline evaluation sends too; `placeholder` is the graph's own
#: stand-in from before there was one.
PROMPT_BUILDERS: dict[str, PROMPT_BUILDER] = {
    "placeholder": build_default_prompt,
    "training": build_training_prompt,
}

#: The server's defaults for what it sends and how long it waits: the
#: offline evaluation's own (configs/evaluation/finetuned.json), so a
#: server started without a config still serves the fine-tuned model's
#: way. The context holds the longest evaluated prompt, 5,495 tokens,
#: with room for its plan; the adapter's own 4096 does not.
DEFAULT_CONTEXT_SIZE = 16384
DEFAULT_READ_TIMEOUT_SECONDS = 600.0
DEFAULT_PROMPT = "training"
DEFAULT_MAX_TOKENS = 256
DEFAULT_DEADLINE_SECONDS = 600.0

#: The `engine` and `generation` fields a config must carry, exactly: a
#: field the server would not read is refused rather than ignored.
_ENGINE_FIELDS = frozenset(
    {
        "backend",
        "base_url",
        "checkpoint",
        "connect_timeout_seconds",
        "context_size",
        "model_name",
        "read_timeout_seconds",
    }
)
_GENERATION_FIELDS = frozenset({"deadline_seconds", "max_tokens"})

#: The `engine_provenance` fields the server checks the running engine
#: against: what the adapter's own probe cannot see.
_CHECKED_PROVENANCE = ("lemonade_version", "llamacpp_args")


class InvalidRuntimeConfigError(ValueError):
    """A config file the server cannot serve from."""


def _positive(value: float, name: str) -> None:
    """Refuse a bound that is not positive and finite.

    Args:
        value: The bound.
        name: Its name, for the message.

    Raises:
        ValueError: If it is not positive and finite.
    """
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be positive and finite")


@dataclass(frozen=True)
class EngineOptions:
    """Which model the server loads, and how.

    Attributes:
        model_name: The exact Lemonade model identifier.
        checkpoint: The exact checkpoint that identifier must load.
        backend: The llama.cpp backend (`cpu`, `cuda`, `vulkan`, ...).
        context_size: The context size to load the model with.
        read_timeout_seconds: The adapter's HTTP read timeout.
        connect_timeout_seconds: The adapter's HTTP connect timeout.
    """

    model_name: str = DEFAULT_MODEL_NAME
    checkpoint: str = DEFAULT_CHECKPOINT
    backend: str = DEFAULT_BACKEND
    context_size: int = DEFAULT_CONTEXT_SIZE
    read_timeout_seconds: float = DEFAULT_READ_TIMEOUT_SECONDS
    connect_timeout_seconds: float = DEFAULT_CONNECT_TIMEOUT_SECONDS

    @property
    def model_identity(self) -> str:
        """Return the identity a Lemonade engine for these options reports.

        Returns:
            `<model_name>@<checkpoint>`, as
            `pmc_agent.inference.lemonade.LemonadeEngine` reports it.
        """
        return f"{self.model_name}@{self.checkpoint}"


@dataclass(frozen=True)
class GenerationOptions:
    """What the request graph sends the engine, and within what bounds.

    Attributes:
        prompt: A `PROMPT_BUILDERS` key.
        grammar: Whether `pmc_core.grammar.build_grammar()` goes with
            every completion.
        max_tokens: The token budget of every completion.
        deadline_seconds: The wall-clock budget of every completion.
    """

    prompt: str = DEFAULT_PROMPT
    grammar: bool = True
    max_tokens: int = DEFAULT_MAX_TOKENS
    deadline_seconds: float = DEFAULT_DEADLINE_SECONDS

    def __post_init__(self) -> None:
        """Refuse bounds every completion request would refuse.

        `CompletionRequest` rejects the same values, but only once a
        request is being generated: checked here, a bad flag stops the
        server before it loads a model or writes its handoff, rather than
        failing every request it later serves.

        Raises:
            ValueError: If `prompt` is not a `PROMPT_BUILDERS` key, if
                `max_tokens` is not positive, or if `deadline_seconds` is
                not positive and finite.
        """
        if self.prompt not in PROMPT_BUILDERS:
            raise ValueError(f"unknown prompt builder: {self.prompt!r}")
        if self.max_tokens <= 0:
            raise ValueError("max_tokens must be positive")
        _positive(self.deadline_seconds, "deadline_seconds")


@dataclass(frozen=True)
class RuntimeConfig:
    """The engine and generation settings one evaluation config records.

    Attributes:
        path: The config file, as resolved.
        base_url: The local Lemonade origin.
        engine: The model to load.
        max_tokens: The token budget of every completion.
        deadline_seconds: The wall-clock budget of every completion.
        provenance: The `engine_provenance` values the running engine is
            checked against (`lemonade_version`, `llamacpp_args`).
    """

    path: Path
    base_url: str
    engine: EngineOptions
    max_tokens: int
    deadline_seconds: float
    provenance: Mapping[str, str]

    def generation(self, *, prompt: str, grammar: bool) -> GenerationOptions:
        """Build the generation options this config bounds.

        The config lists both evaluated conditions, so whether a grammar
        goes with each completion is still the caller's choice.

        Args:
            prompt: A `PROMPT_BUILDERS` key.
            grammar: Whether the grammar goes with every completion.

        Returns:
            The options.
        """
        return GenerationOptions(
            prompt=prompt,
            grammar=grammar,
            max_tokens=self.max_tokens,
            deadline_seconds=self.deadline_seconds,
        )


def _field(data: Mapping[str, Any], key: str, kind: type) -> Any:
    """Read one typed field, the way `pmc_eval.config` reads it.

    Args:
        data: The mapping to read from.
        key: The field.
        kind: The type it must have.

    Returns:
        The value.

    Raises:
        InvalidRuntimeConfigError: If the field is absent or of another
            type.
    """
    if key not in data:
        raise InvalidRuntimeConfigError(f"missing field {key!r}")
    value = data[key]
    if kind is float and isinstance(value, int) and not isinstance(value, bool):
        value = float(value)
    if isinstance(value, bool) or not isinstance(value, kind):
        raise InvalidRuntimeConfigError(f"{key!r} must be {kind.__name__}")
    return value


def _block(data: Mapping[str, Any], key: str, fields: frozenset[str]) -> Any:
    """Read one nested block that must carry exactly `fields`.

    Args:
        data: The decoded config.
        key: The block's name.
        fields: The fields it must carry, and nothing else.

    Returns:
        The block.

    Raises:
        InvalidRuntimeConfigError: If it is absent, not an object, or
            carries a field more or less.
    """
    block = _field(data, key, dict)
    unknown = sorted(set(block) - fields)
    if unknown:
        raise InvalidRuntimeConfigError(
            f"unknown {key} fields {unknown}: the server would ignore them"
        )
    return block


def parse_runtime_config(data: Mapping[str, Any], path: Path) -> RuntimeConfig:
    """Validate the parts of a decoded evaluation config the server reads.

    Args:
        data: The decoded JSON object.
        path: Where it was read from.

    Returns:
        The runtime config.

    Raises:
        InvalidRuntimeConfigError: If any field the server reads is
            missing or invalid.
    """
    engine = _block(data, "engine", _ENGINE_FIELDS)
    generation = _block(data, "generation", _GENERATION_FIELDS)
    provenance = _field(data, "engine_provenance", dict)
    try:
        options = EngineOptions(
            model_name=_field(engine, "model_name", str),
            checkpoint=_field(engine, "checkpoint", str),
            backend=_field(engine, "backend", str),
            context_size=_field(engine, "context_size", int),
            read_timeout_seconds=_field(engine, "read_timeout_seconds", float),
            connect_timeout_seconds=_field(
                engine, "connect_timeout_seconds", float
            ),
        )
        config = RuntimeConfig(
            path=path,
            base_url=_field(engine, "base_url", str),
            engine=options,
            max_tokens=_field(generation, "max_tokens", int),
            deadline_seconds=_field(generation, "deadline_seconds", float),
            provenance={
                name: _field(provenance, name, str)
                for name in _CHECKED_PROVENANCE
            },
        )
        for name, value in (
            ("engine.context_size", options.context_size),
            ("engine.read_timeout_seconds", options.read_timeout_seconds),
            (
                "engine.connect_timeout_seconds",
                options.connect_timeout_seconds,
            ),
        ):
            _positive(value, name)
        config.generation(prompt=DEFAULT_PROMPT, grammar=True)
    except ValueError as error:
        if isinstance(error, InvalidRuntimeConfigError):
            raise
        raise InvalidRuntimeConfigError(str(error)) from error
    return config


def resolve_path(path: Path) -> Path:
    """Resolve a path given on the command line.

    Under `bazel run` the working directory is the runfiles tree, so a
    relative path is taken relative to the workspace, as every other
    `bazel run` tool in this repository does.

    Args:
        path: The path as given.

    Returns:
        The path to open.
    """
    if path.is_absolute():
        return path
    return Path(os.environ.get("BUILD_WORKSPACE_DIRECTORY", ".")) / path


def load_runtime_config(path: Path) -> RuntimeConfig:
    """Read and validate an evaluation config file for serving.

    Args:
        path: The config file.

    Returns:
        The runtime config.

    Raises:
        InvalidRuntimeConfigError: If the file is missing, not a JSON
            object, or invalid.
    """
    resolved = resolve_path(path)
    if not resolved.is_file():
        raise InvalidRuntimeConfigError(f"{resolved} does not exist")
    try:
        data = json.loads(resolved.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise InvalidRuntimeConfigError(
            f"{resolved} is not valid JSON"
        ) from error
    if not isinstance(data, dict):
        raise InvalidRuntimeConfigError(f"{resolved} must hold a JSON object")
    return parse_runtime_config(data, resolved)


def engine_mismatch(
    config: RuntimeConfig,
    *,
    model_identity: str,
    lemonade_version: str,
    llamacpp_args: str | None,
) -> str | None:
    """Name the first way a running engine is not the config's.

    The offline evaluation refuses to run on such an engine
    (`pmc_eval.eval_cli`); a server built from the same config refuses
    to serve on it, for the same reason: its answers would not be the
    measured system's. The llama.cpp arguments carry the pinned chat
    template date (configs/evaluation/README.md), which the adapter's
    own probe cannot see.

    Args:
        config: The config the server was started with.
        model_identity: The connected engine's identity.
        lemonade_version: The version Lemonade reports.
        llamacpp_args: The loaded model's llama.cpp arguments, or None
            if Lemonade did not report them.

    Returns:
        A message naming the field and both values, or None when the
        engine is the config's.
    """
    expected = config.engine.model_identity
    if model_identity != expected:
        return (
            f"the engine is {model_identity!r}, but {config.path.name} "
            f"records {expected!r}"
        )
    for name, reported in (
        ("lemonade_version", lemonade_version),
        ("llamacpp_args", llamacpp_args),
    ):
        recorded = config.provenance[name]
        if reported != recorded:
            return (
                f"the engine reports {name} {reported!r}, but "
                f"{config.path.name} records {recorded!r}"
            )
    return None
