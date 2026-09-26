# Pre-registration: the untuned baseline and item 17's comparison

Committed before any model was evaluated (master plan item 16), so the
comparison item 17 makes against this baseline is fixed before either
side's numbers exist. Changing anything here after the baseline runs
is a new pre-registration, and says so.

## Primary endpoint

**TaskSuccess on `test_gold`** (68 hand-reviewed items on held-out
structures), reported separately for each of the two conditions:

- `no-grammar` -- the specification's ungrammared baseline, and what
  the runtime's request graph does today;
- `grammar` -- `pmc_core.grammar.build_grammar()` sent with every
  generation.

The conditions are never pooled. TaskSuccess is defined in
`src/pmc_eval/grade.py` and summarized in [README.md](README.md).

## The comparison item 17 makes

For each condition, the fine-tuned model is compared with this baseline
on the same 68 samples, paired by sample, with an **exact two-sided
McNemar test** on the discordant pairs. The result is reported whatever
it is, including no difference or a worse fine-tune (SPECIFICATION.md,
success measures).

Both sides are run under the same `configs/evaluation/baseline.json`
except for `engine.model_name` and `engine.checkpoint`, with the same
harness, grader and repair-prompt versions, the same engine and the
same sample order. The fine-tuned model is exported as a Q4_K_M GGUF,
like the base model.

## Secondary and descriptive

- TaskSuccess on `heldout_synthetic` (842 templated samples on the same
  held-out structures): a secondary, structure-generalization figure,
  compared the same way.
- TaskSuccess on attempt 1, on the fully graded samples and on the
  non-vacuous samples; syntax-valid, policy-denied, abstention,
  truncation, empty-selection and repair rates: diagnostic.
- Every per-category, per-term, per-shape, per-difficulty and
  per-structure breakout: descriptive only. Most gold categories hold
  one or two items.
