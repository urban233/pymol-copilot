# Offline evaluation

**Purpose:** what the offline evaluation (master plan item 16) measures,
how, and what a later comparison against its baseline must hold fixed.

**Code:** [`src/pmc_eval/`](../../src/pmc_eval/) · **Config:**
[`configs/evaluation/baseline.json`](../../configs/evaluation/baseline.json)
· **Primary endpoint:** [PREREGISTRATION.md](PREREGISTRATION.md) ·
**Baseline:** `baseline/` (published by `eval_cli publish`; not yet run)

## What one sample goes through

Each stored sample of the held-out split is run through the runtime's
own request graph (`pmc_agent.graph`), compiled exactly as the runtime
compiles it, with three seams wrapped:

1. **The prompt** is `pmc_eval.prompt.contract_prompt`: on a first
   attempt, byte for byte the `Sample.prompt_text` item 17 trains on
   (`pmc_core.prompt.build_for_runtime`); on a repair, the same prompt
   followed by one line per earlier failure, worded as the graph words
   them. The graph's own default builder is a placeholder that differs
   from the training prompt.
2. **The engine** receives `pmc_core.grammar.build_grammar()` on every
   attempt under the `grammar` condition, and none under `no-grammar`
   (the runtime graph always sends none). A completion that does not end
   in a newline has one appended before the graph sees it, because
   `pmc_core.parser.parse_pml` requires it and a chat model rarely
   writes it; the raw completion is kept. This is the one declared
   difference from the runtime, and a no-op under the grammar.
3. **The executor** is the real `pmc_core.executor.execute`, a fresh
   PyMOL child per attempt; every report is kept.

Everything else is the graph's: the clarification rule, the hostile
screen, at most two repairs fed the failure evidence, and the bounds on
what is fed back. Each attempt's outcome is read back from the graph's
own state, not re-derived.

## Outcomes

Every attempt, and so every sample, ends in exactly one of these, in
the graph's order of checks:

| Outcome | Rule | Repaired? |
| --- | --- | --- |
| `truncated` | generation stopped before its natural end (token limit) | no |
| `abstained` | the completion is empty, or one line starting `ask:` | no |
| `denied_hostile` | `pmc_core.screen` finds a character, call form or verb the language has no use for | no |
| `syntax_invalid` | `parse_pml` rejects it | yes |
| `denied_policy` | `pmc_core.policy` denies the parsed plan | yes |
| `execution_failed` | a PyMOL command failed in the sidecar | yes |
| `executed_wrong` | the plan ran cleanly, but a stored assertion fails | no |
| `success` | the plan ran cleanly and every stored assertion holds | no |

An engine failure, or a sidecar failure other than a command failure (a
timeout, a crash), is infrastructure and is never scored; a run is not
finalized while any sample is unscored. The one exception is a failure
the model's own plan reproduces in a fresh sidecar while the sample's
reference plan succeeds: that is `execution_failed`.

## Metrics

**TaskSuccess** — the final outcome is `success`: the final plan
executed, and every assertion stored with the sample holds:

- the resulting-state fingerprint equals the stored one;
- the selections matched the same atom counts, as a sorted multiset,
  with selection names ignored (the prompt leaves naming to the model);
- every command the plan contains ran without error. The plan's length
  is not compared with the reference's.

The reference plan is one correct answer, not the only one; grading is
on the resulting state. TaskSuccess is also reported on attempt 1, on
the **fully graded** samples (dropping the six `orient+select` gold
items, graded on selection counts only, and any sample recording an
assertion it could not make) and on the **non-vacuous** samples
(dropping any sample predicting no change, which any no-op plan
passes).

| Metric | Counts | Over |
| --- | --- | --- |
| Syntax-valid | attempt-1 completions `parse_pml` accepts, after the newline normalization, parsed regardless of the screen | all samples |
| Policy-denied | attempt 1 ended `denied_hostile` or `denied_policy`, with the hostile reasons tallied | all samples |
| Abstention | final outcome `abstained` | all samples |
| Truncated | final outcome `truncated` | all samples |
| Empty selection | some target of the final plan matched no atom: named selections from PyMOL's counts, inline expressions from the independent oracle; a `polymer` target is `unknown` | samples whose final plan executed |
| Repair to a valid plan / to TaskSuccess | final plan executed / final outcome `success` | samples the graph repaired at least once |

Every rate is reported with its count, its denominator and a Wilson 95%
interval, overall and by verb set, selection term, expression shape,
difficulty, held-out structure and category. Most gold categories hold
one or two items; their rows are descriptive only.

Two rates are **zero by construction** and reported as such, never as
model behaviour: a policy denial (the parser and the policy enforce the
same allowlist, so a parsed plan is never denied), and an abstention
under the grammar (it has no way to write `ask:` or nothing). No
evaluation sample is ambiguous, so every abstention that does occur is a
false one.

## Running it

```
cd configs/evaluation/engine
docker compose -f compose.yaml -f compose.nvidia.yaml up -d
./setup.sh cuda        # paste its engine_provenance into baseline.json
cd -                   # and commit it
PMC_LEMONADE_BASE_URL=http://localhost:13305 \
    bazel test //tests/eval:lemonade_real --test_output=all
for set in test_gold heldout_synthetic; do
  for condition in no-grammar grammar; do
    bazel run //src/pmc_eval:eval_cli -- run \
        --split data/splits/split-e4599620801af592 \
        --set $set --condition $condition --resume
  done
done
bazel run //src/pmc_eval:eval_cli -- publish --runs results/eval-*
```

The engine variants are in `configs/evaluation/engine/README.md`,
with a step-by-step tutorial for running the whole baseline on WSL2
with an NVIDIA GPU, from installing WSL2 to committing the result.

A run refuses a modified tracked file, a split other than the committed
one, a sample verified under other contract versions, an unfilled
`engine_provenance`, an engine other than the configured model, and a
prompt that does not fit the context. It checkpoints every sample, and
`--resume` continues an interrupted run. `--limit N` runs a pilot of the
first N samples, which `publish` refuses.

## What item 17's comparison must hold fixed

The tuned model is compared with this baseline only when everything but
the weights is the same:

- the same `configs/evaluation/baseline.json`, except `engine.model_name`
  and `engine.checkpoint`;
- the same harness, grader, repair-prompt and report versions (each run
  records them) and the same sets, conditions and sample order;
- the same engine: Lemonade version, llama.cpp build, context size and
  chat template, including how its date is set;
- the tuned model exported as a **Q4_K_M** GGUF, as the base model is;
- training targets ending in a newline, as every `Sample.plan_pml` does.

If any of these must change, run the base model again under the new
setting and compare against that, not against this baseline.
