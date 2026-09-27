# Copyright 2026 PyMOL Copilot contributors.
"""The evaluation config: which model, which bounds, which sets.

`configs/evaluation/baseline.json` is the one committed instance. It is
hashed into every run's identity, so a run can only be resumed, and a
baseline only compared against, under the exact config that produced
it.

The `engine_provenance` block records what the engine's own capability
probe cannot see -- the GGUF file's SHA-256, the Hugging Face revision
it came from, the llama.cpp build and the extra arguments Lemonade
launches it with (which pin the chat template's date), the container
image and the host -- and is filled in by whoever sets the engine up. A run refuses to start
while any of it is missing: a baseline whose model cannot be pinned to
a file cannot be compared with anything.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pmc_eval.runner import CONDITION_GRAMMAR
from pmc_eval.runner import CONDITION_NO_GRAMMAR
from pmc_eval.runner import Condition

#: The evaluation sets a config may name: the split files item 15 froze
#: for item 16 (docs/dataset/DATASHEET.md).
EVAL_SETS = ("test_gold", "heldout_synthetic")

#: Every field `engine_provenance` must carry.
PROVENANCE_FIELDS = (
    "lemonade_version",
    "llama_cpp_build",
    "llamacpp_args",
    "image",
    "gguf_sha256",
    "hf_revision",
    "host",
    "emulation",
)


class InvalidConfigError(ValueError):
    """The evaluation config is missing a field or holds a bad value."""


@dataclass(frozen=True)
class EngineConfig:
    """How to reach and load the model under evaluation.

    Attributes:
        base_url: The local Lemonade origin.
        model_name: Lemonade's model identifier.
        checkpoint: The exact checkpoint that identifier must load.
        backend: The llama.cpp backend.
        context_size: The context size to load the model with.
        connect_timeout_seconds: The connection budget.
        read_timeout_seconds: The per-read budget; set so it never binds
            on a slow CPU prefill.
    """

    base_url: str
    model_name: str
    checkpoint: str
    backend: str
    context_size: int
    connect_timeout_seconds: float
    read_timeout_seconds: float

    @property
    def model_identity(self) -> str:
        """Return the identity a Lemonade engine for this config reports.

        Returns:
            `<model_name>@<checkpoint>`, as
            `pmc_agent.inference.lemonade.LemonadeEngine` reports it.
        """
        return f"{self.model_name}@{self.checkpoint}"


@dataclass(frozen=True)
class EvalConfig:
    """One evaluation's whole configuration.

    Attributes:
        engine: The engine to evaluate.
        max_tokens: Every generation's token budget.
        generation_deadline_seconds: Every generation's wall-clock budget.
        sidecar_deadline_seconds: Every sidecar run's deadline.
        infra_retries: How often a sample hit by an infrastructure
            failure is retried within one invocation.
        conditions: The condition names every set is run under.
        sets: The evaluation sets to run.
        engine_provenance: What the probe cannot see; see the module
            docstring.
    """

    engine: EngineConfig
    max_tokens: int
    generation_deadline_seconds: float
    sidecar_deadline_seconds: float
    infra_retries: int
    conditions: tuple[str, ...]
    sets: tuple[str, ...]
    engine_provenance: Mapping[str, Any]

    def condition(self, name: str) -> Condition:
        """Build one named condition under this config's bounds.

        Args:
            name: A condition name this config lists.

        Returns:
            The condition.

        Raises:
            InvalidConfigError: If this config does not list it.
        """
        if name not in self.conditions:
            raise InvalidConfigError(f"the config lists no {name!r} condition")
        return Condition(
            name=name,
            grammar=name == CONDITION_GRAMMAR,
            max_tokens=self.max_tokens,
            deadline_seconds=self.generation_deadline_seconds,
        )

    def missing_provenance(self) -> tuple[str, ...]:
        """Name the provenance fields still unfilled.

        Returns:
            Every `PROVENANCE_FIELDS` entry that is absent or null.
        """
        return tuple(
            name
            for name in PROVENANCE_FIELDS
            if self.engine_provenance.get(name) in (None, "")
        )


def _field(data: Mapping[str, Any], key: str, kind: type) -> Any:
    """Read one typed field.

    Args:
        data: The mapping to read from.
        key: The field.
        kind: The type it must have.

    Returns:
        The value.

    Raises:
        InvalidConfigError: If the field is absent or of another type.
    """
    if key not in data:
        raise InvalidConfigError(f"missing field {key!r}")
    value = data[key]
    if kind is float and isinstance(value, int) and not isinstance(value, bool):
        value = float(value)
    if isinstance(value, bool) != (kind is bool) or not isinstance(value, kind):
        raise InvalidConfigError(f"{key!r} must be {kind.__name__}")
    return value


def _positive(value: float, key: str) -> None:
    """Refuse a bound that is not positive.

    Args:
        value: The bound.
        key: Its field name.

    Raises:
        InvalidConfigError: If it is not positive.
    """
    if value <= 0:
        raise InvalidConfigError(f"{key!r} must be positive")


def parse_config(data: Mapping[str, Any]) -> EvalConfig:
    """Validate a decoded config.

    Args:
        data: The decoded JSON object.

    Returns:
        The config.

    Raises:
        InvalidConfigError: If any field is missing or invalid.
    """
    engine = _field(data, "engine", dict)
    generation = _field(data, "generation", dict)
    sidecar = _field(data, "sidecar", dict)
    config = EvalConfig(
        engine=EngineConfig(
            base_url=_field(engine, "base_url", str),
            model_name=_field(engine, "model_name", str),
            checkpoint=_field(engine, "checkpoint", str),
            backend=_field(engine, "backend", str),
            context_size=_field(engine, "context_size", int),
            connect_timeout_seconds=_field(
                engine, "connect_timeout_seconds", float
            ),
            read_timeout_seconds=_field(engine, "read_timeout_seconds", float),
        ),
        max_tokens=_field(generation, "max_tokens", int),
        generation_deadline_seconds=_field(
            generation, "deadline_seconds", float
        ),
        sidecar_deadline_seconds=_field(sidecar, "deadline_seconds", float),
        infra_retries=_field(data, "infra_retries", int),
        conditions=tuple(_field(data, "conditions", list)),
        sets=tuple(_field(data, "sets", list)),
        engine_provenance=_field(data, "engine_provenance", dict),
    )
    for key, value in (
        ("context_size", config.engine.context_size),
        ("connect_timeout_seconds", config.engine.connect_timeout_seconds),
        ("read_timeout_seconds", config.engine.read_timeout_seconds),
        ("max_tokens", config.max_tokens),
        ("generation.deadline_seconds", config.generation_deadline_seconds),
        ("sidecar.deadline_seconds", config.sidecar_deadline_seconds),
    ):
        _positive(value, key)
    if config.infra_retries < 0:
        raise InvalidConfigError("'infra_retries' must not be negative")
    known = {CONDITION_NO_GRAMMAR, CONDITION_GRAMMAR}
    if not config.conditions or not set(config.conditions) <= known:
        raise InvalidConfigError(f"'conditions' must name only {sorted(known)}")
    if not config.sets or not set(config.sets) <= set(EVAL_SETS):
        raise InvalidConfigError(f"'sets' must name only {list(EVAL_SETS)}")
    unknown = set(config.engine_provenance) - set(PROVENANCE_FIELDS)
    if unknown:
        raise InvalidConfigError(
            f"unknown engine_provenance fields {sorted(unknown)}"
        )
    return config


def load_config(path: Path) -> EvalConfig:
    """Read and validate a config file.

    Args:
        path: The config file.

    Returns:
        The config.

    Raises:
        InvalidConfigError: If the file is missing, not a JSON object, or
            invalid.
    """
    if not path.is_file():
        raise InvalidConfigError(f"{path} does not exist")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise InvalidConfigError(f"{path} is not valid JSON") from error
    if not isinstance(data, dict):
        raise InvalidConfigError(f"{path} must hold a JSON object")
    return parse_config(data)
