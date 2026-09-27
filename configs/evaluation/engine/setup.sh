#!/usr/bin/env bash
# Copyright 2026 PyMOL Copilot contributors.
#
# Prepare the evaluation engine and print its provenance (master plan
# item 16). Run it after `docker compose ... up -d` (see compose.yaml):
#
#   configs/evaluation/engine/setup.sh cpu     # CPU, any variant
#   configs/evaluation/engine/setup.sh cuda    # compose.nvidia.yaml
#   configs/evaluation/engine/setup.sh cuda --config \
#       configs/evaluation/finetuned.json      # + compose.local-model.yaml
#
# It pulls the model the config (configs/evaluation/baseline.json by
# default) names -- or, for a GGUF exported under results/ (master plan
# item 17), serves it in place from the read-only mount -- pins the
# chat template's date, installs the CUDA llama.cpp build when asked,
# loads the model exactly as the adapter's probe will, and prints the
# `engine_provenance` block to paste into baseline.json -- together with
# the `engine.backend` to set there. Commit both before a run: a run
# refuses a modified tracked file, and an engine whose Lemonade version
# or llama.cpp arguments differ from what is recorded.
set -euo pipefail

backend="${1:-cpu}"
case "$backend" in
  cpu | cuda) ;;
  *)
    echo "usage: $0 [cpu|cuda] [--config <config.json>]" >&2
    exit 2
    ;;
esac
config="configs/evaluation/baseline.json"
if [ "${2:-}" = "--config" ]; then
  config="${3:?--config needs a file}"
fi
root="$(cd "$(dirname "$0")/../../.." && pwd)"
case "$config" in
  /*) ;;
  *) config="$root/$config" ;;
esac

container="${PMC_EVAL_CONTAINER:-pmc-eval-lemonade}"
base_url="${PMC_LEMONADE_BASE_URL:-http://localhost:13305}"
# The model the config names (item 16's baseline.json by default, or an
# item 17 config for a locally exported GGUF).
read -r model_name checkpoint context_size < <(python3 -c '
import json, sys
engine = json.load(open(sys.argv[1]))["engine"]
print(engine["model_name"], engine["checkpoint"], engine["context_size"])
' "$config")
# The Llama 3.2 template's own fallback date. Item 17 must render its
# training prompts with the same date_string.
template_args="--chat-template-kwargs '{\"date_string\":\"26 Jul 2024\"}'"

# The official image ships its CLI at /opt/lemonade/lemonade; the Debian
# package installs it on PATH.
cli="$(docker exec "$container" sh -c \
  'command -v lemonade || echo /opt/lemonade/lemonade')"
lemonade() {
  docker exec "$container" "$cli" "$@"
}

echo "waiting for Lemonade at $base_url ..." >&2
for _ in $(seq 1 60); do
  curl -sf -m 3 "$base_url/api/v1/health" >/dev/null && break
  sleep 2
done
curl -sf -m 3 "$base_url/api/v1/health" >/dev/null || {
  echo "Lemonade did not come up at $base_url" >&2
  exit 1
}

if [ "$backend" = cuda ]; then
  lemonade backends install llamacpp:cuda >&2
fi
case "$checkpoint" in
  /models/*)
    # A GGUF exported by src/pmc_train/export.py, mounted read-only by
    # compose.local-model.yaml. Lemonade serves the files of its
    # extra_models_dir in place, under their own names, so nothing is
    # copied or downloaded: point it at the file's directory.
    lemonade config set "extra_models_dir=$(dirname "$checkpoint")" >&2
    ;;
  *)
    lemonade pull "user.$model_name" --checkpoint main "$checkpoint" \
      --recipe llamacpp >&2
    ;;
esac
lemonade config set "llamacpp.args=$template_args" >&2

# Load as the adapter's probe does, so health reports what a run will see.
curl -sf -m 30 -X POST "$base_url/api/v1/unload" \
  -H 'Content-Type: application/json' \
  -d "{\"model_name\":\"$model_name\"}" >/dev/null || true
curl -sf -m 600 -X POST "$base_url/api/v1/load" \
  -H 'Content-Type: application/json' \
  -d "{\"model_name\":\"$model_name\",\"llamacpp_backend\":\"$backend\",\"ctx_size\":$context_size}" \
  >/dev/null

health="$(curl -sf -m 10 "$base_url/api/v1/health")"
image="$(docker inspect --format '{{.Image}}' "$container")"
digest="$(docker image inspect --format \
  '{{if .RepoDigests}}{{index .RepoDigests 0}}{{else}}{{.Id}}{{end}}' \
  "$image")"
container_arch="$(docker exec "$container" uname -m)"
host_arch="$(uname -m)"
host="$(uname -srm)"
if command -v nvidia-smi >/dev/null 2>&1; then
  host="$host; $(nvidia-smi --query-gpu=name,driver_version \
    --format=csv,noheader | head -1)"
fi
if grep -qi microsoft /proc/version 2>/dev/null; then
  host="$host; WSL2"
fi
if [ "$(uname -s)" = Darwin ]; then
  host="$host; $(sysctl -n machdep.cpu.brand_string)"
fi
launched() {
  # Only the configured model's launch command: another loaded model
  # (an embedder, say) would otherwise add its own binary or GGUF path.
  printf '%s' "$health" | python3 -c '
import json, sys
health = json.load(sys.stdin)
for model in health.get("all_models_loaded", []):
    if model.get("model_name") != sys.argv[2]:
        continue
    command = model.get("launch_command") or []
    if sys.argv[1] == "binary":
        print(command[0])
    elif "-m" in command:
        print(command[command.index("-m") + 1])
    break
' "$1" "$model_name"
}
model_path="$(launched model)"
gguf_sha256="$(docker exec "$container" sha256sum "$model_path" | cut -d' ' -f1)"
# The build of the llama-server actually launched, e.g. "b10723".
llama_build="$(docker exec "$container" "$(launched binary)" --version 2>&1 \
  | sed -n 's/.*(build \([0-9]*\),.*/b\1/p' | head -1)"

HEALTH="$health" LLAMA_BUILD="$llama_build" BACKEND="$backend" DIGEST="$digest" \
CONTAINER_ARCH="$container_arch" HOST_ARCH="$host_arch" HOST="$host" \
MODEL_PATH="$model_path" GGUF_SHA256="$gguf_sha256" MODEL_NAME="$model_name" \
python3 - <<'PYTHON'
import json
import os
import re

health = json.loads(os.environ["HEALTH"])
loaded = next(
    m
    for m in health["all_models_loaded"]
    if m.get("model_name") == os.environ["MODEL_NAME"]
)
backend = os.environ["BACKEND"]
revision = re.search(r"/snapshots/([0-9a-f]+)/", os.environ["MODEL_PATH"])
container_arch = os.environ["CONTAINER_ARCH"]
host_arch = os.environ["HOST_ARCH"].replace("arm64", "aarch64")
provenance = {
    "emulation": (
        "none (native " + container_arch + ")"
        if container_arch == host_arch
        else f"{container_arch} container under emulation on {host_arch}"
    ),
    "gguf_sha256": os.environ["GGUF_SHA256"],
    "hf_revision": (
        revision.group(1)
        if revision
        else "none (local GGUF; identity is gguf_sha256)"
        if os.environ["MODEL_PATH"].startswith("/models/")
        else None
    ),
    "host": os.environ["HOST"],
    "image": os.environ["DIGEST"],
    "lemonade_version": health.get("version"),
    "llama_cpp_build": os.environ["LLAMA_BUILD"] or None,
    "llamacpp_args": loaded["recipe_options"].get("llamacpp_args"),
}
print(f'engine.backend = "{backend}"; loaded device = "{loaded.get("device")}"')
print('"engine_provenance": ' + json.dumps(provenance, indent=2, sort_keys=True))
PYTHON
