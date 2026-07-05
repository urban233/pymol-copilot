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
"""GGUF export script for the cBioMOL AI assistant.

Merges the LoRA adapter into the base model weights, saves the merged
model in HuggingFace safetensors format, then converts and quantizes
it to GGUF.

Conversion approach
-------------------
``convert_hf_to_gguf.py`` is taken directly from the official llama.cpp
repository, which is cloned into ``<project_root>/vendor/llama.cpp`` on
the first run (shallow clone, ~30 MB).  Subsequent runs detect the
existing clone and skip the git operation.

The ``llama-quantize`` binary still comes from the ``llama-cpp-python``
package, because building the C++ binary from the llama.cpp source
requires a full CMake toolchain that the training machine may not have.

Project root detection
----------------------
The script resolves the project root by walking six ``parent`` levels up
from its own ``__file__`` path:

  training/ → ai/ → pymol_copilot/ → python/ → src/ → <project root>

Output
------
``<output_dir>/pymol_copilot-pymol-assistant-<model-key>-<quantization>.gguf``

Usage
-----
.. code-block:: bash

    python export_gguf.py \\
        --checkpoint_dir checkpoints/best/ \\
        --output_dir models/ \\
        --quantization Q4_K_M

    # Override the vendor directory:
    python export_gguf.py \\
        --checkpoint_dir checkpoints/best/ \\
        --vendor_dir /srv/vendor
"""

from __future__ import annotations

import argparse
import pathlib
import shutil
import subprocess
import sys

import peft
import transformers

import config.training_config as training_config


# ---------------------------------------------------------------------------
# Project root resolution
# ---------------------------------------------------------------------------

#: Canonical llama.cpp repository URL.
_LLAMA_CPP_REPO = "https://github.com/ggerganov/llama.cpp.git"

#: Name of the sub-directory inside vendor/.
_LLAMA_CPP_DIR_NAME = "llama.cpp"

#: Relative path from this script to the project root.
#: training(0) → ai(1) → pymol_copilot(2) → python(3) → src(4) → root(5)
_PROJECT_ROOT: pathlib.Path = pathlib.Path(__file__).resolve().parents[5]


def _default_vendor_dir() -> pathlib.Path:
    """Return the default vendor directory inside the project root.

    Returns:
      ``<project_root>/vendor``
    """
    return _PROJECT_ROOT / "vendor"


# ---------------------------------------------------------------------------
# llama.cpp bootstrap
# ---------------------------------------------------------------------------


def _ensure_llama_cpp(vendor_dir: pathlib.Path) -> pathlib.Path:
    """Ensure the llama.cpp repository is available in ``vendor_dir``.

    On the first call, performs a shallow ``git clone`` (depth 1) which
    downloads only the latest commit — approximately 30 MB.  On subsequent
    calls the clone is detected by the presence of ``vendor_dir/llama.cpp``
    and the clone step is skipped entirely (no network access).

    Args:
      vendor_dir: Directory under which ``llama.cpp/`` will be placed.

    Returns:
      Path to the ``llama.cpp`` clone root (``vendor_dir/llama.cpp``).

    Raises:
      SystemExit: If ``git`` is not on PATH or the clone fails.
    """
    llama_dir = vendor_dir / _LLAMA_CPP_DIR_NAME

    if llama_dir.exists():
        print(
            f"[export_gguf] llama.cpp already present at {llama_dir} (skipping clone)"
        )
        return llama_dir

    if not shutil.which("git"):
        print(
            "[ERROR] 'git' is not on PATH.  Install Git and retry:\n"
            "  https://git-scm.com/downloads",
            file=sys.stderr,
        )
        sys.exit(1)

    vendor_dir.mkdir(parents=True, exist_ok=True)
    print(
        f"[export_gguf] Cloning llama.cpp (shallow) into {llama_dir} ...\n"
        f"  {_LLAMA_CPP_REPO}"
    )
    result = subprocess.run(
        [
            "git",
            "clone",
            "--depth",
            "1",
            _LLAMA_CPP_REPO,
            str(llama_dir),
        ],
        check=False,
    )
    if result.returncode != 0:
        print(
            "[ERROR] git clone failed.  Check your internet connection and "
            "that git is installed.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"[export_gguf] llama.cpp cloned to {llama_dir}")
    return llama_dir


def _find_convert_script(llama_dir: pathlib.Path) -> pathlib.Path:
    """Locate ``convert_hf_to_gguf.py`` inside the llama.cpp clone.

    The script lives at the root of the repository in all recent versions
    of llama.cpp.  A fallback candidate inside ``tools/`` is also checked
    in case the repository structure changes.

    Args:
      llama_dir: Root of the llama.cpp git clone.

    Returns:
      Path to ``convert_hf_to_gguf.py``.

    Raises:
      SystemExit: If the script cannot be found inside the clone.
    """
    candidates = [
        llama_dir / "convert_hf_to_gguf.py",
        llama_dir / "tools" / "convert_hf_to_gguf.py",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate

    print(
        f"[ERROR] convert_hf_to_gguf.py not found in {llama_dir}.\n"
        "The llama.cpp repository structure may have changed.  Delete\n"
        f"  {llama_dir}\n"
        "and re-run this script to fetch a fresh clone.",
        file=sys.stderr,
    )
    sys.exit(1)


# ---------------------------------------------------------------------------
# Merge
# ---------------------------------------------------------------------------


def _merge_adapter(
    checkpoint_dir: pathlib.Path,
    merged_dir: pathlib.Path,
    model_key_or_hf_id: str | None = None,
) -> str:
    """Merge the LoRA adapter into the base model and save.

    Loads the base model in full bf16 precision (NOT 4-bit) so the merge
    is lossless.  The merged model is saved as HuggingFace safetensors.

    Args:
      checkpoint_dir: Path to the saved LoRA adapter directory.
      merged_dir: Directory where the merged full model is saved.
      model_key_or_hf_id: Optional registry key or HuggingFace id override.

    Returns:
      Resolved HuggingFace model id used for the merge.

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
    print(f"[export_gguf] Loading base model (bf16): {model_name}")

    base = transformers.AutoModelForCausalLM.from_pretrained(
        model_name,
        torch_dtype="auto",
        device_map="cpu",  # merge on CPU to avoid VRAM pressure
        trust_remote_code=True,
    )
    tokenizer = transformers.AutoTokenizer.from_pretrained(
        model_name,
        trust_remote_code=True,
    )

    print(f"[export_gguf] Loading adapter: {checkpoint_dir}")
    model = peft.PeftModel.from_pretrained(base, str(checkpoint_dir))

    print("[export_gguf] Merging adapter into base weights ...")
    model = model.merge_and_unload()

    merged_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(merged_dir), safe_serialization=True)
    tokenizer.save_pretrained(str(merged_dir))
    print(f"[export_gguf] Merged model saved to {merged_dir}")
    return model_name


# ---------------------------------------------------------------------------
# Quantize (binary still comes from llama-cpp-python)
# ---------------------------------------------------------------------------


def _find_quantize_binary(
    vendor_dir: pathlib.Path | None = None,
) -> pathlib.Path:
    """Locate the ``llama-quantize`` binary.

    Searches in the following order, stopping at the first hit:

    1. **Explicit fast-path candidates** inside the ``llama_cpp`` package
       directory (covers standard source-built wheels).
    2. **Recursive glob** of the entire ``llama_cpp`` package tree.
       Pre-built wheels from ``https://abetlen.github.io/llama-cpp-python``
       may place the binary in non-standard sub-directories.
    3. **Sibling ``.libs`` directories** at the ``site-packages`` level.
       ``manylinux`` CUDA wheels often ship shared libraries (and
       occasionally the quantize binary) in a ``llama_cpp_python*.libs/``
       directory next to the package.
    4. **System PATH** — catches distro packages and manually compiled
       ``llama-quantize`` binaries.
    5. **Vendor clone build output** — if the llama.cpp clone was already
       built (e.g. ``cmake --build vendor/llama.cpp/build``), the binary
       lives in ``vendor/llama.cpp/build/bin/llama-quantize``.

    Args:
      vendor_dir: Optional vendor directory passed from ``main()``.  Used
        to check the llama.cpp vendor clone build output (stage 5).

    Returns:
      Path to the llama-quantize binary.

    Raises:
      SystemExit: If the binary cannot be found in any of the locations
        described above.
    """
    try:
        import llama_cpp  # noqa: PLC0415 (local import by design)
    except ImportError:
        _abort_missing_llama_cpp()

    pkg_dir = pathlib.Path(llama_cpp.__file__).parent
    searched: list[str] = []

    # Stage 1 — explicit fast-path candidates
    explicit_candidates = [
        pkg_dir / "llama-quantize",
        pkg_dir / "llama-quantize.exe",
        pkg_dir / "lib" / "llama-quantize",
        pkg_dir / "lib" / "llama-quantize.exe",
        pkg_dir / "_llama_cpp_python.libs" / "llama-quantize",
        pkg_dir / "_llama_cpp_python.libs" / "llama-quantize.exe",
    ]
    searched.append(f"  [1] explicit candidates in {pkg_dir}")
    for c in explicit_candidates:
        if c.exists():
            return c

    # Stage 2 — recursive glob of the entire package tree.
    # Pre-built CUDA wheels (abetlen index) may use non-standard layouts.
    searched.append(f"  [2] recursive glob in {pkg_dir}")
    for pattern in ("llama-quantize", "llama-quantize.exe"):
        matches = sorted(pkg_dir.rglob(pattern))
        if matches:
            return matches[0]

    # Stage 3 — sibling .libs directory (manylinux / CUDA wheels).
    # The wheel tag cp3x-linux_x86_64 installs a llama_cpp_python*.libs/
    # directory at the site-packages level alongside the package dir.
    sibling_libs = sorted(pkg_dir.parent.glob("llama_cpp_python*.libs"))
    if sibling_libs:
        searched.append(
            f"  [3] sibling .libs dirs: {[str(s) for s in sibling_libs]}"
        )
        for libs_dir in sibling_libs:
            for pattern in ("llama-quantize", "llama-quantize.exe"):
                matches = sorted(libs_dir.rglob(pattern))
                if matches:
                    return matches[0]
    else:
        searched.append(
            f"  [3] no llama_cpp_python*.libs found next to {pkg_dir}"
        )

    # Stage 4 — system PATH
    searched.append("  [4] system PATH")
    system_bin = shutil.which("llama-quantize")
    if system_bin:
        return pathlib.Path(system_bin)

    # Stage 5 — vendor clone build output
    if vendor_dir is not None:
        vendor_build_candidates = [
            vendor_dir
            / _LLAMA_CPP_DIR_NAME
            / "build"
            / "bin"
            / "llama-quantize",
            vendor_dir
            / _LLAMA_CPP_DIR_NAME
            / "build"
            / "bin"
            / "llama-quantize.exe",
            vendor_dir / _LLAMA_CPP_DIR_NAME / "build" / "llama-quantize",
            vendor_dir / _LLAMA_CPP_DIR_NAME / "build" / "llama-quantize.exe",
        ]
        searched.append(
            f"  [5] vendor clone build at "
            f"{vendor_dir / _LLAMA_CPP_DIR_NAME / 'build'}"
        )
        for c in vendor_build_candidates:
            if c.exists():
                return c
    else:
        searched.append("  [5] vendor_dir not provided — skipped")

    search_summary = "\n".join(searched)
    print(
        "[ERROR] llama-quantize binary not found.\n"
        "Searched:\n"
        f"{search_summary}\n\n"
        "To fix, choose one of:\n"
        "  a) Install the pre-built CUDA wheel:\n"
        "       pip install llama-cpp-python \\\n"
        "         --extra-index-url "
        "https://abetlen.github.io/llama-cpp-python/whl/cu121 \\\n"
        "         --force-reinstall --no-cache-dir\n"
        "  b) Build llama-quantize from the vendor clone and pass its\n"
        "     location via PATH or --vendor_dir:\n"
        "       cmake -B vendor/llama.cpp/build vendor/llama.cpp\n"
        "       cmake --build vendor/llama.cpp/build --target llama-quantize\n"
        "  c) Install a system package that provides llama-quantize and\n"
        "     ensure it is on your PATH.",
        file=sys.stderr,
    )
    sys.exit(1)


def _abort_missing_llama_cpp() -> None:
    """Print an install error and exit.

    Raises:
      SystemExit: Always.
    """
    print(
        "[ERROR] llama-cpp-python is not installed.\n"
        "Install with CUDA support:\n"
        '  CMAKE_ARGS="-DGGML_CUDA=on" '
        "pip install llama-cpp-python==0.3.2",
        file=sys.stderr,
    )
    sys.exit(1)


# ---------------------------------------------------------------------------
# Convert + quantize
# ---------------------------------------------------------------------------


def _convert_to_gguf(
    merged_dir: pathlib.Path,
    output_dir: pathlib.Path,
    convert_script: pathlib.Path,
) -> pathlib.Path:
    """Convert the merged HuggingFace model to a F16 GGUF file.

    Runs ``convert_hf_to_gguf.py`` from the llama.cpp vendor clone as a
    subprocess using the same Python interpreter that is running this
    script.  The script's dependencies (``numpy``, ``sentencepiece``,
    ``gguf``) must be present in the active environment.  Running
    ``pip install -r vendor/llama.cpp/requirements/requirements-convert_hf_to_gguf.txt``
    satisfies them.

    Args:
      merged_dir: Directory containing the merged HF model.
      output_dir: Directory where the GGUF file is written.
      convert_script: Path to ``convert_hf_to_gguf.py``.

    Returns:
      Path to the F16 GGUF file.

    Raises:
      SystemExit: If the conversion script fails.
    """
    f16_path = output_dir / "model_f16.gguf"
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"[export_gguf] Converting to F16 GGUF via {convert_script}")
    cmd = [
        sys.executable,
        str(convert_script),
        str(merged_dir),
        "--outfile",
        str(f16_path),
        "--outtype",
        "f16",
    ]
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        print(
            "[ERROR] GGUF conversion failed.  See output above.\n"
            "If the error mentions a missing module (e.g. 'gguf', 'numpy'),\n"
            "install the llama.cpp conversion dependencies:\n"
            "  pip install -r vendor/llama.cpp/requirements/"
            "requirements-convert_hf_to_gguf.txt",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"[export_gguf] F16 GGUF written to {f16_path}")
    return f16_path


def _quantize_gguf(
    f16_path: pathlib.Path,
    output_dir: pathlib.Path,
    quantization: str,
    model_key: str,
    vendor_dir: pathlib.Path | None = None,
) -> pathlib.Path:
    """Quantize a F16 GGUF file to the target quantization type.

    Args:
      f16_path: Path to the F16 GGUF file.
      output_dir: Directory where the quantized GGUF is written.
      quantization: Quantization type string, e.g. ``'Q4_K_M'``.
      model_key: Registry key embedded in the output filename.
      vendor_dir: Passed through to ``_find_quantize_binary`` so the
        vendor clone build directory is included in the search (stage 5).

    Returns:
      Path to the quantized GGUF file.

    Raises:
      SystemExit: If quantization fails.
    """
    quantize_bin = _find_quantize_binary(vendor_dir)
    out_path = (
        output_dir
        / f"pymol_copilot-pymol-assistant-{model_key}-{quantization}.gguf"
    )

    print(f"[export_gguf] Quantizing to {quantization} via {quantize_bin.name}")
    cmd = [
        str(quantize_bin),
        str(f16_path),
        str(out_path),
        quantization,
    ]
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        print(
            "[ERROR] Quantization failed.  See output above.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Clean up intermediate F16 GGUF to save disk
    f16_path.unlink(missing_ok=True)
    print(f"[export_gguf] Quantized GGUF: {out_path}")
    return out_path


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
      Parsed argument namespace.
    """
    parser = argparse.ArgumentParser(
        description="cBioMOL GGUF export",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--checkpoint_dir",
        type=pathlib.Path,
        default=pathlib.Path("checkpoints/best"),
        help="Path to the saved LoRA adapter directory.",
    )
    parser.add_argument(
        "--output_dir",
        type=pathlib.Path,
        default=pathlib.Path("models"),
        help="Directory where the GGUF file is written.",
    )
    parser.add_argument(
        "--quantization",
        default=training_config.DEFAULT_QUANTIZATION,
        help="GGUF quantization type (e.g. Q4_K_M, Q5_K_M, Q8_0).",
    )
    parser.add_argument(
        "--skip_merge",
        action="store_true",
        help=(
            "Skip the LoRA merge step.  Assumes the merged model already "
            "exists in --output_dir/merged_model/."
        ),
    )
    parser.add_argument(
        "--vendor_dir",
        type=pathlib.Path,
        default=None,
        help=(
            "Override the vendor directory where llama.cpp is cloned.  "
            f"Defaults to <project_root>/vendor "
            f"(resolved as {_default_vendor_dir()})."
        ),
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
    """Entry point for the GGUF export script."""
    args = _parse_args()
    merged_dir = args.output_dir / "merged_model"
    vendor_dir = args.vendor_dir if args.vendor_dir else _default_vendor_dir()

    # Step 0: ensure llama.cpp is available
    llama_dir = _ensure_llama_cpp(vendor_dir)
    convert_script = _find_convert_script(llama_dir)

    # Step 1: merge LoRA adapter
    model_name = training_config.resolve_training_model(
        args.model,
        checkpoint_dir=args.checkpoint_dir,
    )
    training_config.require_transformers_for_model(model_name)
    model_key = training_config.resolve_model_key(model_name)
    if not args.skip_merge:
        _merge_adapter(
            args.checkpoint_dir,
            merged_dir,
            model_key_or_hf_id=args.model,
        )

    # Step 2: convert to F16 GGUF
    f16_path = _convert_to_gguf(merged_dir, args.output_dir, convert_script)

    # Step 3: quantize
    gguf_path = _quantize_gguf(
        f16_path,
        args.output_dir,
        args.quantization,
        model_key,
        vendor_dir,
    )

    print("\n[export_gguf] Done.")
    print(f"  Final GGUF : {gguf_path}")
    print("  Run validate_gguf.py to verify the model responds correctly.")


if __name__ == "__main__":
    main()
