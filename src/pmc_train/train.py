# Copyright 2026 PyMOL Copilot contributors.
"""Fine-tune the base model once, completion-only, and record everything.

    PYTHONPATH=src .venv-train/bin/python -m pmc_train.train \\
        --config configs/training/lora-v1.json [--smoke 5]

The real run uses Unsloth: `FastLanguageModel` loads the 16-bit base
weights and adds the LoRA adapter, which brings Unsloth's fused kernels
and its offloaded gradient checkpointing. The loss is this package's
own (`pmc_train.loss.completion_loss`), computed by a `Trainer`
subclass, so the tensors the masking test checks are the tensors that
train. Every batch is checked for masking as it reaches the loss.

A run refuses a modified tracked file, like the evaluation does, so its
commit names its code, and it never overwrites an earlier run: it works
in a hidden `.train-<run id>.partial/` and renames it only when the run
has finished. It writes `results/train-<run id>/`:

- `run.json`: the config and its SHA-256, both seeds, the commit, the
  split, the base weights, the visiting order's digest, the masking
  check's counts, every installed package, the hardware and the
  determinism settings;
- `loss.jsonl`: one record per logged optimizer step;
- `timings.json`: wall time, throughput and peak GPU memory;
- `adapter/`: the trained LoRA adapter.

`--smoke N` trains N optimizer steps of one sample each on the N longest
samples, to measure memory and speed before the real run; it writes
`results/train-smoke-<run id>/` and no adapter. `--backend hf` trains
with plain Hugging Face and PEFT instead of Unsloth, which the CPU tests
use because Unsloth needs a GPU.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import argparse
import datetime
import hashlib
import importlib.metadata
import json
import platform
import random
import shutil
import subprocess
import time
from collections.abc import Callable
from collections.abc import Sequence
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import Any

import numpy
import torch
from transformers import AutoTokenizer
from transformers import Trainer
from transformers import TrainerCallback
from transformers import TrainingArguments

from pmc_data.sample import Sample
from pmc_train.collate import CompletionCollator
from pmc_train.collate import ExampleDataset
from pmc_train.config import DEFAULT_CONFIG
from pmc_train.config import TrainConfig
from pmc_train.config import config_sha256
from pmc_train.config import load_config
from pmc_train.config import run_id
from pmc_train.data import load_train
from pmc_train.data import order_digest
from pmc_train.data import visit_order
from pmc_train.examples import Example
from pmc_train.examples import build_example
from pmc_train.examples import end_of_turn_id
from pmc_train.loss import assert_batch_masked
from pmc_train.loss import completion_loss

#: Where runs are written, relative to the repository root.
DEFAULT_OUT = Path("results")

#: The version of `run.json`'s layout.
RUN_VERSION = 1

BACKENDS = ("unsloth", "hf")


class DirtyTreeError(RuntimeError):
    """A tracked file differs from the commit a run would record."""


class RunExistsError(RuntimeError):
    """A run with this id has already been written."""


def git_commit(root: Path) -> str:
    """Name the checked-out commit.

    Args:
        root: The repository root.

    Returns:
        The full commit hash.
    """
    return subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        capture_output=True,
        check=True,
        text=True,
    ).stdout.strip()


def ensure_clean(root: Path) -> None:
    """Refuse to run while a tracked file is modified.

    Args:
        root: The repository root.

    Raises:
        DirtyTreeError: If `git status` reports a modified tracked file.
    """
    status = subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain", "-uno"],
        capture_output=True,
        check=True,
        text=True,
    ).stdout
    if status.strip():
        raise DirtyTreeError(
            "tracked files are modified; commit them first:\n" + status
        )


def seed_everything(seed: int) -> None:
    """Seed every random number generator the run touches.

    Args:
        seed: The seed.
    """
    import transformers

    random.seed(seed)
    numpy.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    transformers.set_seed(seed)


def sha256_file(path: Path) -> str:
    """Hash a file in chunks.

    Args:
        path: The file.

    Returns:
        The hex SHA-256 digest.
    """
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def base_weights_path(config: TrainConfig) -> Path:
    """Fetch the pinned base weights and verify them.

    Args:
        config: The training config.

    Returns:
        The local snapshot directory.

    Raises:
        ValueError: If `model.safetensors` is not the pinned file.
    """
    from huggingface_hub import snapshot_download

    path = Path(
        snapshot_download(
            config.base_model.repo, revision=config.base_model.revision
        )
    )
    actual = sha256_file(path / "model.safetensors")
    if actual != config.base_model.safetensors_sha256:
        raise ValueError(f"base weights are {actual}, not the pinned file")
    return path


def build_unsloth_model(config: TrainConfig, weights: Path) -> Any:
    """Load the base weights with Unsloth and add the LoRA adapter.

    Args:
        config: The training config.
        weights: The verified base-weights directory.

    Returns:
        The PEFT model.
    """
    from unsloth import FastLanguageModel

    model, _tokenizer = FastLanguageModel.from_pretrained(
        model_name=str(weights),
        max_seq_length=config.max_seq_length,
        dtype=torch.bfloat16 if config.precision == "bf16" else torch.float32,
        load_in_4bit=False,
        load_in_8bit=False,
        load_in_16bit=True,
        full_finetuning=False,
        use_exact_model_name=True,
        use_gradient_checkpointing=config.gradient_checkpointing,
        random_state=config.seed,
    )
    return FastLanguageModel.get_peft_model(
        model,
        r=config.lora.r,
        target_modules=list(config.lora.target_modules),
        lora_alpha=config.lora.alpha,
        lora_dropout=config.lora.dropout,
        bias="none",
        use_gradient_checkpointing=config.gradient_checkpointing,
        random_state=config.seed,
        use_rslora=False,
        loftq_config=None,
    )


def build_hf_model(config: TrainConfig, base: Any) -> Any:
    """Add the LoRA adapter to a plain Hugging Face model.

    Args:
        config: The training config.
        base: The base causal language model.

    Returns:
        The PEFT model.
    """
    from peft import LoraConfig
    from peft import get_peft_model

    torch.manual_seed(config.seed)
    return get_peft_model(
        base,
        LoraConfig(
            r=config.lora.r,
            lora_alpha=config.lora.alpha,
            lora_dropout=config.lora.dropout,
            target_modules=list(config.lora.target_modules),
            bias="none",
            task_type="CAUSAL_LM",
        ),
    )


def _causal_lm(model: Any) -> Any:
    """Find the causal language model inside a PEFT wrapper.

    Args:
        model: The model the trainer holds.

    Returns:
        The model with `.model` (the decoder) and `.lm_head`.
    """
    return model.get_base_model() if hasattr(model, "get_base_model") else model


class CompletionTrainer(Trainer):
    """A `Trainer` whose loss is `completion_loss`, on checked batches."""

    def __init__(self, *args: Any, eot_id: int, **kwargs: Any) -> None:
        """Remember the end-of-turn token for the masking check.

        Args:
            *args: Passed to `Trainer`.
            eot_id: The end-of-turn token id.
            **kwargs: Passed to `Trainer`.
        """
        super().__init__(*args, **kwargs)
        self.eot_id = eot_id
        self.checked_batches = 0
        self.supervised_tokens = 0
        self.normalized_by_items = False

    def compute_loss(
        self,
        model: Any,
        inputs: dict[str, torch.Tensor],
        return_outputs: bool = False,
        num_items_in_batch: torch.Tensor | int | None = None,
    ) -> Any:
        """Check the batch's masking, then compute the completion loss.

        Args:
            model: The model being trained.
            inputs: A collated batch.
            return_outputs: Unsupported; the loss is all there is.
            num_items_in_batch: The supervised-token count across the
                accumulated step, when the trainer supplies it.

        Returns:
            The loss.

        Raises:
            ValueError: If outputs are requested.
        """
        if return_outputs:
            raise ValueError("completion_loss returns no model outputs")
        self.supervised_tokens += assert_batch_masked(inputs, self.eot_id)
        self.checked_batches += 1
        self.normalized_by_items = num_items_in_batch is not None
        causal = _causal_lm(self.accelerator.unwrap_model(model))
        hidden = causal.model(
            input_ids=inputs["input_ids"],
            attention_mask=inputs["attention_mask"],
        ).last_hidden_state
        return completion_loss(
            hidden, causal.lm_head, inputs["labels"], num_items_in_batch
        )


class LossLog(TrainerCallback):
    """Collect the trainer's log records."""

    def __init__(self) -> None:
        """Start with no records."""
        self.records: list[dict[str, Any]] = []

    def on_log(
        self,
        args: Any,
        state: Any,
        control: Any,
        logs: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Keep one log record.

        Args:
            args: The training arguments.
            state: The trainer state.
            control: The trainer control.
            logs: The logged values.
            **kwargs: Unused.
        """
        del args, control, kwargs
        if logs:
            self.records.append({"step": state.global_step, **logs})


def _versions() -> dict[str, str | None]:
    """Record the versions that decide what trained.

    Returns:
        Python, CUDA and the training packages' versions.
    """
    versions: dict[str, str | None] = {
        "python": platform.python_version(),
        "torch_cuda": torch.version.cuda,
    }
    for package in (
        "torch",
        "transformers",
        "peft",
        "trl",
        "unsloth",
        "unsloth_zoo",
        "accelerate",
        "bitsandbytes",
        "triton",
        "xformers",
    ):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    return versions


def _packages() -> list[str]:
    """List every installed distribution, like `pip freeze`.

    Returns:
        Sorted `name==version` lines.
    """
    return sorted(
        {
            f"{dist.metadata['Name']}=={dist.version}"
            for dist in importlib.metadata.distributions()
        },
        key=str.lower,
    )


def _hardware() -> dict[str, Any]:
    """Describe the machine the run is on.

    Returns:
        The host, the GPU and its driver, when there is one.
    """
    hardware: dict[str, Any] = {
        "host": f"{platform.system()} {platform.release()} {platform.machine()}",
        "cpu": platform.processor() or None,
        "cuda_available": torch.cuda.is_available(),
    }
    if torch.cuda.is_available():
        properties = torch.cuda.get_device_properties(0)
        hardware["gpu"] = properties.name
        hardware["gpu_memory_bytes"] = properties.total_memory
        try:
            hardware["driver"] = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=driver_version",
                    "--format=csv,noheader",
                ],
                capture_output=True,
                check=True,
                text=True,
            ).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            hardware["driver"] = None
    return hardware


@dataclass
class RunResult:
    """What one run wrote.

    Attributes:
        directory: The run's directory.
        manifest: The contents of its `run.json`.
        losses: Its loss records.
    """

    directory: Path
    manifest: dict[str, Any]
    losses: list[dict[str, Any]] = field(default_factory=list)


def train(
    config_path: Path,
    root: Path,
    *,
    backend: str = "unsloth",
    smoke: int | None = None,
    out: Path | None = None,
    samples: Sequence[Sample] | None = None,
    load_base: Callable[[], Any] | None = None,
    tokenizer: Any = None,
    max_steps: int | None = None,
    require_clean: bool = True,
    use_cpu: bool = False,
) -> RunResult:
    """Run one fine-tune (or smoke run) and write its record.

    Args:
        config_path: The training config file.
        root: The repository root.
        backend: `unsloth` for the real run, `hf` for plain PEFT.
        smoke: Train this many one-sample steps on the longest samples.
        out: Where runs are written; `results/` by default.
        samples: The samples to train on; the split's training set by
            default. Tests pass a few.
        load_base: Builds the base model for the `hf` backend; the
            pinned weights by default. Tests pass a tiny model.
        tokenizer: The tokenizer; the pinned one by default.
        max_steps: Stop after this many optimizer steps (tests only).
        require_clean: Refuse a modified tracked file. Only tests turn
            this off, and the run records it.
        use_cpu: Train on the CPU even when a GPU is present (tests).

    Returns:
        The run's directory, manifest and loss records.

    Raises:
        RunExistsError: If a run with this id was already written.
        ValueError: If the backend is unknown.
    """
    if backend not in BACKENDS:
        raise ValueError(f"backend must be one of {BACKENDS}")
    if require_clean:
        ensure_clean(root)
    config = load_config(config_path)
    config_sha = config_sha256(config_path)
    commit = git_commit(root)
    identity = run_id(config_sha, config.split.split_id, commit)
    kind = "smoke" if smoke else "train"
    name = f"train-smoke-{identity}" if smoke else f"train-{identity}"
    directory = (out or root / DEFAULT_OUT) / name
    partial = directory.with_name(f".{name}.partial")
    if directory.exists() or partial.exists():
        raise RunExistsError(f"{directory} (or its partial) already exists")

    seed_everything(config.seed)
    weights = None
    if tokenizer is None or (backend == "unsloth" or load_base is None):
        weights = base_weights_path(config)
    if tokenizer is None:
        tokenizer = AutoTokenizer.from_pretrained(str(weights))
    if samples is None:
        samples = load_train(root / config.split.dir, config.split.split_id)
    examples = [
        build_example(
            sample.sample_id,
            sample.prompt_text,
            sample.plan_pml,
            tokenizer,
            config.chat_template_date,
            config.max_seq_length,
        )
        for sample in samples
    ]
    if smoke:
        visited: list[Example] = sorted(
            examples, key=lambda e: (-len(e.input_ids), e.sample_id)
        )[:smoke]
        accumulation = 1
        steps = len(visited)
    else:
        order = visit_order(
            len(examples), config.data_seed, config.optimizer.epochs
        )
        visited = [examples[index] for index in order]
        accumulation = config.optimizer.gradient_accumulation_steps
        steps = max_steps or -1

    if backend == "unsloth":
        model = build_unsloth_model(config, weights)
    else:
        base = (
            load_base()
            if load_base is not None
            else _load_hf_base(config, weights)
        )
        model = build_hf_model(config, base)

    cuda = torch.cuda.is_available() and not use_cpu
    arguments = TrainingArguments(
        output_dir=str(partial / "trainer"),
        per_device_train_batch_size=config.optimizer.per_device_batch_size,
        gradient_accumulation_steps=accumulation,
        learning_rate=config.optimizer.learning_rate,
        lr_scheduler_type=config.optimizer.lr_scheduler,
        warmup_steps=config.optimizer.warmup_ratio,
        weight_decay=config.optimizer.weight_decay,
        max_grad_norm=config.optimizer.max_grad_norm,
        optim=config.optimizer.name,
        num_train_epochs=1,
        max_steps=steps,
        bf16=cuda and config.precision == "bf16",
        use_cpu=not cuda,
        logging_steps=config.logging_steps,
        save_strategy="no",
        report_to=[],
        seed=config.seed,
        data_seed=config.data_seed,
        train_sampling_strategy="sequential",
        remove_unused_columns=False,
        dataloader_num_workers=0,
        disable_tqdm=True,
    )
    log = LossLog()
    trainer = CompletionTrainer(
        model=model,
        args=arguments,
        train_dataset=ExampleDataset(visited),
        data_collator=CompletionCollator(tokenizer.pad_token_id),
        callbacks=[log],
        eot_id=end_of_turn_id(tokenizer),
    )
    if cuda:
        torch.cuda.reset_peak_memory_stats()
    started = datetime.datetime.now(tz=datetime.UTC)
    clock = time.monotonic()
    trainer.train()
    wall = time.monotonic() - clock
    finished = datetime.datetime.now(tz=datetime.UTC)

    visited_tokens = sum(len(example.input_ids) for example in visited)
    trained_steps = trainer.state.global_step
    trained_tokens = sum(
        len(example.input_ids)
        for example in visited[: trained_steps * accumulation]
    )
    timings: dict[str, Any] = {
        "wall_seconds": wall,
        "optimizer_steps": trained_steps,
        "tokens_trained": trained_tokens,
        "tokens_per_second": trained_tokens / wall if wall else None,
        "peak_gpu_memory_bytes": (
            torch.cuda.max_memory_allocated() if cuda else None
        ),
        "peak_gpu_reserved_bytes": (
            torch.cuda.max_memory_reserved() if cuda else None
        ),
    }
    manifest: dict[str, Any] = {
        "run_version": RUN_VERSION,
        "run_id": identity,
        "kind": kind,
        "backend": backend,
        "config_path": str(config_path.relative_to(root))
        if config_path.is_relative_to(root)
        else str(config_path),
        "config_sha256": config_sha,
        "config": json.loads(config_path.read_text(encoding="utf-8")),
        "seeds": {"seed": config.seed, "data_seed": config.data_seed},
        "commit": commit,
        "clean_tree_required": require_clean,
        "split_id": config.split.split_id,
        "base_model": {
            "repo": config.base_model.repo,
            "revision": config.base_model.revision,
            "safetensors_sha256_verified": weights is not None,
        },
        "samples": len(examples),
        "examples_visited": len(visited),
        "visited_tokens": visited_tokens,
        "order_sha256": order_digest([e.sample_id for e in visited]),
        "masking": {
            "batches_checked": trainer.checked_batches,
            "supervised_tokens": trainer.supervised_tokens,
            "loss_normalized_by_items_in_accumulated_step": (
                trainer.normalized_by_items
            ),
        },
        "started": started.isoformat(),
        "finished": finished.isoformat(),
        "versions": _versions(),
        "hardware": _hardware(),
        "determinism": {
            "cudnn_deterministic": torch.backends.cudnn.deterministic,
            "cudnn_benchmark": torch.backends.cudnn.benchmark,
            "deterministic_algorithms": (
                torch.are_deterministic_algorithms_enabled()
            ),
        },
        "packages": _packages(),
    }
    if smoke:
        projected = (
            sum(len(e.input_ids) for e in examples)
            * config.optimizer.epochs
            / timings["tokens_per_second"]
            if timings["tokens_per_second"]
            else None
        )
        timings["projected_full_run_seconds"] = projected

    shutil.rmtree(partial / "trainer", ignore_errors=True)
    partial.mkdir(parents=True, exist_ok=True)
    if not smoke:
        adapter = partial / "adapter"
        model.save_pretrained(str(adapter))
        manifest["adapter_sha256"] = {
            path.name: sha256_file(path)
            for path in sorted(adapter.iterdir())
            if path.is_file()
        }
    for filename, payload in (
        ("run.json", manifest),
        ("timings.json", timings),
    ):
        (partial / filename).write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    with (partial / "loss.jsonl").open("w", encoding="utf-8") as handle:
        for record in log.records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
    partial.rename(directory)
    return RunResult(directory=directory, manifest=manifest, losses=log.records)


def _load_hf_base(config: TrainConfig, weights: Path | None) -> Any:
    """Load the pinned base weights with plain Hugging Face.

    Args:
        config: The training config.
        weights: The verified base-weights directory.

    Returns:
        The causal language model.
    """
    from transformers import AutoModelForCausalLM

    if weights is None:
        weights = base_weights_path(config)
    return AutoModelForCausalLM.from_pretrained(
        str(weights),
        dtype=torch.bfloat16 if config.precision == "bf16" else torch.float32,
    )


def main(argv: Sequence[str] | None = None) -> None:
    """Parse arguments and run.

    Args:
        argv: The command line, without the program name.
    """
    parser = argparse.ArgumentParser(
        description="Fine-tune the base model (master plan item 17)."
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--smoke", type=int, default=None)
    parser.add_argument("--backend", choices=BACKENDS, default="unsloth")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[2]
    result = train(
        (root / args.config).resolve(),
        root,
        backend=args.backend,
        smoke=args.smoke,
        out=args.out,
    )
    timings = (result.directory / "timings.json").read_text(encoding="utf-8")
    print(timings, end="")
    print(f"wrote {result.directory}")


if __name__ == "__main__":
    main()
