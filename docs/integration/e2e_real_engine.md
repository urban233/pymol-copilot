# The end-to-end suite against the fine-tuned model

**What this is:** `//tests/e2e:real_engine` (master plan item 19). It
runs the end-to-end scenarios against the trained model artifact
instead of a scripted engine, through the production server started as
a user starts it:

```
python -m pmc_server.main --config configs/evaluation/finetuned.json
```

Real headless PyMOL drives it through the handoff file and the real
client. The intent is gold item `gold_056`, on its own held-out
structure.

**How it was run:** at commit `ac3c277`, on 2026-09-30, on Martin's
WSL2 machine with the RTX 4060, with Martin's consent.

1. The engine was brought up with the same config:
   `configs/evaluation/engine/setup.sh cuda --config configs/evaluation/finetuned.json`
   reported `loaded device = "gpu"`, the pinned chat-template date, and
   the GGUF `6c5c76a0…bdbd`.
2. Then the scenarios ran:
   `PMC_LEMONADE_BASE_URL=http://127.0.0.1:13305 bazel test //tests/e2e:real_engine`.

## Result

**6 passed, in 82 s.**

| Scenario | What it checks | Result |
| --- | --- | --- |
| Health | The server names the evaluated model (`Llama-3.2-1B-Instruct-pmc-train-e6c6c4dd8f6caaf9-Q4_K_M@/models/…`), the engine is ready, and every contract matches the client. The server accepted the engine as the config's (model identity, Lemonade version, llama.cpp arguments). | passed |
| Preview | The model's plan is previewed and approvable, and the live session is unchanged. | passed |
| Apply | The applied state has exactly the gold plan's resulting fingerprint (the offline result), and the recovery point is user-only (0600). | passed |
| Rollback | One-level rollback returns the whole session to its pre-apply state. | passed |
| Mid-apply failure | Through a `color` that fails after the plan's `select` really ran, the client restores the whole session automatically. | passed |
| Drift | A change to the session after the preview refuses the apply, and nothing is applied. | passed |

## What does not run against the model, and why

These scenarios stay scripted, where they are, because no real model
can be made to produce their inputs on demand:

- a denied command (`test_denied_command_real_pymol.py`);
- a hostile completion;
- an unavailable engine (`test_server_unavailable_real_pymol.py`).

The scripted expiry scenario needs an injected clock, which the
production server does not take.

CI runs every scenario scripted. This target skips there, because
`PMC_LEMONADE_BASE_URL` is unset.
