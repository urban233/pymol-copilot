# Evaluation configuration

This directory is owned by model evaluation (master plan item 16).

## `baseline.json`

The one configuration the untuned baseline, and item 17's comparison
against it, are run under, consumed by `pmc_eval.eval_cli`:

```
bazel run //src/pmc_eval:eval_cli -- run \
    --split data/splits/split-e4599620801af592 \
    --set test_gold --condition grammar
```

Its SHA-256 is part of every run's identity, so a run resumes, and a
baseline compares, only under the exact file that produced it.

- `engine` names the model under evaluation: the Lemonade model id,
  the exact checkpoint that id must load, and the llama.cpp backend and
  context size. The base model is **Llama-3.2-1B-Instruct at Q4_K_M**,
  a standard llama.cpp quantization item 17's Unsloth GGUF export can
  reproduce, so the baseline and the fine-tune differ only in their
  weights. This fixes item 17's base model.
- `generation` bounds every completion: 256 tokens (the longest
  reference plan is 4 lines, 164 characters) and a 600-second deadline.
  The deadline and `engine.read_timeout_seconds` are set far above what
  a CPU prefill of the longest prompt needs, so a timeout is always an
  infrastructure failure and never a verdict on the model.
- `context_size` is 16384 because the prompts are long: the card lists
  every atom, and the largest held-out prompt is about 14,800
  characters. The adapter's own default, 4096, does not fit it.
- `sidecar.deadline_seconds` is the executor's own default.
- `infra_retries` is how often one invocation retries a sample whose
  engine call or sidecar run failed for infrastructure reasons.
- `engine_provenance` records what the engine's capability probe
  cannot see. A run refuses to start while any field is null. Fill it
  in when the engine is set up (below), then commit it: runs also
  refuse a modified tracked file.

## Setting up the engine

Not yet run; filled in by master plan item 16's Step 9, with the pilot
measurements (wall time per attempt, which context sizes fit the
largest prompt, and how many completions differ between two identical
runs).
