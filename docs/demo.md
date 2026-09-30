# The live demo: runbook and dry-run record

**Purpose:** the live demo in the V1 presentation (SPECIFICATION.md,
V1 scope): one intent through apply, and one deliberate failure
through automatic recovery.

**Length:** sized for a twenty-minute segment.

**Audience:** Martin and Hannah, as presenters.

**Where it runs:** Martin's WSL2 machine with the RTX 4060, the only one
with the fine-tuned model (docs/master_plan.md item 19).

**Status:** the watched dry run is still to be done; its record is at
the end of this page.

## What the audience sees

The demo runs one PyMOL window, with one structure in it: gold item
`gold_056`'s held-out structure, two short chains with two zinc ions
and a water. The fine-tuned model answered that item correctly in the
offline evaluation.

**Beat 1: one intent through apply**

- The presenter types a request in plain words.
- The copilot shows a preview of exactly what it will run, and nothing
  in the session changes yet.
- The presenter approves it, and the session changes.
- Then `copilot_rollback` undoes the whole apply.

**Beat 2: one deliberate failure through recovery**

- The presenter arms a staged failure.
- The same request goes through preview and approval.
- A command fails partway through the plan, after earlier commands have
  already changed the session.
- The copilot restores the whole session by itself.

## Before the presentation (15 minutes)

All commands run from the repository root, on the demo machine.

1. **Start the engine with the fine-tuned model.**

   ```sh
   (cd configs/evaluation/engine && docker compose -f compose.yaml \
       -f compose.nvidia.yaml -f compose.local-model.yaml up -d)
   configs/evaluation/engine/setup.sh cuda --config configs/evaluation/finetuned.json
   ```

   The last line must read `loaded device = "gpu"`. If it does not, see
   [configs/evaluation/engine/README.md](../configs/evaluation/engine/README.md).

2. **Start the server** in its own terminal, from the same config:

   ```sh
   bazel run //src/pmc_server:server -- --config configs/evaluation/finetuned.json
   ```

   Wait for `pymol-copilot server listening on 127.0.0.1:<port>`.

3. **Create the demo environment**, once: the runtime's own PyMOL,
   plus the Qt binding it needs to open a window.

   ```sh
   uv venv --python 3.13 --managed-python .venv-demo
   uv pip install -p .venv-demo --require-hashes -r requirements-demo.txt
   ```

4. **Rehearse both beats headless.** This takes about a minute each and
   must print `REHEARSAL: passed` twice:

   ```sh
   bazel run //tests/demo:demo -- --headless
   bazel run //tests/demo:demo -- --headless --fail-on color
   ```

5. **Open the demo window:**

   ```sh
   PYTHONPATH=src:tools/winstage:tests/demo .venv-demo/bin/python tests/demo/copilot_demo.py
   ```

   PyMOL opens with the structure loaded and prints
   `copilot: connected to the server on 127.0.0.1:<port>`. Under WSLg,
   the launcher points Qt at WSLg's Wayland display itself.

6. **Run `copilot_health`.** It must show:
   - `engine: ready`, running on the GPU;
   - the model as `Llama-3.2-1B-Instruct-pmc-train-e6c6c4dd8f6caaf9-Q4_K_M@/models/...`;
   - `all match this client` for the contracts;
   - `copilot: ready`.

## Beat 1: one intent through apply (about 8 minutes)

1. **Type the request:**

   ```
   copilot select the zinc ions, make them silver and show them as dots
   ```

   The answer takes about ten seconds.

2. **Stop on the preview and let the watcher read it.** This is the
   check SPECIFICATION.md makes of the demo: *a watcher can tell what is
   about to change before apply is confirmed.* The preview shows:
   - **the plan's identifier and when it expires**, in 5 minutes;
   - **the object it acts on**, `pmc_structure` (36 atoms, 1 state);
   - **the numbered commands**, exactly as they will run, with how many
     atoms each selection matched. For this request that is a
     selection of the zinc ions (2 atoms), `color silver` and
     `show dots`;
   - **warnings**, here none;
   - **fidelity**, exact: a separate PyMOL process rebuilt this session
     and ran the plan against it, and the counts come from that run;
   - **what was not checked**, which is whether this is scientifically
     what you meant;
   - **the exact commands** to approve or reject.

   Say what was checked and what was not. The model selected the zinc
   by atom name (`name ZN`), where a person might write the residue
   name (`resn ZN`). Here both match the same two atoms, and the preview
   is where you would catch it if they did not.

3. **Approve:** type `copilot_apply <plan id>`, as the preview shows
   it. The zinc ions turn silver and are shown as dots, and a recovery
   point is saved first.

4. **Undo it:** type `copilot_rollback <plan id>`. The copilot warns
   that this replaces the whole session, and the zinc ions return to
   how they were.

## Beat 2: one deliberate failure through recovery (about 8 minutes)

1. **Arm the failure:** type `copilot_demo_fail color`. The console
   prints:

   > DEMO: the next plan's `color` will fail on purpose, to show
   > automatic recovery.

   Say plainly that this is staged. The demo wraps PyMOL so that
   `color` raises once the plan reaches it. Nothing in the product can
   inject a failure.

2. **Type the same `copilot ...` request.** The preview is the same
   kind as before.

3. **Approve it.** The plan's `select` runs and really changes the
   session. Then `color` fails, and the copilot restores the whole
   session from the recovery point it saved before apply. The console
   says:

   > copilot_apply: plan p-... failed and the complete session was
   > restored cleanly.

   Nothing of the partial plan is left.

4. **Disarm it:** type `copilot_demo_fail off`.

## If something goes wrong on stage

- **The preview does not come back, or `copilot_health` shows the
  engine as unavailable.** The engine or the server stopped. PyMOL
  itself is safe: the copilot has changed nothing it has not reported.
  Restart the engine, then the server, then run `copilot_demo_fail off`
  to reconnect.
- **The model proposes a different plan.** Show it: reject it with
  `copilot_reject <plan id>`, which is the point of the preview. The
  engine answers deterministically at temperature 0, so the rehearsal
  plan is the one to expect.
- **A restore fails, and the copilot halts.** Follow the manual
  recovery in
  [docs/development_setup.md](development_setup.md#manual-recovery-runbook)
  and load the preserved `.pse` file.

## What this depends on

- **The environment:**
  - `requirements-demo.txt` is the runtime's own `pymol-open-source-whl`
    3.2.0.2 and numpy, held to `requirements_lock.txt`, plus
    `PySide6-Essentials` 6.9.3 and `shiboken6` 6.9.3.
    `//tests/demo:demo_environment` checks this.
  - The environment is x86_64 Linux only, like the model.
- **Licence:** PySide6 and shiboken6 are
  `LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only`, as their wheel
  metadata states. They are used unmodified, as installed libraries, and
  are not redistributed.
- **The structure:**
  - `tests/demo/demo_case.json` is gold item `gold_056`'s intent and
    structure, checked against its recorded SHA-256.
  - `//tests/demo:demo_launcher` rehearses both beats against the real
    server with a scripted engine.
  - It also proves the demo's PyMOL process imports only the client and
    the shared core: no LangGraph, no data or evaluation code.

## Dry-run record

The specification requires the failure-then-recovery beat to be
dry-run at least once, with the other developer watching.

- **Date:** *(to fill in)*
- **Machine:** *(to fill in)*
- **Presenter / watcher:** *(to fill in)*

| Beat | Could the watcher tell what was about to change before apply? | What they said | Issues found |
| --- | --- | --- | --- |
| 1: intent through apply and rollback | *(yes/no)* | | |
| 2: deliberate failure through recovery | *(yes/no)* | | |
