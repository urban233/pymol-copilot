# The deliverable notebook (master plan item 18)

## Context

This is item 18 of [docs/master_plan.md](../docs/master_plan.md), Martin's item,
sized at about 3 days. Its prerequisites 14, 15, 16 and 17 are all done;
17 merged as PR #59.

The intent:

```
Write the deliverable notebook: dataset generation, the oracle and its
conformance evidence, the label audit, the split, the untuned baseline, the
fine-tuning run, the per-category comparison, and the limits — every
deferred or unsupported category named, the exact operating system, PyMOL,
Python, Lemonade and model versions, and the licensing record. It has to
read standalone for someone who has never seen this repository.
```

SPECIFICATION.md makes the notebook V1's deliverable for the course
instructor. It must:

- run dataset generation, the oracle, fine-tuning and evaluation "end to
  end" and be "readable on its own" (L85, L205);
- report oracle conformance with an honest error analysis, the comparison
  (including a null or negative result), per-category results that call
  out any category that collapses, and the label error rate (L153-156);
- record the licensing (L299, L842), the retention and deletion rules
  (L474), and the exact OS, architecture, PyMOL, Python, Lemonade, model
  and contract versions (L671-673);
- report every optional item as attempted, negative or not done, never
  silently dropped (L701-755).

### Decisions (settled with Martin)

1. **What the notebook contains.** The real high-level code for dataset
   generation, the oracle and fine-tuning. Then end-user code: the tuned
   model answering an example prompt through the PyMOL API.
2. **What runs when it is executed.** Only the end-user demo runs live,
   on the GPU engine, behind Martin's consent at execution time.
   Generation, the oracle replay and fine-tuning show their real code
   behind a `RUN_*` flag that is off, and load the committed records.
3. **Kernel.** One pinned Python 3.12 notebook venv, `.venv-notebook`: the
   training lock plus Jupyter, the PyMOL wheel (`cp312` exists), httpx and
   langgraph. Every cell imports the real packages in-process. The runtime
   code parses under 3.12 and uses no 3.13-only API (checked). It is Linux
   only, like training.
4. **Committed executed**, with outputs, so it reads on GitHub without
   running.
5. **The demo uses the real copilot flow:** the real server, the PyMOL
   client, `copilot <intent>` → preview → `copilot_apply`.
6. **The server is fixed here to serve the tuned model.** Today
   `pmc_server.main` connects with the adapter's defaults (an old
   checkpoint, 4096 context), the placeholder prompt and no grammar. The
   fix pulls that part of item 19 into this item.
7. **The per-category rejection table comes from regenerating the corpus
   on Linux.** The committed corpus's `report.json` was never committed.
   The notebook states it is a Linux regeneration, with the `orient`
   fingerprint caveat.
8. **The Mac that built the split** ran macOS 15.6.1 on a MacBook Pro M2,
   per Martin.

### Decisions I took, so you can overrule them

- **Server fix: add options, keep the defaults.**
  - New `pmc_server.main` flags: `--model-name`, `--checkpoint`,
    `--backend`, `--context-size`, `--prompt {placeholder,training}` and
    `--grammar`.
  - Every default stays as it is, so the server's current behaviour and
    its tests are unchanged.
  - Item 19 decides whether to flip the defaults, since it owns
    integration.
  - The training prompt (today `pmc_eval.prompt.contract_prompt`) moves
    into `pmc_agent.prompt`, byte for byte, because it depends only on
    `pmc_core`. `pmc_eval` imports it from there, and
    `REPAIR_PROMPT_VERSION` stays 1.
  - This touches Hannah's `src/pmc_agent` and `src/pmc_server`, so the PR
    asks her to review.
- **The corpus regeneration is also the oracle conformance report.**
  Each of its 4,000 random plans is predicted by the oracle and executed
  in real PyMOL. A disagreement is a rejection, and an ungradable plan is
  unsupported. Its `report.json` is therefore the random differential
  evaluation the specification asks for. The committed 52-sample
  conformance slice and its tests are cited beside it.
- **Instant, pure-Python illustrations run live.** Building one
  structure's card, enumerating a plan, the oracle's prediction for it,
  and the masking of one example all take milliseconds, need neither
  PyMOL nor a GPU, and are not the heavy stages.
- **The notebook is built from a reviewable source.**
  `notebooks/source/pymol_copilot.py` holds `# %%` / `# %% [markdown]`
  cells. `notebooks/build_notebook.py` (nbformat) writes
  `notebooks/pymol_copilot.ipynb`, and nbclient executes it. The
  committed `.ipynb` is the executed build.
- **The demo structure** is a held-out synthetic structure (for example
  `two_chains_hetatm`), rebuilt in PyMOL from its snapshot. A real
  protein's card would not fit the 16k context, because the card lists
  every atom, and it would bring in PDB licensing.

## Delivery

1. Create `feat/notebook` from `origin/main` and copy this plan to
   `plans/14-notebook.md`.
2. Use Conventional Commits, one per step.
3. The gate after every step is the item 17 gate:
   - `bazel test //...`
   - `check_dependency_boundaries`
   - ruff check and format (which now lint the `.ipynb` too)
   - pyrefly
   - `PYTHONPATH=src .venv-train/bin/pytest src/pmc_train/tests`
4. Sabotage-check each step's test.
5. Follow the house style.
6. Sonnet cross-reviews after the runtime steps and before the PR.

**The implementer may edit:**

- `notebooks/**` and `requirements-notebook.{in,txt}`;
- `.gitignore` and `.bazelignore`: add `.venv-notebook/` only;
- `docs/development_setup.md`: the notebook section only;
- `src/pmc_agent/prompt.py`, `src/pmc_agent/graph.py`,
  `src/pmc_agent/session.py` and `src/pmc_server/main.py`, with their tests
  in `tests/unit/**` and `tests/integration/**`;
- `src/pmc_eval/prompt.py`: re-export only;
- `tests/notebook/**` (new) and visibility lines in the `BUILD.bazel`
  files for `docs/evaluation`, `docs/dataset` and `docs/training`;
- `docs/dataset/linux-regeneration/**` (new) and
  `docs/training/README.md` (licence rows);
- `docs/master_plan.md`, `results/README.md` and `plans/14-notebook.md`.

**Not** the committed evidence under `docs/evaluation/**`,
`docs/dataset/manifest.json` or `docs/dataset/audit/**`, and not
`pmc_core`, `pmc_client` or `pmc_train`. Stop and ask if any of them
needs a change.

**Human gate:** executing the notebook for the commit (Step 9) runs the
end-user demo on the GPU engine. The session prints the command, commit,
model, expected time and what it writes, and runs it only after an
explicit yes, as in item 17.

---

## Step 1 — Notebook environment

1. Add `requirements-notebook.in`:
   - `-r requirements-train.in`;
   - `pymol-open-source-whl==3.2.0.2`, `httpx==0.28.1`, `langgraph==1.2.11`
     (the runtime pins);
   - `jupyter-core`, `nbformat`, `nbclient`, `ipykernel` and `matplotlib`,
     pinned.
2. Compile it the way the training lock is compiled (Python 3.12,
   x86_64-linux, hashes).
3. Document `.venv-notebook` in `docs/development_setup.md`
   (`uv venv --python 3.12 --managed-python`), and add it to `.gitignore`
   and `.bazelignore`.

**Test:** `notebooks/tests/test_environment.py`, run in `.venv-notebook`.
It checks:

- Python is 3.12;
- the pins match the lock;
- `import pymol`, `pmc_core`, `pmc_data`, `pmc_agent`, `pmc_eval`,
  `pmc_server`, `pmc_client` and `pmc_train` all work;
- a headless `pymol.finish_launching(["pymol", "-cq"])` can
  `cmd.fragment` and `cmd.count_atoms`.

## Step 2 — The training prompt becomes a runtime prompt builder

- Move `repair_line` and `contract_prompt` into `pmc_agent/prompt.py` as
  `repair_line` and `build_training_prompt`, unchanged in behaviour.
- `pmc_eval/prompt.py` re-exports them under the old names, so
  `pmc_eval.runner` and the committed baseline are untouched.

**Test:**

- `tests/eval/test_prompt.py` and `//tests/eval:committed_baseline` pass
  unchanged.
- A new `tests/unit/test_agent_training_prompt.py` checks:
  - the first-attempt prompt is byte-identical to
    `pmc_core.prompt.build_for_runtime(...).text()`;
  - the repair lines are identical to `_error_line`'s wording.

## Step 3 — The graph can send a grammar

- `build_request_graph(..., grammar: str | None = None)` and
  `RequestGraphSession(..., grammar=None)` pass it into every
  `CompletionRequest`. Today the graph hard-codes `grammar=None`
  (`graph.py:662`).
- The default `None` keeps today's behaviour.

**Test:** in `tests/unit/`, a recording fake engine checks two things:

- by default the grammar is `None` on the first attempt and on every
  repair;
- with `grammar=build_grammar()`, that text reaches every attempt.

The existing graph tests pass unchanged.

## Step 4 — The server can serve the tuned model

- New `pmc_server.main` flags: `--model-name`, `--checkpoint`,
  `--backend`, `--context-size`, `--prompt {placeholder,training}` and
  `--grammar`.
- The flags thread through `build_engine`
  (`connect_lemonade(model_name=..., checkpoint=..., backend=...,
  context_size=...)`) and `serve`
  (`RequestGraphSession(prompt_builder=..., grammar=...)`).
- Defaults are unchanged, and `copilot_health` reports what was chosen.

**Test:** `tests/unit/test_server_main.py`, or the existing server-main
test, extended. It checks, with a hermetic httpx client:

- default arguments give today's model, checkpoint, context, placeholder
  prompt and no grammar;
- the flags reach the probe's load request and the session;
- an unknown `--prompt` is refused.

The e2e suite passes unchanged.

## Step 5 — The Linux corpus regeneration: rejection rates and conformance

1. Run
   `bazel run //src/pmc_data:corpus_cli -- --config configs/generation/corpus.json`
   on this machine. It takes about 10–20 minutes on CPU; no gate.
2. Commit its `report.json` and a `README.md` under
   `docs/dataset/linux-regeneration/`. The README states:
   - the host;
   - the commit;
   - that this is not the split's own corpus (which was built on the Mac,
     3,388 kept of 4,000);
   - the `orient` view-fingerprint caveat;
   - that every attempted plan is an oracle-versus-PyMOL differential
     check.

**Test:** `tests/notebook/test_linux_regeneration.py` (Bazel) checks:

- the committed report parses;
- its counts add up (kept + rejected + unsupported = attempted);
- it records the config's seed and target.

## Step 6 — The notebook source and builder

`notebooks/source/pymol_copilot.py` holds the notebook, written for a
reader who has never seen the repository. Each code cell calls the real
package API, and prose explains what it shows.

**Sections:**

0. **Reading guide and environment.** What V1 is, how to read this, and
   how to run it. A cell prints the exact versions table, the same one as
   §10.
1. **The problem and the system.** The restricted command language
   (`select`, `color`, `show`, `hide`, `orient`), the safety design
   (validate in a fresh sidecar, explicit approval, recovery), and where
   the model fits.
2. **Dataset generation.** Live, instant: one controlled structure
   (`pmc_data.structures.build_structure`), its card, one enumerated plan
   and its category. Shown behind `RUN_GENERATION`: the corpus run
   (`corpus_cli`'s entry point). Loaded: the per-category table from
   Step 5.
3. **The oracle and its conformance evidence.** Live, instant:
   `pmc_data.oracle` predicting that plan's resulting state and selection.
   Loaded: the Linux differential (agreement, rejections and unsupported,
   by category) and the committed 52-sample conformance slice. The
   ungradable categories are named with their reasons.
4. **The label audit.** It reads `docs/dataset/audit/result.json` and
   `history/`:
   - 0/50 (Wilson 0–7.1%), judged by Claude, calibrated to Martin's
     verdicts;
   - version 1: 1/50, judged by Martin, and the resulting `slice`
     exclusion.
5. **The split and decontamination.** From `docs/dataset/manifest.json`:
   the six held-out structures, the counts, and decontamination at 0.5
   with its sensitivity.
6. **The untuned baseline.** It recomputes every report with
   `pmc_eval.eval_cli.read_run`, and prints the pre-registration's
   primary endpoint.
7. **Fine-tuning.**
   - Live, instant: one real example's mask, and the zero-gradient
     property on a tiny model.
   - Shown behind `RUN_TRAINING`: `pmc_train.train.train(...)` and
     `pmc_train.export.export(...)`.
   - Loaded: the run manifest (config, seeds, hardware), the loss curve
     (matplotlib, from `loss.jsonl`), the export check, and the
     export-pipeline control.
8. **The comparison, per category.**
   - It recomputes with `pmc_eval.compare.compare`, giving the McNemar
     table.
   - It shows every breakout side by side.
   - It calls out every category and shape that collapses, such as
     `and_or` at 0/6 and `or` at 0/5 under both conditions. SPECIFICATION requires this.
   - It gives the failure analysis: paraphrase, the user's own verb, and
     wrong selections.
9. **Using the model: the real copilot flow.**
   - Start `pmc_server` with the tuned model's flags against Lemonade
     serving the GGUF.
   - Launch headless PyMOL in the kernel and rebuild the demo structure.
   - `connect_from_handoff(cmd, ...)`, then run the example intent through
     `cmd.do("copilot color the zinc ions of chain A magenta")`.
   - Show the preview: plan, selection counts and checks.
   - `copilot_apply`, then show the state before and after (colours and
     counts, plus a `cmd.png` image).
   - `copilot_rollback`, to show recovery.
   - The cell runs only when `PMC_NOTEBOOK_DEMO=1` is set at the gate;
     otherwise it shows why it was skipped.
10. **Limits, versions, licensing and retention.**
    - Every deferred or unsupported item, named:
      - the master plan's "already cut" list;
      - the oracle markers and exclusions;
      - the snapshot markers;
      - the spec's optional items, each marked as attempted or not;
      - the iGPU route, unproven.
    - The versions table:
      - OS: Ubuntu 24.04.4 under WSL2 and its Windows build, and macOS
        15.6.1 on the MacBook Pro M2 for the split;
      - architecture; PyMOL (wheel and contract); Python (3.13.13 and
        3.12.13); the Lemonade version and image digest; the llama.cpp
        builds; the model and GGUF hashes; the contract versions.
    - The licensing record:
      - code, dataset, PyMOL, Llama 3.2, the Claude-drafted gold intents;
      - Lemonade, llama.cpp and Unsloth, read from their licence files in
        the image, the checkout and the dist-info. These are added to
        docs/training/README.md as well.
    - Retention and deletion, from `data/README.md` and
      `results/README.md`.

`notebooks/build_notebook.py` turns the source into `.ipynb`
deterministically. It uses a fixed kernel spec, strips execution
metadata other than outputs, and orders keys.

**Test:** `tests/notebook/test_notebook_source.py` (Bazel, stdlib only)
checks:

- building from source reproduces the committed `.ipynb`'s cells;
- the notebook's code cells are ruff-clean (the CI ruff steps already
  lint `*.ipynb`).

## Step 7 — The committed notebook tells the truth

`tests/notebook/test_notebook_record.py` (Bazel) reads the executed
`.ipynb` as JSON. It checks:

- every code cell executed, in order, with no error output;
- each number the outputs print is recomputed from the evidence:
  - TaskSuccess and McNemar per set and condition (from `compare()`);
  - the audit figures, the split counts, the run's seeds and config
    SHA-256, and the GGUF hashes;
- the versions table matches the configs and run records.

Outputs tag these numbers with a stable marker, such as a
`<!-- pmc:task_success:test_gold:grammar -->` line, so the test reads
them without parsing prose.

## Step 8 — Licences and versions gathered

1. Read and record:
   - Lemonade's LICENSE from the pinned image;
   - llama.cpp's from `.train-tools/llama.cpp-b10707`;
   - Unsloth's and unsloth_zoo's from the dist-info;
   - the Windows build (`cmd.exe /c ver`) and `/etc/os-release`.
2. Add the licence rows to docs/training/README.md.

**Test:** the Step 7 record test covers the rendered table.

## Step 9 — Gate: execute the notebook, commit it

1. Bring up the GPU engine with the tuned model (`setup.sh cuda --config
   configs/evaluation/finetuned.json`).
2. **After an explicit yes**, run
   `PMC_NOTEBOOK_DEMO=1 .venv-notebook/bin/python notebooks/build_notebook.py --execute`.
   It takes a few minutes. The demo makes a handful of requests; the rest
   loads committed evidence.
3. Commit the executed `.ipynb`.

**Test:** Steps 6 and 7 pass on the committed notebook.

## Step 10 — Master plan and hand-over

1. Mark item 18 done with its PR.
2. Update the notes for item 19. The server now takes the tuned model's
   flags, and item 19 decides the defaults. Say what remains:
   - the missing-newline normalization when no grammar is sent;
   - flipping the defaults;
   - the integrated TaskSuccess measurement.

**Test:** the gate is green.

---

## Verification (end to end)

```
git switch -c feat/notebook origin/main
uv venv --python 3.12 --managed-python .venv-notebook && uv pip install -p .venv-notebook -r requirements-notebook.txt
PYTHONPATH=src .venv-notebook/bin/pytest notebooks/tests
bazel test //... --lockfile_mode=error      # includes tests/notebook
# gated: PMC_NOTEBOOK_DEMO=1 .venv-notebook/bin/python notebooks/build_notebook.py --execute
```

**Acceptance:**

1. The committed notebook reads standalone. It covers every topic in the
   intent, shows the real code, and states each number with its source.
2. Every number in it recomputes from committed evidence (Step 7).
3. The demo shows `copilot <intent>` → preview → apply → rollback,
   against the tuned model, in real PyMOL.
4. Every deferred or unsupported item is named, with the complete
   versions and licensing record, and the retention and deletion rules.
5. With default flags the server behaves exactly as before.

## Risks

- **The demo's intent fails.** The tuned model is right on 47% of gold
  with the grammar. Pick the example from categories the model gets right
  on held-out structures, and show whatever it does: if the plan is
  wrong, the notebook says so, since this is not a cherry-picked success
  claim.
- **Headless PyMOL inside a Jupyter kernel.** Step 1's test proves
  `finish_launching(["pymol", "-cq"])` works in the venv first.
- **The two-venv drift.** `.venv-notebook` includes `requirements-train.in`
  so the training stack cannot diverge; the runtime pins are copied from
  `requirements.in`, and Step 1's test checks them.
- **Ruff on the `.ipynb`.** The builder output must be ruff-formatted, and
  Step 6's test catches it before CI does.
