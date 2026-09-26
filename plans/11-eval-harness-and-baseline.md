# Eval harness and untuned baseline

## Context

This is item 16 of [docs/master_plan.md](../docs/master_plan.md). It is Martin's
item, sized at about 3 days of building plus unattended run time. It blocks
items 17 and 18.

Every prerequisite has merged: item 9 (PRs #46 and #48), item 14 (#45) and
item 15 (#53, merged 2026-09-25). The master plan's state table is stale on
items 8 and 9. **Local `main` is behind `origin/main` (`b021d9b`), so branch
from `origin/main`.**

The outcome is one Bazel command that does four things:

- runs a model through the runtime's own request graph (generate, screen,
  parse, policy, sidecar, repair);
- grades every sample against its stored assertions;
- writes the evidence for each sample;
- writes a report broken out by category.

The untuned base model's numbers are committed under
`docs/evaluation/baseline/` before `src/pmc_train/` holds any code. Item 17
compares against that commit.

### What exploration established

- **No grader exists.** Nothing takes a stored sample and an execution report
  and returns pass/fail per assertion. `verifier.py` is pinned to the legacy
  chain-A/red fixture. `SPECIFICATION.md` names TaskSuccess (L643, L701) but
  never defines it.
- **The graph can be driven unchanged.** The engine, prompt builder, executor,
  plan-id source and clock are all injectable into `build_request_graph`
  (`graph.py:1064`). Two things block using it as it stands:
  - its default prompt builder is a placeholder whose bytes differ from
    `Sample.prompt_text`, which is what item 17 trains on;
  - it hard-codes `grammar=None` (`graph.py:630`).

  An engine wrapper can fix the second. An injected builder can fix the first.
- **`parse_pml` requires a trailing newline** (`parser.py:285`). Chat
  completions usually lack one. Without a grammar, a correct plan is rejected
  as `alternate_whitespace`.
- **The screen rejects most prose.** `screen_completion` flags any apostrophe,
  quote, backtick, `/`, `word(`, and whole words such as `set`, `run`, `load`,
  `label` or `create` (`screen.py:77-141`). It runs before parsing, and a
  hostile completion gets no repair.
- **Two rates are zero by construction.**
  - Policy denial: a plan the parser accepts cannot be denied
    (`graph.py:732-739`).
  - Abstention under the grammar: the grammar is `root ::= command+`, so it has
    no way to abstain.
  - In addition, the gold set has no should-abstain items, so any abstention is
    a false one.
- **Prompts are long.** The largest gold prompt is 14,842 characters, an
  estimated 5–7k tokens, which is more than the adapter's
  `DEFAULT_CONTEXT_SIZE = 4096`. Samples on the same spec share their card, and
  the intent comes last. Ordering samples by spec lets llama.cpp's prefix cache
  reuse the card.
- **Grading gaps and structural limits.**
  - Some samples are only partly graded:
    - the 6 gold `orient+select` items have selection counts only;
    - 143 heldout samples carry `unsupported_assertions`.
  - 65 heldout samples predict no change at all (`predicted_no_change`).
  - Neither `pmc_agent` nor `pmc_data` can depend on the other.
  - `results/` and `data/` are gitignored. The committed
    `src/pmc_data/gold/gold_samples.jsonl` is byte-identical to
    `test_gold.jsonl`.

### Decisions (settled with Martin)

1. **Base model: Llama-3.2-1B-Instruct, Q4_K_M GGUF.** Q4_K_M is a standard
   llama.cpp quantization that item 17's Unsloth export can reproduce. It is
   registered in Lemonade as a user model, the same path the tuned model will
   take. **This fixes item 17's base model.**
2. **Two conditions, reported side by side:**
   - `no-grammar`: the spec's ungrammared baseline, and today's runtime;
   - `grammar`: `build_grammar()` sent on every attempt.
3. **TaskSuccess means every stored assertion holds, with selection names
   ignored.** The full definition is under Metrics below.
4. **Both eval sets are committed:**
   - `test_gold` (68 samples) is the headline;
   - `heldout_synthetic` (842 samples) is secondary.

   With two conditions, that makes four runs.
5. **The harness normalizes a missing final newline.** Before the graph sees a
   completion, the harness appends `\n` if the completion does not already end
   with one. This is a no-op under the grammar. The raw completion and a
   `newline_appended` flag are recorded for each attempt. This is a declared
   deviation from the runtime. It is recorded for item 19, and flagged to
   Hannah.
6. **Everything lives in `src/pmc_eval/`, with no edits to `pmc_core` or
   `pmc_agent`.** Two pieces of logic are copied from those packages, and each
   copy is guarded by a drift test:
   - the repair-line wording;
   - the screen's hostile reasons.

### Decisions I took, so you can overrule them

- **The harness drives the compiled request graph**, as the unit tests do, and
  does not reimplement the loop. That makes it match the runtime by
  construction: ask rule, repair budget, message bounds, envelope fallback.
  Three seams are wrapped:
  - **an engine wrapper**: injects the grammar, normalizes the newline, and
    records each request and raw completion;
  - **an executor wrapper**: records each `ExecutionReport`;
  - **a deterministic plan-id source and clock.**
- **The repair prompt is the training prompt plus the graph's own
  failure-line wording, appended after the intent.** This keeps the card
  prefix cacheable. It is versioned by `REPAIR_PROMPT_VERSION`.
- **Bounds.**
  - `max_tokens=256`. The longest reference plan is 4 lines, 164 characters.
  - The graph's deadline and the adapter's read timeout are both 600 s, so they
    never bind on a slow CPU.
  - `context_size=16384`, verified by a preflight.
- **Infrastructure failures are retried, never scored.** A run is finalized
  only when none remain. The one exception: when the executor fails for a
  reason other than a command failure, the harness first runs the sample's own
  reference plan on the same snapshot. If that control run succeeds, the
  failure is attributed to the model and scored as `execution_failed`.
- **Pre-registration.** The primary endpoint is committed before any model
  run: TaskSuccess on `test_gold`, for each condition separately. Item 17
  compares its paired samples with an exact McNemar test. `heldout_synthetic`
  is secondary. The per-category table is descriptive only.
- **Committed evidence lives in `docs/evaluation/baseline/`**, following the
  `docs/dataset/` precedent. Timings go in a separate file, so reruns stay
  byte-identical.

## Metrics

**Outcome classes.** Each sample gets an outcome for attempt 1 and a final
outcome. The classes partition all samples, in the graph's order of checks:

| Outcome | Rule | Repaired? |
| --- | --- | --- |
| `truncated` | `stop_reason != "end"` (the graph's `engine_incomplete`) | no |
| `abstained` | the stripped completion is empty, or is a single line starting with `ask:` | no |
| `denied_hostile` | `screen_completion` is hostile; the reasons are kept | no |
| `syntax_invalid` | `parse_pml` rejects it; the category is kept | yes |
| `denied_policy` | `evaluate_plan` denies it (0 by construction) | yes |
| `execution_failed` | the executor returns `command_failure` (envelope kept), or the control-attributed failure above | yes / no |
| `executed_wrong` | the executor returns `ok`, but an assertion fails | no |
| `success` | the executor returns `ok`, and every assertion holds | no |

**TaskSuccess** means the final outcome is `success`. Three conditions must all
hold:

- **`resulting_snapshot`**: the resulting fingerprint equals the stored detail.
- **`selection_counts`**: the sorted multiset of atom counts is equal, with
  names ignored.
- **`commands_succeeded`**: every command outcome is `ok`. The model's command
  count is not compared with the reference's.

Each sample also carries two flags:

- `grading_complete`: false for counts-only samples, or when there are
  unsupported assertions;
- `vacuous`: set when `predicted_no_change` holds.

TaskSuccess is reported three ways: over all samples, over the fully graded
samples, and over the non-vacuous samples. TaskSuccess on attempt 1 is also
reported.

**The other rates:**

- **Syntax-valid:** the share of attempt-1 completions that `parse_pml`
  accepts after the newline normalization. It is parsed regardless of the
  screen, as a diagnostic (spec L161).
- **Policy-denied:** the share of attempt-1 completions refused before any
  sidecar run. It is split into hostile (with a reason breakdown) and policy.
  The policy part is shown as "n/a (0 by construction)".
- **Empty-selection:** among final plans that executed `ok`, the share where
  some target resolves to 0 atoms.
  - Named selections are taken from the executor's counts.
  - Inline expressions are counted with `pmc_data.oracle.selected_serials`.
  - A target with an unsupported term is counted as `unknown`.
- **Abstention:** the share of samples whose outcome is `abstained`.
  - Every eval item is answerable, so this is a false-abstention rate.
  - Under the grammar it is "n/a (0 by construction)".
- **Repair success:** among samples whose attempt 1 failed in a repairable way,
  the share whose final attempt executed `ok`, and the share that reach
  TaskSuccess. Mean attempts are reported too.
- **Also reported:** the newline-appended count, and p50 engine and sidecar
  latency.

**Breakouts.** Every rate is broken out by verb set, term, shape, difficulty
and spec, each with a Wilson 95% interval (`pmc_data.audit.wilson_interval`).
The full category table is included too, but it holds only 1–2 items per
category.

## Delivery

Create branch `feat/eval-harness-baseline` from `origin/main`. First copy this
plan to `plans/11-eval-harness-and-baseline.md`; number 10 is taken by
PR #55. Use Conventional Commits, one per step. After every step, run this
gate:

```
bazel test //... --lockfile_mode=error
bazel run //tools/bazel:check_dependency_boundaries --lockfile_mode=error
bazel run //tools/quality:ruff --lockfile_mode=error -- check .
bazel run //tools/quality:ruff --lockfile_mode=error -- format --check .
bazel run //tools/quality:pyrefly --lockfile_mode=error -- check
```

Each step's test must also pass a sabotage check: break what the test covers,
confirm that exactly that test fails, then restore. Code follows the house
style: copyright header, `__future__` import with its `noqa`, Google
docstrings, one import per line, and 80 columns.

**The implementer may edit:**

- `src/pmc_eval/**`, `tests/eval/**`, `configs/evaluation/**` and
  `docs/evaluation/**`;
- visibility lines only in `src/pmc_data/BUILD.bazel`,
  `docs/dataset/BUILD.bazel` and `tests/adversarial/BUILD.bazel`;
- `tests/integration/test_subsystem_imports.py`;
- `pyproject.toml`, `.github/CODEOWNERS` and `.gitattributes`;
- `results/README.md`, `docs/master_plan.md` and
  `plans/11-eval-harness-and-baseline.md`.

**Not** `src/pmc_core/**` or `src/pmc_agent/**`.

**Human gates** are in Step 9 only. The session sets up Lemonade itself, and
stops if setup fails or if the chat template stamps a date.

---

## Step 1 — Package skeleton and visibility

1. Add `src/pmc_eval/{__init__.py,BUILD.bazel}`. The `py_library` depends on:
   - `pmc_core`;
   - `pmc_agent` and `pmc_agent/inference`;
   - `pmc_data`.

   It does **not** depend on `pmc_sidecar`. That goes only on the binary and on
   the real-PyMOL test, as with `corpus_cli`.
2. Widen visibility, adding a comment each time:
   - `pmc_data`, to `//src/pmc_eval:__pkg__`;
   - the `docs/dataset` filegroup and `denied_forms_corpus`, to
     `//tests/eval:__pkg__`.
3. Add `src/pmc_eval` to pyrefly's `project-includes`.
4. Add `/src/pmc_eval/ @urban233` to CODEOWNERS.
5. Add `tests/eval/{BUILD.bazel,README.md}`.
6. Add `pmc_eval` to `test_subsystem_imports`.

**Touches:** those files.

**Test:** `test_subsystem_imports` passes, and the boundary checker passes.
**Sabotage:** give `pmc_agent` a dependency on `pmc_eval`. The checker must
fail, because `pmc_data` then enters `pmc_agent`'s closure.

## Step 2 — Contract prompt

Add `pmc_eval/prompt.py`:

- `REPAIR_PROMPT_VERSION = 1`.
- `contract_prompt(inputs: PromptInputs) -> str`. This is
  `build_for_runtime(inputs.snapshot, inputs.intent).text()` followed by one
  line per `AttemptFailure`. It is compatible with `PROMPT_BUILDER`, so it can
  be injected into the graph, and item 19 can reuse it.
- `snapshot_for(sample)`. It rebuilds the structure from
  `sample.structure.spec` and raises if `snapshot_sha256` or
  `structure_digest` does not match.

**Touches:** `src/pmc_eval/prompt.py`, the BUILD files,
`tests/eval/test_prompt.py`.

**Test:** `test_prompt.py`, three tests:

- `test_first_attempt_prompt_is_the_training_prompt`. For each of the 68
  committed gold samples, rebuild the snapshot, **round-trip it through
  `to_json` and `from_json`** (the graph's path), and check that the prompt
  equals `prompt_text` byte for byte.
- `test_repair_lines_match_the_graphs_wording`. This is the drift guard: the
  lines must equal the lines `pmc_agent.prompt.build_default_prompt` renders
  for the same failures.
- `test_repair_lines_follow_the_intent_and_keep_the_prefix` and
  `test_broken_lineage_is_refused`.

## Step 3 — Hostile reasons

Add `pmc_eval/screen_reasons.py` with
`hostile_reasons(text) -> tuple[str, ...]`. The possible reasons are
`character:'`, `call_form`, `verb:set`, `if_else` and `lambda`. It is a
harness-side copy of the rules in `screen.py`, and it is diagnostic only.

**Touches:** `src/pmc_eval/screen_reasons.py`, the BUILD files,
`tests/eval/test_screen_reasons.py`.

**Test:** `test_reasons_agree_with_the_screen`. The result must be non-empty
exactly when `screen_completion` returns hostile. The check runs over
`denied_forms` plus a small local corpus of prose, fenced output and legal
plans. That is the drift guard.

## Step 4 — Graph-driven sample runner

Add `pmc_eval/runner.py`:

- **`Condition(name, grammar, max_tokens, deadline_seconds)`.**
- **`RecordingEngine(inner, grammar_text | None)`.** It sets `grammar` on every
  request and appends `\n` when the completion does not end with one. It keeps
  the requests, the raw completions and the `newline_appended` flags.
- **`RecordingExecutor(inner)`.** It records each report.
- **`request_state_for(sample)`.** It builds the `RequestState`, with snapshot
  identity and fidelity built as in `pmc_client/command.py:366-381` and
  `CURRENT_CONTRACT_MANIFEST`.
- **`run_sample(sample, *, engine, condition, executor=execute) -> SampleOutcome | InfraFailure`.**
  1. It refuses a sample whose `versions` differ from the current contract
     constants or from the PyMOL wheel.
  2. It compiles the graph with `InMemorySaver`, with
     `prompt_builder=contract_prompt` and deterministic plan-id and clock
     sources.
  3. It invokes the graph and maps the terminal state to an outcome.
  4. It runs the control rule for failures other than command failures.

  Grading plugs in at Step 5.

**Touches:** `src/pmc_eval/runner.py`, the BUILD files,
`tests/eval/{fakes.py,test_runner.py}`. `fakes.py` holds scripted executors in
the style of `tests/data/oracle_executor.py`.

**Test:** `test_runner.py`, using `FakeEngine` and fake executors:

- `test_wrappers_are_transparent`. The grammar is off and completions already
  end in a newline. The graph with the wrappers and the graph without them
  must give the same final state and the same engine calls.
- One test per outcome row, reached through the real graph.
- `test_grammar_is_sent_only_under_the_grammar_condition`.
- `test_newline_is_appended_only_when_missing_and_raw_is_kept`.
- `test_repairs_stop_after_two`.
- `test_engine_failure_is_infrastructure`.
- `test_control_run_attributes_a_plan_induced_crash_to_the_model`.
- `test_version_drift_is_refused`.

## Step 5 — Grading

Add `pmc_eval/grade.py` with `grade(sample, report, plan, snapshot) -> Grade`.
It returns:

- a pass/fail for each assertion;
- `task_success`;
- `grading_complete`;
- `vacuous`;
- `empty_selection`, which is true, false or unknown.

The TaskSuccess definition goes in the docstring, word for word.

**Touches:** `src/pmc_eval/grade.py`, the BUILD files,
`tests/eval/test_grade.py`.

**Test:** `test_grade.py`:

- `test_wrong_fingerprint_fails`
- `test_renamed_selection_passes`
- `test_extra_selection_fails`
- `test_command_count_is_not_compared`
- `test_counts_only_sample_is_flagged_incomplete`
- `test_no_change_sample_is_flagged_vacuous`
- `test_inline_empty_target_is_an_empty_selection`
- `test_polymer_target_is_unknown_not_empty`

## Step 6 — Aggregation and report

Add `pmc_eval/metrics.py`:

- **`aggregate(outcomes) -> Report`.** It computes every metric and breakout
  listed under Metrics above. It takes the category parts from
  `pmc_data.taxonomy`. Where a rate is zero by construction, it reports
  "n/a (0 by construction)".
- **`render_markdown(reports)`.** It renders one table per set, with
  `no-grammar` and `grammar` side by side.

Write JSON the way `manifest.write_json` does, and JSONL the way
`sample.write_samples` does.

**Touches:** `src/pmc_eval/metrics.py`, the BUILD files,
`tests/eval/test_metrics.py`.

**Test:** `test_metrics.py`:

- `test_outcomes_partition_the_samples`
- `test_rates_on_a_hand_computed_fixture`
- `test_wilson_matches_the_audit_helper`
- `test_repair_denominator_is_repairable_first_failures_only`
- `test_zero_by_construction_rates_render_na`
- `test_subsets_exclude_incomplete_and_vacuous`

## Step 7 — CLI, config, pre-registration

**Config.** Add `configs/evaluation/baseline.json`. It holds:

- `base_url`;
- `model_name: user.Llama-3.2-1B-Instruct-Q4_K_M` and the checkpoint;
- `backend: cpu`, `context_size: 16384` and the timeouts;
- `max_tokens`;
- the two conditions and the two sets;
- an `engine_provenance` block, which the operator fills in at Step 9: GGUF
  sha256, Hugging Face revision, Lemonade version, llama.cpp build, image
  digest, host architecture and emulation.

**Pre-registration.** Add `docs/evaluation/PREREGISTRATION.md`, stating the
primary endpoint described above.

**CLI.** Add `pmc_eval/eval_cli.py`, following the structure of `split_cli.py`.

- **The `run` subcommand** takes `--config`, `--split`, `--set` and
  `--condition`, plus an optional `--resume`.
  - It **refuses** any of these:
    - a dirty tree;
    - `validate_manifest` failing;
    - a `split_id` that is not the one in `docs/dataset/manifest.json`;
    - a failed engine probe;
    - a `model_identity` that does not match the config;
    - a Lemonade version that differs from the provenance block;
    - a failed context preflight (the longest prompt in the set, sent with
      `max_tokens=1`).
  - It runs samples one after another, ordered by `(spec_id, sample_id)`.
  - It checkpoints into `results/.eval-<id>.partial/`.
  - It retries infrastructure failures up to 2 times.
  - It finalizes to `results/eval-<id>/{run.json,samples.jsonl,report.json}`
    plus `timings.jsonl` (per-attempt timings and PIDs). Only `timings.jsonl`
    holds them, and it is outside the id.
  - `<id>` is a sha256 over these inputs:
    - the harness, grader and repair-prompt versions and the normalization rule;
    - the config sha;
    - the `split_id`, the set's file sha and the condition;
    - the model identity, the engine capabilities and the provenance block;
    - `current_versions()` and the grammar sha;
    - `PINNED_PYMOL_WHEEL` and the git commit.
- **The `publish` subcommand** copies the runs into
  `docs/evaluation/baseline/`, writes a digest `manifest.json`, and renders
  `BASELINE.md`.

The engine is injected through an `engine_factory` seam. Mark
`docs/evaluation/** -text`.

**Touches:** `src/pmc_eval/eval_cli.py`, `src/pmc_eval/BUILD.bazel` (a
`py_binary` with `//src/pmc_sidecar`), `configs/evaluation/**`,
`docs/evaluation/PREREGISTRATION.md`, `.gitattributes`,
`tests/eval/test_eval_cli.py`.

**Test:** `test_eval_cli.py`, hermetic, with one test per refusal:

- `test_refuses_a_dirty_tree`
- `test_refuses_a_split_that_is_not_the_committed_one`
- `test_refuses_a_model_identity_mismatch`
- `test_refuses_a_failed_context_preflight`
- `test_refuses_to_finalize_with_infrastructure_failures`

It also covers resume and byte-identity:

- `test_resume_skips_finished_samples`
- `test_rerun_is_byte_identical`: `timings.jsonl` is excluded.

## Step 8 — Real-PyMOL grader proof and Lemonade smoke test

**`tests/eval/test_reference_model_real_pymol.py`** uses `FakeEngine` and the
real executor. It carries `size="large"`, `tags=["exclusive"]`, a long timeout
and `//src/pmc_sidecar`. Scripted completions land as follows:

| Scripted completion | Expected result |
| --- | --- |
| each gold sample's own `plan_pml` | `success` on all 68/68 |
| that plan without its trailing newline | normalized, then `success` |
| wrong colour, or an extra selection | `executed_wrong` |
| the `orient` dropped, on counts-only items | passes, but flagged `grading_complete=false` |

**`tests/eval/test_lemonade_real.py`** follows the `lemonade_real` pattern:
`tags=["external"]`, `env_inherit=["PMC_LEMONADE_BASE_URL"]`, and it skips when
the variable is unset. It runs 2 gold samples in each condition and asserts
that the identity fields reach `run.json`.

**Touches:** those files and `tests/eval/BUILD.bazel`.

**Test:** the files themselves. CI stays green on all three operating systems.

## Step 9 — Lemonade setup and pilot (human gate if setup fails)

1. Start Lemonade from `tests/discovery/lemonade/compose.yaml`. Try the arm64
   route if emulation is too slow.
2. Confirm that `unsloth/Llama-3.2-1B-Instruct-GGUF` has a `Q4_K_M` file, and
   register it as `user.Llama-3.2-1B-Instruct-Q4_K_M` with the `llamacpp`
   recipe. Check the exact pull form against the installed version.
3. Fill in `engine_provenance`, then record the launch command's
   parallel-slot (`-np`) and `--jinja` settings.
4. **Check whether the chat template stamps today's date** (Llama 3.2's
   template can, via `strftime_now`). **If it does, stop and ask Martin.** It
   would make prompts change from day to day, and item 17 would have to render
   its training data through the same template.
5. Pilot run:
   - Run `test_gold` in both conditions, twice. Record how many completions
     flip between the two runs (whether prompt caching is deterministic) and
     the wall time per attempt. From that, extrapolate the full four runs.
   - Run the largest prompt at 4096, 8192 and 16384 context. Record which fit.
6. Record the findings in `configs/evaluation/README.md` and freeze the config.

**Test:** `test_lemonade_real` passes with `PMC_LEMONADE_BASE_URL` set.

## Step 10 — Full baseline, publish, commit

1. Run all four runs, resuming as needed.
2. `publish` them.
3. Commit, before any change to `src/pmc_train/`.
4. Add `tests/eval/test_committed_baseline.py`:
   - `test_report_recomputes_from_samples`: the summary can't be hand-edited.
   - `test_stored_completions_reclassify_identically`: re-screen and re-parse
     every stored raw completion with today's code. If screen or parser rules
     drift, this test says the baseline is stale.
   - `test_manifest_digests_hold`.
   - `test_baseline_is_on_the_committed_split`: the `split_id` must equal the
     one in `docs/dataset/manifest.json`.
   - `test_config_hash_matches`.

**Touches:** `docs/evaluation/baseline/**` (generated),
`docs/evaluation/BUILD.bazel` (a filegroup visible to `//tests/eval`),
`tests/eval/test_committed_baseline.py`, `tests/eval/BUILD.bazel`.

**Test:** the tests above.

## Step 11 — Documentation and the master plan

**Files.**

- **`docs/evaluation/README.md`** covers the metric definitions, how to re-run,
  and what item 17 must hold fixed:
  - the same harness identity, sets, conditions, engine and ordering;
  - the tuned GGUF exported as Q4_K_M;
  - training targets ending in `\n`.
- **`results/README.md` and `tests/eval/README.md`.**

**`docs/master_plan.md` changes.**

1. Mark item 16 done, with the PR number.
2. Record the headline TaskSuccess per condition, as numbers with intervals.
3. Refresh the stale states of items 8 and 9.
4. Add notes:
   - **item 17:** the base model is now fixed, and the sequence length has to
     cover the longest prompt;
   - **item 19 / Hannah:** four issues —
     - the runtime's 4096 context does not fit the largest held-out card;
     - the graph's default prompt is not the training prompt, and
       `contract_prompt` is the drop-in replacement;
     - the graph sends no grammar;
     - the parser rejects a missing final newline, which the harness
       normalizes and the runtime does not.

**Test:** the gate is green.

---

## Verification (end to end)

```
git fetch && git switch -c feat/eval-harness-baseline origin/main
bazel test //... --lockfile_mode=error          # plus the gate above
docker compose -f tests/discovery/lemonade/compose.yaml up -d   # + register Q4_K_M
PMC_LEMONADE_BASE_URL=http://localhost:13305 bazel test //tests/eval:lemonade_real --test_output=all
for s in test_gold heldout_synthetic; do for c in no-grammar grammar; do
  bazel run //src/pmc_eval:eval_cli -- run --config configs/evaluation/baseline.json \
    --split data/splits/split-e4599620801af592 --set $s --condition $c --resume
done; done
bazel run //src/pmc_eval:eval_cli -- publish --runs results/eval-* --out docs/evaluation/baseline
```

**Acceptance:**

1. Through the real executor, the reference plans score 68/68, and the
   sabotaged plans land in the outcome class the Step 8 table expects.
2. The first-attempt prompt is byte-identical to `Sample.prompt_text` on the
   graph's JSON round-trip path.
3. With the grammar off and completions already ending in a newline, the
   wrapped graph behaves identically to the bare graph.
4. Four runs with zero infrastructure failures are committed, and each
   report recomputes from its stored samples.
5. The master plan states baseline TaskSuccess per condition, with intervals.
   The pre-registration was committed before the runs.

## Risks

- **CPU throughput under amd64 emulation.**
  - The pilot measures it before the long runs.
  - The levers are the arm64 image and card-prefix cache locality.
- **Nondeterminism at temperature 0**, from llama.cpp prompt caching.
  - The pilot measures the flip count and the report discloses it.
  - Item 17 must use the same engine and ordering.
- **PR #55 edits `graph.py`.**
  - If it merges mid-build, rebase and re-run `test_wrappers_are_transparent`.
  - The harness uses only `build_request_graph` and the terminal state fields.
- **The copied rules can drift.**
  - The repair-line and screen-reason copies are guarded by tests.
  - Grading does not depend on the screen-reason copy.
- **The no-grammar numbers will mostly be `denied_hostile`**, from
  apostrophes, code fences and English words like "set". That is the runtime's
  real behaviour. The report's breakdown shows it for what it is, rather than
  "the model attempted attacks".
- **Weak grading on 6 counts-only gold items and 65 no-change heldout
  samples.** They are flagged, and TaskSuccess is reported with and without
  them.
