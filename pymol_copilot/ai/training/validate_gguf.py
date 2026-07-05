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
"""GGUF model smoke test for the cBioMOL AI assistant.

Loads the quantized GGUF model via ``llama-cpp-python`` and runs five
canonical prompts.  Each prompt is scored as PASS or FAIL:

- **PASS** if the output contains a ``<tool_call>`` block with valid JSON
  (positive cases) or contains no ``<tool_call>`` block (negative cases).
- **FAIL** otherwise.

The five canonical prompts are the same as in ``test_model.py``.

Usage
-----
.. code-block:: bash

    python validate_gguf.py \\
        --model models/pymol_copilot-pymol-assistant-Q4_K_M.gguf
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

import llama_cpp

import pymol_copilot.ai.app.models.plan_parser as plan_parser_module
import pymol_copilot.ai.backend.config as config_module
import pymol_copilot.ai.inference.conversation as conversation_module
import pymol_copilot.ai.inference.prompt_builder as prompt_builder_module


# ---------------------------------------------------------------------------
# Canonical test prompts (mirrors test_model.py)
# ---------------------------------------------------------------------------

_TEST_CASES: list[dict] = [
    {
        "label": "1 — Positive single tool (load structure)",
        "user": "Load the human insulin receptor from the PDB (2HR7).",
        "expect_tool_call": True,
    },
    {
        "label": "2 — Positive multi-step (load + color + save)",
        "user": (
            "Load hemoglobin (4HHB), color each chain a different "
            "color, then save a preview PNG image."
        ),
        "expect_tool_call": True,
    },
    {
        "label": "3 — Negative viewport (rotate)",
        "user": "Rotate the molecule 90 degrees around the Y axis.",
        "expect_tool_call": False,
    },
    {
        "label": "4 — Negative out-of-scope (molecular dynamics)",
        "user": "Run a 10 ns molecular dynamics simulation of this protein.",
        "expect_tool_call": False,
    },
    {
        "label": "5 — Context-aware (refer to loaded structure)",
        "user": "Now color the structure I just loaded by secondary structure.",
        "expect_tool_call": True,
    },
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_tool_schemas() -> list[dict]:
    """Load tool schemas from ``data/tools.json``.

    Returns:
      List of tool schema dicts, or an empty list if the file is absent.
    """
    schemas_file = pathlib.Path("data") / "tools.json"
    if schemas_file.exists():
        with open(schemas_file, encoding="utf-8") as fh:
            return json.load(fh)
    return []


def _build_prompt(
    user_content: str,
    tool_schemas: list[dict],
    prompt_family: config_module.PromptFamily,
) -> str:
    """Build the raw text prompt for the GGUF model.

    Delegates to the shared runtime prompt builder so validation matches
    llama.cpp inference in the PyQt application.

    Args:
      user_content: The user's natural-language request.
      tool_schemas: Tool schemas to embed in the system prompt.
      prompt_family: ``'qwen2'`` or ``'qwen3'`` prompt formatting.

    Returns:
      The formatted prompt string.
    """
    conversation = conversation_module.Conversation()
    conversation.append_user(user_content)
    return prompt_builder_module.build_prompt(
        conversation,
        tool_schemas=tool_schemas,
        prompt_family=prompt_family,
    )


def _score_output(output: str, expect_tool_call: bool) -> bool:
    """Determine whether the model output meets the expected criterion.

    Args:
      output: Raw generated text from the GGUF model.
      expect_tool_call: True if a ``<tool_call>`` block is required;
        False if the output should contain no tool call.

    Returns:
      True if the output matches the expectation; False otherwise.
    """
    matches = plan_parser_module.iter_tool_call_payloads(output)
    if expect_tool_call:
        if not matches:
            return False
        for payload in matches:
            parsed = plan_parser_module.parse_tool_call_payload(payload)
            if parsed is not None and "name" in parsed:
                return True
        return False
    else:
        return len(matches) == 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
      Parsed argument namespace.
    """
    parser = argparse.ArgumentParser(
        description="cBioMOL GGUF smoke test",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--model",
        type=pathlib.Path,
        required=True,
        help="Path to the quantized GGUF file.",
    )
    parser.add_argument(
        "--n_gpu_layers",
        type=int,
        default=-1,
        help=(
            "Number of model layers to offload to GPU (-1 = all). "
            "Set to 0 for CPU-only inference."
        ),
    )
    parser.add_argument(
        "--ctx_size",
        type=int,
        default=2048,
        help="Context size (tokens).",
    )
    parser.add_argument(
        "--prompt-family",
        choices=("qwen2", "qwen3"),
        default=None,
        help=(
            "ChatML prompt family override. Defaults to filename detection "
            "('qwen3' when the GGUF name contains qwen3)."
        ),
    )
    return parser.parse_args()


def main() -> None:
    """Entry point for the GGUF smoke test."""
    args = _parse_args()

    if not args.model.exists():
        print(
            f"[ERROR] GGUF file not found: {args.model}",
            file=sys.stderr,
        )
        sys.exit(1)

    tool_schemas = _load_tool_schemas()
    prompt_family = args.prompt_family or config_module.detect_prompt_family(
        args.model,
    )

    print(f"[validate_gguf] Loading GGUF: {args.model}")
    print(f"[validate_gguf] Prompt family: {prompt_family}")
    llm = llama_cpp.Llama(
        model_path=str(args.model),
        n_gpu_layers=args.n_gpu_layers,
        n_ctx=args.ctx_size,
        verbose=False,
    )

    separator = "-" * 60
    print(f"\n{separator}")
    print("cBioMOL GGUF Validation")
    print(separator)

    passed = 0
    failed = 0

    for case in _TEST_CASES:
        prompt = _build_prompt(
            case["user"],
            tool_schemas,
            prompt_family,
        )
        result = llm(
            prompt,
            max_tokens=256,
            stop=["<|im_end|>"],
            echo=False,
        )
        output = result["choices"][0]["text"]
        ok = _score_output(output, case["expect_tool_call"])
        status = "PASS ✓" if ok else "FAIL ✗"
        if ok:
            passed += 1
        else:
            failed += 1

        print(f"\n[{case['label']}]")
        print(f"  USER   : {case['user']}")
        print(f"  OUTPUT : {output.strip()[:200]}")
        print(f"  RESULT : {status}")

    print(f"\n{separator}")
    print(
        f"Results: {passed} passed, {failed} failed out of {len(_TEST_CASES)}"
    )
    print(separator)

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
