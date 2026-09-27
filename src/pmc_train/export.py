# Copyright 2026 PyMOL Copilot contributors.
"""Export a trained adapter as the Q4_K_M GGUF the engine loads.

    PYTHONPATH=src .venv-train/bin/python -m pmc_train.export \\
        --run results/train-<id>           # the fine-tuned model
    PYTHONPATH=src .venv-train/bin/python -m pmc_train.export \\
        --base-only --out results/export-control

The pipeline is the same for the fine-tune and for the export-pipeline
control, which differs only in having no adapter to merge:

1. load the pinned, verified 16-bit base weights;
2. merge the adapter into them (skipped by `--base-only`);
3. save the result, with the base tokenizer, as a Hugging Face model;
4. convert it with the pinned llama.cpp's `convert_hf_to_gguf.py` to an
   f16 GGUF;
5. quantize that with the pinned `llama-quantize` to Q4_K_M, with no
   importance matrix;
6. check the result against the baseline's own GGUF
   (`pmc_train.gguf_check`).

Unsloth's own `save_pretrained_gguf` is not used: it builds whatever
llama.cpp is current, where this build is pinned to the release the
evaluation engine ran (`src/pmc_train/build_llama_cpp.sh`). The export
writes `export.json`, with every file's SHA-256, the llama.cpp commit
and the check's result.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import argparse
import json
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import torch

from pmc_train.config import DEFAULT_CONFIG
from pmc_train.config import TrainConfig
from pmc_train.config import config_sha256
from pmc_train.config import load_config
from pmc_train.gguf_check import compare
from pmc_train.gguf_check import file_type_name
from pmc_train.train import base_weights_path
from pmc_train.train import sha256_file

#: The file name the engine will serve, per export.
GGUF_NAME = "{name}-Q4_K_M.gguf"

#: How every exported model's name begins. The Llama 3.2 Community
#: License requires a model trained or fine-tuned from Llama materials,
#: once distributed, to carry "Llama" at the beginning of its name
#: (docs/training/README.md, "License").
MODEL_PREFIX = "Llama-3.2-1B-Instruct"


class ExportCheckError(RuntimeError):
    """The exported GGUF differs from the baseline's where it must not."""


def llama_cpp_dir(root: Path, config: TrainConfig) -> Path:
    """Find the pinned llama.cpp build.

    Args:
        root: The repository root.
        config: The training config.

    Returns:
        The checkout, built by `build_llama_cpp.sh`.

    Raises:
        FileNotFoundError: If it has not been built.
    """
    path = root / ".train-tools" / f"llama.cpp-{config.export.llama_cpp_tag}"
    if not (path / "build" / "bin" / "llama-quantize").is_file():
        raise FileNotFoundError(
            f"{path} is not built; run src/pmc_train/build_llama_cpp.sh"
        )
    return path


def save_merged(
    weights: Path, adapter: Path | None, out: Path, load_base: Any = None
) -> None:
    """Merge an adapter into the base weights and save a HF model.

    Args:
        weights: The verified base-weights directory.
        adapter: The adapter directory, or None for the base alone.
        out: Where to save the merged model.
        load_base: Builds the base model instead of loading `weights`
            (tests pass a tiny model).
    """
    from transformers import AutoModelForCausalLM
    from transformers import AutoTokenizer

    if load_base is not None:
        model = load_base()
    else:
        model = AutoModelForCausalLM.from_pretrained(
            str(weights), dtype=torch.bfloat16
        )
    if adapter is not None:
        from peft import PeftModel

        model = PeftModel.from_pretrained(model, str(adapter))
        model = model.merge_and_unload()
    model.save_pretrained(str(out), safe_serialization=True)
    AutoTokenizer.from_pretrained(str(weights)).save_pretrained(str(out))
    # The converter turns generation_config.json into default sampling
    # metadata (general.sampling.*), which the baseline's GGUF does not
    # carry. Leave it out, so the file differs from the baseline's only
    # in its weights.
    (out / "generation_config.json").unlink(missing_ok=True)


def convert_and_quantize(
    llama_cpp: Path, model_dir: Path, out: Path, quantization: str
) -> Path:
    """Convert a HF model to f16 GGUF, then quantize it.

    Args:
        llama_cpp: The pinned llama.cpp checkout.
        model_dir: The HF model directory.
        out: The quantized GGUF to write.
        quantization: The llama.cpp quantization type.

    Returns:
        The quantized file.
    """
    f16 = out.with_name(out.stem + ".f16.gguf")
    subprocess.run(
        [
            sys.executable,
            str(llama_cpp / "convert_hf_to_gguf.py"),
            str(model_dir),
            "--outfile",
            str(f16),
            "--outtype",
            "f16",
            "--model-name",
            out.name.removesuffix(".gguf"),
        ],
        check=True,
    )
    subprocess.run(
        [
            str(llama_cpp / "build" / "bin" / "llama-quantize"),
            str(f16),
            str(out),
            quantization,
        ],
        check=True,
    )
    f16.unlink()
    return out


def reference_gguf(config: TrainConfig) -> Path:
    """Fetch the baseline's GGUF and verify it.

    Args:
        config: The training config.

    Returns:
        The local file.

    Raises:
        ValueError: If it is not the pinned file.
    """
    from huggingface_hub import hf_hub_download

    gguf = config.export.base_gguf
    path = Path(hf_hub_download(gguf.repo, gguf.file, revision=gguf.revision))
    if sha256_file(path) != gguf.sha256:
        raise ValueError(f"{path} is not the baseline's GGUF")
    return path


def export(
    config_path: Path,
    root: Path,
    out: Path,
    *,
    adapter: Path | None,
    name: str,
    reference: Path | None = None,
    weights: Path | None = None,
    load_base: Any = None,
) -> dict[str, Any]:
    """Run the whole export and write `export.json`.

    Args:
        config_path: The training config file.
        root: The repository root.
        out: The export directory; it must not exist.
        adapter: The trained adapter, or None for the control.
        name: The model's name, used in the GGUF file name.
        reference: The GGUF to check against; the baseline's by default.
        weights: The base weights; the pinned ones by default.
        load_base: Builds the base model instead (tests only).

    Returns:
        The export record.

    Raises:
        FileExistsError: If `out` exists.
        ExportCheckError: If the check finds a mismatch.
    """
    config = load_config(config_path)
    if out.exists():
        raise FileExistsError(f"{out} already exists")
    llama_cpp = llama_cpp_dir(root, config)
    weights = weights or base_weights_path(config)
    reference = reference or reference_gguf(config)
    out.mkdir(parents=True)
    merged = out / "merged-hf"
    save_merged(weights, adapter, merged, load_base)
    gguf = convert_and_quantize(
        llama_cpp,
        merged,
        out / GGUF_NAME.format(name=name),
        config.export.quantization,
    )
    shutil.rmtree(merged)
    result = compare(gguf, reference)
    commit = subprocess.run(
        ["git", "-C", str(llama_cpp), "rev-parse", "HEAD"],
        capture_output=True,
        check=True,
        text=True,
    ).stdout.strip()
    record: dict[str, Any] = {
        "name": name,
        "gguf": gguf.name,
        "gguf_sha256": sha256_file(gguf),
        "gguf_bytes": gguf.stat().st_size,
        "file_type": file_type_name(gguf),
        "adapter": str(adapter) if adapter else None,
        "adapter_sha256": (
            {
                path.name: sha256_file(path)
                for path in sorted(adapter.iterdir())
                if path.is_file()
            }
            if adapter
            else None
        ),
        "config_sha256": config_sha256(config_path),
        "base_model": {
            "repo": config.base_model.repo,
            "revision": config.base_model.revision,
        },
        "llama_cpp": {"tag": config.export.llama_cpp_tag, "commit": commit},
        "pipeline": [
            "merge adapter into bf16 base" if adapter else "no adapter",
            "save_pretrained (safetensors)",
            "convert_hf_to_gguf.py --outtype f16",
            f"llama-quantize {config.export.quantization} (no imatrix)",
        ],
        "reference": {"path": reference.name, "sha256": sha256_file(reference)},
        "check": result.to_json(),
    }
    (out / "export.json").write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if not result.ok:
        raise ExportCheckError(json.dumps(result.to_json(), indent=2))
    return record


def main(argv: Sequence[str] | None = None) -> None:
    """Parse arguments and export.

    Args:
        argv: The command line, without the program name.

    Raises:
        SystemExit: If neither or both of `--run` and `--base-only` are
            given.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--run", type=Path, default=None)
    parser.add_argument("--base-only", action="store_true")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)
    if (args.run is None) == (not args.base_only):
        raise SystemExit("give exactly one of --run and --base-only")
    root = Path(__file__).resolve().parents[2]
    if args.base_only:
        out = args.out or root / "results" / "export-control"
        record = export(
            (root / args.config).resolve(),
            root,
            out,
            adapter=None,
            name=f"{MODEL_PREFIX}-pmc-export-control",
        )
    else:
        run = args.run.resolve()
        out = args.out or run / "export"
        record = export(
            (root / args.config).resolve(),
            root,
            out,
            adapter=run / "adapter",
            name=f"{MODEL_PREFIX}-pmc-{run.name}",
        )
    print(json.dumps(record, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
