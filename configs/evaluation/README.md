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

- `engine` names the model under evaluation: the Lemonade model id
  (see "Setting up the engine" for why it has no `user.` prefix),
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

The spike's container rig serves the model (Lemonade 11.9.0, the
official `linux/amd64` image, llama.cpp `b10723` on CPU):

```
docker compose -f tests/discovery/lemonade/compose.yaml up -d
docker exec lemonade-spike /opt/lemonade/lemonade pull \
    user.Llama-3.2-1B-Instruct-Q4_K_M \
    --checkpoint main \
    unsloth/Llama-3.2-1B-Instruct-GGUF:Llama-3.2-1B-Instruct-Q4_K_M.gguf \
    --recipe llamacpp
```

A model is pulled as `user.<name>` but catalogued, loaded and reported
as `<name>`, so `model_name` is `Llama-3.2-1B-Instruct-Q4_K_M`, without
the prefix; with it, the adapter's catalog check refuses the model.

What was established on 2026-09-26 (Apple M2 Pro, macOS 27.0, OrbStack
29.4.0; the container runs `x86_64` under emulation):

- The catalog reports exactly the configured checkpoint, and the file
  Lemonade downloaded is Hugging Face revision
  `b69aef112e9f895e6f98d7ae0949f72ff09aa401` with SHA-256
  `3f5a22426976ab26cfe84dba63c1d08391717abb1af893e10f1b2968d862dcc1`,
  the hash Hugging Face publishes for it.
- Loaded at `ctx_size` 16384, Lemonade launches `llama-server ...
  --ctx-size 16384 --jinja --metrics --parallel 1`: one slot, and the
  model's own Jinja chat template.
- **That template stamps today's date into every prompt.** Rendered
  through the server's `/apply-template`, a one-line user message
  becomes `Cutting Knowledge Date: December 2023` / `Today Date: 26 Sep
  2026` in a system block, then the message. A run on another day sees
  another prompt. `llama-server` accepts `--chat-template-kwargs
  '{"date_string": "..."}'`, which fixes it.
- **The item 9 adapter cannot yet drive this server.** Its capability
  probe loads the model and then fails its grammar canary with
  `malformed SSE framing`: after a cold load the stream opens with an
  SSE comment, `: ping`, which the SSE format says a client ignores and
  the adapter refuses. The long prompts here make that keep-alive
  routine rather than rare. Past it, the stream's `model` field for
  this model is the GGUF's file path, not the model name, which the
  adapter's identity check also refuses.

Both of the last two are open decisions for master plan item 16's
Step 9; nothing has been evaluated yet. The pilot measurements (wall
time per attempt, which context sizes fit the largest prompt, and how
many completions differ between two identical runs) follow once they
are settled.
