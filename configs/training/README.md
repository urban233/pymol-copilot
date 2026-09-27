# Training configuration

This directory is owned by model development (master plan item 17).

## `lora-v1.json`

The one config the fine-tune is trained under, read by
`pmc_train.config.load_config`. Every field is required and every
unknown field is refused, at every level, so the file is exactly what
trained. Its SHA-256 is part of the run's identity
(`pmc_train.config.run_id`), and it was committed before the training
run existed (see [docs/training/README.md](../../docs/training/README.md)).

- `base_model` names the 16-bit weights the adapter trains on:
  `unsloth/Llama-3.2-1B-Instruct` at revision
  `5a8abab4a5d6f164389b1079fb721cfab8d7126c`. That repository is an
  ungated mirror of `meta-llama/Llama-3.2-1B-Instruct`: its
  `model.safetensors` has SHA-256
  `1ff795ff6a07e6a68085d206fb84417da2f083f68391c2843cd2b8ac6df8538f`,
  the same hash Hugging Face publishes for Meta's own file (revision
  `9213176726f574b556790deb65791e0c5aa438b6`), checked on 2026-09-27.
  So the weights are Meta's. Only the tokenizer files differ in
  formatting, and `pmc_train`'s render-parity test pins the prompt
  bytes and token ids against the engine itself.
- `chat_template_date` is the `date_string` every prompt is rendered
  with: `26 Jul 2024`, the one the evaluation engine pins
  (configs/evaluation/README.md).
- `max_seq_length` is 16384, the evaluation context. It covers the
  longest training sample. A longer one is refused, never truncated.
- `lora`, `optimizer`, `precision` and `gradient_checkpointing` are the
  one set of settings the run uses. No sweep chose them, and none
  follows.
- `seed` seeds the adapter's initialization, dropout and every library
  RNG. `data_seed` seeds the order samples are visited in.
- `split` names the frozen split. Only its `train.jsonl` is read.
- `export` fixes the GGUF export: Q4_K_M, by llama.cpp `b10707` (the
  build the baseline engine ran), checked against the baseline's own
  GGUF, whose revision and SHA-256 are those in
  `configs/evaluation/baseline.json`.
