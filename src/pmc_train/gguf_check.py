# Copyright 2026 PyMOL Copilot contributors.
"""Check an exported GGUF against the baseline's own GGUF.

The comparison with the untuned baseline holds everything but the
weights fixed (docs/evaluation/README.md). So the exported file must be
the same quantization, the same architecture and shape, with the same
chat template and the same tokenizer, as the file the baseline ran. A
different template or vocabulary would change what the model sees for
reasons that have nothing to do with fine-tuning.

Metadata that says only how a file was produced (its name, the
quantizer's version, an importance matrix) is reported, not refused:
the export-pipeline control (docs/training/README.md) measures its
effect instead.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import argparse
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gguf import GGUFReader
from gguf import LlamaFileType

#: Metadata that must be identical.
MUST_MATCH = (
    "general.architecture",
    "general.file_type",
    "tokenizer.chat_template",
    "tokenizer.ggml.model",
    "tokenizer.ggml.pre",
    "tokenizer.ggml.tokens",
    "tokenizer.ggml.token_type",
    "tokenizer.ggml.merges",
    "tokenizer.ggml.bos_token_id",
    "tokenizer.ggml.eos_token_id",
)

#: Key suffixes of the architecture's own hyperparameters, all of which
#: must match (`llama.context_length`, `llama.block_count`, ...).
ARCHITECTURE_PREFIX = "llama."

#: Metadata key prefixes that describe how a file was made, reported only.
PROVENANCE_PREFIXES = ("general.", "quantize.", "split.")


@dataclass(frozen=True)
class CheckResult:
    """The outcome of one comparison.

    Attributes:
        mismatches: Keys that must match but differ, with both values
            summarized.
        reported: Keys that differ but only describe provenance.
        tensor_mismatches: Tensors whose name or shape differs.
        tensor_type_differences: Tensors quantized to another type.
    """

    mismatches: dict[str, tuple[str, str]]
    reported: dict[str, tuple[str, str]]
    tensor_mismatches: list[str]
    tensor_type_differences: dict[str, tuple[str, str]]

    @property
    def ok(self) -> bool:
        """Whether nothing that must match differs.

        Returns:
            True when the export may be evaluated against the baseline.
        """
        return not self.mismatches and not self.tensor_mismatches

    def to_json(self) -> dict[str, Any]:
        """Serialize the result.

        Returns:
            A JSON-ready mapping.
        """
        return {
            "ok": self.ok,
            "mismatches": {k: list(v) for k, v in self.mismatches.items()},
            "reported": {k: list(v) for k, v in self.reported.items()},
            "tensor_mismatches": self.tensor_mismatches,
            "tensor_type_differences": {
                k: list(v) for k, v in self.tensor_type_differences.items()
            },
        }


def metadata(path: Path) -> tuple[dict[str, Any], dict[str, tuple[Any, str]]]:
    """Read a GGUF's key-value metadata and tensor table.

    Args:
        path: The GGUF file.

    Returns:
        The metadata by key, and each tensor's shape and type by name.
    """
    reader = GGUFReader(path)
    values: dict[str, Any] = {}
    for key, field in reader.fields.items():
        if key.startswith("GGUF."):
            continue
        content = field.contents()
        if hasattr(content, "tolist"):
            content = content.tolist()
        values[key] = content
    tensors = {
        tensor.name: (
            tuple(int(n) for n in tensor.shape),
            tensor.tensor_type.name,
        )
        for tensor in reader.tensors
    }
    return values, tensors


def _summary(value: Any) -> str:
    """Summarize a metadata value for a report.

    Args:
        value: The value.

    Returns:
        A short string: the value itself, or a length and digest-like
        prefix for long lists and strings.
    """
    if isinstance(value, list):
        return f"list[{len(value)}] starting {value[:3]!r}"
    text = repr(value)
    return text if len(text) <= 80 else f"{text[:77]}..."


def compare(candidate: Path, reference: Path) -> CheckResult:
    """Compare an exported GGUF with the reference GGUF.

    Args:
        candidate: The exported file.
        reference: The baseline's file.

    Returns:
        What differs.
    """
    ours, our_tensors = metadata(candidate)
    theirs, their_tensors = metadata(reference)
    mismatches: dict[str, tuple[str, str]] = {}
    reported: dict[str, tuple[str, str]] = {}
    for key in sorted(set(ours) | set(theirs)):
        mine, other = ours.get(key), theirs.get(key)
        if mine == other:
            continue
        pair = (_summary(mine), _summary(other))
        if key in MUST_MATCH or key.startswith(ARCHITECTURE_PREFIX):
            mismatches[key] = pair
        elif key.startswith(PROVENANCE_PREFIXES) or key.startswith(
            "tokenizer."
        ):
            reported[key] = pair
        else:
            mismatches[key] = pair
    for key in MUST_MATCH:
        if key not in ours and key not in theirs:
            continue
        if key not in ours or key not in theirs:
            mismatches[key] = (
                _summary(ours.get(key)),
                _summary(theirs.get(key)),
            )
    tensor_mismatches = sorted(
        name
        for name in set(our_tensors) | set(their_tensors)
        if our_tensors.get(name, (None,))[0]
        != their_tensors.get(name, (None,))[0]
    )
    types = {
        name: (our_tensors[name][1], their_tensors[name][1])
        for name in sorted(set(our_tensors) & set(their_tensors))
        if our_tensors[name][1] != their_tensors[name][1]
    }
    return CheckResult(mismatches, reported, tensor_mismatches, types)


def file_type_name(path: Path) -> str:
    """Name a GGUF's declared file type.

    Args:
        path: The GGUF file.

    Returns:
        The `LlamaFileType` name, such as `MOSTLY_Q4_K_M`.
    """
    values, _ = metadata(path)
    return LlamaFileType(int(values["general.file_type"])).name


def main(argv: Sequence[str] | None = None) -> None:
    """Compare two GGUF files and print the result as JSON.

    Args:
        argv: The command line, without the program name.

    Raises:
        SystemExit: With status 1 when something that must match differs.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("reference", type=Path)
    args = parser.parse_args(argv)
    result = compare(args.candidate, args.reference)
    print(json.dumps(result.to_json(), indent=2, sort_keys=True))
    if not result.ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
