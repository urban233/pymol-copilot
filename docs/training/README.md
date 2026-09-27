# Fine-tuning

**Purpose:** how the local model is fine-tuned (master plan item 17), why
this base model, and what the run and its evaluation found.

**Code:** [`src/pmc_train/`](../../src/pmc_train/) · **Config:**
[`configs/training/lora-v1.json`](../../configs/training/lora-v1.json) ·
**Plan:** [plans/13-fine-tuning.md](../../plans/13-fine-tuning.md) ·
**Baseline:** [../evaluation/baseline/BASELINE.md](../evaluation/baseline/BASELINE.md)

This page and the config were committed before the training run, so no
setting here was chosen after a tuned number existed. The results
sections below are filled in afterwards, and say so.

## The base model: Llama-3.2-1B-Instruct at Q4_K_M

Item 16 fixed the base model, and the untuned baseline was measured on
it (configs/evaluation/README.md). A fine-tune compared against that
baseline has to start from the same weights, so this item records why
the model was picked rather than picking again. A different base model
would need a new baseline first.

Why this model:

- **It fits laboratory machines.** V1 runs "primarily on CPU and may use
  an iGPU when Lemonade supports it" (SPECIFICATION.md). At Q4_K_M the
  file is 0.8 GB. CPU prefill of the longest held-out prompt (5,495
  tokens) took 23 s natively on an Apple M2 Pro during item 16's pilot
  (configs/evaluation/README.md). The tuned model's own CPU figures
  are under "Runs on CPU" below.
- **Lemonade and llama.cpp run it as is.** Lemonade's `llamacpp` recipe
  serves it with its own chat template, with the per-request grammar the
  spike (item 1) proved enforced, on the CPU. That path is proven on
  both an M2 Pro and an x86_64 WSL2 machine (item 16).
- **It is an instruct model with a chat template.** That gives a strong
  small starting point for learning a narrow output format.
- **Its quantization can be reproduced.** Q4_K_M is a standard
  llama.cpp type, which our own export can produce from the fine-tuned
  weights (`src/pmc_train/export.py`).

Alternatives that were not taken now: Qwen2.5-0.5B/1.5B-Instruct and
SmolLM2-1.7B-Instruct (Apache 2.0, a looser license) and Gemma 3 1B. Any
of them would need its own baseline, and item 16's comparison design
holds the model fixed. They remain the candidates for the
size-and-quantization comparison the specification defers.

### Integrated GPU: unproven

The iGPU route is Lemonade's `llamacpp:vulkan` backend. llama.cpp's
Vulkan backend runs on Intel and AMD integrated GPUs, and item 9's
adapter already accepts a `vulkan` engine, whose device Lemonade
reports as `gpu`. **It has not been run on an integrated GPU here.**
The Apple M2 Pro's Docker has no GPU passthrough into a Linux container
(tests/discovery/lemonade/FINDINGS.md), and the WSL2 machine's GPU, an
RTX 4060, is discrete. What is measured is the CPU; see "Runs on CPU"
below.

### License

Llama 3.2 is distributed under the **Llama 3.2 Community License
Agreement** and its Acceptable Use Policy. This is a record of the terms
the project acts on, not legal advice:

- redistributing the model, or a model derived from it, requires
  shipping a copy of the agreement and showing "Built with Llama";
- a model trained or fine-tuned from it that is distributed must carry
  "Llama" at the beginning of its name, which is why every export is
  named `Llama-3.2-1B-Instruct-pmc-...` (`pmc_train.export.MODEL_PREFIX`);
- use must comply with the Acceptable Use Policy;
- the extra terms for licensees with more than 700 million monthly
  active users do not apply.

The training weights come from `unsloth/Llama-3.2-1B-Instruct`, an
ungated mirror whose `model.safetensors` is byte-identical to Meta's
(configs/training/README.md).

## Method

**Completion-only supervised fine-tuning, with LoRA, run with Unsloth.**

- **Data.** The 2,389 samples of the frozen split's `train.jsonl`, and
  nothing else (`pmc_train.data.load_train`). The split manifest is
  re-verified, and a run refuses any training sample whose id or
  structure is held out. `test_gold` and `heldout_synthetic` are opened
  only to read their ids.
- **Prompts are the engine's.** Each prompt is rendered the way the
  evaluation engine renders it: `Sample.prompt_text` as one user
  message, through the Llama 3.2 chat template, with the template's date
  pinned to `26 Jul 2024`. The render is byte- and token-identical to
  llama-server's own for the longest gold and training prompts
  (`src/pmc_train/tests/test_render.py`).
- **Only the plan is learned.** The target is `Sample.plan_pml`, which
  always ends in a newline, followed by `<|eot_id|>`. Every prompt token
  is masked out of the loss (label -100). The end of turn is supervised
  on purpose: the untuned model never stopped on its own, and almost
  every baseline completion was cut off at 256 tokens.
  `src/pmc_train/tests/test_masking.py` proves at the tensor level that
  prompt positions receive exactly zero gradient.
- **Loss.** `pmc_train.loss.completion_loss` applies the output layer
  only where the next token is supervised, so a 14k-token prompt never
  materializes its 14k x 128k logits. It is proven equal to the standard
  masked loss, and it is cross-checked against the Unsloth model's own
  loss before every run. Every batch is checked for masking as it
  reaches the loss.
- **Length.** The longest training example is 13,946 tokens; 425 exceed
  8,192, all from the two largest training structures. Sequences run to
  16,384 tokens, the evaluation context, so no sample is dropped or
  truncated (`src/pmc_train/tests/data/train_lengths.json`).
- **Settings** (`configs/training/lora-v1.json`, one run, no sweep):
  - bf16 LoRA on the 16-bit base, not QLoRA, so that merging and then
    quantizing matches how the base GGUF was made;
  - r 16, alpha 32, dropout 0, on every attention and MLP projection;
  - AdamW, learning rate 2e-4 with a cosine schedule and 3% warmup;
  - 2 epochs, one sample per step with 16 accumulated, for 299
    optimizer steps;
  - Unsloth's offloaded gradient checkpointing.
- **Seeds.** `seed` (20260927) seeds the adapter's initialization and
  every library RNG; `data_seed` (20260928) fixes the visiting order, one
  seeded permutation per epoch. Both are recorded in `run.json`, with the
  config's SHA-256 and the order's digest.
- **Export.** The adapter is merged into the bf16 base, converted with
  llama.cpp `b10707` (the release the evaluation engine runs) to f16,
  and quantized to Q4_K_M with no importance matrix. The result is
  checked against the baseline's GGUF: same file type, architecture,
  chat template, tokenizer and tensor shapes (`pmc_train.gguf_check`).

### The export-pipeline control

The baseline's GGUF is Unsloth's own upload, quantized with an
importance matrix (`imatrix_unsloth.dat`); ours is quantized without
one. To measure what our pipeline alone changes, the untuned weights go
through the same export
([export-control.json](export-control.json)) and are evaluated on
`test_gold` in both conditions. This is a secondary check. The
pre-registered comparison is still the fine-tune against the published
baseline.

### Every GPU run is gated

The smoke run, the training run and every evaluation on the GPU engine
run only after Martin's explicit consent, given in the session for that
run. The exported GGUF stays local under `results/`, and only its
SHA-256 and records are committed. Nothing is uploaded.

## Reproducing the run

```
uv venv --python 3.12 .venv-train && uv pip install -p .venv-train -r requirements-train.txt
PYTHONPATH=src .venv-train/bin/pytest src/pmc_train/tests
src/pmc_train/build_llama_cpp.sh
PYTHONPATH=src .venv-train/bin/python -m pmc_train.train --smoke 5     # gated
PYTHONPATH=src .venv-train/bin/python -m pmc_train.train               # gated
PYTHONPATH=src .venv-train/bin/python -m pmc_train.export --run results/train-<id>
```

A run refuses a modified tracked file and never overwrites an earlier
run.

## Runs on CPU

*Filled in after the run.*

## Result

*Filled in after the evaluation. Whatever it shows, including no
difference or a worse fine-tune, is reported here.*
