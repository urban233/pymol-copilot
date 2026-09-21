# Generation configuration

This directory is owned by model-data generation.

## `corpus.json`

The standing configuration for the generalized dataset run (master
plan item 14), consumed by `pmc_data.corpus_cli`:

```
bazel run //src/pmc_data:corpus_cli -- --workers 8
```

It declares the `seed` every structure, plan and sample identity
derives from, and the `samples_target` the run is budgeted to.

`samples_target` bounds *attempts*, not kept samples: an attempt the
oracle cannot grade is reported as unsupported rather than kept, so
the corpus that comes out is smaller than the number here.

When the target is below the number of enumerated plans, the subset is
chosen stratified across categories rather than truncated, so a budget
at or above the number of categories never drops one. Below that it
cannot reach them all, and it covers the first `samples_target`
categories in name order.

Both can be overridden on the command line with `--seed` and
`--target`. `--slice` instead regenerates the small committed
conformance slice under `src/pmc_data/conformance/`.

## `chain_a_red_structures.json`

The original single-fixture pipeline (issue #8). Each entry reapplies
the one accepted canonical plan (`select copilot_selection, chain A` /
`color red, copilot_selection`) to a different controlled structure and
is verified through `pmc_data.verifier.verify_gold_case` before it may
ever be written as a gold record -- see `pmc_data/generate.py` for the
schema and `tests/data/test_generate_real_pymol.py` for the real-PyMOL
conformance evidence.

It is kept as it was. The generalized pipeline adds a `Sample` record
beside `GoldCase` rather than replacing it, so the two hand-authored
gold records keep their fixed-plan drift guard.
