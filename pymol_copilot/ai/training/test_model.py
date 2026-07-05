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
"""LoRA adapter smoke test for the cBioMOL AI assistant.

Loads the fine-tuned LoRA adapter on top of the 4-bit base model and
runs five canonical prompts.  The output is printed verbatim for manual
inspection — no automated pass/fail judgment is made at this stage,
because generation quality is subjective.

The five canonical prompts cover:
1. Single positive tool call (load structure)
2. Multi-step tool call (load + color + save image)
3. Negative viewport request (rotate)
4. Negative out-of-scope request (molecular dynamics)
5. Context-aware request (refer to already-loaded structure)

Run this step BEFORE the GGUF export to verify the adapter produces
recognisable tool calls.  If the outputs look wrong, inspect
``checkpoints/`` and use an earlier checkpoint.

Usage
-----
.. code-block:: bash

    python test_model.py --checkpoint_dir checkpoints/best/
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

import peft
import torch
import transformers

import config.chat_templates as chat_templates
import config.training_config as training_config


# ---------------------------------------------------------------------------
# Canonical test prompts
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are a PyMOL AI assistant for the cBioMOL platform. "
    "You help structural biologists automate protein visualization "
    "workflows using natural language. "
    "When the user asks you to perform a structural biology operation, "
    "respond with the appropriate tool call. "
    "For viewport operations (rotate, zoom), explain they must be done "
    "manually."
)

_TEST_CASES: list[dict] = [
    {
        "label": "1 — Positive single tool (load structure)",
        "user": "Load the human insulin receptor from the PDB (2HR7).",
        "expected": "load_structure",
    },
    {
        "label": "2 — Positive multi-step (load + color + save)",
        "user": (
            "Load hemoglobin (4HHB), color each chain a different "
            "color, then save a preview PNG image."
        ),
        "expected": "multiple tool calls",
    },
    {
        "label": "3 — Negative viewport (rotate)",
        "user": "Rotate the molecule 90 degrees around the Y axis.",
        "expected": "[] or text refusal",
    },
    {
        "label": "4 — Negative out-of-scope (molecular dynamics)",
        "user": "Run a 10 ns molecular dynamics simulation of this protein.",
        "expected": "[] or text refusal",
    },
    {
        "label": "5 — Context-aware (refer to loaded structure)",
        "user": "Now color the structure I just loaded by secondary structure.",
        "expected": "color_by_secondary_structure",
    },
]


# ---------------------------------------------------------------------------
# Model loading
# ---------------------------------------------------------------------------


def _load_model(
    checkpoint_dir: pathlib.Path,
    model_key_or_hf_id: str | None = None,
) -> tuple[peft.PeftModel, transformers.PreTrainedTokenizer, str]:
    """Load the fine-tuned LoRA adapter on the 4-bit base model.

    The base model is loaded in 4-bit NF4 (identical settings to
    training) and the LoRA adapter from ``checkpoint_dir`` is applied.

    Args:
      checkpoint_dir: Path to the saved LoRA adapter directory
        (output of ``finetune.py``).
      model_key_or_hf_id: Optional registry key or HuggingFace id override.

    Returns:
      A (peft_model, tokenizer, hf_model_id) tuple ready for inference.

    Raises:
      SystemExit: If the checkpoint directory does not exist.
    """
    if not checkpoint_dir.exists():
        print(
            f"[ERROR] Checkpoint directory not found: {checkpoint_dir}",
            file=sys.stderr,
        )
        sys.exit(1)

    model_name = training_config.resolve_training_model(
        model_key_or_hf_id,
        checkpoint_dir=checkpoint_dir,
    )
    training_config.require_transformers_for_model(model_name)
    print(f"[test_model] Base model : {model_name}")
    print(f"[test_model] Adapter    : {checkpoint_dir}")

    bnb_config = transformers.BitsAndBytesConfig(
        load_in_4bit=training_config.LOAD_IN_4BIT,
        bnb_4bit_use_double_quant=training_config.BNB_4BIT_USE_DOUBLE_QUANT,
        bnb_4bit_quant_type=training_config.BNB_4BIT_QUANT_TYPE,
        bnb_4bit_compute_dtype=torch.bfloat16,
    )

    base = transformers.AutoModelForCausalLM.from_pretrained(
        model_name,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
    )
    base.config.use_cache = True  # enable KV cache for inference

    model = peft.PeftModel.from_pretrained(base, str(checkpoint_dir))
    model.eval()

    tokenizer = transformers.AutoTokenizer.from_pretrained(
        str(checkpoint_dir),
        trust_remote_code=True,
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    return model, tokenizer, model_name


# ---------------------------------------------------------------------------
# Inference
# ---------------------------------------------------------------------------


def _run_inference(
    model: peft.PeftModel,
    tokenizer: transformers.PreTrainedTokenizer,
    adapter: chat_templates.ChatTemplateAdapter,
    tool_schemas: list[dict],
    user_content: str,
) -> str:
    """Run a single inference pass and return the generated text.

    Args:
      model: The fine-tuned PeftModel.
      tokenizer: Matching tokenizer.
      adapter: Chat template adapter for prompt formatting.
      tool_schemas: Tool schemas embedded in the system prompt.
      user_content: The user's natural-language request.

    Returns:
      The decoded model output string (raw text after the prompt).
    """
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    prompt = adapter.apply(tokenizer, messages, tool_schemas)
    # Add generation-prompt suffix
    prompt += tokenizer.decode(
        tokenizer.encode(
            adapter.response_template_token + "\n",
            add_special_tokens=False,
        )
    )

    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
    prompt_len = inputs["input_ids"].shape[1]

    with torch.no_grad():
        output_ids = model.generate(
            **inputs,
            max_new_tokens=256,
            do_sample=False,
            temperature=None,
            top_p=None,
            pad_token_id=tokenizer.eos_token_id,
        )

    new_tokens = output_ids[0][prompt_len:]
    return tokenizer.decode(new_tokens, skip_special_tokens=False)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _load_tool_schemas(checkpoint_dir: pathlib.Path) -> list[dict]:
    """Load tool schemas from the data directory adjacent to checkpoints.

    Looks for ``data/tools.json`` relative to the script location.

    Args:
      checkpoint_dir: Path to the checkpoint directory (unused for path
        resolution, but kept for future flexibility).

    Returns:
      List of tool schema dicts, or an empty list if not found.
    """
    schemas_file = pathlib.Path("data") / "tools.json"
    if schemas_file.exists():
        with open(schemas_file, encoding="utf-8") as fh:
            return json.load(fh)
    print(
        "[test_model] WARNING: data/tools.json not found; "
        "running without tool schemas in system prompt."
    )
    return []


def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
      Parsed argument namespace.
    """
    parser = argparse.ArgumentParser(
        description="cBioMOL LoRA adapter smoke test",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--checkpoint_dir",
        type=pathlib.Path,
        default=pathlib.Path("checkpoints/best"),
        help="Path to the saved LoRA adapter directory.",
    )
    supported = sorted(training_config.SUPPORTED_BASE_MODELS)
    parser.add_argument(
        "--model",
        default=None,
        help=(
            "Registry key or HuggingFace id for the base model. "
            "Defaults to adapter_config.json inside --checkpoint_dir, "
            f"then {training_config.DEFAULT_MODEL_KEY}. "
            f"Supported keys: {', '.join(supported)}."
        ),
    )
    return parser.parse_args()


def main() -> None:
    """Entry point for the adapter smoke test."""
    args = _parse_args()
    model, tokenizer, model_name = _load_model(
        args.checkpoint_dir,
        model_key_or_hf_id=args.model,
    )
    tool_schemas = _load_tool_schemas(args.checkpoint_dir)
    adapter = chat_templates.ChatTemplateAdapter.for_model(model_name)

    separator = "-" * 60
    print(f"\n{separator}")
    print("cBioMOL LoRA Adapter Smoke Test")
    print(separator)

    for case in _TEST_CASES:
        print(f"\n[{case['label']}]")
        print(f"  PROMPT  : {case['user']}")
        print(f"  EXPECTED: {case['expected']}")
        output = _run_inference(
            model, tokenizer, adapter, tool_schemas, case["user"]
        )
        print(f"  OUTPUT  :\n{output.strip()}")
        print()

    print(separator)
    print("Inspection complete.  Check that tool-call outputs contain")
    print("valid JSON within <tool_call> blocks.")
    print(separator)


if __name__ == "__main__":
    main()
