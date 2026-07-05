# cBioMOL - open C++ and Python platform for BioMOLecular visualization and analysis
# -------------------------------------------------------------------
# This file contains source code for the cBioMOL computer program
# Copyright (C) 2026 Hannah Kullik, Martin Urban (hannah.kullik@studmail.w-hs.de, martin.urban@studmail.w-hs.de)
# Source code is available at <https://github.com/urban233/cBioMOL>
# -------------------------------------------------------------------
# It is unlawful to modify or remove this copyright notice.
# -------------------------------------------------------------------
# Please see the accompanying LICENSE file for further information.
# -------------------------------------------------------------------
# Primary author of this source file:
#
# ==============================================================================
#
"""QLoRA fine-tuning script for the cBioMOL PyMOL AI assistant.

This script fine-tunes ``Qwen/Qwen2.5-1.5B-Instruct`` (or any model
configured in ``config/training_config.py``) on the tool-call dataset
produced by ``generate_dataset.py``.

The training stack:
- **PEFT** LoRA (rank-16 on all attention and MLP projection layers)
- **BitsAndBytes** 4-bit NF4 quantization of the base model weights
- **TRL** ``SFTTrainer`` with ``DataCollatorForCompletionOnlyLM`` for
  loss masking (only assistant turns are trained on)
- **PyTorch** bf16 mixed precision on Ada Lovelace (RTX 4060)

Usage
-----
.. code-block:: bash

    python finetune.py --data_dir data/ --output_dir checkpoints/

Hardware
--------
Calibrated for an NVIDIA RTX 4060 8 GB VRAM.  Peak VRAM usage is
approximately 3.5 GB.  On lower-end GPUs reduce ``MAX_SEQ_LENGTH`` or
``GRADIENT_ACCUMULATION_STEPS`` in ``config/training_config.py``.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

import datasets
import peft
import torch
import transformers
import trl

import config.chat_templates as chat_templates
import config.training_config as training_config


# ---------------------------------------------------------------------------
# Dataset helpers
# ---------------------------------------------------------------------------


def _load_jsonl(path: pathlib.Path) -> list[dict]:
    """Load a JSONL file into a list of dicts.

    Args:
      path: Path to the JSONL file.

    Returns:
      A list of parsed JSON objects.

    Raises:
      SystemExit: If the file does not exist.
    """
    if not path.exists():
        print(f"[ERROR] File not found: {path}", file=sys.stderr)
        sys.exit(1)
    records: list[dict] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _load_tool_schemas(data_dir: pathlib.Path) -> list[dict]:
    """Load tool schemas from ``data_dir/tools.json``.

    Args:
      data_dir: Directory containing ``tools.json``.

    Returns:
      List of tool schema dicts.

    Raises:
      SystemExit: If the file does not exist.
    """
    schemas_file = data_dir / "tools.json"
    if not schemas_file.exists():
        print(
            f"[ERROR] {schemas_file} not found.  "
            "Copy data/tools.json to the data directory.",
            file=sys.stderr,
        )
        sys.exit(1)
    with open(schemas_file, encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# Model and LoRA
# ---------------------------------------------------------------------------


def _build_bnb_config() -> transformers.BitsAndBytesConfig:
    """Build the 4-bit NF4 BitsAndBytesConfig for the base model.

    Returns:
      A configured ``BitsAndBytesConfig`` instance.
    """
    return transformers.BitsAndBytesConfig(
        load_in_4bit=training_config.LOAD_IN_4BIT,
        bnb_4bit_use_double_quant=training_config.BNB_4BIT_USE_DOUBLE_QUANT,
        bnb_4bit_quant_type=training_config.BNB_4BIT_QUANT_TYPE,
        bnb_4bit_compute_dtype=torch.bfloat16,
    )


def _load_model_and_tokenizer(
    model_name: str,
    bnb_config: transformers.BitsAndBytesConfig,
    gpu_id: int | None = None,
) -> tuple[transformers.PreTrainedModel, transformers.PreTrainedTokenizer]:
    """Load the base model in 4-bit and the matching tokenizer.

    Args:
      model_name: HuggingFace model identifier.
      bnb_config: BitsAndBytes quantization configuration.
      gpu_id: Optional GPU device index for ``device_map`` pinning.

    Returns:
      A (model, tokenizer) tuple.
    """
    print(f"[finetune] Loading model: {model_name}")

    # Configure strict map if GPU ID is provided, otherwise fall back to auto
    device_map = "auto" if gpu_id is None else {"": gpu_id}

    model = transformers.AutoModelForCausalLM.from_pretrained(
        model_name,
        quantization_config=bnb_config,
        device_map=device_map,
        trust_remote_code=True,
    )
    model.config.use_cache = False  # incompatible with grad checkpointing

    tokenizer = transformers.AutoTokenizer.from_pretrained(
        model_name,
        trust_remote_code=True,
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    return model, tokenizer


def _apply_lora(
    model: transformers.PreTrainedModel,
    target_modules: list[str],
) -> peft.PeftModel:
    """Prepare the 4-bit model for training and wrap it with LoRA adapters.

    ``peft.prepare_model_for_kbit_training`` must be called BEFORE
    ``peft.get_peft_model`` when the base model is loaded in 4-bit.  It
    enables gradient computation on the non-quantized (fp32/bf16) parts,
    freezes the quantized weights, and casts the layer-norm and embedding
    layers to a trainable dtype.  Without this call, the loss tensor has
    no ``grad_fn`` and ``.backward()`` raises a ``RuntimeError``.

    Args:
      model: The 4-bit quantized base model.
      target_modules: Projection layer names to attach LoRA adapters to.

    Returns:
      A ``PeftModel`` with LoRA adapters added and gradients enabled.
    """
    # Enable gradient flow through the non-quantized (fp32) parts of the
    # 4-bit model and cast normalisation layers to the compute dtype.
    model = peft.prepare_model_for_kbit_training(
        model,
        use_gradient_checkpointing=training_config.GRADIENT_CHECKPOINTING,
    )

    lora_cfg = peft.LoraConfig(
        r=training_config.LORA_R,
        lora_alpha=training_config.LORA_ALPHA,
        target_modules=target_modules,
        lora_dropout=training_config.LORA_DROPOUT,
        bias=training_config.LORA_BIAS,
        task_type=peft.TaskType.CAUSAL_LM,
    )
    model = peft.get_peft_model(model, lora_cfg)
    model.print_trainable_parameters()
    return model


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------


def _make_formatting_func(
    adapter: chat_templates.ChatTemplateAdapter,
):
    """Return a formatting function compatible with TRL SFTTrainer.

    Uses ``adapter.format_for_training`` which produces a compact ChatML
    string WITHOUT injecting full tool schemas into the system prompt.

    Why no schemas in training:
      The tool schemas contain thousands of tokens when serialised as JSON.
      Injecting them into every training example pushes the assistant turn
      past the 2048-token truncation boundary, causing
      ``DataCollatorForCompletionOnlyLM`` to never find the response
      template and masking all labels to -100.  Fine-tuning teaches the
      FORMAT of tool calls (when to call a tool, how to structure the
      JSON), not the schema content — schemas are injected at inference
      time by the Qwen2.5 chat template.

    Args:
      adapter: The chat template adapter for the target model.

    Returns:
      A callable ``(example: dict) -> list[str]`` for SFTTrainer's
      ``formatting_func`` argument.
    """

    def _format(example: dict) -> list[str]:
        """Format one training example.

        Args:
          example: A dataset batch dict with a ``messages`` list.

        Returns:
          A list containing the single formatted string.
        """
        return [adapter.format_for_training(msg) for msg in example["messages"]]

    return _format


def _build_training_args(output_dir: pathlib.Path) -> trl.SFTConfig:
    """Construct the SFTConfig for the SFTTrainer.

    All values come from ``config/training_config.py``.

    Args:
        output_dir: Directory where checkpoints are saved.

    Returns:
        A configured ``SFTConfig`` instance.
    """
    return trl.SFTConfig(
        output_dir=str(output_dir),
        per_device_train_batch_size=(
            training_config.PER_DEVICE_TRAIN_BATCH_SIZE
        ),
        gradient_accumulation_steps=(
            training_config.GRADIENT_ACCUMULATION_STEPS
        ),
        num_train_epochs=training_config.NUM_TRAIN_EPOCHS,
        learning_rate=training_config.LEARNING_RATE,
        warmup_ratio=training_config.WARMUP_RATIO,
        lr_scheduler_type=training_config.LR_SCHEDULER_TYPE,
        bf16=training_config.BF16,
        fp16=training_config.FP16,
        gradient_checkpointing=training_config.GRADIENT_CHECKPOINTING,
        optim=training_config.OPTIM,
        logging_steps=training_config.LOGGING_STEPS,
        eval_strategy="steps",
        eval_steps=training_config.EVAL_STEPS,
        save_strategy="steps",
        save_steps=training_config.SAVE_STEPS,
        save_total_limit=training_config.SAVE_TOTAL_LIMIT,
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        report_to="none",
        dataloader_num_workers=training_config.DATALOADER_NUM_WORKERS,
        max_seq_length=training_config.MAX_SEQ_LENGTH,  # <-- Moved here to fix truncation
    )


# def _build_training_args(output_dir: pathlib.Path) -> transformers.TrainingArguments:
#   """Construct the TrainingArguments for the SFTTrainer.

#   All values come from ``config/training_config.py``.

#   Args:
#     output_dir: Directory where checkpoints are saved.

#   Returns:
#     A configured ``TrainingArguments`` instance.
#   """
#   return transformers.TrainingArguments(
#     output_dir=str(output_dir),
#     per_device_train_batch_size=(
#       training_config.PER_DEVICE_TRAIN_BATCH_SIZE
#     ),
#     gradient_accumulation_steps=(
#       training_config.GRADIENT_ACCUMULATION_STEPS
#     ),
#     num_train_epochs=training_config.NUM_TRAIN_EPOCHS,
#     learning_rate=training_config.LEARNING_RATE,
#     warmup_ratio=training_config.WARMUP_RATIO,
#     lr_scheduler_type=training_config.LR_SCHEDULER_TYPE,
#     bf16=training_config.BF16,
#     fp16=training_config.FP16,
#     gradient_checkpointing=training_config.GRADIENT_CHECKPOINTING,
#     optim=training_config.OPTIM,
#     logging_steps=training_config.LOGGING_STEPS,
#     eval_strategy="steps",
#     eval_steps=training_config.EVAL_STEPS,
#     save_strategy="steps",
#     save_steps=training_config.SAVE_STEPS,
#     save_total_limit=training_config.SAVE_TOTAL_LIMIT,
#     load_best_model_at_end=True,
#     metric_for_best_model="eval_loss",
#     report_to="none",
#     dataloader_num_workers=training_config.DATALOADER_NUM_WORKERS,
#   )


def _train(
    data_dir: pathlib.Path,
    output_dir: pathlib.Path,
    model_key_or_hf_id: str | None = None,
    gpu_id: int | None = None,
) -> None:
    """Run the full QLoRA fine-tuning pipeline.

    Steps:
    1. Load model + tokenizer in 4-bit NF4.
    2. Apply LoRA adapters.
    3. Format training and validation datasets.
    4. Run SFTTrainer with DataCollatorForCompletionOnlyLM.
    5. Save the best LoRA adapter checkpoint.

    Args:
      data_dir: Directory containing train.jsonl, val.jsonl, tools.json.
      output_dir: Directory where LoRA adapter checkpoints are saved.
      model_key_or_hf_id: Registry key or HuggingFace id for the base model.
      gpu_id: Optional GPU device index to hard-lock execution to.
    """
    if gpu_id is not None:
        if not torch.cuda.is_available():
            print(
                "[ERROR] CUDA is completely unavailable, but --gpu flag was passed.",
                file=sys.stderr,
            )
            sys.exit(1)
        if gpu_id >= torch.cuda.device_count():
            print(
                f"[ERROR] Requested GPU ID {gpu_id}, but only {torch.cuda.device_count()} device(s) found.",
                file=sys.stderr,
            )
            sys.exit(1)
        print(
            f"[finetune] Hard locking pipeline to GPU device: {torch.cuda.get_device_name(gpu_id)}"
        )

    _load_tool_schemas(data_dir)
    model_name = training_config.resolve_training_model(model_key_or_hf_id)
    training_config.require_transformers_for_model(model_name)
    target_modules = training_config.resolve_lora_target_modules(model_name)
    adapter = chat_templates.ChatTemplateAdapter.for_model(model_name)

    bnb_config = _build_bnb_config()
    model, tokenizer = _load_model_and_tokenizer(
        model_name,
        bnb_config,
        gpu_id=gpu_id,
    )
    model = _apply_lora(model, target_modules)

    train_records = _load_jsonl(data_dir / "train.jsonl")
    val_records = _load_jsonl(data_dir / "val.jsonl")
    print(f"[finetune] train={len(train_records)}, val={len(val_records)}")

    # Wrap in HuggingFace Dataset for SFTTrainer compatibility.
    # Each record has a "messages" key (list of message dicts).
    train_ds = datasets.Dataset.from_list(train_records)
    val_ds = datasets.Dataset.from_list(val_records)

    formatting_func = _make_formatting_func(adapter)

    # Use token IDs for the response template rather than the raw string.
    # DataCollatorForCompletionOnlyLM encodes the string in isolation, but
    # the tokenizer may produce different IDs for the same character sequence
    # depending on surrounding context (e.g. newline handling, BPE merges).
    # Passing pre-computed token IDs avoids this mismatch entirely.
    response_template_ids = adapter.response_template_token_ids(tokenizer)
    collator = trl.DataCollatorForCompletionOnlyLM(
        response_template=response_template_ids,
        tokenizer=tokenizer,
    )

    training_args = _build_training_args(output_dir)

    trainer = trl.SFTTrainer(
        model=model,
        args=training_args,
        train_dataset=train_ds,
        eval_dataset=val_ds,
        tokenizer=tokenizer,
        # processing_class=tokenizer,
        data_collator=collator,
        formatting_func=formatting_func,
        # max_seq_length=training_config.MAX_SEQ_LENGTH,
    )

    print("[finetune] Starting training ...")
    trainer.train()

    best_dir = output_dir / "best"
    trainer.save_model(str(best_dir))
    tokenizer.save_pretrained(str(best_dir))
    print(f"[finetune] Saved best adapter to {best_dir}")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
      Parsed argument namespace.
    """
    parser = argparse.ArgumentParser(
        description="cBioMOL QLoRA fine-tuning",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--data_dir",
        type=pathlib.Path,
        default=pathlib.Path("data"),
        help="Directory containing train.jsonl, val.jsonl, tools.json.",
    )
    parser.add_argument(
        "--output_dir",
        type=pathlib.Path,
        default=pathlib.Path("checkpoints"),
        help="Directory where LoRA adapter checkpoints are saved.",
    )
    parser.add_argument(
        "--gpu",
        type=int,
        default=None,
        help="Hard lock execution to a specific GPU ID (e.g., 0). Fails fast if unavailable.",
    )
    supported = sorted(training_config.SUPPORTED_BASE_MODELS)
    parser.add_argument(
        "--model",
        default=None,
        help=(
            "Registry key or HuggingFace id for the base model "
            f"(default: {training_config.DEFAULT_MODEL_KEY}). "
            f"Supported keys: {', '.join(supported)}."
        ),
    )
    return parser.parse_args()


def main() -> None:
    """Entry point for the fine-tuning script."""
    args = _parse_args()
    _train(
        args.data_dir,
        args.output_dir,
        model_key_or_hf_id=args.model,
        gpu_id=args.gpu,
    )


if __name__ == "__main__":
    main()
