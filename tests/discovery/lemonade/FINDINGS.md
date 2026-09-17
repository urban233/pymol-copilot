# Lemonade capability spike: findings

Answers [docs/master_plan.md](../../../docs/master_plan.md)'s day-one spike and
feed [SPECIFICATION.md:490](../../../SPECIFICATION.md#L490)'s "bounded local
completion" and item 9's `src/pmc_agent/inference/` engine boundary. See
[plans/02-lemonade-capability-spike.md](../../../plans/02-lemonade-capability-spike.md)
for how these were produced. Every number in the four verdicts below is
reproducible by running `docker compose -f compose.yaml up -d && python3
probe.py --all` against this same container; the one-time setup evidence
(`evidence/01-*`, `evidence/02-*` — first boot and the initial model pull) is
from the manual steps that came before `probe.py` existed and is not
reproduced by `--all`.

This document went through two rounds of adversarial review. The first found
several claims that outran their evidence (an unrepeated grammar test, a
missing "during generation" CPU control, an unrecorded completion time for
the abandoned request, and a log line quoted from nowhere); `probe.py` was
fixed to actually gather that evidence, and the document was rewritten
against a re-run of the fixed script. The second round, run against that
rewrite, found one number that was still stale (a throughput figure that no
longer matched the regenerated evidence file it cited) and confirmed
everything else checked out digit-for-digit; that number was replaced with a
better-evidenced one already sitting in the cancellation probe's own output.
See git history on this file for what changed and why.

## Verdict table

| # | Question | Verdict | Evidence |
|---|---|---|---|
| 1 | Enforce a supplied grammar per request | **YES** | `evidence/04-grammar.json` |
| 2 | Cancel a request mid-generation | **PARTIAL** — streaming yes, non-streaming no | `evidence/05-cancel.json` |
| 3 | Report model identity | **YES** | `evidence/03-identity.json` |
| 4 | Run on CPU | **YES** | `evidence/06-cpu.json` |
| 4 | Run on this machine's integrated GPU | **NOT PROVEN ON THIS MACHINE** — Docker on an Apple M2 Pro has no GPU passthrough into a Linux container | `evidence/06-gpu-absent.txt` |

None of these is a clean "no", but one (non-streaming cancellation) is a real
gap that item 9 must design around, not silently accept.

---

## Q1 — Grammar: YES

**Proof.** Prompt: *"What is the capital of France? Answer with one word."*
Grammar: `root ::= "Berlin" | "Madrid" | "Rome"` — this makes "Paris"
*unreachable*, not merely deprioritised.

- **Control** (no grammar, `temperature: 0`, 3 runs): every run returned
  `"Paris"` (`evidence/04-grammar.json`'s `control.outputs`). The prior is
  confirmed, so a constrained result means something.
- **R1 — `grammar` field on `/api/v1/chat/completions`** (the per-request
  shape the master plan asks about), **repeated 3 times**: every run
  returned `"Rome"` (`r1_grammar_field.outputs`, `deterministic: true`) —
  deterministic, not a lucky single call. Then, still per request (not via
  `llamacpp_args` — that is R3, below), tightened to `root ::= "Berlin"` — a
  single legal token: the server returned exactly `"Berlin"`
  (`r1_single_token_tightened`). **Enforced, deterministically, per
  request, down to an exact forced token.**
- **R2 — `response_format: {type: json_schema, ...}`** with an `enum`
  excluding Paris: returned `{"city": "Berlin"}`. Also enforced — a second,
  independent route to the same guarantee.
- **R3 — `--grammar` via `llamacpp_args` at `/api/v1/load`** (a server-wide,
  load-time grammar rather than per-request): also enforced, returning
  `"Berlin"`. This time confirmed two ways, not inferred from the output
  alone: the load call succeeded, **and** the resulting
  `/api/v1/health.launch_command` argv was captured and shown to literally
  contain `["--grammar", "root ::= \"Berlin\""]`
  (`r3_llamacpp_args_grammar_flag.launch_command`,
  `flag_present_in_launch_command: true`) — the flag genuinely reached
  llama-server's process arguments. Notably, this flag was *not* blocked by
  Lemonade's `llamacpp_args` allow-list (issue
  [#2018](https://github.com/lemonade-sdk/lemonade/issues/2018) blocks
  path-taking flags like `--grammar-file` for arbitrary-file-read reasons,
  but not inline `--grammar` text).
- **R4 — the same `grammar` field sent directly to the llama-server backend
  port** (`http://127.0.0.1:8001/v1/chat/completions`, read from
  `/api/v1/health`'s `backend_url`, bypassing Lemonade's HTTP layer
  entirely), with a *different* single-alternative grammar
  (`root ::= "Madrid"`) so this result cannot be explained by R3's load-time
  grammar leaking through: returned `"Madrid"` — the only string that
  grammar permits. This also rules out R3 contaminating this result (a
  Berlin-only load-time grammar cannot produce "Madrid"); the plain reload
  in `cmd_grammar`'s `finally` block before R4 runs is what makes that
  possible in the first place. Confirms the capability is llama.cpp's own
  and Lemonade genuinely forwards it — it is not a façade-only illusion.

`probe.py`'s verdict logic also covers the two outcomes this run did not hit:
if R1 fails but R4 (direct-to-backend) still enforces the grammar, it reports
`PARTIAL (backend only)` — llama.cpp can do it, Lemonade's HTTP layer just
doesn't forward it — distinct from `NO (rejected)` and `NO (silently
ignored)`, which is the failure mode this spike was specifically warned to
watch for.

**Against the desk research written into the plan:** this is the opposite of
what the upstream docs suggested going in. `docs/api/openai.md` in
`lemonade-sdk/lemonade@main` does not mention `grammar` at all, and the one
GitHub issue asking for this
([#1759](https://github.com/lemonade-sdk/lemonade/issues/1759)) was closed
with a comment on 2026-06-02 asking *"Why is this closed, but also says the
request still stands? ... AFAICT it isn't documented anywhere."* The empirical
answer, on v11.9.0 against the `llamacpp` recipe: **it works, it just isn't
documented.** The most likely explanation, based on how cleanly it passes
through at every layer (chat completions, `response_format`, load-time args,
and the raw backend), is that Lemonade forwards unrecognized request-body
fields to llama-server rather than deliberately implementing `grammar`
support — which is exactly why it works today and exactly why it is the kind
of thing that regresses silently in a later release without anyone treating
it as a breaking change.

**Consequence for item 9.** Grammar enforcement is real and multiply
confirmed, so `src/pmc_agent/inference/`'s bounded-completion interface can
accept an optional grammar and rely on it being honored on the `llamacpp`
recipe. Because it is undocumented — and plausibly an accident of passthrough
rather than a supported feature — item 9 should still probe it at startup
with a canary shaped exactly like R1 (a grammar that forbids the model's
otherwise-deterministic answer) and treat anything other than the constrained
output as a hard failure, per
[docs/master_plan.md:230-231](../../../docs/master_plan.md#L230-L231)'s
"treat silently-ignored grammar as a hard engine failure, not a warning."

## Q2 — Cancellation: PARTIAL (streaming yes, non-streaming no)

**Streaming.** Opened a streaming completion for a 2000-token essay, read a
few SSE chunks, and — while still connected and still reading, before any
disconnect — took a CPU sample as a positive control: **394.4%**
(`streaming.cpu_percent_during_generation_before_disconnect`; lower than
non-streaming's 800%+, most likely because this sample's ~1-second
`docker stats` window straddles a small-chunk SSE flush rather than
continuous decode, not because streaming generation itself uses less CPU).
Then closed the socket without reading further. Two independent signals of
when the server noticed: `/api/v1/health`'s `is_busy` had already flipped to
`false` in the very first post-disconnect sample, at **~2.0 seconds**, while
CPU was still draining (155.04% at that same sample); full CPU quiescence
(under 5%) took **~4.1 seconds**
(`streaming.idle_within_window_at_seconds`). Either way, CPU stayed
near-idle for the rest of the 20-second observation window. **Disconnecting
a streaming request reliably stops compute, within a few seconds, from a
confirmed mid-generation baseline.**

**Non-streaming.** Sent the same 2000-token request with `stream: false` over
a raw socket, waited 1 second for generation to begin, then closed the socket
without ever reading a response. Container CPU stayed at **804–889% and
`/api/v1/health`'s `is_busy` stayed `true` for the entire 20-second
observation window** (`non_streaming.samples_after_disconnect` — every
sample's third field, `is_busy`, is `true`). Past that window, `probe.py`
kept polling `is_busy` for up to 220 more seconds specifically to answer
whether the abandoned request ever finishes on its own: it did, at
**~158.4 seconds** after the disconnect
(`non_streaming.drain_poll.finished_at_seconds`). **Disconnecting a
non-streaming request does not stop compute** — it runs to completion
regardless. This matches the architecture: a non-streaming response is
buffered and written once, at the end, so the server has no partial write
through which to notice the client is gone until it tries to deliver the
finished answer.

There is no documented cancel *endpoint* in Lemonade's API — cancellation, to
the extent it exists, is disconnect-driven only.

**Consequence for item 9.** The bounded-completion interface promises a
*time limit*, not merely a client-side "please stop." If the agent always
requests streaming and disconnects to cancel, the time-limit and
cancellation guarantee both hold, at roughly the few-second latency measured
here. If any code path requests non-streaming completions, cancelling it does
not stop the underlying compute — confirmed to run to completion (~158s for
this 2000-token request) regardless of client disconnect. That request must
be avoided outright, or item 9's engine boundary needs a second enforcement
layer (e.g., a hard wall-clock deadline enforced by killing/restarting the
Lemonade backend process, since the HTTP layer alone cannot cut it off).
**The adapter should always call the streaming endpoint internally, even for
a conceptually "single-shot" completion, and cancel by ceasing to read the
stream.**

## Q3 — Model identity: YES

Three independent surfaces agree, and a negative test shows the server
validates identity rather than echoing whatever the client sent:

- `GET /api/v1/models/{id}` reports `checkpoint`:
  `"unsloth/Llama-3.2-1B-Instruct-GGUF:Llama-3.2-1B-Instruct-UD-Q4_K_XL.gguf"`
  — an exact Hugging Face repo and GGUF filename.
- `GET /api/v1/health`'s per-model block repeats the same `checkpoint`, plus
  `device`, `recipe`, `backend_url`, `pid`, and the full `launch_command`
  argv used to start llama-server (including the resolved absolute path to
  the downloaded `.gguf` file).
- A chat completion's own `model` field echoes the requested model name
  (`"Llama-3.2-1B-Instruct-GGUF"`) — on its own this would be a weak
  signal (it could be a blind echo), so it was tested directly: **a request
  naming a *lowercased* variant of the same model
  (`"llama-3.2-1b-instruct-gguf"`) was rejected with HTTP 404
  `model_not_found`**, not silently served
  (`evidence/03-identity.json`'s `echo_test`). Identity is checked
  case-sensitively against the resolved catalog id, not merely echoed — a
  caveat worth stating precisely: this proves the *name* is validated
  against the catalog, not that the response's `model` field is derived from
  the loaded checkpoint rather than the (validated) request string.

The download log (`evidence/01-startup.txt`, full capture in
`evidence/01-startup-full.txt`) additionally shows Lemonade hash-verifying
the downloaded GGUF file — *"(Download) File already exists and hash
verified: .../Llama-3.2-1B-Instruct-UD-Q4_K_XL.gguf"*, followed by
*"(ModelManager) All files downloaded and validated from Hugging Face"* — and
the snapshot directory name
(`b69aef112e9f895e6f98d7ae0949f72ff09aa401`) is the exact Hugging Face
commit hash of that revision, so the full chain from a human-readable model
name down to a content-verified file is inspectable, not just a label.

**Consequence for item 9.** `model_name` + `checkpoint` (or the full
`launch_command`, if a stronger pin is wanted) is enough for the bounded
completion interface's required "model identity" field, and enough to
support "a deterministic shipping configuration"
([SPECIFICATION.md:490](../../../SPECIFICATION.md#L490)): pin a `checkpoint`
string, not just a friendly model name, and treat a `model_not_found` at
startup as the capability probe's first, cheapest check.

## Q4 — CPU and integrated GPU

**CPU: YES.** `/api/v1/health`'s per-model block
(`evidence/06-cpu.json`) reports `"device": "cpu"`, and `launch_command`
shows no GPU-offload flag (no `-ngl`/`--n-gpu-layers`). The best available
throughput estimate is not a dedicated benchmark but a side effect of the Q2
cancellation probe: the abandoned non-streaming request (`max_tokens: 2000`)
ran to completion ~158.4 seconds after being disconnected
(`evidence/05-cancel.json`'s `non_streaming.drain_poll.finished_at_seconds`)
— **~12.6 tokens/second**, *if* it generated the full 2000 tokens rather than
stopping earlier on its own (the response was never read, by design, so this
is an assumption, not a certainty). The passing 2–3-token samples taken
elsewhere (`evidence/02-chat-smoke.json`: 11.08 tok/s over 2 tokens;
`evidence/04-grammar.json`'s R4: 2.51 tok/s over 3 tokens, slower because
that request's prompt was not cache-hot) are consistent with this but far too
small a sample to lean on individually. Treat "~12–13 tokens/second" as a
rough order of magnitude, not a benchmark, and one produced under full
x86_64-on-arm64 emulation (see below) besides.

**Integrated GPU: NOT PROVEN ON THIS MACHINE.** This is not a soft "unknown"
— it is demonstrated:

- `docker exec ... ls -la /dev/dri` → *No such file or directory*
- `docker exec ... ls -la /dev/kfd` → *No such file or directory*
- `docker exec ... vulkaninfo --summary` finds exactly one Vulkan "device":
  `llvmpipe (LLVM 20.1.2, 128 bits)`, Mesa's **software** rasterizer — not a
  real GPU.
- `GET /api/v1/system-info`'s own hardware probe agrees:
  `amd_gpu: []`, `amd_npu.available: false`, `nvidia_gpu[0].available: false`.

This is the structurally expected outcome, not a probe failure: a Linux
container on an Apple Silicon Mac has no `/dev/dri` or `/dev/kfd` device node
to pass through (there is no Linux DRM/KFD stack on the host to begin with),
and Metal cannot be exposed into a Linux container. Mandatory Docker and "this
machine's integrated GPU" cannot both hold on this hardware — full stop.

**What would close this** (~1 hour on the right host, reusing `compose.yaml`
and `probe.py` unchanged apart from two flags — the exact commands are below;
`evidence/06-gpu-absent.txt` holds this run's raw command output):

- AMD iGPU via ROCm on x86_64 Linux: `--device=/dev/kfd --device=/dev/dri
  --group-add video --group-add render`, load with
  `{"llamacpp_backend": "rocm"}`.
- AMD/Intel iGPU via Vulkan on x86_64 Linux: `--device=/dev/dri`, load with
  `{"llamacpp_backend": "vulkan"}`.
- In both cases, assert `/api/v1/health`'s `device` field explicitly —
  Lemonade auto-selects Vulkan first and silently falls back to CPU if
  unavailable, so an absence of an error is not proof of GPU use.

**Consequence for item 9.** The CPU path is fully validated and is what V1
should assume by default. The GPU path's *mechanism* (backend selection,
device flags, and how to assert success) is fully documented above and
requires no new design — only a run on the right hardware to convert "not
proven" into a real number.

---

## Environment

| | |
|---|---|
| Lemonade version | 11.9.0 (`lemond --version` inside the container; matches `/api/v1/health`'s `"version"`) |
| Image | `ghcr.io/lemonade-sdk/lemonade-server:v11.9.0` (route A — the official image; route B, the local arm64 Dockerfile, was not needed) |
| Image platform | `linux/amd64` (confirmed via the GHCR manifest — one platform entry) |
| Host | Apple M2 Pro (arm64), OrbStack Docker Desktop replacement |
| Emulation | The container runs entirely under QEMU/Rosetta full-system emulation (`uname -m` inside the container reports `x86_64`); llama.cpp build `b10723` ran without incident under emulation — no SIGILL, contrary to the plan's prior expectation |
| Backend | `llamacpp`, `llamacpp_backend: "cpu"` |
| Model | `Llama-3.2-1B-Instruct-GGUF` — a small, non-reasoning instruct model, deliberately not a Qwen3-class thinking model (issue [#1759](https://github.com/lemonade-sdk/lemonade/issues/1759)'s closing comment documents grammar constraints leaking into `reasoning_content` and looping on Qwen3.x) |
| Checkpoint | `unsloth/Llama-3.2-1B-Instruct-GGUF:Llama-3.2-1B-Instruct-UD-Q4_K_XL.gguf`, HF snapshot `b69aef112e9f895e6f98d7ae0949f72ff09aa401` |
| Throughput | ~12–13 tokens/second decode (CPU, emulated) — from the Q2 drain-poll's ~2000 tokens over ~158s, assuming it ran to `max_tokens`; not a production planning number |

Re-run `docker compose -f compose.yaml up -d && python3 probe.py --all` to
reproduce Q1–Q4 (roughly 5–6 minutes end to end, dominated by the
non-streaming drain-completion poll in Q2).
