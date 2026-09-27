# The evaluation engine

Lemonade 11.9.0 serving `Llama-3.2-1B-Instruct-Q4_K_M` for the offline
evaluation (master plan item 16), in Docker, on the loopback port
`configs/evaluation/baseline.json` points at. Three variants share one
`compose.yaml`:

| Host | Command | `engine.backend` |
| --- | --- | --- |
| x86_64 Linux or WSL2, CPU | `docker compose -f compose.yaml up -d` | `cpu` |
| x86_64 Linux or WSL2, NVIDIA GPU (the baseline; see the tutorial below) | `docker compose -f compose.yaml -f compose.nvidia.yaml up -d` | `cuda` |
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

## Tutorial: running the baseline on WSL2 with an NVIDIA GPU

From a Windows machine with an NVIDIA GPU to a committed baseline under
`docs/evaluation/baseline/`. The baseline runs on this machine because
item 17 trains here, and the tuned model must be evaluated on the same
engine as the base model.

Run end to end on 2026-09-27 on WSL2 with an RTX 4060, producing the
committed baseline. The one surprise was step 5's device line: Lemonade
reports a GPU-loaded model as `gpu`, not `cuda`, and the adapter's probe
now accepts that.

### 1. Windows: WSL2, the NVIDIA driver and Docker

In an administrator PowerShell:

```powershell
wsl --install -d Ubuntu-24.04
wsl --update
```

Install the current NVIDIA driver **on Windows** (GeForce or Studio
driver from nvidia.com). Do not install an NVIDIA driver inside the
distro; WSL2 passes the Windows driver through. Inside Ubuntu,
`nvidia-smi` must list your GPU.

Install **Docker Desktop**, and under Settings → Resources → WSL
integration enable it for `Ubuntu-24.04`. Its WSL2 backend includes GPU
support. (Alternatively, Docker Engine inside the distro plus the NVIDIA
Container Toolkit works too: install Docker with
`curl -fsSL https://get.docker.com | sh`, the toolkit as NVIDIA's
install guide describes, then `sudo nvidia-ctk runtime configure
--runtime=docker && sudo systemctl restart docker`.)

Check, inside Ubuntu, that a container sees the GPU:

```bash
docker run --rm --gpus all nvidia/cuda:12.6.3-base-ubuntu24.04 nvidia-smi
```

Optional, in `%UserProfile%\.wslconfig`: `memory=16GB` under `[wsl2]`
if the machine has 32 GB or more, and `networkingMode=mirrored` if step
5 cannot reach the engine on `localhost`. Run `wsl --shutdown` after
editing it.

Runs take hours: set Windows not to sleep while plugged in.

### 2. Ubuntu: tools

```bash
sudo apt update
sudo apt install -y git curl ca-certificates python3 tmux libgl1
mkdir -p ~/.local/bin
curl -fsSL -o ~/.local/bin/bazel \
    https://github.com/bazelbuild/bazelisk/releases/download/v1.29.0/bazelisk-linux-amd64
chmod +x ~/.local/bin/bazel
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc && . ~/.bashrc
```

`libgl1` is the one system library PyMOL's Linux wheel needs that a
fresh Ubuntu 24.04 lacks; the wheel bundles the rest. Bazelisk selects
Bazel 9.2.0 from `.bazelversion`, and Bazel downloads its own Python.

### 3. The repository and the frozen split

Clone into the Linux file system, not under `/mnt/c` (Bazel is slow and
unreliable on the Windows mount):

```bash
cd ~
git clone https://github.com/urban233/pymol-copilot.git
cd pymol-copilot
git switch feat/eval-harness-baseline
git config user.name "Martin Urban"
git config user.email "<your email>"
```

Pushing later needs GitHub credentials in the distro (`gh auth login`,
or an SSH key).

Copy the frozen split `data/splits/split-e4599620801af592/` (47 MB,
gitignored) from the Mac that built it. **Do not regenerate it**: its 79
`orient` samples record view fingerprints that differ between macOS and
Linux, so a split rebuilt here would hash to another id, and a run
refuses any split but the one `docs/dataset/manifest.json` records. On
the Mac:

```bash
tar -C data/splits -czf ~/split-e4599620801af592.tgz split-e4599620801af592
```

Move the archive to Windows (a USB stick, a cloud folder, `scp`), then
in Ubuntu:

```bash
mkdir -p data/splits
tar -C data/splits -xzf /mnt/c/Users/<you>/Downloads/split-e4599620801af592.tgz
python3 -c "import json; print(json.load(open('data/splits/split-e4599620801af592/manifest.json'))['split_id'])"
```

The last line must print `e4599620801af592`. Every run also recomputes
every file's hash before it starts.

### 4. The build, once

```bash
bazel test //tests/eval/... //tests/data:gold_set_real_pymol
```

The first build downloads Bazel, Python and the locked wheels. These
suites prove the harness and the PyMOL sidecar work on this machine,
before any model is involved; `//tests/eval:lemonade_real` skips here
and `//tests/eval:committed_baseline` skips until step 9. If a
real-PyMOL test fails with a missing shared library, install it with
`apt` and rerun.

### 5. The engine

```bash
cd configs/evaluation/engine
docker compose -f compose.yaml -f compose.nvidia.yaml up -d
./setup.sh cuda
cd ../../..
```

`setup.sh` installs Lemonade's CUDA build of llama.cpp, downloads the
model (about 800 MB), pins the chat template's date, loads the model at
a 16384-token context, and prints two things:

```text
engine.backend = "cuda"; loaded device = "gpu"
"engine_provenance": { ... }
```

**Check the first line.** Lemonade reports a model loaded on the GPU
as device `gpu`, which the adapter's capability probe accepts for the
`cuda` and `vulkan` backends. If it says anything else (for example
`cpu`, meaning the GPU was not used), stop here and report the line
together with the output of `curl -s localhost:13305/api/v1/health`.

If `setup.sh` cannot reach `http://localhost:13305`, check
`docker ps` shows `pmc-eval-lemonade` running, then try the mirrored
networking setting from step 1.

### 6. Record the engine and commit

Paste the printed `engine_provenance` block over the empty one in
`configs/evaluation/baseline.json` (`engine.backend` is already
`"cuda"`), then:

```bash
git add configs/evaluation/baseline.json
git commit -m "chore(eval): Record the WSL2 NVIDIA engine's provenance"
```

Runs refuse a modified tracked file, an engine whose Lemonade version or
llama.cpp arguments differ from what is recorded, and an unfilled
provenance. **From here until step 9, commit nothing**: the four runs
must come from one commit, or `publish` refuses them.

### 7. Smoke test and pilot

```bash
PMC_LEMONADE_BASE_URL=http://localhost:13305 \
    bazel test //tests/eval:lemonade_real --test_output=all
split=data/splits/split-e4599620801af592
bazel run //src/pmc_eval:eval_cli -- run --split $split \
    --set test_gold --condition grammar --limit 5 --out results/pilot
```

The smoke test runs two gold samples per condition through the real
engine and sidecar. The pilot prints one line per sample; its pace
tells you how long the full runs will take (the Mac's CPU needed about
20 s per sample). Keep pilots under `results/pilot`, never
`results/`, so step 9's `results/eval-*` holds only the real runs.

### 8. The four runs

In `tmux` (so a closed terminal does not stop them):

```bash
tmux new -s baseline
split=data/splits/split-e4599620801af592
for set in test_gold heldout_synthetic; do
  for condition in grammar no-grammar; do
    bazel run //src/pmc_eval:eval_cli -- run --split $split \
        --set $set --condition $condition --resume || break 2
  done
done 2>&1 | tee -a ~/eval-runs.log
```

Detach with `Ctrl-b d`, reattach with `tmux attach -t baseline`. Each
run ends with `WROTE results/eval-<id>`.

- **Interrupted** (reboot, `Ctrl-c`): rerun the same loop; `--resume`
  continues each run from its last scored sample.
- **`INCOMPLETE: n samples hit infrastructure failures`**: an engine or
  sidecar failure left samples unscored. Check the engine
  (`curl -s localhost:13305/api/v1/health`), then rerun the loop.
- **`REFUSED: ...`**: nothing was written; the message says why (see
  Troubleshooting).

Then repeat the gold runs once, to measure how deterministic the engine
is:

```bash
for condition in grammar no-grammar; do
  bazel run //src/pmc_eval:eval_cli -- run --split $split \
      --set test_gold --condition $condition --out results/determinism
done
python3 - <<'EOF'
import glob, json, os

def completions(run):
    by_sample = {}
    for line in open(f"{run}/samples.jsonl"):
        record = json.loads(line)
        by_sample[record["sample_id"]] = [
            attempt["completion"] for attempt in record["attempts"]
        ]
    return by_sample

for rerun in sorted(glob.glob("results/determinism/eval-*")):
    first = "results/" + os.path.basename(rerun)
    a, b = completions(first), completions(rerun)
    condition = json.load(open(f"{first}/run.json"))["identity"]["condition"]
    print(condition, sum(a[k] != b[k] for k in a), "of", len(a), "samples differ")
EOF
```

Note the two numbers for the README's pilot measurements.

### 9. Publish and commit the baseline

```bash
bazel run //src/pmc_eval:eval_cli -- publish --runs results/eval-*
bazel test //tests/eval:committed_baseline --test_output=errors
git add docs/evaluation/baseline
git commit -m "feat(eval): Record the untuned baseline"
git push
```

`publish` refuses a pilot, a run from a modified tree, runs from
different commits, and any report that does not recompute from its
samples. The committed-baseline test now runs instead of skipping. The
headline figures are the `test_gold` TaskSuccess rows of
`docs/evaluation/baseline/BASELINE.md`; they go into item 16 of
`docs/master_plan.md`.

### Troubleshooting

| Message | Meaning and fix |
| --- | --- |
| `nvidia-smi` fails inside Ubuntu | The Windows driver is missing or too old; update it on Windows, then `wsl --shutdown`. |
| `could not select device driver "nvidia"` | Docker cannot see the GPU: enable WSL integration in Docker Desktop, or install the NVIDIA Container Toolkit. |
| `the engine did not connect: engine_unknown: lemonade loaded an unexpected device` | Lemonade reports the loaded device as something other than `gpu`; see step 5. |
| `the engine did not connect: engine_unavailable` | Lemonade is not reachable: `docker ps`, `curl -s localhost:13305/api/v1/health`, then mirrored networking. |
| `the engine reports llamacpp_args ...` | The template date is not pinned as recorded: rerun `./setup.sh cuda`. |
| `the longest prompt does not complete` | The model is not loaded at the 16384-token context; rerun `./setup.sh cuda`. |
| `a tracked file is modified` | Commit the config (step 6); nothing else may change during the runs. |
| `... is split <id>, not the committed split e4599620801af592` | The split was regenerated or damaged; copy it again (step 3). |
| `fill in engine_provenance first` | Step 6 was skipped. |
| `holds an unfinished run; pass --resume` | Continue the run with `--resume`. |
| `spawn_or_load_failure` in a run | The PyMOL sidecar cannot start; run step 4's tests to find the missing library. |
