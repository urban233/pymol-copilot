# Integration (master plan item 19)

## Context

Item 19 is the last item in [docs/master_plan.md](../docs/master_plan.md). It is
owned jointly and sized at about 3 days. Its prerequisites 12 and 17 are done,
and item 18 merged as PR #60, although the master plan on `main` still lists 18
as "in progress". The intent:

```
Pair one trained model artifact with the runtime and run the end-to-end
suite against it. Measure integrated TaskSuccess against the offline number
and explain any gap rather than averaging it away. Then dry-run the demo:
one intent through apply, one deliberate failure through recovery, with the
other developer watching to check they can tell what's about to change
before apply is confirmed.
```

### Where the repository stands

**The end-to-end suite never runs a real model.**
- Every scenario in `tests/e2e/` uses a scripted `FakeEngine`, built in
  `scenario_support.build_lifecycle` (`tests/e2e/scenario_support.py:379`).
- Item 12's plan promised an opt-in real-Lemonade target (plans/12:205-212).
  It was never built.

**The offline harness and the runtime share one request graph, but differ
elsewhere.** Both use `pmc_agent.graph.build_request_graph`. The offline
harness (`pmc_eval.runner`) adds several things the runtime lacks:
- the training prompt;
- the grammar;
- `max_tokens` 256 and a 600 s deadline;
- a 16384 context;
- a check of the chat-template date (`llamacpp_args`);
- a final newline appended to the completion (`runner.py:261-273`).

On the runtime side, `pmc_server.main` gained flags for all of these in item
18, but its defaults are still the untuned model with a 4096 context, the
placeholder prompt and no grammar. The runtime graph passes the raw completion
text to `parse_pml` (`graph.py:886`), which rejects text without a final
newline (`parser.py:285`). For the fine-tuned model, the offline harness never
had to append that newline (0 of 220 attempts), so the offline figures don't
depend on it.

**Nothing grades gold samples through the live path** (server, client and
live PyMOL). The pieces exist:
- the notebook rebuilds a gold structure in headless PyMOL with
  `pmc_core.snapshot.reconstruct`;
- `connect_from_handoff` accepts any `cmd` object;
- a gold sample is graded on its resulting fingerprint
  (`sha256(to_json(extract(...)))`, `pmc_sidecar/child.py:292`), its
  selection counts and whether every command succeeded.

**There is no demo script** (the specification's V1 scope, SPECIFICATION.md
L208-210). Nothing in the product can inject a failure. The e2e suite's
`FailColorProxy` (`scenario_support.py:334`) wraps real PyMOL and raises from
`color`.

**LangGraph warns about unregistered types.** It logs "Deserializing
unregistered type" because `InMemorySaver()` uses the permissive default
serializer (`session.py:215`, `runner.py`). langgraph-checkpoint 4.2.0 accepts
`JsonPlusSerializer(allowed_msgpack_modules=[...])`, and the warning shows up
under `LANGGRAPH_STRICT_MSGPACK=true`.

**What the specification requires:**
- **Recovery fidelity (L158):** a failed apply restores the pre-apply
  session, and rollback restores the same snapshot.
- **Presentation clarity (L159):** "a watcher can tell what is about to
  change before apply is confirmed", checked in an informal joint dry run.
- **Demo-ready (L793):** the failure-then-recovery beat has been dry-run at
  least once.
- **Train/serve skew (L624, L839):** it blocks pairing the model with the
  runtime. The integrated-agent comparison is what reveals it.

### Decisions (settled with Martin)

1. **Integrated TaskSuccess is measured under both conditions:** grammar and
   no-grammar, all 68 `test_gold` samples each. Each sample is paired with
   its own offline result (32/68 and 19/68).
2. **The server reads the evaluation config.** `--config
   configs/evaluation/finetuned.json` sets the engine and generation from the
   same file the offline number came from. The defaults move to the training
   prompt, the grammar on and a 16384 context. The placeholder prompt stays
   selectable.
3. **The deliberate failure comes from a demo-only launcher** under
   `tools/demo/`. It wraps PyMOL's `cmd` so that one named verb raises, and
   says so on screen. Nothing is added to `src/`.
4. **The dry-run is delivered as a runbook plus a record.**
   - This item writes `docs/demo.md` and the launcher.
   - It rehearses the demo headless behind a GPU gate.
   - Martin and Hannah do the watched run in GUI PyMOL and report the
     outcome, which this item commits.

### Decisions I took, so you can overrule them

- **The server does not import `pmc_eval`.** A small strict reader,
  `pmc_server/config.py`, reads only the `engine`, `generation` and
  `engine_provenance` fields. A test proves it agrees with
  `pmc_eval.config.load_config` on every committed config.
- **`--config` cannot be mixed with the engine or generation flags.** Mixing
  them is refused at startup, so one run has exactly one source of truth.
  `--prompt` and `--grammar/--no-grammar` stay as flags, because the config
  lists both conditions.
- **The server refuses a mismatched engine under `--config`.** At startup it
  compares what Lemonade reports against the config's model name,
  checkpoint, context, Lemonade version and loaded `llamacpp_args`, which
  include the pinned date. On any mismatch the engine is marked unavailable,
  and `copilot_health` names the field. This is the harness's own check
  (`eval_cli.py:561`). Its helper `_loaded_llamacpp_args` moves into
  `pmc_agent.inference.lemonade` so both callers use it.
- **The newline rule moves into the graph.** A completion missing its final
  newline gets exactly one appended before screening and parsing, the same
  rule as the harness, and a trailing blank line is still rejected. The
  harness keeps its own wrapper, so the committed records are unchanged; with
  both in place, the graph's rule is a no-op offline.
- **The server gets an opt-in trace, `--trace-file PATH`.** Off by default,
  it writes one mode-0600 JSONL line per engine call:
  - the request id and attempt;
  - the prompt's SHA-256 and whether a grammar was sent;
  - the completion text, stop reason and elapsed time.

  The integrated run needs it to explain gaps, because the client sees only
  bounded error envelopes. It fits SPECIFICATION L448: nothing is retained
  unless the user asks for it.
- **The live grader reuses `pmc_eval.grade.grade` unchanged.** It builds a
  `pmc_core` `ExecutionReport` from what the live session shows after
  `copilot_apply`: the fingerprint of `extract(cmd, "pmc_structure")`,
  `cmd.count_atoms` for each of the plan's selections, and each command's
  outcome.
- **The server gets a test-only engine seam.** `serve(..., engine=None)` is
  used only by tests, like `ready=` and `stop=`, so a real-PyMOL test can run
  a scripted engine through the real server.

## Delivery

- **Branch:** `feat/integration` from `origin/main`. Copy this plan to
  `plans/15-integration.md`.
- **Commits:** Conventional Commits, one per step.
- **After every step, the item 18 gate:**
  - `bazel test //... --lockfile_mode=error`
  - `check_dependency_boundaries`
  - ruff check and format
  - pyrefly
- **Checks:** sabotage-check each step's test, and have Sonnet cross-review
  after the runtime steps and before the PR.
- **Review:** this item touches Hannah's `pmc_agent`, `pmc_server` and
  `tests/e2e`, so the PR asks her to review.

**The implementer may edit:**
- `src/pmc_server/**`, `src/pmc_agent/graph.py`, `src/pmc_agent/session.py`
  and `src/pmc_agent/inference/lemonade.py`;
- `src/pmc_eval/eval_cli.py`, only to call the moved helper;
- `src/pmc_eval/runner.py`, only for the checkpointer;
- the new `src/pmc_eval/integrated*.py`;
- `tests/unit/**`, `tests/integration/**`, `tests/e2e/**`, `tests/eval/**`
  and the new `tests/integrated/**`;
- the new `tools/demo/**`, `docs/demo.md` and `docs/integration/**`;
- `docs/development_setup.md`, `docs/latency.md` and `docs/master_plan.md`;
- `plans/15-integration.md`.

**The implementer may not touch:**
- `pmc_core`, `pmc_client`, `pmc_data` or `pmc_train`;
- the committed evidence under `docs/evaluation/**` and `docs/dataset/**`;
- the notebook.

If any of these needs a change, stop and ask.

**Human gates.** Every GPU run is printed first (command, commit, model,
expected time, what it writes) and runs only after its own explicit yes:

- **Gate A:** the real-engine e2e run (Step 7), a few minutes.
- **Gate B:** the integrated measurement (Step 8), both conditions, about 30–45 min.
- **Gate C:** the headless demo rehearsal (Step 10), a few minutes.

---

## Step 1 — Master plan: item 18 done

- Mark item 18 **done — PR #60** in the table, the graph and the "State as
  of" line.
- Set item 19 to **in progress — `feat/integration`**.

**Test:** the gate.

## Step 2 — The checkpoint allowlist

- Add `pmc_agent.graph.new_checkpointer()`. It returns
  `InMemorySaver(serde=JsonPlusSerializer(allowed_msgpack_modules=[...]))`,
  listing every `pmc_core` class that `RequestState` stores.
- `session.py` and `pmc_eval/runner.py` both use it.

**Test:** `tests/unit/test_graph_checkpointer.py`, with
`LANGGRAPH_STRICT_MSGPACK=true` and a fake engine, drives a request through
`pending_approval` and a resume. It asserts:
- the state round-trips;
- no "unregistered type" warning is logged.

Sabotage: drop one class from the list, and the test must fail.
`//tests/eval:committed_baseline` must still pass unchanged.

## Step 3 — Newline normalization in the graph

In `_generating`, a `CompletionResult` whose text lacks a final `"\n"` gets
exactly one appended. Nothing else changes.

**Tests:** in `tests/unit/test_request_graph_repair.py`:
- `"color red, chain A"` with no newline previews;
- `"color red, chain A\n\n"` is still rejected as `alternate_whitespace`;
- `ask:` and empty-completion classification are unchanged.

The committed-baseline and fine-tuned record tests must pass unchanged.

## Step 4 — The server reads the evaluation config

1. Add `pmc_server/config.py`, with `load_runtime_config(path) ->
   RuntimeConfig(engine: EngineOptions, generation, provenance)`. It is
   strict: an unknown or missing field fails.
2. `EngineOptions` gains `base_url` and `connect_timeout_seconds`.
3. `main.py`:
   - adds `--config`;
   - refuses `--config` together with any engine or generation flag;
   - changes `--grammar` to `BooleanOptionalAction`, default on;
   - changes the `--prompt` default to `training`;
   - changes the `--context-size` default to 16384;
   - leaves the model and checkpoint defaults as they are (no
     machine-specific path);
   - raises the `--max-tokens`, deadline and read-timeout defaults to the
     config's 256 / 600 / 600.
4. Move `_loaded_llamacpp_args` from `eval_cli.py` to
   `pmc_agent.inference.lemonade.loaded_llamacpp_args`.
5. Under `--config`, `build_engine` compares the engine's capabilities and
   loaded `llamacpp_args` against the config. On a mismatch it returns
   `UnavailableEngine`, with a message naming the field and both values.
6. Update `docs/development_setup.md` to use
   `bazel run //src/pmc_server:server -- --config configs/evaluation/finetuned.json`.

**Tests:**
- `tests/unit/test_server_entrypoint.py`, with a hermetic httpx client:
  - the new defaults reach the session;
  - `--config` reaches the probe's load request and the session;
  - mixing flags is refused;
  - each mismatched field (a wrong date in `llamacpp_args`, a wrong
    checkpoint, a wrong context) gives unavailable, and `copilot_health`
    names the field;
  - `--no-grammar` sends no grammar.
- `tests/unit/test_server_config_parity.py`: for every file in
  `configs/evaluation/*.json`, `load_runtime_config` agrees with
  `pmc_eval.config.load_config` field by field.
- `//tests/eval:eval_cli` passes, using the moved helper.

## Step 5 — The opt-in trace

1. Add `--trace-file PATH`. `serve` wraps the engine in
   `pmc_server.trace.TracingEngine`.
2. The trace file is created with mode 0600 and appended one line per
   `complete` call. It is off by default.
3. Add `serve(..., engine=None)`, the test-only seam.

**Test:** `tests/unit/test_server_trace.py` checks:
- no file is created by default;
- with the flag, one line per attempt (a repair gives two), mode 0600;
- the prompt SHA-256 matches `build_training_prompt`;
- the recorded text is the engine's raw text, before the newline rule.

## Step 6 — The live grader and the integrated runner

Add `src/pmc_eval/integrated.py` (library) and
`src/pmc_eval/integrated_cli.py` (a `py_binary`). The binary's deps are
`pmc_eval`, `pmc_client`, `pmc_server`, `pmc_sidecar` and the PyMOL wheel;
the library keeps `pmc_eval`'s visibility.

**Per sample:**
1. `cmd.reinitialize()`, then `reconstruct` the sample's structure.
2. Assert that the live `extract` has the sample's `snapshot_sha256`. The
   client then sends the same snapshot, so the prompt is byte-identical to
   the offline one; a mismatch is recorded as `prompt_skew`.
3. Run `copilot <intent>` through a synchronous console driver, as in the
   notebook. The client's timeout stays at its default.
4. For a preview, run `copilot_apply <id>`. Then grade it live, as above.
5. For an `ask:` response, a failure or a refused apply, record the outcome
   and its bounded message.

The run starts **one** real `pmc_server.main` subprocess per condition,
with `--config`, `--trace-file` and `--grammar` or `--no-grammar`. Recovery
points go to a scratch store.

**Output:** `docs/integration/test_gold/<condition>/`, containing:
- `samples.jsonl`: outcome, grade, the plan's canonical text, the trace
  lines, and the preview and apply timings;
- `run.json`: commit, config SHA-256, engine capabilities, host.

It supports `--resume` and `--samples`.

**Tests:**
- `tests/integrated/test_live_grade.py` (hermetic): `ExecutionReport`s built
  from given live readings grade as the offline `grade` does, including a
  wrong count and a failed command.
- `tests/integrated/test_reference_live_real_pymol.py` (real PyMOL, CPU, no
  model):
  - the real server, through the Step 5 seam, is given a scripted engine
    that returns each sample's reference `plan_pml`;
  - a stratified subset (one sample per structure spec and per assertion
    kind) must all be TaskSuccess through the live path;
  - sabotage: a scripted engine that is off by one atom must fail.
- **By hand, no GPU, committed:** the same reference run over all 68
  samples, `docs/integration/reference/`. It must give 68/68, proving the
  live grader before any model is involved.

## Step 7 — The e2e suite against the model (Gate A)

Add `tests/e2e/test_real_engine.py`, the target `//tests/e2e:real_engine`.
Following `lemonade_real`, it is tagged `external`, has
`env_inherit = ["PMC_LEMONADE_BASE_URL"]` and a longer invocation deadline.
It skips when the variable is unset, so CI stays scripted.

It starts `pmc_server.main --config configs/evaluation/finetuned.json` and
connects through `connect_from_handoff`, on gold_056's structure and intent.
The scenarios check structure, not exact text:
- **Preview:** nothing is changed.
- **Apply:** the live fingerprint equals the sample's expected one, and the
  recovery `.pse` has mode 0600.
- **Rollback:** restores the pre-apply digest.
- **Mid-apply failure:** runs through a `FailColorProxy` `cmd` and is
  restored cleanly.
- **Drift:** a change between preview and apply is refused.

Scenarios 4 (denied), 5 (server unavailable) and the hostile completion stay
scripted only, because a real model cannot be made to produce their inputs.
The test's docstring says so.

**Gate A:** after a yes, bring the engine up with the fine-tuned config
(`setup.sh cuda --config configs/evaluation/finetuned.json`) and run
`PMC_LEMONADE_BASE_URL=http://127.0.0.1:13305 bazel test //tests/e2e:real_engine`.
Commit the test log summary under `docs/integration/e2e_real_engine.md`.

## Step 8 — Integrated TaskSuccess (Gate B)

After a yes, run:
`bazel run //src/pmc_eval:integrated_cli -- --config configs/evaluation/finetuned.json --conditions grammar,no-grammar`.

Then write `docs/integration/REPORT.md`, generated by the CLI's `report`
subcommand:
- integrated vs offline TaskSuccess per condition, with Wilson intervals;
- a paired exact McNemar test (`pmc_eval.metrics`) on the same 68 samples;
- per-category and per-shape breakouts beside the offline ones;
- **every discordant sample, with its explanation.** Where the evidence
  decides it, the explanation is classified automatically:
  - `prompt_skew` (the snapshot SHA-256 differs);
  - `engine_drift` (same prompt SHA-256, different completion);
  - `intent_transport` (PyMOL's command line changed the intent, for
    example the apostrophes in gold_031/043/044);
  - `fidelity_not_exact` (apply was refused);
  - `apply_vs_sidecar` (the live fingerprint differs from the sidecar's);
  - `timeout`.
  Anything left over is investigated and explained by hand, never averaged.
- live latency: preview and apply p50/p90.

`docs/latency.md` gets a pointer to it, replacing "generate not measured".

**Test:** `tests/integrated/test_integrated_record.py` (Bazel) recomputes:
- every figure in REPORT.md from the committed `samples.jsonl`;
- the pairing against `docs/evaluation/finetuned`'s records.

It also checks that every discordant sample has an explanation.

## Step 9 — The demo launcher and runbook

`tools/demo/copilot_demo.py`, run as `bazel run //tools/demo:demo`, launches
GUI PyMOL with `pymol.finish_launching()`, then:
- rebuilds the demo structure (gold_056's `two_chains_hetatm`);
- connects through `connect_from_handoff`.

With `--fail-on color`, it wraps `cmd` in a proxy that raises from that verb
and prints a banner: "DEMO: the next `color` will fail on purpose." It has no
effect without the flag. `--headless` runs the same script through the
console driver, for Gate C.

`docs/demo.md` is the 20-minute runbook:
- **Setup:** engine up, the setup check reads `gpu`, server with `--config`,
  `copilot_health` shows the fine-tuned model and all contracts match.
- **Beat 1:** one intent through preview, a pause for the watcher, then
  `copilot_apply`, then `copilot_rollback`.
- **Beat 2:** with `--fail-on color`, an intent whose plan colours goes
  through preview and `copilot_apply`, fails, and is restored cleanly.
- **What the preview shows** (SPECIFICATION L503-511), and what to say at
  each point.
- **Recovery if something goes wrong on stage:** the development setup's
  manual `.pse` runbook.
- **The dry-run record template:** date, machine, who watched, and for each
  beat "could the watcher tell what was about to change before apply?"
  (yes/no, what they said), plus any issue found.

**Tests:** `tests/demo/test_demo_launcher.py` (real PyMOL, headless,
scripted engine through the seam) checks:
- without the flag, apply succeeds;
- with `--fail-on color`, apply is restored cleanly and the banner was
  printed;
- the proxy never wraps anything other than the named verb.

**Risk check first:** GUI PyMOL from the wheel under WSLg. If
`finish_launching()` with a window fails, stop and ask. The fallback is
running the headless demo in a terminal.

## Step 10 — Headless rehearsal (Gate C) and hand-over

1. After a yes, run `bazel run //tools/demo:demo -- --headless` both
   without and with `--fail-on color` against the fine-tuned engine. Commit
   the transcript to `docs/integration/demo_rehearsal.md`.
2. Hand over to Martin and Hannah for the watched GUI dry run.
3. When they report back, fill in `docs/demo.md`'s record and commit it.
4. Master plan: item 19 **done** with its PR, the "State as of" line, and a
   Progress section:
   - integrated vs offline;
   - the gaps and their explanations;
   - the e2e real-engine result;
   - the dry-run outcome.

**Test:** the gate is green.

---

## Verification (end to end)

```
git switch -c feat/integration origin/main
bazel test //... --lockfile_mode=error            # CI: real-engine tests skip
bazel run //src/pmc_eval:integrated_cli -- --reference --out docs/integration/reference   # CPU, 68/68
# Gate A: PMC_LEMONADE_BASE_URL=http://127.0.0.1:13305 bazel test //tests/e2e:real_engine
# Gate B: bazel run //src/pmc_eval:integrated_cli -- --config configs/evaluation/finetuned.json --conditions grammar,no-grammar
# Gate C: bazel run //tools/demo:demo -- --headless [--fail-on color]
```

**Acceptance:**
1. `pmc_server --config finetuned.json` serves exactly the offline
   configuration, and refuses a skewed engine.
2. The e2e scenarios that can run against a real model pass against it. The
   ones that can't are named, with the reason.
3. Integrated TaskSuccess is reported next to the offline number for both
   conditions, and every discordant sample is explained.
4. The demo runbook and launcher exist and have been rehearsed. The watched
   dry run is recorded, including the presentation-clarity answer.
5. The LangGraph warning is gone under strict msgpack. With default flags,
   the server runs the training prompt with the grammar.

## Risks

- **The integrated number differs.** That is the point of the item: every
  difference is explained per sample, never smoothed.
- **The client's command line changes an intent** (apostrophes, commas). If
  that happens, it is reported as a real integration loss. Fixing it would
  touch `pmc_client`, so stop and ask.
- **GUI PyMOL under WSLg** (Step 9): stop and ask if it fails.
- **Runtime length:** 136 samples, each with reconstruct, fidelity sidecar,
  validation sidecar and apply, at about 15 s each, so about 35 min. The run
  supports `--resume`.
