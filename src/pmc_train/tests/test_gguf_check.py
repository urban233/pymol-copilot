# Copyright 2026 PyMOL Copilot contributors.
"""The GGUF check refuses what must match and only reports provenance."""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

from pathlib import Path

import numpy
import pytest
from gguf import GGUFWriter
from gguf import LlamaFileType

from pmc_train.gguf_check import compare
from pmc_train.gguf_check import file_type_name


def _write(
    path: Path,
    *,
    template: str = "{{ bos_token }}",
    tokens: tuple[str, ...] = ("a", "b", "c"),
    context: int = 131072,
    shape: tuple[int, int] = (4, 8),
    imatrix: str | None = None,
    name: str = "model",
) -> Path:
    """Write a tiny GGUF with the metadata the check reads.

    Args:
        path: Where to write it.
        template: Its chat template.
        tokens: Its vocabulary.
        context: Its context length.
        shape: Its one tensor's shape.
        imatrix: An importance-matrix file name to record, if any.
        name: Its general name.

    Returns:
        The path.
    """
    writer = GGUFWriter(str(path), "llama")
    writer.add_name(name)
    writer.add_file_type(LlamaFileType.MOSTLY_Q4_K_M)
    writer.add_context_length(context)
    writer.add_chat_template(template)
    writer.add_tokenizer_model("gpt2")
    writer.add_token_list(list(tokens))
    writer.add_bos_token_id(0)
    writer.add_eos_token_id(1)
    if imatrix is not None:
        writer.add_string("quantize.imatrix.file", imatrix)
    writer.add_tensor(
        "token_embd.weight", numpy.zeros(shape, dtype=numpy.float32)
    )
    writer.write_header_to_file()
    writer.write_kv_data_to_file()
    writer.write_tensors_to_file()
    writer.close()
    return path


def test_identical_files_pass(tmp_path: Path) -> None:
    """Two files with the same metadata and tensors pass."""
    result = compare(_write(tmp_path / "a.gguf"), _write(tmp_path / "b.gguf"))
    assert result.ok
    assert file_type_name(tmp_path / "a.gguf") == "MOSTLY_Q4_K_M"


@pytest.mark.parametrize(
    ("change", "key"),
    [
        ({"template": "{{ eos_token }}"}, "tokenizer.chat_template"),
        ({"tokens": ("a", "b", "d")}, "tokenizer.ggml.tokens"),
        ({"context": 8192}, "llama.context_length"),
    ],
)
def test_a_contract_difference_is_refused(
    tmp_path: Path, change: dict[str, object], key: str
) -> None:
    """A different template, vocabulary or hyperparameter fails the check."""
    candidate = _write(tmp_path / "a.gguf", **change)
    result = compare(candidate, _write(tmp_path / "b.gguf"))
    assert not result.ok
    assert key in result.mismatches


def test_a_tensor_shape_difference_is_refused(tmp_path: Path) -> None:
    """A tensor of another shape fails the check."""
    result = compare(
        _write(tmp_path / "a.gguf", shape=(4, 16)), _write(tmp_path / "b.gguf")
    )
    assert not result.ok
    assert result.tensor_mismatches == ["token_embd.weight"]


def test_provenance_is_reported_not_refused(tmp_path: Path) -> None:
    """A different name or importance matrix is reported and passes."""
    result = compare(
        _write(tmp_path / "a.gguf", name="tuned"),
        _write(tmp_path / "b.gguf", imatrix="imatrix.dat"),
    )
    assert result.ok
    assert set(result.reported) == {"general.name", "quantize.imatrix.file"}
