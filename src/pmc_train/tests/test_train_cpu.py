# Copyright 2026 PyMOL Copilot contributors.
"""The training loop runs end to end on the CPU and records its run.

Unsloth needs a GPU, so this drives the same `train()` with the `hf`
backend and a tiny randomly initialized Llama over the real vocabulary,
on four real training samples. What it proves is the loop around the
model: the committed config reaches the trainer, every batch is checked
for masking as it reaches the loss, the run records its seeds and
config, a dirty tree is refused, and a seed fixes the result.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import torch
from transformers import LlamaConfig
from transformers import LlamaForCausalLM

from pmc_data.sample import read_samples
from pmc_train.config import DEFAULT_CONFIG
from pmc_train.config import TrainConfig
from pmc_train.config import config_sha256
from pmc_train.examples import end_of_turn_id
from pmc_train.train import UNSLOTH_HIDDEN
from pmc_train.train import DirtyTreeError
from pmc_train.train import RunExistsError
from pmc_train.train import RunResult
from pmc_train.train import ensure_clean
from pmc_train.train import final_hidden
from pmc_train.train import train

ROOT = Path(__file__).resolve().parents[3]
CONFIG = ROOT / DEFAULT_CONFIG

#: The manifest fields every run must record.
REQUIRED = {
    "run_id",
    "kind",
    "backend",
    "config_sha256",
    "config",
    "seeds",
    "commit",
    "split_id",
    "base_model",
    "order_sha256",
    "masking",
    "versions",
    "hardware",
    "determinism",
    "packages",
    "started",
    "finished",
}


def _samples(config: TrainConfig) -> list[Any]:
    """Pick the four shortest training samples.

    Args:
        config: The committed training config.

    Returns:
        The samples.
    """
    samples = read_samples(ROOT / config.split.dir / "train.jsonl")
    return sorted(samples, key=lambda s: (len(s.prompt_text), s.sample_id))[:4]


def _run(
    tokenizer: Any, config: TrainConfig, out: Path, *, smoke: int | None = None
) -> RunResult:
    """Train the tiny model for three steps on the CPU.

    Args:
        tokenizer: The base model's tokenizer.
        config: The committed training config.
        out: Where to write the run.
        smoke: Run in smoke mode with this many steps.

    Returns:
        The run.
    """

    def tiny() -> LlamaForCausalLM:
        torch.manual_seed(0)
        return LlamaForCausalLM(
            LlamaConfig(
                vocab_size=len(tokenizer),
                hidden_size=64,
                intermediate_size=128,
                num_hidden_layers=2,
                num_attention_heads=4,
                num_key_value_heads=2,
                max_position_embeddings=4096,
                pad_token_id=tokenizer.pad_token_id,
                bos_token_id=tokenizer.bos_token_id,
                eos_token_id=end_of_turn_id(tokenizer),
            )
        )

    return train(
        CONFIG,
        ROOT,
        backend="hf",
        smoke=smoke,
        out=out,
        samples=_samples(config),
        load_base=tiny,
        tokenizer=tokenizer,
        max_steps=3,
        require_clean=False,
        use_cpu=True,
    )


@pytest.fixture(scope="module")
def run(
    tokenizer: Any,
    config: TrainConfig,
    tmp_path_factory: pytest.TempPathFactory,
) -> RunResult:
    """One CPU training run.

    Args:
        tokenizer: The base model's tokenizer.
        config: The committed training config.
        tmp_path_factory: Pytest's scratch directories.

    Returns:
        The run.
    """
    return _run(tokenizer, config, tmp_path_factory.mktemp("run"))


def test_run_records_its_seeds_and_config(run: RunResult) -> None:
    """run.json holds every required field, and the config's own bytes."""
    manifest = json.loads((run.directory / "run.json").read_text("utf-8"))
    assert set(manifest) >= REQUIRED
    assert manifest["config_sha256"] == config_sha256(CONFIG)
    assert manifest["config"] == json.loads(CONFIG.read_text("utf-8"))
    assert manifest["seeds"] == {
        "seed": manifest["config"]["seed"],
        "data_seed": manifest["config"]["data_seed"],
    }
    assert manifest["clean_tree_required"] is False
    assert (run.directory / "adapter" / "adapter_config.json").is_file()
    assert manifest["adapter_sha256"]


def test_every_trained_batch_was_mask_checked(run: RunResult) -> None:
    """Every batch the trainer drew was checked before its loss.

    Four samples over two epochs is eight visited examples. That is
    fewer than one accumulated step of 16, so each of the three
    optimizer steps draws all eight: 24 batches.
    """
    masking = run.manifest["masking"]
    assert run.manifest["examples_visited"] == 8
    assert masking["batches_checked"] == 3 * 8
    assert masking["supervised_tokens"] > 0
    assert masking["loss_normalized_by_items_in_accumulated_step"] is True


def test_the_losses_were_cross_checked_before_training(run: RunResult) -> None:
    """The trained loss matched the model's own loss on one batch."""
    check = run.manifest["loss_cross_check"]
    assert check["relative"] < 1e-5


def test_loss_is_logged_every_step(run: RunResult) -> None:
    """One loss record per optimizer step, all finite."""
    losses = [r for r in run.losses if "loss" in r]
    assert [r["step"] for r in losses] == [1, 2, 3]
    assert all(r["loss"] == r["loss"] for r in losses)


def test_same_seed_same_losses(
    run: RunResult, tokenizer: Any, config: TrainConfig, tmp_path: Path
) -> None:
    """A second run with the same seed logs identical losses."""
    again = _run(tokenizer, config, tmp_path)
    keys = ("step", "loss", "grad_norm", "learning_rate")

    def pick(records: list[dict[str, Any]]) -> list[tuple[Any, ...]]:
        return [tuple(r.get(k) for k in keys) for r in records if "loss" in r]

    assert pick(again.losses) == pick(run.losses)
    assert again.manifest["order_sha256"] == run.manifest["order_sha256"]


def test_a_run_is_never_overwritten(
    run: RunResult, tokenizer: Any, config: TrainConfig
) -> None:
    """Writing the same run id twice is refused."""
    with pytest.raises(RunExistsError):
        _run(tokenizer, config, run.directory.parent)


def test_smoke_run_projects_the_full_run(
    tokenizer: Any, config: TrainConfig, tmp_path: Path
) -> None:
    """Smoke mode trains the longest samples one per step, with no adapter."""
    smoke = _run(tokenizer, config, tmp_path, smoke=2)
    assert smoke.directory.name.startswith("train-smoke-")
    assert smoke.manifest["kind"] == "smoke"
    assert smoke.manifest["masking"]["batches_checked"] == 2
    timings = json.loads((smoke.directory / "timings.json").read_text("utf-8"))
    assert timings["projected_full_run_seconds"] > 0
    assert not (smoke.directory / "adapter").exists()


def test_a_dirty_tree_is_refused(tmp_path: Path) -> None:
    """A modified tracked file stops a run before anything trains."""

    def git(*args: str) -> None:
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True)

    git("init", "-q")
    (tmp_path / "tracked.txt").write_text("one\n", encoding="utf-8")
    git("add", "tracked.txt")
    git(
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@example.invalid",
        "commit",
        "-q",
        "-m",
        "init",
    )
    ensure_clean(tmp_path)
    (tmp_path / "tracked.txt").write_text("two\n", encoding="utf-8")
    with pytest.raises(DirtyTreeError):
        ensure_clean(tmp_path)


class _FakeUnslothCausal:
    """Stands in for Unsloth's causal LM: hidden states only on request."""

    def __init__(self) -> None:
        """Record nothing yet."""
        self.seen: list[str | None] = []

    def __call__(
        self, *, input_ids: torch.Tensor, attention_mask: torch.Tensor
    ) -> Any:
        """Return hidden states in `logits` when the variable asks for them.

        Args:
            input_ids: The token ids.
            attention_mask: The attention mask.

        Returns:
            An object whose `logits` holds a marker tensor.
        """
        del attention_mask
        flag = os.environ.get(UNSLOTH_HIDDEN)
        self.seen.append(flag)
        value = 1.0 if flag == "1" else -1.0
        return SimpleNamespace(logits=torch.full((*input_ids.shape, 2), value))


def test_unsloth_hidden_states_come_from_the_causal_forward() -> None:
    """Under Unsloth, the causal-LM forward (with its causal mask) is used.

    Calling Unsloth's decoder directly would drop the causal mask it is
    given by that forward; `final_hidden` must never do so, and must
    leave the environment as it found it.
    """
    causal = _FakeUnslothCausal()
    ids = torch.zeros((1, 3), dtype=torch.long)
    before = os.environ.get(UNSLOTH_HIDDEN)
    hidden = final_hidden(causal, ids, torch.ones_like(ids), "unsloth")
    assert causal.seen == ["1"]
    assert bool((hidden == 1.0).all())
    assert os.environ.get(UNSLOTH_HIDDEN) == before
