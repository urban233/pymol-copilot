# The live grader's reference run

**What this is:** the integrated measurement (master plan item 19) run
with no model. Every gold sample goes through the running product:

1. its structure is rebuilt in live headless PyMOL;
2. `copilot <intent>` is typed at PyMOL's command line and goes through
   the real client and the real server (`pmc_server.main.serve`);
3. the preview is approved with `copilot_apply`;
4. the live session is graded with the offline evaluation's grader.

The server's engine is scripted to answer each sample's own gold plan.
A correct plan must therefore succeed on every sample. This run proves
the live grader, and the path to it, before any model is measured.

**How it was made:** at commit `4d76a5d`, on Martin's WSL2 machine
(CPU only), with this command:

```
bazel run //tests/integrated:integrated_cli -- run --reference --out docs/integration/reference
```

## What it found

| Condition | TaskSuccess | Live prompt identical to the offline one | Structure skew | Preview p50 | Apply p50 |
| --- | --- | --- | --- | --- | --- |
| grammar | 68/68 | 68/68 | 0 | 7.3 s | 1.0 s |
| no-grammar | 68/68 | 68/68 | 0 | 7.2 s | 1.0 s |

- **The prompt is the offline one.** For every sample, the first
  prompt the server sent has the same SHA-256 as the one the offline
  evaluation sent. The live PyMOL session and the client's extraction
  reproduce the recorded structure exactly, and the server builds the
  training prompt from it byte for byte.
- **The grammar reaches the engine** under the grammar condition only.
  Each trace line records it.
- **The latency is the product's own, without inference.**
  - A preview is about 7 s: the client's fidelity probe plus the
    server's validation sidecar, each a fresh PyMOL process.
  - An apply is about 1 s.

## Files

- `test_gold/<condition>/samples.jsonl`: one record per sample, with its
  outcome, grade, trace lines and timings;
- `test_gold/<condition>/run.json`: the commit, the server and its
  health;
- `test_gold/<condition>/trace.jsonl`: the server's trace of every
  completion call.
