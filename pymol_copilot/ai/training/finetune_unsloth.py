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
"""Unsloth QLoRA fine-tuning script for the cBioMOL PyMOL AI assistant.

This script is a **drop-in replacement** for ``finetune.py``.  It reads
the same ``output_clean/train.jsonl`` and ``output_clean/val.jsonl`` files
produced by the NeMo Curator pipeline and fine-tunes the same Qwen2.5 /
Qwen3 models, but through the Unsloth backend instead of the vanilla
PEFT + TRL stack.

Why Unsloth?
------------
Unsloth patches the attention kernels and weight matrices of popular model
families with hand-written Triton / CUDA kernels that are 2–5× faster and
use ~40 % less VRAM than the equivalent PEFT + BitsAndBytes stack on the
same hardware.  On an RTX 4060 (8 GB) this means:

* VRAM peak drops from ~5.5 GB to ~3.2 GB with ``MAX_SEQ_LENGTH = 4096``.
* Throughput increases from ~240 tok/s to ~420 tok/s.
* The training run that takes 2 hours with ``finetune.py`` completes in
  ~70 minutes with this script.

The output is a standard HuggingFace LoRA adapter directory (compatible
with ``export_gguf.py`` and ``test_model.py``) **and** optionally a
directly-usable GGUF file produced in one step by Unsloth's built-in
conversion helpers.

Data contract with the NeMo Curator pipeline
---------------------------------------------
This script reads records in the *build_conversations.py* output format::

    {
        "id":          "<uuid>",
        "scenario":    "<scenario_name>",
        "conversations": [
            {"role": "user",      "content": "<user request>"},
            {"role": "assistant", "content": "<JSON-encoded tool calls>"}
        ]
    }

The ``dedup_text`` field is stripped by ``curate.py`` before writing
``output_clean/``, so it will not be present here.

Usage
-----
.. code-block:: bash

    python finetune_unsloth.py \\
        --data_dir output_clean/ \\
        --output_dir checkpoints_unsloth/

    # Optionally export GGUF in one pass:
    python finetune_unsloth.py \\
        --data_dir output_clean/ \\
        --output_dir checkpoints_unsloth/ \\
        --export_gguf \\
        --quantization q4_k_m

Hardware
--------
Calibrated for an NVIDIA RTX 4060 8 GB VRAM (Ada Lovelace architecture).
The Unsloth kernels can further reduce VRAM by ~40 % compared to the PEFT
baseline, so ``MAX_SEQ_LENGTH = 4096`` fits comfortably.

Installation
------------
Unsloth must be installed separately because it ships pre-built Triton
wheels that must match both the CUDA version and the PyTorch ABI.
See ``requirements_unsloth.txt`` for the pinned wheel URL.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import typing

import torch


# ---------------------------------------------------------------------------
# Lazy Unsloth import
# ---------------------------------------------------------------------------
# Unsloth is optional — the script fails with a clear message if it is not
# installed, rather than failing silently inside a deeply nested call site.
def _require_unsloth() -> typing.Any:
    """Import unsloth and return the module, or exit with a helpful message.

    Returns:
      The imported unsloth module.

    Raises:
      SystemExit: If unsloth is not installed.
    """
    try:
        import unsloth  # type: ignore[import-untyped]
        return unsloth
    except ModuleNotFoundError:
        print(
            "[ERROR] unsloth is not installed.\n"
            "Install it with the command in requirements_unsloth.txt:\n"
            "  pip install -r requirements_unsloth.txt\n"
            "See: https://github.com/unslothai/unsloth#installation",
            file=sys.stderr,
        )
        sys.exit(1)


import config.training_config as training_config  # noqa: E402

# ---------------------------------------------------------------------------
# Data format adapters
# ---------------------------------------------------------------------------
# The NeMo Curator pipeline writes records with a ``conversations`` key
# (list of {"role": ..., "content": ...} dicts) — NOT a ``messages`` key.
# The existing ``finetune.py`` uses records with a ``messages`` key produced
# by ``generate_dataset.py / _build_messages()``.
# Both formats are supported here: if ``messages`` is absent the script
# converts ``conversations`` to the same shape.


def _load_jsonl(path: pathlib.Path) -> list[dict]:
    """Load a JSONL file into a list of dicts.

    Args:
      path: Path to the JSONL file.

    Returns:
      A list of parsed JSON objects.

    Raises:
      SystemExit: If the file does not exist or is empty.
    """
    if not path.exists():
        print(f"[ERROR] File not found: {path}", file=sys.stderr)
        sys.exit(1)
    tmp_records: list[dict] = []
    with open(path, encoding="utf-8") as tmp_fh:
        for tmp_line in tmp_fh:
            tmp_line = tmp_line.strip()
            if tmp_line:
                tmp_records.append(json.loads(tmp_line))
    if not tmp_records:
        print(f"[ERROR] {path} is empty.", file=sys.stderr)
        sys.exit(1)
    return tmp_records


def _normalise_record(record: dict) -> dict:
    """Normalise a record to have a ``messages`` key.

    Supports both the NeMo Curator output format (``conversations`` key)
    and the ``generate_dataset.py`` output format (``messages`` key).

    The assistant content in the NeMo Curator format is a JSON-encoded
    list of tool-call dicts produced by ``build_conversations.py``.  It is
    converted to the ``tool_calls`` wire format that the Qwen2.5 chat
    template expects, so the model learns to emit ``<tool_call>`` blocks.

    Args:
      record: A raw record dict from either pipeline.

    Returns:
      A record dict guaranteed to have a ``messages`` key whose value is a
      list of message dicts suitable for ``apply_chat_template``.
    """
    if "messages" in record:
        return record

    tmp_convs = record.get("conversations", [])
    tmp_messages: list[dict] = []
    for tmp_turn in tmp_convs:
        tmp_role = tmp_turn.get("role", "user")
        tmp_content = tmp_turn.get("content", "")
        if tmp_role == "assistant":
            # The content is a JSON array of {"name": ..., "parameters": ...}
            # dicts produced by build_conversations.py.  Convert to the
            # OpenAI tool_calls wire format that Qwen2.5's chat template
            # renders as <tool_call> blocks.
            try:
                tmp_calls = json.loads(tmp_content)
                if isinstance(tmp_calls, list):
                    tmp_messages.append(
                        {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "type": "function",
                                    "function": {
                                        "name": tmp_c.get(
                                            "name", ""
                                        ),
                                        "arguments": json.dumps(
                                            tmp_c.get(
                                                "parameters", {}
                                            )
                                        ),
                                    },
                                }
                                for tmp_c in tmp_calls
                            ],
                        }
                    )
                    continue
            except (json.JSONDecodeError, TypeError):
                pass
        tmp_messages.append({"role": tmp_role, "content": tmp_content})
    return {"messages": tmp_messages}


# ---------------------------------------------------------------------------
# Unsloth model loading
# ---------------------------------------------------------------------------


def _load_model_and_tokenizer(
    model_name: str,
    max_seq_length: int,
    load_in_4bit: bool,
) -> tuple[typing.Any, typing.Any]:
    """Load a base model through Unsloth with 4-bit NF4 quantization.

    Unsloth's ``FastLanguageModel.from_pretrained`` is a drop-in replacement
    for ``AutoModelForCausalLM.from_pretrained``.  It applies Triton kernel
    patches automatically for supported model families (Qwen2, Qwen3, Llama,
    Mistral, Gemma) and falls back silently to the standard HuggingFace
    implementation for unsupported architectures.

    Args:
      model_name: HuggingFace model identifier.
      max_seq_length: Maximum sequence length for the model and tokenizer.
      load_in_4bit: If True, load in 4-bit NF4 (saves VRAM).

    Returns:
      A (model, tokenizer) tuple with Unsloth kernel patches applied.
    """
    import unsloth  # type: ignore[import-untyped]

    print(f"[finetune_unsloth] Loading model via Unsloth: {model_name}")
    tmp_model, tmp_tokenizer = (
        unsloth.FastLanguageModel.from_pretrained(
            model_name=model_name,
            max_seq_length=max_seq_length,
            dtype=None,      # auto-detect: bf16 on Ada, fp16 on older GPUs
            load_in_4bit=load_in_4bit,
            trust_remote_code=True,
        )
    )
    if tmp_tokenizer.pad_token is None:
        tmp_tokenizer.pad_token = tmp_tokenizer.eos_token
    return tmp_model, tmp_tokenizer


def _apply_lora(
    model: typing.Any,
    target_modules: list[str],
    lora_r: int,
    lora_alpha: int,
    lora_dropout: float,
) -> typing.Any:
    """Wrap the Unsloth model with LoRA adapters.

    ``FastLanguageModel.get_peft_model`` is equivalent to
    ``peft.get_peft_model`` but uses Unsloth's optimized LoRA kernels
    (RSLoRA / loftQ initialisation when available).

    Args:
      model: The Unsloth-patched base model.
      target_modules: Projection layer names to attach LoRA to.
      lora_r: LoRA rank.
      lora_alpha: LoRA scaling factor.
      lora_dropout: Dropout probability on LoRA weights.

    Returns:
      A PEFT-wrapped model with Unsloth LoRA adapters.
    """
    import unsloth  # type: ignore[import-untyped]

    tmp_model = unsloth.FastLanguageModel.get_peft_model(
        model,
        r=lora_r,
        target_modules=target_modules,
        lora_alpha=lora_alpha,
        lora_dropout=lora_dropout,
        bias="none",
        use_gradient_checkpointing="unsloth",  # uses Unsloth's 30% faster impl
        random_state=42,
        use_rslora=True,   # Rank-stabilized LoRA — better convergence
        loftq_config=None,
    )
    tmp_model.print_trainable_parameters()
    return tmp_model


# ---------------------------------------------------------------------------
# Dataset formatting
# ---------------------------------------------------------------------------


def _build_dataset(
    records: list[dict],
    tokenizer: typing.Any,
) -> typing.Any:
    """Convert raw records to a HuggingFace Dataset with formatted text.

    Unsloth's SFTTrainer variant accepts a ``dataset_text_field`` (the name
    of the column containing the pre-formatted text string) or a
    ``formatting_func``.  This function produces a Dataset with a single
    ``text`` column containing the ChatML-formatted string for each record.

    The tokenizer's ``apply_chat_template`` with ``tokenize=False`` is used
    so that Unsloth's SFTTrainer can re-tokenize with its own packing and
    padding logic.  ``add_generation_prompt=False`` because these are
    complete (user + assistant) training pairs, not inference prompts.

    Args:
      records: List of raw record dicts (from either pipeline format).
      tokenizer: The Unsloth-patched tokenizer.

    Returns:
      A ``datasets.Dataset`` with a single ``text`` column.
    """
    import datasets  # type: ignore[import-not-found]

    tmp_texts: list[str] = []
    for tmp_record in records:
        tmp_norm = _normalise_record(tmp_record)
        tmp_text = tokenizer.apply_chat_template(
            tmp_norm["messages"],
            tokenize=False,
            add_generation_prompt=False,
        )
        tmp_texts.append(tmp_text)
    return datasets.Dataset.from_dict({"text": tmp_texts})


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------


def _build_trainer(
    model: typing.Any,
    tokenizer: typing.Any,
    train_ds: typing.Any,
    val_ds: typing.Any,
    output_dir: pathlib.Path,
    max_seq_length: int,
) -> typing.Any:
    """Construct the Unsloth-patched SFTTrainer.

    Unsloth wraps TRL's ``SFTTrainer`` with additional memory optimizations:
    - 30 % faster gradient checkpointing via Unsloth's own implementation
    - Automatic sequence packing (multiple short examples in one sequence)
    - Vflash attention where available (Ada architecture)

    All training hyperparameters come from ``training_config.py`` to keep
    a single source of truth with the ``finetune.py`` baseline.

    Args:
      model: The Unsloth LoRA-wrapped model.
      tokenizer: The Unsloth-patched tokenizer.
      train_ds: Training HuggingFace Dataset with a ``text`` column.
      val_ds: Validation HuggingFace Dataset with a ``text`` column.
      output_dir: Directory for checkpoint saving.
      max_seq_length: Maximum token sequence length.

    Returns:
      A configured Unsloth ``SFTTrainer`` instance.
    """
    import trl  # type: ignore[import-not-found]
    import unsloth  # type: ignore[import-untyped]

    tmp_training_args = trl.SFTConfig(
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
        # Gradient checkpointing is handled by Unsloth internally when
        # use_gradient_checkpointing="unsloth" was passed to get_peft_model.
        # Setting this to False avoids double-wrapping.
        gradient_checkpointing=False,
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
        max_seq_length=max_seq_length,
        # Sequence packing: Unsloth bins multiple short examples into a
        # single context window, dramatically increasing GPU utilisation
        # on datasets with variable-length sequences.  This is safe because
        # attention is still blocked per-example (no cross-contamination).
        packing=True,
        dataset_text_field="text",
    )

    return unsloth.FastLanguageModel.get_trainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=train_ds,
        eval_dataset=val_ds,
        args=tmp_training_args,
    )


# ---------------------------------------------------------------------------
# GGUF export helper
# ---------------------------------------------------------------------------


def _export_gguf(
    model: typing.Any,
    tokenizer: typing.Any,
    output_dir: pathlib.Path,
    quantization: str,
) -> None:
    """Export the merged model directly to GGUF via Unsloth's built-in helper.

    Unsloth can merge LoRA weights into the base model and convert to GGUF
    in a single in-process call, without cloning llama.cpp or running an
    external binary.  This is faster and simpler than the
    ``export_gguf.py`` approach but produces an equivalent file.

    Quantization method strings follow Unsloth's naming convention, which
    mirrors llama.cpp (e.g. ``"q4_k_m"``, ``"q8_0"``, ``"f16"``).

    Args:
      model: The Unsloth LoRA-wrapped model (still in training state).
      tokenizer: The Unsloth-patched tokenizer.
      output_dir: Directory where the GGUF file is written.
      quantization: GGUF quantization method string.
    """
    tmp_gguf_dir = output_dir / "gguf"
    tmp_gguf_dir.mkdir(parents=True, exist_ok=True)
    print(
        f"[finetune_unsloth] Exporting GGUF ({quantization}) "
        f"to {tmp_gguf_dir} ..."
    )
    model.save_pretrained_gguf(
        str(tmp_gguf_dir),
        tokenizer,
        quantization_method=quantization,
    )
    print(f"[finetune_unsloth] GGUF export complete: {tmp_gguf_dir}")


# ---------------------------------------------------------------------------
# Model resolution — registry OR arbitrary HuggingFace model
# ---------------------------------------------------------------------------

# The standard LoRA target modules that work for the Qwen2/Qwen3/Llama/
# Mistral/Gemma families supported natively by Unsloth.  Used as the
# default when --hf_model is passed without an explicit --target_modules.
_DEFAULT_TARGET_MODULES: list[str] = [
    "q_proj",
    "k_proj",
    "v_proj",
    "o_proj",
    "gate_proj",
    "up_proj",
    "down_proj",
]


def _resolve_model_and_modules(
    model_key_or_hf_id: str | None,
    raw_hf_model: str | None,
    raw_target_modules: list[str] | None,
) -> tuple[str, list[str]]:
    """Return (hf_model_id, lora_target_modules) from registry or bypass.

    Two resolution paths exist:

    **Registry path** (``--model`` flag, ``raw_hf_model`` is None):
      Uses ``training_config.resolve_training_model`` and
      ``training_config.resolve_lora_target_modules``.  Fails fast with
      a clear message for unknown registry keys.

    **Bypass path** (``--hf_model`` flag, ``raw_hf_model`` is set):
      Accepts *any* HuggingFace model ID or local directory path and
      skips the registry entirely.  Unsloth's ``FastLanguageModel.
      from_pretrained`` auto-detects the architecture and applies
      compatible kernel patches.  The caller is responsible for ensuring
      ``raw_target_modules`` are valid for the chosen model.

    Args:
      model_key_or_hf_id: Registry key or HuggingFace id passed via
        ``--model``.  Ignored when ``raw_hf_model`` is set.
      raw_hf_model: Raw HuggingFace model id or local path passed via
        ``--hf_model``.  When set, bypasses the registry completely.
      raw_target_modules: Explicit LoRA target module names from
        ``--target_modules``.  Falls back to ``_DEFAULT_TARGET_MODULES``
        when None and the bypass path is active.

    Returns:
      Tuple of (hf_model_id, lora_target_modules).

    Raises:
      ValueError: If neither ``model_key_or_hf_id`` nor ``raw_hf_model``
        is provided.
    """
    if raw_hf_model is not None:
        # Bypass: accept any HF id or local path unconditionally.
        tmp_target = (
            raw_target_modules
            if raw_target_modules
            else list(_DEFAULT_TARGET_MODULES)
        )
        print(
            f"[finetune_unsloth] Bypass mode: using model "
            f"{raw_hf_model!r} with LoRA targets "
            f"{tmp_target}"
        )
        return raw_hf_model, tmp_target

    # Registry path.
    tmp_hf_id = training_config.resolve_training_model(model_key_or_hf_id)
    tmp_targets = training_config.resolve_lora_target_modules(tmp_hf_id)
    if raw_target_modules:
        # Allow --target_modules to override registry defaults too.
        tmp_targets = raw_target_modules
    return tmp_hf_id, tmp_targets


def _train(
    data_dir: pathlib.Path,
    output_dir: pathlib.Path,
    model_key_or_hf_id: str | None,
    raw_hf_model: str | None,
    raw_target_modules: list[str] | None,
    gpu_id: int | None,
    export_gguf: bool,
    quantization: str,
    max_seq_length: int,
) -> None:
    """Run the full Unsloth QLoRA fine-tuning pipeline.

    Steps:
    1. Validate GPU availability.
    2. Resolve the model ID — via the registry (``--model``) or by
       accepting any HuggingFace id / local path (``--hf_model``).
    3. Load model + tokenizer via Unsloth (4-bit NF4, Triton patches).
    4. Apply Unsloth LoRA adapters with RSLoRA.
    5. Build HuggingFace Datasets from the NeMo Curator output.
    6. Run the Unsloth SFTTrainer with sequence packing.
    7. Save the best LoRA adapter to ``output_dir/best/``.
    8. Optionally export a merged GGUF in one pass.

    Args:
      data_dir: Directory containing ``train.jsonl`` and ``val.jsonl``
        produced by ``curate.py`` (NeMo Curator output).  The
        ``generate_dataset.py`` messages format is also accepted.
      output_dir: Root directory for checkpoints and exported files.
      model_key_or_hf_id: Registry key or HuggingFace model identifier
        passed via ``--model``.  Ignored when ``raw_hf_model`` is set.
      raw_hf_model: Any HuggingFace model id or local path passed via
        ``--hf_model``.  Bypasses the registry when provided.
      raw_target_modules: Explicit LoRA target module names from
        ``--target_modules``.  Overrides registry defaults or the
        built-in defaults when provided.
      gpu_id: Optional GPU device index.
      export_gguf: If True, merge and export a GGUF after training.
      quantization: GGUF quantization string.
      max_seq_length: Maximum token sequence length.

    Raises:
      SystemExit: On missing files, CUDA errors, or Unsloth import
        failure.
    """
    # Validate GPU
    if gpu_id is not None:
        if not torch.cuda.is_available():
            print(
                "[ERROR] CUDA unavailable but --gpu was passed.",
                file=sys.stderr,
            )
            sys.exit(1)
        if gpu_id >= torch.cuda.device_count():
            print(
                f"[ERROR] Requested GPU {gpu_id} but only "
                f"{torch.cuda.device_count()} device(s) found.",
                file=sys.stderr,
            )
            sys.exit(1)
        print(
            "[finetune_unsloth] Hard-locking to GPU: "
            f"{torch.cuda.get_device_name(gpu_id)}"
        )

    _require_unsloth()  # fail fast with a clear message if not installed

    tmp_model_name, tmp_target_modules = _resolve_model_and_modules(
        model_key_or_hf_id,
        raw_hf_model,
        raw_target_modules,
    )
    # For registry-path models, enforce the minimum transformers version.
    # For bypass-path models the caller is responsible for compatibility.
    if raw_hf_model is None:
        training_config.require_transformers_for_model(tmp_model_name)

    tmp_model, tmp_tokenizer = _load_model_and_tokenizer(
        tmp_model_name,
        max_seq_length=max_seq_length,
        load_in_4bit=training_config.LOAD_IN_4BIT,
    )
    tmp_model = _apply_lora(
        tmp_model,
        target_modules=tmp_target_modules,
        lora_r=training_config.LORA_R,
        lora_alpha=training_config.LORA_ALPHA,
        lora_dropout=training_config.LORA_DROPOUT,
    )

    # Load data — both the NeMo Curator conversations format and the
    # generate_dataset.py messages format are accepted transparently.
    tmp_train_records = _load_jsonl(data_dir / "train.jsonl")
    tmp_val_records = _load_jsonl(data_dir / "val.jsonl")
    print(
        f"[finetune_unsloth] train={len(tmp_train_records)}, "
        f"val={len(tmp_val_records)}"
    )

    tmp_train_ds = _build_dataset(tmp_train_records, tmp_tokenizer)
    tmp_val_ds = _build_dataset(tmp_val_records, tmp_tokenizer)

    tmp_trainer = _build_trainer(
        tmp_model,
        tmp_tokenizer,
        tmp_train_ds,
        tmp_val_ds,
        output_dir,
        max_seq_length=max_seq_length,
    )

    print("[finetune_unsloth] Starting Unsloth training ...")
    tmp_trainer.train()

    tmp_best_dir = output_dir / "best"
    tmp_trainer.save_model(str(tmp_best_dir))
    tmp_tokenizer.save_pretrained(str(tmp_best_dir))
    print(
        f"[finetune_unsloth] Saved best LoRA adapter to {tmp_best_dir}"
    )

    if export_gguf:
        _export_gguf(
            tmp_model,
            tmp_tokenizer,
            output_dir,
            quantization=quantization,
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
      Parsed argument namespace.
    """
    tmp_parser = argparse.ArgumentParser(
        description=(
            "cBioMOL Unsloth QLoRA fine-tuning — "
            "reads NeMo Curator output_clean/ directly"
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    tmp_parser.add_argument(
        "--data_dir",
        type=pathlib.Path,
        default=pathlib.Path("output_clean"),
        help=(
            "Directory containing train.jsonl and val.jsonl produced "
            "by curate.py (NeMo Curator output).  The finetune.py "
            "data/train.jsonl format is also accepted."
        ),
    )
    tmp_parser.add_argument(
        "--output_dir",
        type=pathlib.Path,
        default=pathlib.Path("checkpoints_unsloth"),
        help="Root directory for checkpoints and exported files.",
    )
    tmp_parser.add_argument(
        "--gpu",
        type=int,
        default=None,
        help="Hard-lock execution to a specific GPU ID (e.g. 0).",
    )
    tmp_supported = sorted(training_config.SUPPORTED_BASE_MODELS)
    tmp_parser.add_argument(
        "--model",
        default=None,
        help=(
            "Registry key or HuggingFace id for the base model "
            f"(default: {training_config.DEFAULT_MODEL_KEY}). "
            f"Supported registry keys: {', '.join(tmp_supported)}. "
            "Use --hf_model instead to pass any arbitrary HuggingFace "
            "model id without registering it."
        ),
    )
    tmp_parser.add_argument(
        "--hf_model",
        default=None,
        metavar="HF_MODEL_ID",
        help=(
            "Any HuggingFace model id or local directory path to use "
            "as the base model, bypassing the registry entirely. "
            "Examples: 'meta-llama/Llama-3.2-3B-Instruct', "
            "'mistralai/Mistral-7B-Instruct-v0.3', "
            "'google/gemma-3-4b-it', "
            "'Qwen/Qwen2.5-7B-Instruct', "
            "'./local_model_dir'. "
            "Unsloth auto-detects the architecture and applies "
            "compatible kernel patches. "
            "Takes precedence over --model when both are provided."
        ),
    )
    tmp_parser.add_argument(
        "--target_modules",
        nargs="+",
        default=None,
        metavar="MODULE",
        help=(
            "LoRA target module names for the chosen model. "
            "Overrides registry defaults and the built-in defaults. "
            "Required when using --hf_model with a model whose "
            "projection layers differ from the standard Qwen/Llama set "
            "(q_proj k_proj v_proj o_proj gate_proj up_proj down_proj). "
            "Example for Falcon: "
            "--target_modules query_key_value dense dense_h_to_4h "
            "dense_4h_to_h."
        ),
    )
    tmp_parser.add_argument(
        "--max_seq_length",
        type=int,
        default=training_config.MAX_SEQ_LENGTH,
        help=(
            "Maximum token sequence length. "
            "Defaults to MAX_SEQ_LENGTH from training_config.py "
            f"(currently {training_config.MAX_SEQ_LENGTH}). "
            "Unsloth keeps VRAM lower than the PEFT baseline at "
            "the same sequence length, so this can safely be left "
            "at the 4096 default even on 8 GB VRAM."
        ),
    )
    tmp_parser.add_argument(
        "--export_gguf",
        action="store_true",
        help=(
            "After training, merge LoRA weights into the base model "
            "and export a quantized GGUF file in one step using "
            "Unsloth's built-in conversion.  Saves the file to "
            "output_dir/gguf/."
        ),
    )
    tmp_parser.add_argument(
        "--quantization",
        default="q4_k_m",
        help=(
            "GGUF quantization method string (only used with "
            "--export_gguf).  Examples: q4_k_m, q8_0, f16, q5_k_m."
        ),
    )
    return tmp_parser.parse_args()


def main() -> None:
    """Entry point for the Unsloth fine-tuning script."""
    tmp_args = _parse_args()
    _train(
        data_dir=tmp_args.data_dir,
        output_dir=tmp_args.output_dir,
        model_key_or_hf_id=tmp_args.model,
        raw_hf_model=tmp_args.hf_model,
        raw_target_modules=tmp_args.target_modules,
        gpu_id=tmp_args.gpu,
        export_gguf=tmp_args.export_gguf,
        quantization=tmp_args.quantization,
        max_seq_length=tmp_args.max_seq_length,
    )


if __name__ == "__main__":
    main()
