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

### How long a run takes

Every attempt spawns one `pmc_sidecar.child` process that imports
PyMOL and rebuilds the structure, so the run is CPU-bound in process
startup and scales linearly with the attempt count. Measured on a
12-core Apple Silicon machine at `--workers 8`: the configured
4,000-attempt run takes ten and a half minutes, and the shorter runs
agree with it -- 240 attempts in 44s, 1,200 in 214s. That puts the
full 9,594-plan enumeration (`--target` omitted) at roughly half an
hour. More workers than physical cores will not help; the 8-worker
run already measures 7.3x parallelism.

`--slice` is 52 attempts, about twelve seconds.

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
