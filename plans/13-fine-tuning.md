# Fine-tuning (master plan item 17)

## Context

This is item 17 of [docs/master_plan.md](../docs/master_plan.md). It is Martin's
item, sized at about 5 days plus unattended GPU time. It blocks items 18 and 19.
Every prerequisite is done: 0 (#24), 1 (#25), 15 (#53) and 16 (#58).

The intent:

```
Fine-tune in src/pmc_train/, in the separate virtual environment, outside
the Bazel closure. Completion-only supervised fine-tuning — include a test
that asserts at the tensor level that prompt tokens are masked out of the
loss. Choose a base model that will actually run on CPU and integrated GPU
through Lemonade and record why you picked it. Log seeds and configs.
Afterwards re-run the eval harness and compare per category against the
recorded baseline. If the fine-tune doesn't beat the baseline, report that
result — don't chase it.
```

Martin added one constraint: **every GPU run is gated behind his explicit
consent.**

The outcome:

- one LoRA fine-tune of the fixed base model, trained from one committed
  config with logged seeds;
- that model exported as a Q4_K_M GGUF;
- the model evaluated by the unchanged item 16 harness;
- a committed per-category comparison against the baseline, with the
  pre-registered McNemar test, reported whatever it shows.

### What exploration established

**The base model is already fixed.** Item 16 fixed it as
Llama-3.2-1B-Instruct at Q4_K_M
(`unsloth/Llama-3.2-1B-Instruct-GGUF:Llama-3.2-1B-Instruct-Q4_K_M.gguf`,
HF revision `b69aef11…`, SHA-256 `3f5a2242…`), and the baseline was measured
on it. The comparison holds everything but the weights fixed
(`docs/evaluation/README.md:131-146`, `PREREGISTRATION.md:21-33`). So "choose
a base model" means writing down why this model was picked; it does not mean
re-picking. A different model would need a new baseline.

**The baseline is 0/68 TaskSuccess on `test_gold` under both conditions.**
Almost every sample is `truncated` at 256 tokens:

- without the grammar, the model copies the structure card;
- with the grammar, the model loops over commands.

The fine-tune has to learn to emit the plan **and stop**, so the EOT token
must be inside the loss.

**The prompt path the engine sees:**

- `LemonadeEngine` posts `/api/v1/chat/completions` with
  `messages=[{"role":"user","content":prompt}]`, no system message,
  `temperature=0` (`src/pmc_agent/inference/lemonade.py:470-488`).
- llama-server runs `--jinja` with the GGUF's own template, and the date is
  pinned by `--chat-template-kwargs {"date_string":"26 Jul 2024"}`.
- So training must render `[{"role":"user","content":Sample.prompt_text}]`
  through the Llama 3.2 template with `date_string="26 Jul 2024"` and
  `add_generation_prompt=True`.
- The target is `Sample.plan_pml` (which always ends in `\n`) followed by
  `<|eot_id|>`.
- `prompt_text` is one raw string with no system/user split
  (`pmc_core/prompt.py:195-213`).

**The data:**

- Load it with `pmc_data.sample.read_samples(path)` (`src/pmc_data/sample.py:900`)
  and check it with `pmc_data.manifest.validate_manifest(dir)`
  (`manifest.py:175`). Both are stdlib plus `pmc_core` constants.
- The code must stay 3.12-compatible.
- Train has 2,389 samples in 120 categories.

**The training prompts are far longer than the eval prompts.** The longest
train `prompt_text` is 37,574 characters, about 14k tokens. 425 samples
(`everything_four_chains`, `everything_three_chains`) run to 37k characters.
Gold tops out at 5,495 tokens. The GPU is an RTX 4060 with 8 GB.

**No eval code compares two runs yet.** There is no `compare` command and no
McNemar test. Three things in the existing code also stand in the way:

- `publish` hard-codes the title "Untuned baseline" (`eval_cli.py:803`);
- `publish` needs every set × condition;
- `tests/eval/test_committed_baseline.py:50` hard-codes
  `docs/evaluation/baseline`.

**The engine can't load a local GGUF yet:**

- `setup.sh` hard-codes the model name and checkpoint (`:30-31`);
- the compose file has named volumes only, with no bind mount;
- `hf_revision` is parsed from an HF cache path, and `run` refuses a null
  provenance field;
- `_served_model_path` (`lemonade.py:805-838`) accepts any `<x>:<file>`
  checkpoint whose launched `-m` path ends in `/<file>`.

**How the training code must be tested:**

- `tests/` is Bazel-owned, and `pyproject.toml` has `testpaths=["tests"]`
  with `filterwarnings=error`.
- So training tests live in `src/pmc_train/tests/`, which is inside
  `.bazelignore` and outside `testpaths`, with their own `pytest.ini`.
- Ruff (run in CI) still lints `src/pmc_train`, so house style applies.
- Pyrefly excludes it.
- `requirements-train.in` has no pytest.
- `.venv-train` is in neither `.gitignore` nor `.bazelignore`.
- `unsloth` needs CUDA at import time.

### Decisions (settled with Martin)

1. **Base model stays Llama-3.2-1B-Instruct.** Record why in
   `docs/training/README.md`.
   - **CPU is measured:** the tuned GGUF runs on Lemonade's CPU backend.
   - **iGPU is stated as unproven**, with the Vulkan route named. It is not
     measured.
2. **GPU gates:**
   - the training run, including a short smoke run first;
   - every eval run on the GPU engine.

   Downloads and the GGUF export are not gated.
3. **Gate protocol.** At each gate the session prints:
   - the exact command;
   - the config SHA-256 and the commit;
   - the expected duration and GPU memory;
   - what the command writes.

   Then it **stops and asks**. It launches only on an explicit "yes" in that
   session. Each gate needs its own yes: an earlier yes does not carry over,
   and any other reply means don't run.
4. **The tuned GGUF stays local**, under gitignored
   `results/train-<id>/export/`. Its SHA-256, config and manifest are
   committed. Hannah gets the file out of band. **Nothing is uploaded
   anywhere.**
5. **`max_seq_length` is 16384**, the eval context. A gated smoke run on the
   longest samples proves it fits in 8 GB. **If it OOMs, stop and ask.**
   Never drop or truncate samples silently.
6. **An export-pipeline control:**
   - the untuned HF weights go through our own convert/quantize pipeline;
   - that GGUF is evaluated on `test_gold` in both conditions;
   - the result is reported next to the published baseline.

   It is secondary, and it does not replace the pre-registered comparison.

### Unsloth: what it does in the real run

**The real run (Gates B and C) uses Unsloth.** It is the default
`--backend`, as `docs/development_setup.md:106` intends.

- **Model loading:** `FastLanguageModel.from_pretrained(..., dtype=bf16,
  load_in_4bit=False)` and `FastLanguageModel.get_peft_model(...,
  use_gradient_checkpointing="unsloth", random_state=seed)`.
- **What Unsloth supplies:**
  - its Triton kernels for RoPE, RMSNorm, SwiGLU and the LoRA MLP/QKV
    paths;
  - its offloaded gradient checkpointing, which keeps activations in CPU
    RAM;
  - its fixed gradient accumulation.

  That is where its speed and memory savings come from, and it is what
  makes 16k-token sequences on 8 GB plausible.
- **The one Unsloth piece we don't use is its fused cross-entropy.** Our
  `completion_loss` applies `lm_head` only to the roughly 40–60 supervised
  positions per sample, not to all 16k. That saves more memory than a fused
  kernel over every position would, and it makes the masking test test the
  loss that actually trains.
- **We don't use `train_on_responses_only` / `SFTTrainer`.** Instead we
  write the mask ourselves as `labels = -100` on prompt tokens, so the
  tensor-level test can check exactly those tensors.
- **The `hf` backend (plain HF plus PEFT) exists only for the CPU unit
  tests**, because Unsloth needs CUDA at import time. The runtime
  `assert_batch_masked` on real Unsloth batches in Gate B closes that gap.
- **If Gate B still OOMs,** the next levers are Unsloth's `load_in_4bit`
  (QLoRA) or a shorter `max_seq_length`. Both are Martin's call.

### Decisions I took, so you can overrule them

- **One run, one config, no sweeps.** `configs/training/lora-v1.json` is
  committed before the training gate. These are the settings:
  - bf16 LoRA on a 16-bit base, not QLoRA, so that merge-then-quantize
    matches how the base GGUF was made;
  - r=16, alpha=32, dropout 0;
  - targets `q,k,v,o,gate,up,down`;
  - lr 2e-4, cosine schedule, 3% warmup;
  - 2 epochs;
  - batch 1 with gradient accumulation 16;
  - Unsloth gradient checkpointing;
  - seeds `seed` and `data_seed`.

  The final checkpoint is exported. No validation set drives any choice, and
  no test or held-out data is ever loaded by `pmc_train`. A re-run is allowed
  only after an infrastructure failure, with the same config and seed, and
  it is recorded.
- **A `transformers.Trainer` on the Unsloth model, with our own collator
  and loss, not TRL's `SFTTrainer`.** TRL 0.24's collator rebuilds `labels` from its own
  `completion_mask`. Owning the tensors makes the masking test test what
  actually trains. TRL stays pinned but unused.
- **The loss is computed only at supervised positions.** `completion_loss`
  applies `lm_head` only to the hidden states whose next-token label is not
  -100. Full logits at 16k × 128k vocab would take about 4 GB in bf16. A
  test proves this loss equals the full-logit masked loss.
- **The runtime mask check runs on the real batch.** `train.py` runs
  `assert_batch_masked` on the first real batches taken from
  `trainer.get_train_dataloader()`, before `trainer.train()`. This catches
  any rewrite by Unsloth or the Trainer that the CPU tests (which run without
  Unsloth) cannot see.
- **The GGUF export uses pinned llama.cpp `b10707`**, the build the baseline
  engine ran:
  - merge the adapter into the bf16 base;
  - convert with `convert_hf_to_gguf.py --outtype f16`;
  - run `llama-quantize Q4_K_M` with no imatrix;
  - then check the metadata against the base GGUF: `file_type`,
    `tokenizer.chat_template`, the token list and the architecture.

  Unsloth's `save_pretrained_gguf` is not used, because it builds an
  unpinned llama.cpp.
- **Base weights for training** come from `unsloth/Llama-3.2-1B-Instruct`,
  the ungated safetensors mirror, at a revision pinned in the config.
  Step 2 checks that it is the same model the base GGUF was made from.
- **CI does not run training tests.** There is no training environment in
  CI. Ruff covers `src/pmc_train` there, and the tests run in `.venv-train`.
  The PR description says so.

## Delivery

1. `git fetch`, then create `feat/fine-tuning` from `origin/main`.
2. First copy this plan to `plans/13-fine-tuning.md`.
3. Use Conventional Commits, one per step.

**Gate after every step:**

```
bazel test //... --lockfile_mode=error
bazel run //tools/bazel:check_dependency_boundaries --lockfile_mode=error
bazel run //tools/quality:ruff --lockfile_mode=error -- check .
bazel run //tools/quality:ruff --lockfile_mode=error -- format --check .
bazel run //tools/quality:pyrefly --lockfile_mode=error -- check
PYTHONPATH=src .venv-train/bin/pytest src/pmc_train/tests      # from step 1 on
```

**Sabotage check for each step's test:** break what the test covers, confirm
that exactly that test fails, then restore.

**House style:**

- copyright header;
- the `__future__` import with its `noqa`;
- Google docstrings;
- one import per line;
- 80 columns;
- `pmc_train` code stays 3.12-compatible.

**The implementer may edit:**

- `src/pmc_train/**`, `configs/training/**` and `docs/training/**`;
- `requirements-train.in` and `requirements-train.txt`, plus the training
  section of `docs/development_setup.md`;
- `.gitignore` and `.bazelignore`, adding `.venv-train/` and `/.train-tools/`
  only;
- `src/pmc_eval/**`, `tests/eval/**`, `configs/evaluation/**` and
  `docs/evaluation/**`;
- `docs/evaluation/BUILD.bazel`;
- `results/README.md`, `docs/master_plan.md` and `plans/13-fine-tuning.md`.

**Not** `src/pmc_core/**`, `src/pmc_agent/**` or `src/pmc_data/**`. If the
adapter or the data code needs a change, stop and ask. Never edit
`PREREGISTRATION.md` or `docs/evaluation/baseline/**`.

**Human gates:** Gates A–D below, using the protocol in decision 3.

**Stop and ask** in any of these cases:

- the smoke run OOMs;
- Lemonade cannot serve a local GGUF;
- the chat-template parity test fails;
- the export's metadata differs from the base GGUF's.

---

## Step 1 — Training environment and test harness

1. Add `pytest` and `gguf` (the metadata reader) to `requirements-train.in`.
   Recompile `requirements-train.txt` with the command in
   `docs/development_setup.md:129`.
2. Add `.venv-train/` and `/.train-tools/` to both `.gitignore` and
   `.bazelignore`.
3. Add `src/pmc_train/pytest.ini`:
   - its own `testpaths = tests`;
   - `--strict-markers`;
   - `filterwarnings = error`, with narrow per-module ignores only;
   - a `gpu` marker.
4. Add `src/pmc_train/tests/__init__.py` and `test_environment.py`.

**Test:** `test_environment.py` asserts four things:

- Python is 3.12;
- the torch, transformers and peft versions equal the lock's pins;
- `pmc_data.sample.read_samples`, `pmc_data.manifest.validate_manifest` and
  `pmc_core.prompt` import under 3.12;
- `unsloth` is **not** imported by `import pmc_train`.

Also, `bazel query 'kind(rule, //...)' | grep pmc_train` stays empty.

## Step 2 — Training config and run identity

- **`src/pmc_train/config.py`** holds a frozen `TrainConfig`, following the
  strict-loader pattern of `src/pmc_eval/config.py`: unknown or missing keys
  raise.
- **`configs/training/lora-v1.json`** holds these fields:
  - `base_model` (repo plus pinned `revision`);
  - `chat_template_date` (`"26 Jul 2024"`);
  - `max_seq_length` (16384);
  - the LoRA and optimizer fields from the decisions;
  - `seed` and `data_seed`;
  - `split_dir` and `split_id` (`split-e4599620801af592`);
  - `export`: `quantization` `Q4_K_M` and `llama_cpp_tag` `b10707`.
- **`config_sha256(path)`** hashes the file.
- **`run_id(config_sha, split_id, commit)`** is a digest of its inputs.

Pin the revision by querying the HF API, and write down in
`configs/training/README.md` that the mirror equals Meta's
Llama-3.2-1B-Instruct. Replace that file's stub.

**Test:** `tests/test_config.py` checks:

- the committed config loads;
- an unknown key, a missing key or a wrong type raises;
- the hash is stable, and changes when one byte changes;
- `split_id` equals the id in `docs/dataset/manifest.json`.

## Step 3 — Prompt rendering, with parity against the engine

1. **`src/pmc_train/render.py`**:
   - `render_prompt(tokenizer, prompt_text, date_string) -> str` calls
     `apply_chat_template([{"role":"user","content":prompt_text}],
     tokenize=False, add_generation_prompt=True, date_string=...)`;
   - `prompt_ids(...)` tokenizes that string with `add_special_tokens=False`,
     because the template already emits `<|begin_of_text|>`.
2. **`src/pmc_train/capture_engine_render.py`**, a dev-only helper, posts
   the same messages to llama-server's `/apply-template` and `/tokenize`
   inside the running engine container. Run it against the CPU engine (no
   gate) for four samples:
   - `gold_061` (the longest gold sample);
   - one short gold sample;
   - one train sample from `everything_four_chains`;
   - one other train sample.

   Commit the rendered strings and token ids to
   `src/pmc_train/tests/data/engine_render/`.

**Test:** `tests/test_render.py` checks:

- the rendered string is **byte-equal** to the engine's;
- HF token ids equal llama.cpp's `/tokenize` ids;
- there is exactly one `<|begin_of_text|>`;
- `Today Date: 26 Jul 2024` is present, and today's date is absent;
- a different `date_string` breaks equality (the sabotage).

**If parity fails, stop and ask.**

## Step 4 — Examples, collator and completion-only loss (the masking centerpiece)

**`src/pmc_train/examples.py`**:
`build_example(sample, tokenizer, cfg) -> Example(input_ids, labels,
completion_start)`.

- The completion is the tokens of `plan_pml` plus `eot_id`.
- `labels` is `[-100] * len(prompt)` followed by the completion ids.
- It **raises** if the sequence is longer than `max_seq_length`. It never
  truncates.

**`src/pmc_train/collate.py`** pads on the right: pad ids, attention mask 0,
and label -100 at padded positions. It emits only `input_ids`,
`attention_mask` and `labels`.

**`src/pmc_train/loss.py`**:

- `completion_loss(hidden, lm_head, labels)` shifts the labels, selects the
  positions whose next-token label is not -100, applies `lm_head` only
  there, and computes a mean cross-entropy;
- `assert_batch_masked(batch, completion_starts)`.

**Test:** `tests/test_masking.py` uses the real pinned tokenizer and template,
plus a tiny randomly initialized `LlamaForCausalLM` on CPU (hidden 64,
2 layers, the real vocabulary). It checks:

- **labels:** every prompt position is -100; completion positions equal
  `input_ids`; the last supervised label is `eot_id`; the number of
  supervised tokens is the plan's token count plus 1;
- **decoding:** the supervised tokens decode to `plan_pml + "<|eot_id|>"`;
- **boundary stability:** tokenizing the rendered prompt plus `plan_pml` in
  one call gives the same ids as the prompt and completion tokenized
  separately;
- **gradients at the logits (the tensor-level proof):** with
  `logits.retain_grad()`, `logits.grad` is exactly 0 at positions
  `0..P-2`, and nonzero at `P-1..L-2`;
- **loss value:** `completion_loss` equals the HF model's own
  `forward(labels=...)` loss and a manual masked cross-entropy (atol 1e-6),
  and its parameter gradients equal the full-logit path's;
- **padding:** in a padded batch of two, padded positions carry no loss and
  the loss is unchanged by padding;
- **overlong input:** `build_example` raises;
- **`assert_batch_masked`:** it raises on a batch where `labels = input_ids`
  (the sabotage), and passes on the real collator's output.

`tests/test_train_lengths.py` tokenizes every train sample with the real
template. It checks that everything fits in 16384, and records the exact
longest length and its sample in `tests/data/train_lengths.json`, replacing
the 2.7 characters-per-token estimate.

## Step 5 — Training data loading and order

**`src/pmc_train/data.py`** provides
`load_train(cfg) -> tuple[Sample, ...]`:

- it calls `validate_manifest` on the split directory;
- it reads **only** `train.jsonl`;
- it refuses a split id other than the one configured;
- it asserts that no train `sample_id` or `structure.spec_id` appears in
  `test_gold.jsonl` or `heldout_synthetic.jsonl`. It reads their ids only.

`ordered(samples, data_seed)` is a seeded permutation.

**Test:** `tests/test_data.py` checks:

- loading 2,389 samples;
- a tampered manifest raises;
- a path pointing at `test_gold` raises;
- the order is deterministic per seed, and differs across seeds;
- the leakage check fires on an injected held-out id (the sabotage).

## Step 6 — Trainer, run manifest and smoke mode

**`src/pmc_train/train.py`** is run as
`python -m pmc_train.train --config ... [--smoke N] [--backend unsloth|hf]`.

- It refuses a dirty tracked tree, using the `git status --porcelain -uno`
  rule as in `eval_cli`.
- It sets `random`, `numpy`, `torch` and `transformers.set_seed(seed)`. The
  seed is passed as the LoRA `random_state`, and `data_seed` drives the
  order.
- It builds the model:
  - `unsloth` (default): `FastLanguageModel.from_pretrained(...,
    load_in_4bit=False, dtype=bf16)` and `get_peft_model`, imported lazily;
  - `hf`: plain HF plus PEFT, used by the CPU tests.
- A `Trainer` subclass overrides `compute_loss` with `completion_loss`.
- `assert_batch_masked` runs on the first 8 real dataloader batches before
  `train()`.
- `--smoke N` trains N steps on the N longest samples and records peak
  `torch.cuda.max_memory_allocated`, tokens per second and the projected
  full-run time. It writes to `results/train-smoke-<id>/` and never exports.
- Outputs go to `results/train-<id>/`:
  - `run.json`: the config and its SHA, both seeds, the commit, the split
    id, the base revision, `pip freeze`, the torch, CUDA, driver and GPU
    names, the Unsloth version, and the determinism flags;
  - `loss.jsonl`: per logging step;
  - `adapter/`;
  - `timings.json`.

**Test:** `tests/test_train_cpu.py` runs `--backend hf` with the tiny random
model on 4 samples for 3 steps. It checks that:

- `run.json` has every required field, including both seeds and the config
  SHA;
- the masked-batch assertion was executed;
- a dirty tree is refused;
- two runs with the same seed give identical `loss.jsonl` on CPU.

## Step 7 — GGUF export pipeline and control export

1. **`src/pmc_train/build_llama_cpp.sh`** clones llama.cpp at tag `b10707`
   into `/.train-tools/llama.cpp-b10707` and builds `llama-quantize` for
   CPU.
2. **`src/pmc_train/export.py`** runs merge (skipped with `--base-only`),
   then save as fp16 HF, then `convert_hf_to_gguf.py --outtype f16`, then
   `llama-quantize ... Q4_K_M`.
3. **`src/pmc_train/gguf_check.py`** compares the result with the base GGUF
   (downloaded at the pinned `hf_revision`, SHA verified). It checks:
   - `general.file_type` is Q4_K_M;
   - `tokenizer.chat_template` is identical;
   - the token list and the special-token ids are identical;
   - the architecture and context length match.

   It reports, and does not fail on, differences in imatrix or quantize
   metadata.
4. Write `export.json`: the SHA-256 of every file, the llama.cpp commit and
   the check result.
5. **Run the control export now**: `--base-only` on the untuned weights. It
   runs on CPU, so there is no gate.

**Test:**

- `tests/test_gguf_check.py` checks pass and mismatch cases on tiny GGUFs
  written with gguf-py.
- `tests/test_export_tiny.py` (marker `slow`) runs a tiny random Llama with
  hidden 256 and the real tokenizer through the full export, and
  `gguf_check` passes against itself.

## Step 8 — Serving a local GGUF through Lemonade, and the configs

1. **`configs/evaluation/engine/compose.local-model.yaml`** is an override
   that bind-mounts one export directory read-only at `/models/<name>/`.
   Lemonade and its image are unchanged.
2. **`setup.sh`** takes `--config <file>` and reads `model_name` and
   `checkpoint` from it. The default stays `baseline.json`, and the
   baseline's output is byte-identical.
   - For a checkpoint that is not in the HF cache, it records `hf_revision`
     as `"none (local GGUF; identity is gguf_sha256)"`.
3. **Probe on the CPU engine** with the control GGUF (no gate):
   - find the `lemonade pull user.<name> --checkpoint ... --recipe llamacpp`
     form that 11.9.0 accepts for a local file;
   - confirm the catalog's checkpoint, the launch command's `-m` path and
     the adapter's `probe_capabilities`.

   **If Lemonade can't register a local file, or the adapter refuses it,
   stop and ask.** The fallback, a private HF upload, is outward-facing and
   Martin's call.
4. **New configs:**
   - `configs/evaluation/export_control.json`;
   - `configs/evaluation/finetuned.json`;
   - `configs/evaluation/finetuned_cpu.json`.

   The first two are identical to `baseline.json` except `engine.model_name`,
   `engine.checkpoint` and `engine_provenance.{gguf_sha256,hf_revision}`.
   The CPU one also differs in `engine.backend` and the host provenance
   fields.
5. `test_lemonade_real.py` reads `PMC_EVAL_CONFIG`, with `baseline.json` as
   the default.

**Test:** `tests/eval/test_configs_hold_fixed.py` loads each config and
asserts that its difference from `baseline.json` is exactly the allowed key
set. `test_lemonade_real` passes with
`PMC_EVAL_CONFIG=configs/evaluation/export_control.json` on the CPU engine.

## Step 9 — Comparison tooling in `pmc_eval`

**`src/pmc_eval/compare.py`** and `eval_cli compare --baseline <published
dir> --candidate <published dir> --out <dir>`:

- Pair the samples by `sample_id`, per set and condition.
- **Refuse the comparison** if any of these differ:
  - the split id, sample order, sets or conditions;
  - the harness, grader, repair-prompt, report or normalization version;
  - `generation`, `context_size`, `lemonade_version`, `llama_cpp_build`,
    `llamacpp_args` or `image`;
  - any config key outside the allowed set.
- For TaskSuccess per condition, compute the **exact two-sided McNemar test**
  on the discordant counts b and c:
  `p = min(1, 2·Σ_{k≤min(b,c)} C(b+c,k)/2^(b+c))`, and `p = 1` when b+c=0.
- Show every metric side by side with Wilson intervals and deltas.
- Show every breakout side by side, labelled descriptive: verb set, term,
  shape, difficulty, structure and **category**.
- Write `comparison.json` and `COMPARISON.md`.

**`publish`** gains `--title` and `--sets`. `--sets` publishes a subset, for
the gold-only control. Defaults keep today's behaviour byte-identical.

`test_committed_baseline.py` is generalized to every published directory
under `docs/evaluation/`, and to the committed comparison recomputing from
its inputs.

**Test:** `tests/eval/test_compare.py` checks:

- McNemar values: (0,0) gives 1.0; (0,10) gives 0.001953125; (3,7) gives
  0.34375; (5,5) gives 1.0;
- refusals on a changed harness version, a reordered sample list and an
  extra config key;
- the per-category rows match hand-built fixture records from
  `tests/eval/fakes.py`;
- `publish` with no new flags still reproduces `docs/evaluation/baseline`
  byte for byte.

## Step 10 — Record the model choice and freeze the plan of record

**`docs/training/README.md`** records:

- **Why Llama-3.2-1B-Instruct:**
  - Q4_K_M is about 0.8 GB, so it fits the RAM and CPU throughput of
    laboratory machines;
  - it has first-class llama.cpp and Lemonade `llamacpp` recipe support,
    with CPU proven (spike and item 16);
  - it is a 1B instruct model with a chat template, and a strong small
    base;
  - Q4_K_M can be reproduced from our own export.
- **Its license:** the Llama 3.2 Community License, with its attribution and
  acceptable-use terms.
- **Alternatives:** Qwen2.5-0.5B/1.5B-Instruct, Gemma-3-1B and SmolLM2-1.7B,
  and why they are not taken now: a switch needs a new baseline.
- **The iGPU route:** Lemonade's `llamacpp:vulkan` backend, which the
  adapter already accepts as `gpu`. It is stated as **unproven on our
  hardware**, together with why (M2 Docker has no GPU passthrough, and the
  RTX 4060 is discrete).
- **The method:** how prompt masking works, the length handling, and how to
  reproduce the run.

Commit this together with `configs/training/lora-v1.json` **before Gate B**,
so the training config is fixed before any tuned number exists.

**Test:** the gate is green, and `test_config` loads the committed file.

## Step 11 — Gate A: control eval on the GPU engine

Bring up the NVIDIA engine with `compose.local-model.yaml` and run
`setup.sh cuda --config export_control.json`. Commit the provenance. Then,
**after an explicit yes**, run:

```
for c in no-grammar grammar; do bazel run //src/pmc_eval:eval_cli -- run \
  --config configs/evaluation/export_control.json \
  --split data/splits/split-e4599620801af592 --set test_gold --condition $c --resume; done
```

That is about 10 minutes. Then publish to `docs/evaluation/export_control/`
with `--sets test_gold`, and compare against the baseline.

Report the flips against the baseline. If the control's outcomes diverge
materially from the baseline's (the gate reports the counts), **stop and
ask** before training.

**Test:** the runs finalize with zero infrastructure failures, and
`test_committed_baseline` covers the new directory.

## Step 12 — Gate B: GPU smoke run

**After an explicit yes**, run
`python -m pmc_train.train --config configs/training/lora-v1.json --smoke 5`.
It takes a few minutes.

Report:

- the peak memory against 8 GB;
- tokens per second;
- the projected full-run time;
- the masked-batch assertion result on real Unsloth batches.

**If it OOMs, stop and ask. Do not change the config unasked.** Commit
`smoke.json` under `docs/training/runs/<run-id>/`.

**Test:** the smoke completes, and `assert_batch_masked` passed on the real
dataloader.

## Step 13 — Gate C: full training run

**After an explicit yes**, with the projected duration from Gate B shown,
run `python -m pmc_train.train --config configs/training/lora-v1.json`.
This is the single run. Commit these under `docs/training/runs/<run-id>/`:

- `run.json`;
- `loss.jsonl`;
- `timings.json`;
- the adapter's SHA-256.

The adapter itself stays in `results/`.

**Test:** `run.json` passes `test_config`'s schema, and its config SHA
equals the committed file's.

## Step 14 — Export the tuned model

Run `export.py` on the adapter. Then run `gguf_check` against the base GGUF,
and commit `export.json`. **Any metadata mismatch other than imatrix or
quantize fields means stop.** Fill in `finetuned.json` and
`finetuned_cpu.json` with the tuned GGUF's SHA-256.

**Test:** `gguf_check` passes, and `test_configs_hold_fixed` passes on the
filled configs.

## Step 15 — Gate D: tuned eval on the GPU engine

Register the tuned GGUF, run `setup.sh cuda --config finetuned.json`, and
commit the provenance. Then, **after an explicit yes**, run all four runs:
both sets under both conditions with `--config
configs/evaluation/finetuned.json --resume`. The baseline's four runs took
about 3 hours; the tuned model should stop earlier.

Publish to `docs/evaluation/finetuned/` with the title "Fine-tuned model".

**Test:** four finalized runs, and the published reports recompute from
their samples.

## Step 16 — CPU run (no gate)

Bring up the CPU engine (`compose.yaml` plus `compose.local-model.yaml`),
run `setup.sh cpu --config finetuned_cpu.json`, and run
`eval_cli run --limit 10` on `test_gold` under both conditions.

Record in the "Runs on CPU" section of `docs/training/README.md`:

- the median engine seconds per attempt;
- tokens per second;
- llama-server's RSS;
- the host CPU.

These are pilot runs, used for latency only and never for quality.

**Test:** both pilot runs complete, and their `timings.jsonl` numbers are
the ones quoted.

## Step 17 — Comparison, report and master plan

1. Run `eval_cli compare --baseline docs/evaluation/baseline --candidate
   docs/evaluation/finetuned --out docs/evaluation/comparison/`. Add a
   section for the control against the baseline.
2. In `docs/training/README.md`, state the headline figures:
   - TaskSuccess per condition, with intervals;
   - McNemar b, c and p;
   - the per-category table.

   **If the fine-tune does not beat the baseline, say so plainly and stop
   there.** No second run and no config change.
3. Update `docs/master_plan.md`:
   - mark item 17 done with its PR number;
   - add the result;
   - add a note for item 18 (where the evidence lives);
   - add a note for item 19 (the local GGUF path and SHA-256; that the
     runtime needs 16384 context, the contract prompt, the newline fix and
     the grammar; and how to register the model).
4. Update `results/README.md` for `train-*/`.

**Test:** the gate is green, and `test_committed_baseline` recomputes the
comparison.

---

## Verification (end to end)

```
git fetch && git switch -c feat/fine-tuning origin/main
uv venv --python 3.12 .venv-train && uv pip install -p .venv-train -r requirements-train.txt
PYTHONPATH=src .venv-train/bin/pytest src/pmc_train/tests          # masking, render parity, data, CPU train, export
bazel test //... --lockfile_mode=error                              # plus the rest of the gate
# Gates A–D as above, each after an explicit yes
bazel run //src/pmc_eval:eval_cli -- compare --baseline docs/evaluation/baseline \
  --candidate docs/evaluation/finetuned --out docs/evaluation/comparison
```

**Acceptance:**

1. `test_masking.py` proves at tensor level that the logit gradients are
   exactly zero at every prompt position, that EOT is supervised, and that
   `completion_loss` equals the full-logit masked loss.
2. The training render is byte- and token-identical to what llama-server
   renders.
3. One training run, whose config was committed before it ran, has its
   seeds, config SHA, versions and hardware in `run.json`.
4. The tuned Q4_K_M GGUF passes `gguf_check` against the base GGUF, and runs
   through Lemonade on GPU and on CPU.
5. `COMPARISON.md` gives per-condition McNemar results and the per-category
   side-by-side table, including a null or negative result.
6. The iGPU is stated as unproven. The model choice and its license are
   recorded.

## Risks

- **16k sequences on 8 GB.** Gate B measures it, and the completion-only
  logits remove the largest tensor. If it still OOMs, stop and ask.
- **Unsloth patches Trainer or model internals.** The runtime
  `assert_batch_masked` on real batches and the smoke run expose this. The
  `hf` backend is the fallback, and switching to it needs Martin's ok.
- **Lemonade 11.9.0 may not register a local file.** Step 8 probes it on CPU
  before any GPU time is spent. Stop if it fails.
- **The export pipeline differs from Unsloth's upload.** Gate A's control
  measures the effect and reports it.
- **The template or tokenizer drifts between HF and GGUF.** This is guarded
  by Step 3's parity fixtures and Step 14's `gguf_check`.
- **The fine-tune is null or worse.** It is reported as it is. The config
  is frozen before Gate C.
