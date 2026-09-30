# Integrated TaskSuccess: the model paired with the runtime

**What this is:** master plan item 19's measurement: *"Measure integrated
TaskSuccess against the offline number and explain any gap rather than
averaging it away."*

**What was measured:** the 68 `test_gold` samples, run through the
running product against the fine-tuned model. For each sample:

1. its structure is rebuilt in live headless PyMOL;
2. `copilot <intent>` is typed at PyMOL's command line;
3. the real client sends it to the production server, which is started
   as its own process with
   `pmc_server.main --config configs/evaluation/finetuned.json`;
4. the preview is approved with `copilot_apply`;
5. the live session is graded with the offline evaluation's own grader.

**How it was run:** at commit `5b184a8`, on 2026-09-30, on Martin's
WSL2 machine with the RTX 4060, with his consent. Each sample was
paired with its own published offline record
([docs/evaluation/finetuned/](../evaluation/finetuned/REPORT.md)). The
generated comparison, per category and per shape, is
[REPORT.md](REPORT.md).

## Result

| Condition | Offline TaskSuccess | Integrated TaskSuccess | Discordant samples | Exact McNemar p |
| --- | --- | --- | --- | --- |
| grammar | 32/68 (47.1%, 35.7-58.8%) | **33/68** (48.5%, 37.1-60.2%) | 1: gold_044, integrated only | 1 |
| no-grammar | 19/68 (27.9%, 18.7-39.6%) | **19/68** (27.9%, 18.7-39.6%) | 0 | 1 |

**The integrated number is the offline number, up to one sample.**

- Under the grammar, every sample reached a preview and was applied.
- Without the grammar, 25 reached a preview and 43 came back with no
  plan. Those 43 are exactly the samples the offline run could not
  execute either: 41 whose every attempt was syntax-invalid, and 2
  screened as hostile.
- No sample was refused approval, failed to apply, or timed out.

## The gap, and what explains it

**The runtime path adds nothing.** Before any model was involved, the
reference run ([reference/](reference/README.md)) put every gold
sample's own plan through the same path. It proved three things:

- **68/68 succeed** under both conditions, so the live grader and the
  apply path are right;
- **every first prompt is byte for byte the offline one**, 136 of 136;
- **the grammar reaches the engine** under the grammar condition, and
  only there.

The model run confirms this: all 136 first prompts have the offline
prompt's SHA-256, and no rebuilt structure differed from the recorded
one.

**What differs is the engine.**

- **How often:** for 8 samples with the grammar and 11 without, the
  model wrote a different completion to an identical prompt.
- **What changed:**
  - mostly a near tie: the arbitrary number in a selection's name
    (`copilot_sel0244` against `copilot_sel0249`), or a synonym;
  - two are substantive:
    - gold_001 added a second command (`color magenta, name ZN`);
    - gold_044 wrote `name CA` where offline wrote `name C`.
- **Effect on grades:** only gold_044 changed, and in the integrated
  run's favour. The report classifies it as `engine_drift`, the first
  place the two runs part.

**The engine's answer depends on its history, not on the prompt alone.**
Both runs sent the same prompts in the same order at temperature 0.

`drift_probe.json` records a diagnostic, run with Martin's consent,
that asked why. It sent gold_001's and gold_044's prompts after four
different preceding prompts, each sequence twice:

- **gold_001:** every time the live completion, including after the
  offline run's own first request (the preflight's longest prompt).
  The offline completion was not reproduced.
- **gold_044:** after the same predecessor, the first time `name CA`
  (the live answer) and the second time `name C` (the offline one).
  After every other predecessor, `name C`.

So on this engine, the completion is not a function of the prompt, nor
of the prompt and the request before it. It depends on the engine's
longer history since the model was loaded. llama-server keeps a cache
of earlier prompts and reuses their prefixes. That changes how a
prompt's tokens are batched, and so the floating-point sums a near tie
turns on. This is our reading; the probe shows the dependence, not its
mechanism.

The offline determinism check, rerunning both gold runs with the same
completions ([configs/evaluation/README.md](../../configs/evaluation/README.md)),
replayed the same history in the same order, and is consistent with
this.

## What it means

- **Integrated TaskSuccess is 33/68 with the grammar and 19/68
  without.** The server serves grammar-on by default.
- **The difference from offline is within the engine's own variation:**
  - 1 of 136 grades changed, McNemar p = 1;
  - 8 and 11 of 68 completions changed with the grammar and without it;
  - none of it came from the runtime path.
- **The recorded runs are still reproducible.** The trace of every
  completion is committed beside each run (`trace.jsonl`), so any
  single outcome can be checked against what the model actually wrote.
- **Not done here:** making the engine history-independent, for
  example by disabling prompt-cache reuse per request. That would
  change the evaluated configuration, and would need both the offline
  and the integrated runs repeated.

## Files

- `test_gold/<condition>/`:
  - `samples.jsonl`: one record per sample, with its outcome, live
    grade, the server's trace lines for it, the client's console output
    and timings;
  - `run.json`: the commit, config hash, server command and health;
  - `trace.jsonl`: every completion call, with its raw text and prompt
    hash (the prompt itself is not stored).
- `report.json` and `REPORT.md`: the comparison, as
  `bazel run //tests/integrated:integrated_cli -- report` writes it.
  `//tests/integrated:integrated_record` recomputes both from the
  records, and holds every discordant sample to an explanation.
- `drift_probe.json`: the engine-history diagnostic above.
- `reference/`: the reference run that proves the live grader.
- `e2e_real_engine.md`: the end-to-end scenarios against the model.
