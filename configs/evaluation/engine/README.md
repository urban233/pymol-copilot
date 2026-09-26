# The evaluation engine

Lemonade 11.9.0 serving `Llama-3.2-1B-Instruct-Q4_K_M` for the offline
evaluation (master plan item 16), in Docker, on the loopback port
`configs/evaluation/baseline.json` points at. Three variants share one
`compose.yaml`:

| Host | Command | `engine.backend` |
| --- | --- | --- |
| x86_64 Linux or WSL2, CPU | `docker compose -f compose.yaml up -d` | `cpu` |
| x86_64 Linux or WSL2, NVIDIA GPU | `docker compose -f compose.yaml -f compose.nvidia.yaml up -d` | `cuda` |
| Apple Silicon | `docker compose -f compose.yaml -f compose.arm64.yaml up -d --build` | `cpu` |

Then, from this directory:

```
./setup.sh cpu     # or: ./setup.sh cuda
```

`setup.sh` pulls the model, pins the chat template's date (see
`../README.md`), installs the CUDA llama.cpp build for `cuda`, loads the
model the way the adapter's probe does, and prints the
`engine_provenance` block and the `engine.backend` to put in
`baseline.json`. Commit that before running: a run refuses a modified
tracked file, and an engine whose Lemonade version or llama.cpp
arguments differ from what the config records.

**A baseline and every comparison against it run on the same engine
variant, on the same host.** A different backend or build changes the
arithmetic, and a greedy completion can change with it. If item 17's
fine-tune is evaluated elsewhere, run the base model there too.

## Apple Silicon

The official image is `linux/amd64` only, so on an Apple Silicon Mac it
runs under emulation. `compose.arm64.yaml` builds `Dockerfile.arm64`
instead: Lemonade's own Debian 13 arm64 package, with the same llama.cpp
build (`b10723`). Measured on an M2 Pro with the longest gold prompt
(5,495 tokens): prompt processing at 238 tokens/s against 43 under
emulation, and a 256-token completion in about 18 s against about 45.

Lemonade also has a native macOS build with a Metal backend
(`Lemonade-11.9.0-Darwin.pkg`), which would be faster again. It is not
set up here, because it installs Lemonade on the host rather than in a
container.

## WSL2 with an NVIDIA GPU

Not yet run on such a machine: the steps are what Lemonade and Docker
document, and the first run will show whether anything differs.

1. **GPU in Docker.** Install the current NVIDIA driver on Windows (not
   inside the distro), then either Docker Desktop with the WSL2 backend
   and integration enabled for your distro, or Docker Engine inside the
   distro with the NVIDIA Container Toolkit. Check with
   `docker run --rm --gpus all nvidia/cuda:12.6.3-base-ubuntu24.04 nvidia-smi`.
2. **The repository inside the distro**, not on `/mnt/c`: Bazel and the
   PyMOL sidecar run there exactly as on `ubuntu-24.04` in CI. **Copy
   the frozen split** `data/splits/split-e4599620801af592/` (47 MB,
   gitignored) from the machine that built it into the same path; do
   not regenerate it. Its 79 `orient` samples record view fingerprints
   that differ between macOS and Linux, so a split rebuilt on Linux
   would hash to another id, and a run refuses any split but the one
   `docs/dataset/manifest.json` records.
3. **The engine**: `docker compose -f compose.yaml -f compose.nvidia.yaml
   up -d`, then `./setup.sh cuda`. The first line it prints names the
   device Lemonade reports for the loaded model. The adapter's probe
   requires it to equal `engine.backend`; if it is not `cuda`, the probe
   will refuse the engine, and that is the one thing to report back.
4. **Reachability**: the harness talks to `http://localhost:13305` from
   inside the distro. With Docker Desktop that is normally forwarded; if
   it is not, set `networkingMode=mirrored` in `%UserProfile%\.wslconfig`.
5. **The config**: `engine.backend` is already `"cuda"`; paste the
   printed `engine_provenance` into `configs/evaluation/baseline.json`,
   commit, and run as in `docs/evaluation/README.md`.
