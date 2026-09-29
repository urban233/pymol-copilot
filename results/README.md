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

`pmc_train.train` (master plan item 17) writes each training run to
`train-<id>/` -- `run.json`, `loss.jsonl`, `timings.json` and the LoRA
`adapter/` -- and a smoke run to `train-smoke-<id>/`, working in a
hidden `.train-<id>.partial/` until it finishes. `pmc_train.export`
writes the Q4_K_M GGUF to `train-<id>/export/` (the export-pipeline
control to `export-control/`), and
`configs/evaluation/engine/compose.local-model.yaml` mounts this
directory read-only so the engine can serve it. Their records, not the
weights, are committed under `docs/training/`.
