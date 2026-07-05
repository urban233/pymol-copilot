# cBioMOL AI Training Package

Self-contained QLoRA fine-tuning pipeline for the cBioMOL PyMOL AI
assistant.  Copy this entire `training/` directory (including
`data/tools.json`) to any machine with an NVIDIA GPU and follow the
steps below.

**Target hardware:** NVIDIA RTX 4060 8 GB VRAM.
**Default base model:** `Qwen/Qwen2.5-1.5B-Instruct`
**Alternate base model:** `Qwen/Qwen3-0.6B`
**Expected VRAM peak:** ~3.5 GB (Qwen2.5) / ~2.5 GB (Qwen3-0.6B)
**Expected training time:** 60–90 minutes (Qwen2.5) / 45–60 minutes (Qwen3-0.6B)

---

## Prerequisites

- Python 3.11+
- CUDA 12.1+ and NVIDIA driver ≥ 535
- `pip` or `conda`
- A free Hugging Face account (accept the Qwen2.5 and/or Qwen3 model licenses)
- Any LLM interface for dataset generation (web app, CLI agent, local
  model) — **no API keys required in the scripts**

---

## Setup

```bash
# 1. Install dependencies (re-run after pulling Qwen3 support)
pip install -r requirements.txt

# Verify transformers for Qwen3 (must be >= 4.51.0):
python -c "import transformers; print(transformers.__version__)"

# 2. Log in to Hugging Face (accept model licenses at
#    https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct and/or
#    https://huggingface.co/Qwen/Qwen3-0.6B)
huggingface-cli login
```

> **Note on `bitsandbytes` on Windows:** Use WSL2 with the CUDA toolkit
> installed inside the WSL2 environment.  Native Windows support for
> `bitsandbytes` is experimental.

> **Note on `llama-cpp-python` CUDA support:** If the default wheel was
> installed without GPU support, reinstall with:
> ```bash
>pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu121 --force-reinstall --no-cache-dir
> ```

---

## Step 0 — Export Tool Schemas

Run this once on the **main cBioMOL project machine** to produce
`data/tools.json`, then copy it alongside this `training/` directory:

**PowerShell** (the `>` redirect writes UTF-16 LE by default — use
`Out-File -Encoding utf8` to avoid a decode error):

```powershell
# From the cBioMOL project root (PowerShell)
python -c "import json, sys; sys.path.insert(0, 'src/python'); from pymol_copilot.ai.schemas import tool_schemas; print(json.dumps(tool_schemas.TOOL_SCHEMAS, indent=2))" | Out-File -Encoding utf8 src/python/pymol_copilot/ai/training/data/tools.json
```

**Linux / macOS / WSL** (plain `>` redirect is UTF-8 by default):

```bash
python -c "
import json, sys
sys.path.insert(0, 'src/python')
from pymol_copilot.ai.schemas import tool_schemas
print(json.dumps(tool_schemas.TOOL_SCHEMAS, indent=2))
" > src/python/pymol_copilot/ai/training/data/tools.json
```

> **Note:** The scripts auto-detect UTF-16 and UTF-8 BOMs, so a file
> produced by either method will be read correctly. The `Out-File
> -Encoding utf8` variant is still preferred as it produces smaller,
> more portable files.

---

## Step 1 — Generate the Dataset (prompt-file workflow)

### 1a. Write prompt batch files

```bash
python generate_dataset.py --mode generate_prompts --n_positive 2000 --n_negative 1200 --n_context 600 --output_dir data/
```

This creates `data/prompts/batch_001.txt`, `batch_002.txt`, …
Each file is a self-contained instruction that any LLM can process.

### 1b. Submit prompts to your LLM

You can submit the generated prompts and collect responses in one of three ways:

#### Option A: Local Ollama (Recommended)

If you have a local Ollama server running, you can automate response generation using a local model:

```bash
python generate_dataset_ollama.py \
    --prompts_dir data/prompts/ \
    --model qwen2.5:1.5b-instruct

# Or for Qwen3:
python generate_dataset_ollama.py \
    --prompts_dir data/prompts/ \
    --model qwen3:0.6b
```

#### Option B: Google Gemini API

If you have a Google AI Studio API key, you can automate generation using the Gemini API:

```bash
# Free tier (respects rate limits: 15 RPM / 1,500 RPD)
python generate_dataset_gemini.py --prompts_dir data/prompts/ --tier free

# Paid tier (higher throughput)
python generate_dataset_gemini.py --prompts_dir data/prompts/ --tier paid
```

#### Option C: Manual Submission

Open each `.txt` file and submit it to any LLM web interface or CLI client. Save each response to a sibling `.response.txt` file (e.g. `batch_001.response.txt`). The responses must be valid JSON arrays matching the requested tool schema format.

### 1c. Validate and collect

```bash
python generate_dataset.py --mode collect_responses --input_dir data/prompts/ --output_dir data/

# Expected output (numbers vary with rejection rate):
# [collect_responses] valid=2750, train=2475, val=275, rejected=50
# → data/train.jsonl
# → data/val.jsonl
# → data/rejected.jsonl (review & re-submit if rejection rate > 20%)
```

---

## Step 2 — Fine-Tune

```bash
python finetune.py --data_dir data/ --output_dir checkpoints/

# Fine-tune Qwen3-0.6B instead:
python finetune.py --data_dir data/ --output_dir checkpoints/ --model qwen3-0.6b

# Expected runtime: 60–90 min on RTX 4060 8 GB (Qwen2.5)
#                   45–60 min on RTX 4060 8 GB (Qwen3-0.6B)
# Peak VRAM:        ~3.5 GB (Qwen2.5) / ~2.5 GB (Qwen3-0.6B)
# Output:           checkpoints/best/  (LoRA adapter)
```

**Troubleshooting:**
| Symptom | Fix |
|---|---|
| CUDA OOM | Reduce `MAX_SEQ_LENGTH` to 1536 in `config/training_config.py` |
| Very slow | Verify `nvidia-smi` shows GPU utilization > 0% |
| `bitsandbytes` error | Use WSL2 or a Linux machine |

---

## Step 3 — Test the Adapter

Run this before exporting to GGUF to confirm the adapter produces
recognisable tool calls:

```bash
python test_model.py --checkpoint_dir checkpoints/best/
```

Expected output for each prompt:

```
[1 — Positive single tool (load structure)]
  PROMPT  : Load the human insulin receptor from the PDB (2HR7).
  EXPECTED: load_structure
  OUTPUT  :
<tool_call>
{"name": "load_structure", "arguments": {"pdb_id": "2HR7"}}
</tool_call>
```

If the output does not contain a valid `<tool_call>` block, check
`checkpoints/` for an earlier checkpoint and try again, or verify that
the training loss converged (check the training logs).

---

## Step 4 — Export to GGUF

On the **first run**, the script performs a shallow `git clone` of the
official llama.cpp repository into `<project_root>/vendor/llama.cpp`
(~30 MB, depth 1).  Subsequent runs skip the clone.

Install the conversion script's Python dependencies once:

```bash
pip install -r ../../../../../../vendor/llama.cpp/requirements/requirements-convert_hf_to_gguf.txt
```

Then run the export:

```bash
python export_gguf.py \
    --checkpoint_dir checkpoints/best/ \
    --output_dir models/ \
    --quantization Q4_K_M

# Qwen3 export (model key embedded in filename):
python export_gguf.py \
    --checkpoint_dir checkpoints/best/ \
    --output_dir models/ \
    --model qwen3-0.6b \
    --quantization Q4_K_M

# Output examples:
#   models/pymol_copilot-pymol-assistant-qwen2.5-1.5b-Q4_K_M.gguf (~1 GB)
#   models/pymol_copilot-pymol-assistant-qwen3-0.6b-Q4_K_M.gguf (~0.4 GB)
```

Override the vendor location if needed (e.g. shared across projects):

```bash
python export_gguf.py \
    --checkpoint_dir checkpoints/best/ \
    --vendor_dir /srv/vendor \
    --quantization Q4_K_M
```

> **Note:** `llama-quantize` (the quantizer binary) still comes from the
> `llama-cpp-python` wheel — it is a compiled C++ binary.  Ensure that
> package is installed with CUDA support:
> `CMAKE_ARGS="-DGGML_CUDA=on" pip install llama-cpp-python`

---

## Step 5 — Validate the GGUF

```bash
python validate_gguf.py \
    --model models/pymol_copilot-pymol-assistant-Q4_K_M.gguf

# Runs 5 canonical prompts and prints PASS/FAIL for each.
# Exits with code 1 if any test fails.
```

Expected output:

```
[1 — Positive single tool (load structure)]
  USER   : Load the human insulin receptor from the PDB (2HR7).
  OUTPUT : <tool_call>{"name": "load_structure", ...}</tool_call>
  RESULT : PASS ✓

Results: 5 passed, 0 failed out of 5
```

Copy the validated GGUF back to the main cBioMOL project for use by
the inference engine.

---

## Directory Layout

```
training/
├── README.md                   ← This file
├── requirements.txt            ← Pinned dependencies
│
├── generate_dataset.py         ← Step 1: dataset generation
├── generate_dataset_gemini.py  ← Step 1: Gemini API generation
├── generate_dataset_ollama.py  ← Step 1: Local Ollama generation
├── finetune.py                 ← Step 2: QLoRA training
├── test_model.py               ← Step 3: adapter smoke test
├── export_gguf.py              ← Step 4: GGUF export
├── validate_gguf.py            ← Step 5: GGUF validation
│
├── config/
│   ├── training_config.py      ← All hyperparameters
│   └── chat_templates.py       ← Model-agnostic format adapter
│
├── data/
│   ├── tools.json              ← Tool schemas (copy from main project)
│   ├── prompts/                ← Batch prompt and response files
│   ├── train.jsonl             ← Generated training set
│   ├── val.jsonl               ← Generated validation set
│   └── rejected.jsonl          ← Failed validation examples
│
├── checkpoints/                ← LoRA adapter checkpoints
└── models/                     ← Final GGUF output
```

---

## Hyperparameters

All tunable values are in [`config/training_config.py`](config/training_config.py).
Key settings for 8 GB VRAM:

| Parameter | Value | Rationale |
|---|---|---|
| `LORA_R` | 16 | Narrow structured task; r=8 underfits |
| `MAX_SEQ_LENGTH` | 2048 | Fits multi-step chains with headroom |
| `PER_DEVICE_TRAIN_BATCH_SIZE` | 1 | Mandatory for 8 GB |
| `GRADIENT_ACCUMULATION_STEPS` | 16 | Effective batch = 16 |
| `BF16` | True | Ada Lovelace native bf16; safer than fp16 |
| `GRADIENT_CHECKPOINTING` | True | Halves activation VRAM |
| `OPTIM` | adamw_bnb_8bit | 8-bit optimizer saves ~0.5 GB |

## Adding Support for a New Model

Supported base models are registered in [`config/training_config.py`](config/training_config.py)
under ``SUPPORTED_BASE_MODELS``.  Each entry maps a short CLI key to a
HuggingFace id and optional per-model LoRA settings.

To add another base model:

1. Add a new entry to ``SUPPORTED_BASE_MODELS`` in
   ``config/training_config.py`` (``hf_id`` and ``lora_target_modules``).
2. Add a ``ChatTemplateAdapter`` subclass in ``config/chat_templates.py``.
3. Register it in ``_REGISTRY`` with the model name substring as key.
4. Update ``LORA_TARGET_MODULES`` in the registry entry if the new model
   uses different projection layer names.
5. If the model uses a different runtime ChatML wire format, extend
   ``inference/prompt_builder.py`` and ``detect_prompt_family`` in
   ``backend/config.py``.

Select a model at training time with ``--model <registry-key>`` on
``finetune.py``, ``test_model.py``, and ``export_gguf.py``.  When omitted,
the default is ``qwen2.5-1.5b``.  ``test_model.py`` and ``export_gguf.py``
also auto-detect the base model from ``adapter_config.json`` inside the
checkpoint directory.

> **Qwen3 prerequisite:** ``transformers>=4.51.0`` is required.  Older
> versions raise ``KeyError: 'qwen3'`` when loading ``Qwen/Qwen3-0.6B``.

## CUDA
If it becomes necessary to build llama.cpp from source, use the following command:

```shell
cmake -B vendor/llama.cpp/build vendor/llama.cpp -DGGML_CUDA=ON -DCMAKE_CUDA_COMPILER=/usr/local/cuda-12.1/bin/nvcc -DCMAKE_C_COMPILER=gcc-12 -DCMAKE_CXX_COMPILER=g++-12 -DCMAKE_CUDA_HOST_COMPILER=/usr/bin/gcc-12
```
and
```shell
cmake --build vendor/llama.cpp/build --config Release -j$(nproc)
```
