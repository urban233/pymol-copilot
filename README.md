<p align="center">
  <img src="assets/logo/logo.png" alt="PyMOL-Copilot logo" width="100">
</p>

<h1 align="center">PyMOL-Copilot</h1>

<p align="center">
  Plain-language requests in, checked PyMOL commands out. Runs entirely on your machine.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/status-experimental-orange.svg" alt="Status: experimental">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-BSD%203--Clause-blue.svg" alt="License: BSD 3-Clause"></a>
  <img src="https://img.shields.io/badge/python-3.13-blue.svg" alt="Python 3.13">
</p>

PyMOL-Copilot adds a `copilot` command to [PyMOL](https://pymol.org). You
describe what you want to see; a small language model running locally
writes a short plan of PyMOL commands; the plan is checked and rehearsed
in a separate PyMOL process; you read a preview and decide whether to
apply it. Nothing changes in your session until you approve, an applied
plan can be rolled back, and no data leaves the machine.

```
PyMOL>copilot select the zinc ions, make them silver and show them as dots

copilot plan p-5667af31-… (expires in 5 min)
  object:    pmc_structure (36 atoms, 1 state)
  commands:
    1 | select copilot_sel0244, name ZN   -> 2 atoms
    2 | color silver, copilot_sel0244
    3 | show dots, copilot_sel0244
  warnings:  none
  fidelity:  exact on the declared state scope
  NOT checked: whether this is scientifically what you meant
  apply:     copilot_apply p-5667af31-…
  reject:    copilot_reject p-5667af31-…
```

## How it works

1. **Snapshot.** The client reads the loaded structure into a canonical
   snapshot and checks that it can rebuild the session from it exactly.
2. **Structure card.** The snapshot is rendered as text: every atom with
   its chain, residue, name, colour and representation.
3. **Generation.** A fine-tuned Llama-3.2-1B-Instruct (Q4_K_M GGUF,
   served by [Lemonade](https://github.com/lemonade-sdk/lemonade)) reads
   the card and the request and writes the plan. A grammar can constrain
   it to the command language below.
4. **Validation.** The plan is parsed by the project's own parser,
   checked by an independent policy, and run against a rebuilt copy of
   the session in a fresh PyMOL process. A failed plan gets at most two
   repair attempts.
5. **Approval.** The preview lists the commands, the atoms each
   selection matched, and what was and was not checked.
6. **Apply and recovery.** The session is saved before the first command
   runs. If any command fails, the session is restored automatically;
   `copilot_rollback` undoes a successful apply.

The model may only use a restricted command language: the verbs
`select`, `color`, `show`, `hide` and `orient`, over selections built
from `chain`, `resi`, `resn`, `name`, `hetatm` and `polymer` joined by
`and`, `or` and `not`. Anything else (Python, `load`, `set`, plugins)
is rejected before it runs. The server listens on loopback only and
requires a per-session credential.

## Results

TaskSuccess means the plan runs cleanly in PyMOL and leaves exactly the
expected session state. It is measured on 68 hand-reviewed requests on
six structures held out of training, comparing the fine-tuned model with
the untuned base model, paired per request with an exact McNemar test:

| Condition | Base model | Fine-tuned | McNemar p |
| --- | --- | --- | --- |
| Free generation | 0/68 | 19/68 | 3.8e-06 |
| Grammar-constrained | 0/68 | 32/68 | 4.7e-10 |

On 842 templated requests on the same held-out structures the fine-tuned
model is correct every time, but those requests share their phrasing
with the training data. Its main weakness is paraphrase: everyday words
become invented atom names, and "chains A and B" is read as `and` where
the user means `or`. Details: [docs/evaluation/](docs/evaluation/README.md).

## Getting started

### Windows: the portable bundle

One ZIP holds Python, PyMOL, Lemonade, the model and a JupyterLab
notebook that runs the whole project, the live copilot included, on the
CPU. Extract it and double-click `Start PyMOL Copilot.bat`; nothing is
installed. It needs about 4 GB of free memory and 3 GB of disk, and each
answer takes tens of seconds to a minute on a CPU. The ZIP is built
from a checkout with the model file; see [docs/bundle.md](docs/bundle.md).

### Linux: from source

Requirements: x86_64 Linux,
[Bazelisk](https://github.com/bazelbuild/bazelisk), Docker with the
NVIDIA Container Toolkit, and [uv](https://docs.astral.sh/uv/).

The fine-tuned model is not distributed. Generate the dataset
([configs/generation/](configs/generation/README.md)), then train and
export the model ([docs/training/](docs/training/README.md)); the GGUF
lands under `results/`.

1. Start Lemonade with the model:

   ```sh
   (cd configs/evaluation/engine && docker compose -f compose.yaml \
       -f compose.nvidia.yaml -f compose.local-model.yaml up -d)
   configs/evaluation/engine/setup.sh cuda --config configs/evaluation/finetuned.json
   ```

2. Start the server; it writes its port and credential to
   `~/.pymol-copilot/session.json`:

   ```sh
   bazel run //src/pmc_server:server -- --config configs/evaluation/finetuned.json
   ```

3. Create the PyMOL environment once:

   ```sh
   uv venv --python 3.13 --managed-python .venv-demo
   uv pip install -p .venv-demo --require-hashes -r requirements-demo.txt
   ```

4. In a PyMOL running from that environment, with `src` and
   `tools/winstage` on `PYTHONPATH` and one structure loaded, connect
   the client:

   ```python
   from pathlib import Path
   from pmc_client.bootstrap import connect_from_handoff

   connect_from_handoff(
       cmd, print, path=Path.home() / ".pymol-copilot" / "session.json"
   )
   ```

   `tests/demo/copilot_demo.py` does all of this with a test structure;
   [docs/demo.md](docs/demo.md) walks through it.

### Commands

| Command | What it does |
| --- | --- |
| `copilot <request>` | Plan the request and show the preview. Changes nothing. |
| `copilot_apply <plan id>` | Save the session, then run the plan. |
| `copilot_reject <plan id>` | Discard the plan. |
| `copilot_rollback <plan id>` | Restore the session saved before that plan was applied. |
| `copilot_health` | Show the server, engine, model and contract versions. |

## Notebooks

- [notebooks/pymol_copilot.ipynb](notebooks/pymol_copilot.ipynb): the
  complete record in English: dataset generation, the oracle, the split,
  baseline, fine-tuning, the comparison and a live session. Every number
  is recomputed from evidence committed in `docs/`.
- [notebooks/pymol_copilot_kurz.ipynb](notebooks/pymol_copilot_kurz.ipynb):
  a short German version with the same live session.

Both are committed executed, so they can be read without running them.

## Development

Bazel 9.2.0 with a hermetic CPython 3.13.13 builds and tests the
runtime:

```sh
bazel test //... --lockfile_mode=error
bazel run //tools/quality:ruff --lockfile_mode=error -- check .
bazel run //tools/quality:pyrefly --lockfile_mode=error -- check
```

Training (`.venv-train`) and the notebooks (`.venv-notebook`) use
separate Python 3.12 environments, so torch never enters the runtime.
Full commands: [docs/development_setup.md](docs/development_setup.md).
Contribution rules: [CONTRIBUTING.md](CONTRIBUTING.md).

## Repository layout

| Path | Contents |
| --- | --- |
| `src/pmc_core` | Shared contract: plan language, parser, policy, snapshot, structure card, grammar, protocol |
| `src/pmc_client` | The PyMOL side: commands, preview, approval, apply and recovery |
| `src/pmc_server` | Loopback server |
| `src/pmc_agent` | LangGraph request graph and the inference adapters |
| `src/pmc_sidecar` | The separate PyMOL process that rehearses plans |
| `src/pmc_data` | Synthetic structures, the oracle, dataset generation, split and audit |
| `src/pmc_eval` | Offline evaluation harness and comparison |
| `src/pmc_train` | Completion-only LoRA fine-tuning and GGUF export |
| `configs/` | Generation, training, evaluation and engine configurations |
| `docs/` | Committed evidence: dataset, evaluation, training, integration |
| `notebooks/` | The two notebooks and their sources |
| `tools/bundle/` | Builds and checks the Windows bundle |

## Limitations

- The training and test structures are small synthetic proteins; real
  PDB entries have not been evaluated.
- Training requests come from templates, so natural phrasing is the
  weakest point.
- Five verbs only: no loading, labels, settings or measurements.
- One training run with one seed; only Q4_K_M was evaluated.
- The model runs on CPU or NVIDIA GPU; integrated GPUs are untested.

## License

The code is released under the [BSD 3-Clause License](LICENSE). The
model is derived from Llama 3.2 and is subject to the Llama 3.2
Community License and Acceptable Use Policy. Built with Llama.

Authors: Martin Urban and Hannah Kullik.
