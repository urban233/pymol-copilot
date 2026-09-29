# Copyright 2026 PyMOL Copilot contributors.
"""The training config: which weights, which data, which settings, which seeds.

`configs/training/lora-v1.json` is the one committed instance, and it
is committed before the run it configures (docs/training/README.md), so
no setting can be chosen after a tuned number exists. Its SHA-256 is
part of the run's identity. Every level is read strictly: a missing
field, an unknown field or a value of the wrong type is refused rather
than defaulted, so what the file says is exactly what trained.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pmc_data.manifest import sha256_of

#: The one committed training config.
DEFAULT_CONFIG = Path("configs") / "training" / "lora-v1.json"


class InvalidConfigError(ValueError):
    """The training config is missing a field or holds a bad value."""


@dataclass(frozen=True)
class BaseModel:
    """The 16-bit weights the adapter is trained on.

    Attributes:
        repo: The Hugging Face repository.
        revision: The exact commit of that repository.
        safetensors_sha256: The SHA-256 of its `model.safetensors`.
    """

    repo: str
    revision: str
    safetensors_sha256: str


@dataclass(frozen=True)
class BaseGguf:
    """The GGUF the untuned baseline was evaluated on.

    Attributes:
        repo: The Hugging Face repository.
        file: The GGUF file inside it.
        revision: The exact commit of that repository.
        sha256: The file's SHA-256.
    """

    repo: str
    file: str
    revision: str
    sha256: str


@dataclass(frozen=True)
class LoraConfig:
    """The adapter's shape.

    Attributes:
        r: The rank.
        alpha: The scaling numerator.
        dropout: The dropout on the adapter's input.
        target_modules: The linear layers that carry an adapter.
    """

    r: int
    alpha: int
    dropout: float
    target_modules: tuple[str, ...]


@dataclass(frozen=True)
class OptimizerConfig:
    """How the adapter is optimized.

    Attributes:
        name: The `transformers` optimizer name.
        learning_rate: The peak learning rate.
        lr_scheduler: The `transformers` schedule name.
        warmup_ratio: The share of steps spent warming up.
        weight_decay: The decoupled weight decay.
        epochs: Passes over the training set.
        per_device_batch_size: Samples per forward pass.
        gradient_accumulation_steps: Forward passes per optimizer step.
        max_grad_norm: The gradient clipping norm.
    """

    name: str
    learning_rate: float
    lr_scheduler: str
    warmup_ratio: float
    weight_decay: float
    epochs: int
    per_device_batch_size: int
    gradient_accumulation_steps: int
    max_grad_norm: float


@dataclass(frozen=True)
class ExportConfig:
    """How the tuned model becomes the GGUF the engine loads.

    Attributes:
        quantization: The llama.cpp quantization type.
        llama_cpp_tag: The llama.cpp release that converts and quantizes.
        base_gguf: The baseline's GGUF, which the export is checked
            against.
    """

    quantization: str
    llama_cpp_tag: str
    base_gguf: BaseGguf


@dataclass(frozen=True)
class SplitConfig:
    """The frozen split whose training set is read.

    Attributes:
        dir: The split directory, relative to the repository root.
        split_id: The id its manifest must carry.
    """

    dir: Path
    split_id: str


@dataclass(frozen=True)
class TrainConfig:
    """One fine-tuning run's complete configuration.

    Attributes:
        base_model: The weights trained on.
        chat_template_date: The `date_string` every prompt is rendered
            with, the one the engine pins.
        max_seq_length: The longest prompt plus target trained on; a
            longer sample is refused, never truncated.
        lora: The adapter's shape.
        optimizer: How it is optimized.
        precision: The training dtype.
        gradient_checkpointing: The checkpointing mode.
        logging_steps: Optimizer steps between loss records.
        seed: The seed for weights, dropout and every library RNG.
        data_seed: The seed for the order samples are visited in.
        split: The split read.
        export: How the result is exported.
    """

    base_model: BaseModel
    chat_template_date: str
    max_seq_length: int
    lora: LoraConfig
    optimizer: OptimizerConfig
    precision: str
    gradient_checkpointing: str
    logging_steps: int
    seed: int
    data_seed: int
    split: SplitConfig
    export: ExportConfig


def _object(data: Mapping[str, Any], keys: set[str], where: str) -> None:
    """Refuse a mapping whose keys are not exactly the expected ones.

    Args:
        data: The mapping.
        keys: The keys it must have.
        where: Its position in the file, for the message.

    Raises:
        InvalidConfigError: If a key is missing or unknown.
    """
    missing = keys - set(data)
    unknown = set(data) - keys
    if missing:
        raise InvalidConfigError(f"{where}: missing {sorted(missing)}")
    if unknown:
        raise InvalidConfigError(f"{where}: unknown {sorted(unknown)}")


def _field(data: Mapping[str, Any], key: str, kind: type) -> Any:
    """Read one typed field.

    Args:
        data: The mapping to read from.
        key: The field.
        kind: The type it must have.

    Returns:
        The value.

    Raises:
        InvalidConfigError: If the field is of another type.
    """
    value = data[key]
    if kind is float and isinstance(value, int) and not isinstance(value, bool):
        value = float(value)
    if isinstance(value, bool) != (kind is bool) or not isinstance(value, kind):
        raise InvalidConfigError(f"{key!r} must be {kind.__name__}")
    return value


def _positive(value: float, key: str) -> None:
    """Refuse a value that is not positive.

    Args:
        value: The value.
        key: Its field name.

    Raises:
        InvalidConfigError: If it is not positive.
    """
    if value <= 0:
        raise InvalidConfigError(f"{key!r} must be positive")


def _sub(data: Mapping[str, Any], key: str, keys: set[str]) -> dict[str, Any]:
    """Read one nested object and check its keys.

    Args:
        data: The parent mapping.
        key: The nested object's field.
        keys: The keys it must have.

    Returns:
        The nested object.
    """
    value = _field(data, key, dict)
    _object(value, keys, key)
    return value


def parse_config(data: Mapping[str, Any]) -> TrainConfig:
    """Validate a decoded config.

    Args:
        data: The decoded JSON object.

    Returns:
        The config.

    Raises:
        InvalidConfigError: If any field is missing, unknown or invalid.
    """
    _object(
        data,
        {
            "base_model",
            "chat_template_date",
            "max_seq_length",
            "lora",
            "optimizer",
            "precision",
            "gradient_checkpointing",
            "logging_steps",
            "seed",
            "data_seed",
            "split",
            "export",
        },
        "config",
    )
    base = _sub(data, "base_model", {"repo", "revision", "safetensors_sha256"})
    lora = _sub(data, "lora", {"r", "alpha", "dropout", "target_modules"})
    optimizer = _sub(
        data,
        "optimizer",
        {
            "name",
            "learning_rate",
            "lr_scheduler",
            "warmup_ratio",
            "weight_decay",
            "epochs",
            "per_device_batch_size",
            "gradient_accumulation_steps",
            "max_grad_norm",
        },
    )
    split = _sub(data, "split", {"dir", "split_id"})
    export = _sub(
        data, "export", {"quantization", "llama_cpp_tag", "base_gguf"}
    )
    gguf = _sub(export, "base_gguf", {"repo", "file", "revision", "sha256"})
    targets = _field(lora, "target_modules", list)
    if not targets or not all(isinstance(t, str) for t in targets):
        raise InvalidConfigError("'target_modules' must list module names")
    config = TrainConfig(
        base_model=BaseModel(
            repo=_field(base, "repo", str),
            revision=_field(base, "revision", str),
            safetensors_sha256=_field(base, "safetensors_sha256", str),
        ),
        chat_template_date=_field(data, "chat_template_date", str),
        max_seq_length=_field(data, "max_seq_length", int),
        lora=LoraConfig(
            r=_field(lora, "r", int),
            alpha=_field(lora, "alpha", int),
            dropout=_field(lora, "dropout", float),
            target_modules=tuple(targets),
        ),
        optimizer=OptimizerConfig(
            name=_field(optimizer, "name", str),
            learning_rate=_field(optimizer, "learning_rate", float),
            lr_scheduler=_field(optimizer, "lr_scheduler", str),
            warmup_ratio=_field(optimizer, "warmup_ratio", float),
            weight_decay=_field(optimizer, "weight_decay", float),
            epochs=_field(optimizer, "epochs", int),
            per_device_batch_size=_field(
                optimizer, "per_device_batch_size", int
            ),
            gradient_accumulation_steps=_field(
                optimizer, "gradient_accumulation_steps", int
            ),
            max_grad_norm=_field(optimizer, "max_grad_norm", float),
        ),
        precision=_field(data, "precision", str),
        gradient_checkpointing=_field(data, "gradient_checkpointing", str),
        logging_steps=_field(data, "logging_steps", int),
        seed=_field(data, "seed", int),
        data_seed=_field(data, "data_seed", int),
        split=SplitConfig(
            dir=Path(_field(split, "dir", str)),
            split_id=_field(split, "split_id", str),
        ),
        export=ExportConfig(
            quantization=_field(export, "quantization", str),
            llama_cpp_tag=_field(export, "llama_cpp_tag", str),
            base_gguf=BaseGguf(
                repo=_field(gguf, "repo", str),
                file=_field(gguf, "file", str),
                revision=_field(gguf, "revision", str),
                sha256=_field(gguf, "sha256", str),
            ),
        ),
    )
    for key, value in (
        ("max_seq_length", config.max_seq_length),
        ("r", config.lora.r),
        ("alpha", config.lora.alpha),
        ("learning_rate", config.optimizer.learning_rate),
        ("epochs", config.optimizer.epochs),
        ("per_device_batch_size", config.optimizer.per_device_batch_size),
        (
            "gradient_accumulation_steps",
            config.optimizer.gradient_accumulation_steps,
        ),
        ("max_grad_norm", config.optimizer.max_grad_norm),
        ("logging_steps", config.logging_steps),
    ):
        _positive(value, key)
    # The trainer reads a warmup value of 1 or more as a step count, not
    # a ratio (`TrainingArguments.warmup_steps`), so a ratio must be < 1.
    for key, value in (
        ("warmup_ratio", config.optimizer.warmup_ratio),
        ("dropout", config.lora.dropout),
    ):
        if not 0 <= value < 1:
            raise InvalidConfigError(f"{key!r} must be in [0, 1)")
    if config.optimizer.weight_decay < 0:
        raise InvalidConfigError("'weight_decay' must not be negative")
    if config.precision not in ("bf16", "fp32"):
        raise InvalidConfigError("'precision' must be 'bf16' or 'fp32'")
    return config


def load_config(path: Path) -> TrainConfig:
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


def config_sha256(path: Path) -> str:
    """Hash a config file's exact bytes.

    Args:
        path: The config file.

    Returns:
        The hex SHA-256 digest.
    """
    return sha256_of(path)


def run_id(config_sha: str, split_id: str, commit: str) -> str:
    """Name a training run by everything its result depends on.

    Args:
        config_sha: The config file's SHA-256.
        split_id: The split trained on.
        commit: The commit of the code that trains.

    Returns:
        A 16-hex-digit digest.
    """
    material = json.dumps(
        {"config_sha256": config_sha, "split_id": split_id, "commit": commit},
        sort_keys=True,
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
