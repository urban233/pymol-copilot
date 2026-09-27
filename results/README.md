# Results

Generated evaluation and training results belong here when content-addressed
and intentionally produced by a later task. Generated contents are ignored;
this README is tracked.

`pmc_eval.eval_cli run` (master plan item 16) writes each finished run to
`eval-<id>/` -- `run.json`, `samples.jsonl`, `report.json` and
`timings.jsonl` -- and checkpoints an unfinished one in a hidden
`.eval-<id>.partial/`. The id is a digest of everything the run's result
depends on, so an existing run is never overwritten. The runs that make up
the untuned baseline are copied to the tracked `docs/evaluation/baseline/`
by `eval_cli publish`; see docs/evaluation/README.md.
