#!/usr/bin/env bash
# Copyright 2026 PyMOL Copilot contributors.
#
# Build the pinned llama.cpp that exports the fine-tuned model (master
# plan item 17): the release the evaluation engine ran, `b10707`
# (configs/evaluation/baseline.json, engine_provenance.llama_cpp_build),
# so the converter and quantizer are the ones whose output that engine
# was built to read. CPU only: exporting needs `convert_hf_to_gguf.py`
# and `llama-quantize`, not a GPU.
#
#   src/pmc_train/build_llama_cpp.sh            # into .train-tools/
#
# Idempotent: an existing checkout at the pinned commit is rebuilt in
# place; a checkout at any other commit is refused.
set -euo pipefail

# Override both together: a tag is only trusted at its own commit.
tag="${PMC_LLAMA_CPP_TAG:-b10707}"
commit="${PMC_LLAMA_CPP_COMMIT:-62acc89c26c66076cb72e049f307fbe93b8b9750}"
if [ -n "${PMC_LLAMA_CPP_TAG:-}" ] && [ -z "${PMC_LLAMA_CPP_COMMIT:-}" ]; then
  echo "PMC_LLAMA_CPP_TAG needs PMC_LLAMA_CPP_COMMIT, its commit" >&2
  exit 2
fi
root="$(cd "$(dirname "$0")/../.." && pwd)"
dir="$root/.train-tools/llama.cpp-$tag"

if [ ! -d "$dir/.git" ]; then
  git clone --quiet --depth 1 --branch "$tag" \
    https://github.com/ggml-org/llama.cpp "$dir"
fi
actual="$(git -C "$dir" rev-parse HEAD)"
if [ "$actual" != "$commit" ]; then
  echo "$dir is at $actual, not $tag ($commit)" >&2
  exit 1
fi
cmake -S "$dir" -B "$dir/build" -DCMAKE_BUILD_TYPE=Release \
  -DGGML_CUDA=OFF -DLLAMA_CURL=OFF -DLLAMA_BUILD_SERVER=OFF \
  -DLLAMA_BUILD_TESTS=OFF >/dev/null
cmake --build "$dir/build" --target llama-quantize -j "$(nproc 2>/dev/null || sysctl -n hw.ncpu)" >/dev/null
echo "$dir"
