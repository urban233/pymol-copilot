# Copyright 2026 PyMOL Copilot contributors.
"""Prompt tokens are masked out of the loss, proven at the tensor level.

This is the test the master plan's item 17 asks for. The first tests
check the labels a real sample produces: every prompt position is
ignored, the plan and the end of turn are supervised. The later tests
check the loss itself on a tiny randomly initialized Llama with the real
vocabulary: the gradient reaching every prompt position's logits (and,
for the loss the run trains on, every prompt position's final hidden
state) is exactly zero, and the completion-only loss equals the
standard full-logit masked loss.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import json
from pathlib import Path
from typing import Any

import pytest
import torch
import torch.nn.functional as functional
from transformers import LlamaConfig
from transformers import LlamaForCausalLM

from pmc_data.sample import read_samples
from pmc_train.collate import CompletionCollator
from pmc_train.collate import example_item
from pmc_train.config import TrainConfig
from pmc_train.examples import IGNORE_INDEX
from pmc_train.examples import SequenceTooLongError
from pmc_train.examples import build_example
from pmc_train.examples import end_of_turn_id
from pmc_train.loss import MaskingError
from pmc_train.loss import assert_batch_masked
from pmc_train.loss import completion_loss
from pmc_train.render import render_prompt

ROOT = Path(__file__).resolve().parents[3]
GOLD = read_samples(ROOT / "src" / "pmc_data" / "gold" / "gold_samples.jsonl")
SAMPLE = next(sample for sample in GOLD if sample.sample_id == "gold_028")

#: Short prompts for the model-level tests, so the full logits stay small.
SHORT = (
    ("short_a", 'intent="Color chain A red."\n', "color red, chain A\n"),
    (
        "short_b",
        'card-version=1\nintent="Select chain B and show it as sticks."\n',
        "select copilot_sel0, chain B\nshow sticks, copilot_sel0\n",
    ),
)


@pytest.fixture(scope="module")
def tiny_model(tokenizer: Any) -> LlamaForCausalLM:
    """A tiny randomly initialized Llama over the real vocabulary.

    Args:
        tokenizer: The base model's tokenizer.

    Returns:
        The model, in float32, in eval mode (no dropout).
    """
    torch.manual_seed(0)
    config = LlamaConfig(
        vocab_size=len(tokenizer),
        hidden_size=64,
        intermediate_size=128,
        num_hidden_layers=2,
        num_attention_heads=4,
        num_key_value_heads=2,
        max_position_embeddings=512,
        pad_token_id=tokenizer.pad_token_id,
        bos_token_id=tokenizer.bos_token_id,
        eos_token_id=end_of_turn_id(tokenizer),
    )
    return LlamaForCausalLM(config).eval()


def _example(tokenizer: Any, config: TrainConfig, index: int = 0) -> Any:
    """Build one of the short examples.

    Args:
        tokenizer: The base model's tokenizer.
        config: The committed training config.
        index: Which short example.

    Returns:
        The example.
    """
    sample_id, prompt, plan = SHORT[index]
    return build_example(
        sample_id,
        prompt,
        plan,
        tokenizer,
        config.chat_template_date,
        config.max_seq_length,
    )


def _real(tokenizer: Any, config: TrainConfig) -> Any:
    """Build the example for a real gold sample.

    Args:
        tokenizer: The base model's tokenizer.
        config: The committed training config.

    Returns:
        The example.
    """
    return build_example(
        SAMPLE.sample_id,
        SAMPLE.prompt_text,
        SAMPLE.plan_pml,
        tokenizer,
        config.chat_template_date,
        config.max_seq_length,
    )


def test_prompt_labels_are_ignored_and_the_completion_is_supervised(
    tokenizer: Any, config: TrainConfig
) -> None:
    """Every prompt label is ignored; every completion label is its token."""
    example = _real(tokenizer, config)
    labels = torch.tensor(example.labels)
    input_ids = torch.tensor(example.input_ids)
    start = example.completion_start
    assert start > 1000
    assert bool((labels[:start] == IGNORE_INDEX).all())
    assert torch.equal(labels[start:], input_ids[start:])
    assert int(labels[-1]) == end_of_turn_id(tokenizer)
    plan_tokens = tokenizer(SAMPLE.plan_pml, add_special_tokens=False)
    supervised = int((labels != IGNORE_INDEX).sum())
    assert supervised == len(plan_tokens["input_ids"]) + 1


def test_supervised_tokens_decode_to_the_plan_and_the_end_of_turn(
    tokenizer: Any, config: TrainConfig
) -> None:
    """Exactly the plan text and `<|eot_id|>` carry loss."""
    example = _real(tokenizer, config)
    supervised = [token for token in example.labels if token != IGNORE_INDEX]
    decoded = tokenizer.decode(supervised, skip_special_tokens=False)
    assert decoded == SAMPLE.plan_pml + "<|eot_id|>"


def test_prompt_and_plan_tokenize_the_same_apart_and_together(
    tokenizer: Any, config: TrainConfig
) -> None:
    """Tokenizing the prompt and plan apart changes no token boundary."""
    example = _real(tokenizer, config)
    whole = (
        render_prompt(tokenizer, SAMPLE.prompt_text, config.chat_template_date)
        + SAMPLE.plan_pml
    )
    together = tokenizer(whole, add_special_tokens=False)["input_ids"]
    assert list(example.input_ids[:-1]) == together


def test_every_committed_gold_sample_builds(
    tokenizer: Any, config: TrainConfig
) -> None:
    """Every gold sample's plan and end of turn are the only supervision."""
    eot = end_of_turn_id(tokenizer)
    for sample in GOLD:
        example = build_example(
            sample.sample_id,
            sample.prompt_text,
            sample.plan_pml,
            tokenizer,
            config.chat_template_date,
            config.max_seq_length,
        )
        start = example.completion_start
        assert set(example.labels[:start]) == {IGNORE_INDEX}
        assert example.labels[start:] == example.input_ids[start:]
        assert example.labels[-1] == eot


def test_logit_gradients_are_zero_at_every_prompt_position(
    tokenizer: Any, config: TrainConfig, tiny_model: LlamaForCausalLM
) -> None:
    """Through the standard loss, no prompt position's logits get gradient.

    Logits at position `i` predict token `i + 1`. With the first
    completion token at `P`, positions `0..P-2` predict prompt tokens
    and must get exactly zero gradient; `P-1..L-2` predict completion
    tokens and must get some. Position `L-1` predicts nothing.
    """
    example = _example(tokenizer, config)
    input_ids = torch.tensor([example.input_ids])
    labels = torch.tensor([example.labels])
    tiny_model.zero_grad()
    output = tiny_model(input_ids=input_ids)
    logits = output.logits
    logits.retain_grad()
    loss = functional.cross_entropy(
        logits[0, :-1].float(), labels[0, 1:], ignore_index=IGNORE_INDEX
    )
    loss.backward()
    gradient = logits.grad
    assert gradient is not None
    start = example.completion_start
    per_position = gradient[0].abs().sum(dim=-1)
    assert bool((per_position[: start - 1] == 0).all())
    assert bool((per_position[start - 1 : -1] > 0).all())
    assert float(per_position[-1]) == 0.0


def test_completion_loss_never_reads_a_prompt_hidden_state(
    tokenizer: Any, config: TrainConfig, tiny_model: LlamaForCausalLM
) -> None:
    """The trained loss sends exactly zero gradient to prompt positions."""
    example = _example(tokenizer, config)
    input_ids = torch.tensor([example.input_ids])
    labels = torch.tensor([example.labels])
    hidden = tiny_model.model(input_ids=input_ids).last_hidden_state
    hidden.retain_grad()
    completion_loss(hidden, tiny_model.lm_head, labels).backward()
    gradient = hidden.grad
    assert gradient is not None
    start = example.completion_start
    per_position = gradient[0].abs().sum(dim=-1)
    assert bool((per_position[: start - 1] == 0).all())
    assert bool((per_position[start - 1 : -1] > 0).all())


def test_completion_loss_equals_the_full_logit_masked_loss(
    tokenizer: Any, config: TrainConfig, tiny_model: LlamaForCausalLM
) -> None:
    """Same value and same parameter gradients as the standard loss."""
    example = _example(tokenizer, config)
    input_ids = torch.tensor([example.input_ids])
    labels = torch.tensor([example.labels])

    tiny_model.zero_grad()
    reference = tiny_model(input_ids=input_ids, labels=labels).loss
    reference.backward()
    reference_grads = {
        name: parameter.grad.clone()
        for name, parameter in tiny_model.named_parameters()
        if parameter.grad is not None
    }

    logits = tiny_model(input_ids=input_ids).logits[0, :-1].float()
    manual = functional.cross_entropy(
        logits, labels[0, 1:], ignore_index=IGNORE_INDEX
    )

    tiny_model.zero_grad()
    hidden = tiny_model.model(input_ids=input_ids).last_hidden_state
    loss = completion_loss(hidden, tiny_model.lm_head, labels)
    loss.backward()

    torch.testing.assert_close(loss, reference, rtol=1e-6, atol=1e-6)
    torch.testing.assert_close(loss, manual, rtol=1e-6, atol=1e-6)
    for name, parameter in tiny_model.named_parameters():
        if name in reference_grads:
            assert parameter.grad is not None, name
            torch.testing.assert_close(
                parameter.grad, reference_grads[name], rtol=1e-5, atol=1e-7
            )


def test_padding_carries_no_loss(
    tokenizer: Any, config: TrainConfig, tiny_model: LlamaForCausalLM
) -> None:
    """In a padded batch, padding is ignored and changes no row's loss."""
    examples = [_example(tokenizer, config, 0), _example(tokenizer, config, 1)]
    collator = CompletionCollator(tokenizer.pad_token_id)
    batch = collator([example_item(example) for example in examples])
    shorter = min(range(2), key=lambda row: len(examples[row].input_ids))
    length = len(examples[shorter].input_ids)
    assert bool((batch["labels"][shorter, length:] == IGNORE_INDEX).all())
    assert bool((batch["attention_mask"][shorter, length:] == 0).all())

    hidden = tiny_model.model(
        input_ids=batch["input_ids"], attention_mask=batch["attention_mask"]
    ).last_hidden_state
    batched = completion_loss(hidden, tiny_model.lm_head, batch["labels"])

    total = torch.tensor(0.0)
    count = 0
    for example in examples:
        single = collator([example_item(example)])
        single_hidden = tiny_model.model(
            input_ids=single["input_ids"]
        ).last_hidden_state
        supervised = int((single["labels"] != IGNORE_INDEX).sum())
        total = total + supervised * completion_loss(
            single_hidden, tiny_model.lm_head, single["labels"]
        )
        count += supervised
    torch.testing.assert_close(batched, total / count, rtol=1e-5, atol=1e-6)


def test_overlong_sequence_is_refused(
    tokenizer: Any, config: TrainConfig
) -> None:
    """A sequence over the limit raises; nothing is truncated."""
    example = _real(tokenizer, config)
    with pytest.raises(SequenceTooLongError):
        build_example(
            SAMPLE.sample_id,
            SAMPLE.prompt_text,
            SAMPLE.plan_pml,
            tokenizer,
            config.chat_template_date,
            len(example.input_ids) - 1,
        )
    exact = build_example(
        SAMPLE.sample_id,
        SAMPLE.prompt_text,
        SAMPLE.plan_pml,
        tokenizer,
        config.chat_template_date,
        len(example.input_ids),
    )
    assert exact == example


def test_the_collated_batch_passes_the_runtime_mask_check(
    tokenizer: Any, config: TrainConfig
) -> None:
    """The real collator's output is masked; the check counts supervision."""
    examples = [_example(tokenizer, config, 0), _example(tokenizer, config, 1)]
    batch = CompletionCollator(tokenizer.pad_token_id)(
        [example_item(example) for example in examples]
    )
    supervised = assert_batch_masked(batch, end_of_turn_id(tokenizer))
    assert supervised == int((batch["labels"] != IGNORE_INDEX).sum())


@pytest.mark.parametrize(
    "sabotage",
    ["labels_are_inputs", "one_prompt_label", "padding_label", "no_eot"],
)
def test_the_runtime_mask_check_catches_a_rewritten_batch(
    tokenizer: Any, config: TrainConfig, sabotage: str
) -> None:
    """A batch that supervises the prompt, or padding, is refused."""
    examples = [_example(tokenizer, config, 0), _example(tokenizer, config, 1)]
    batch = CompletionCollator(tokenizer.pad_token_id)(
        [example_item(example) for example in examples]
    )
    labels = batch["labels"]
    if sabotage == "labels_are_inputs":
        batch["labels"] = batch["input_ids"].clone()
    elif sabotage == "one_prompt_label":
        labels[0, 3] = batch["input_ids"][0, 3]
    elif sabotage == "padding_label":
        shorter = int(batch["attention_mask"].sum(dim=1).argmin())
        labels[shorter, -1] = tokenizer.pad_token_id
    else:
        batch["input_ids"][0, len(examples[0].input_ids) - 1] = 0
        labels[0, len(examples[0].input_ids) - 1] = 0
    with pytest.raises(MaskingError):
        assert_batch_masked(batch, end_of_turn_id(tokenizer))


def test_fixture_prompts_are_the_committed_gold_prompts() -> None:
    """The engine capture for gold_028 is this test's real sample."""
    capture = json.loads(
        (
            Path(__file__).parent / "data" / "engine_render" / "gold_028.json"
        ).read_text(encoding="utf-8")
    )
    assert capture["prompt_text"] == SAMPLE.prompt_text
