# The demo, rehearsed against the fine-tuned model

**What this is:** Gate C of master plan item 19. Both demo beats
([docs/demo.md](../demo.md)) were rehearsed headless against the
fine-tuned model, at commit `6fad86e`, on 2026-09-30, on Martin's WSL2
machine with the RTX 4060, with his consent.

**How it was run:** the production server was started from the
evaluated config:

```
bazel run //src/pmc_server:server -- --config configs/evaluation/finetuned.json
```

The launcher's rehearsal then drove headless PyMOL through the real
client, on the framed demo structure:

```
bazel run //tests/demo:demo -- --headless
bazel run //tests/demo:demo -- --headless --fail-on color
```

**Result:** both beats passed.

- **Beat 1:**
  - the preview changed nothing;
  - apply changed the session and kept a recovery point;
  - rollback restored the session exactly.
- **Beat 2:**
  - the staged `color` failure came after the plan's `select` had
    really run;
  - the whole session was restored cleanly.

The model's plan was the one the offline evaluation graded correct:
it selects the zinc ions by atom name, then applies `color silver` and
`show dots`. Only the arbitrary number in the selection's name differs
between runs (see [README.md](README.md) on the engine's history).

## Beat 1: one intent through apply and rollback

```
copilot: connected to the server on 127.0.0.1:34715.
PyMOL> copilot_health
copilot health
  client:    application 0.0.0, protocol 1
  server:    reachable, application 0.0.0
  engine:    ready -- lemonade 11.9.0 on cuda
  model:     Llama-3.2-1B-Instruct-pmc-train-e6c6c4dd8f6caaf9-Q4_K_M@/models/train-e6c6c4dd8f6caaf9/export/Llama-3.2-1B-Instruct-pmc-train-e6c6c4dd8f6caaf9-Q4_K_M.gguf
  contracts: plan 1, policy 1, snapshot 1, card 1, prompt 1, grammar 1, errorEnvelope 1, executor 1 -- all match this client
  copilot:   ready
(0.0 s)
PyMOL> copilot select the zinc ions, make them silver and show them as dots
copilot plan p-9c968718-f430-403d-8955-7eae4d907460 (expires 2026-09-30T19:13:42.134Z, in 5 min)
  object:    pmc_structure (36 atoms, 1 state)
  commands:
    1 | select copilot_sel0250, name ZN   -> 2 atoms
    2 | color silver, copilot_sel0250
    3 | show dots, copilot_sel0250
  warnings:  none
  fidelity:  exact on the declared state scope
  checked:   the plan parses, policy allows it, and a fresh PyMOL sidecar reconstructed this session's declared state exactly, then ran the plan against it -- the counts above are from that run
  NOT checked: whether this is scientifically what you meant
  apply:     copilot_apply p-9c968718-f430-403d-8955-7eae4d907460
  reject:    copilot_reject p-9c968718-f430-403d-8955-7eae4d907460
(14.8 s)
PyMOL> copilot_apply p-9c968718-f430-403d-8955-7eae4d907460
copilot_apply: plan p-9c968718-f430-403d-8955-7eae4d907460 applied. Recovery point retained at /tmp/pmc-demo-g2g4bzda/.pymol-copilot/recovery/plan-9c968718-f430-403d-8955-7eae4d907460.pse.
(2.8 s)
PyMOL> copilot_rollback p-9c968718-f430-403d-8955-7eae4d907460
copilot_rollback: replacing the entire session with the pre-apply recovery point; later changes will be discarded.
copilot_rollback: plan p-9c968718-f430-403d-8955-7eae4d907460 rolled back and its recovery point was removed.
(0.0 s)
REHEARSAL: passed
```

## Beat 2: one deliberate failure through recovery

```
DEMO: the next plan's `color` will fail on purpose, to show automatic recovery. `copilot_demo_fail off` disarms it.
copilot: connected to the server on 127.0.0.1:34715.
PyMOL> copilot_health
copilot health
  client:    application 0.0.0, protocol 1
  server:    reachable, application 0.0.0
  engine:    ready -- lemonade 11.9.0 on cuda
  model:     Llama-3.2-1B-Instruct-pmc-train-e6c6c4dd8f6caaf9-Q4_K_M@/models/train-e6c6c4dd8f6caaf9/export/Llama-3.2-1B-Instruct-pmc-train-e6c6c4dd8f6caaf9-Q4_K_M.gguf
  contracts: plan 1, policy 1, snapshot 1, card 1, prompt 1, grammar 1, errorEnvelope 1, executor 1 -- all match this client
  copilot:   ready
(0.0 s)
PyMOL> copilot select the zinc ions, make them silver and show them as dots
copilot plan p-48caa77c-97ae-432a-924d-68f035a9bcd2 (expires 2026-09-30T19:13:59.844Z, in 5 min)
  object:    pmc_structure (36 atoms, 1 state)
  commands:
    1 | select copilot_sel0250, name ZN   -> 2 atoms
    2 | color silver, copilot_sel0250
    3 | show dots, copilot_sel0250
  warnings:  none
  fidelity:  exact on the declared state scope
  checked:   the plan parses, policy allows it, and a fresh PyMOL sidecar reconstructed this session's declared state exactly, then ran the plan against it -- the counts above are from that run
  NOT checked: whether this is scientifically what you meant
  apply:     copilot_apply p-48caa77c-97ae-432a-924d-68f035a9bcd2
  reject:    copilot_reject p-48caa77c-97ae-432a-924d-68f035a9bcd2
(9.7 s)
PyMOL> copilot_apply p-48caa77c-97ae-432a-924d-68f035a9bcd2
copilot_apply: plan p-48caa77c-97ae-432a-924d-68f035a9bcd2 failed and the complete session was restored cleanly.
(1.0 s)
REHEARSAL: passed
```
