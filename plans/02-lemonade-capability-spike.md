# Lemonade capability spike

## Context

[docs/master_plan.md:82-96](docs/master_plan.md#L82-L96) calls this "the largest
external unknown in the project" and asks for it on day one. Item 9 of the same
document ([docs/master_plan.md:222-236](docs/master_plan.md#L222-L236)) builds
`src/pmc_agent/inference/` — a bounded completion interface taking prompt,
optional grammar, token limit, time limit, cancellation and model identity —
"using what the spike found". Those five capabilities are exactly the four
questions below. If Lemonade cannot supply one of them, item 9's interface is
wrong and the cost of finding out in week four is a rewrite of the agent's
engine boundary.

[SPECIFICATION.md:307](SPECIFICATION.md#L307) already records this as an
**assumption**, not a fact: *"Lemonade supplies required local grammar,
CPU/iGPU, cancellation, and candidate-platform behavior."*
[SPECIFICATION.md:490](SPECIFICATION.md#L490) makes it load-bearing: *"Bounded
local completion with prompt, grammar, token/time limits, cancellation, model
identity — **no remote fallback**."* There is no fallback to hide a missing
capability behind.

Today the repository contains no Lemonade code at all. The only traces are a
docstring in [src/pmc_agent/runtime.py:2](src/pmc_agent/runtime.py#L2) and the
string `"lemonade"` in
[tools/bazel/check_dependency_boundaries.py:31](tools/bazel/check_dependency_boundaries.py#L31).
`build_engine_client()` returns a bare `httpx.Client` and sends no request.

**Outcome:** one markdown file, `tests/discovery/lemonade/FINDINGS.md`, that
answers four questions with a verdict, the exact command that produced it, and
the exact response. Plus a re-runnable container rig beside it. No production
code, no new runtime dependency, no change to `requirements.in`.

### What desk research already established

This shapes the plan; it does not replace the empirical run.

- **The official image is `linux/amd64` only.** Confirmed against the GHCR
  manifest for `ghcr.io/lemonade-sdk/lemonade-server:latest`: one platform
  entry, `linux/amd64`. This host is an Apple M2 Pro (arm64), so the official
  image runs under emulation, and Rosetta does not implement AVX2. llama.cpp's
  x86-64 builds very likely fault. Step 1 is written around that.
- **Grammar is the question most likely to come back "no".**
  `docs/api/openai.md` in `lemonade-sdk/lemonade@main` mentions `grammar`
  **zero times**, and lists `response_format` only for audio and image
  endpoints — not for chat completions. Issue
  [#2018](https://github.com/lemonade-sdk/lemonade/issues/2018) (closed
  2026-08-06) replaced backend-argument validation with a strict **allow-list**
  and names `-grammar-file` explicitly as a blocked dangerous flag, so the
  `llamacpp_args` route is expected to be closed by design. Issue
  [#1759](https://github.com/lemonade-sdk/lemonade/issues/1759) asked for a
  passthrough `grammar` field and is closed *as completed*, but the only
  evidence in it is a community report against version 10.2.0, and a later
  comment (2026-06-02) reads: *"Why is this closed, but also says the request
  still stands? Is this actually working? AFAICT it isn't documented anywhere."*
  That contradiction is precisely what the spike must settle.
- **Cancellation has history.** Issue
  [#119](https://github.com/lemonade-sdk/lemonade/issues/119) ("Lemonade Server
  currently does not respect attempts to halt generation") was closed
  2025-09-29, and [#366](https://github.com/lemonade-sdk/lemonade/issues/366)
  added a streaming cancel path. There is no documented cancel *endpoint*, so
  cancellation is expected to be client-disconnect only. Whether disconnect
  actually stops the compute is the thing to measure.
- **Model identity looks strong on paper.** `GET /api/v1/health` reports
  `model`, `recipe`, `device`, `backend_url`, `pid` and `launch_command`;
  `GET /api/v1/models` reports `id`, `checkpoint`, `size`,
  `max_context_window`. The open question is whether the `model` field in a
  chat response is the *loaded checkpoint* or merely an echo of the request
  string.
- **Device selection exists.** `llamacpp.backend` takes `cpu`, `vulkan`,
  `rocm`, `cuda`, `metal`, `system`, settable globally via `config.json` /
  `lemonade config set`, or per load via `llamacpp_backend` on
  `POST /api/v1/load`.

### Decisions already taken (from the clarifying questions)

- **The iGPU half of question 4 will be answered NOT PROVEN, deliberately.** A
  Linux container on an Apple M2 Pro gets no GPU: no `/dev/dri`, no `/dev/kfd`,
  no Metal passthrough. Docker is mandatory for this spike, so the honest answer
  is that this machine cannot prove it. Step 6 proves the *absence* rather than
  hand-waving it, and writes down the exact host, flags and backend that would
  close it in under an hour.
- **Step 1 tries the official amd64 image first and falls back** to a small
  local `linux/arm64` Dockerfile built from Lemonade's Debian 13 arm64 `.deb`.
  What the emulated image does is itself spike evidence and gets recorded.
- **Everything lives in `tests/discovery/lemonade/`**, the repository's existing
  home for disposable prototypes
  ([tests/discovery/README.md](tests/discovery/README.md): *"Nothing under this
  directory is a production snapshot, card, or executor API"*).
- **Pin Lemonade v11.9.0** (stable, 2026-09-02) — not the
  `candidate-v2026.39.1` prerelease. Every recorded answer is a statement about
  a specific version and must say so.

### Two gates this directory is subject to

`tests/discovery/lemonade/` is *not* a free-for-all, and getting this wrong is
the most likely way this spike turns red CI:

1. **pyrefly checks it.** `project-includes` in
   [pyproject.toml](pyproject.toml) is
   `["src/pmc_core", "src/pmc_agent", "src/pmc_data", "tests", "tools/winstage"]`
   at `preset = "strict"` with `check-unannotated-defs = true`. Any `.py` file
   placed here is strictly type-checked.
2. **ruff lints it.** `exclude` is only `["tmp"]` plus `.agents`/`.claude`. The
   rule set includes `CPY001` (copyright header), `D`/`DOC` (Google docstrings),
   `ANN001`/`ANN201`, `Q000` (double quotes) and 80-column formatting.

Bazel, however, does **not** see it: a directory with no `BUILD.bazel` is not a
package, so `bazel build //...` and `bazel test //...` never expand into it. Do
**not** add a `BUILD.bazel` here, and do **not** add anything to
`.bazelignore` — neither is needed.

Consequences, decided:

- The probe is **one Python file using only the standard library**
  (`urllib.request`, `http.client`, `json`, `socket`). No httpx, no new
  dependency, no Bazel target. Stdlib also gives direct control over closing a
  socket mid-stream, which is the whole of question 2.
- Copy the copyright header verbatim from an existing file such as
  [tests/discovery/h02/harness.py](tests/discovery/h02/harness.py) so `CPY001`
  passes on the first try.

---

## Ground rules for the whole spike

- **No production code.** Nothing under `src/` is touched. `requirements.in`,
  `requirements_lock.txt` and `MODULE.bazel` are not touched.
- **Every answer carries its evidence.** A verdict with no pasted command and
  response is not an answer. Save raw responses under
  `tests/discovery/lemonade/evidence/`.
- **Every answer names the version.** Lemonade version, image digest or `.deb`
  filename, llama.cpp backend build, model id and checkpoint.
- **"No" is a successful outcome.** A clean, early "no" with evidence is the
  point of the exercise.
- Work on a branch, e.g. `spike/lemonade-capabilities`. One PR, linked to an
  issue, per [CONTRIBUTING.md](CONTRIBUTING.md).

---

## Step 1 — Get a Lemonade server answering `/api/v1/health` in Docker

**Files:**
- `tests/discovery/lemonade/README.md` (new) — disposability notice, modelled on
  [tests/discovery/h02/README.md](tests/discovery/h02/README.md)
- `tests/discovery/lemonade/compose.yaml` (new)
- `tests/discovery/lemonade/Dockerfile.arm64` (new, fallback route)
- `tests/discovery/lemonade/evidence/01-startup.txt` (new)

Start the Docker daemon first — OrbStack is installed at
`~/.orbstack/run/docker.sock` but was not running when this plan was written.

**Route A, attempted first.** Pin by digest, not `:latest`:

```text
docker pull ghcr.io/lemonade-sdk/lemonade-server:v11.9.0
docker run -d --name lemonade-spike -p 13305:13305 \
  -v lemonade-cache:/opt/lemonade/.cache/huggingface \
  -v lemonade-llama:/opt/lemonade/llama \
  -v lemonade-data:/opt/lemonade/.cache/lemonade \
  -v lemonade-config:/opt/lemonade/.config/lemonade \
  ghcr.io/lemonade-sdk/lemonade-server:v11.9.0
docker logs -f lemonade-spike
```

Expect a platform-mismatch warning. Record whether the server starts, and
separately whether the downloaded llama.cpp backend binary *executes* — the
failure mode to watch for is `Illegal instruction` / SIGILL once a model load is
attempted, because Rosetta has no AVX2. A server that answers `/health` but
cannot run a model is still a failure of route A.

**Route B, fallback.** `Dockerfile.arm64`, roughly fifteen lines:

```dockerfile
FROM debian:13
ADD https://github.com/lemonade-sdk/lemonade/releases/download/v11.9.0/lemonade-server_11.9.0-debian13_arm64.deb /tmp/l.deb
RUN apt-get update && apt-get install -y /tmp/l.deb && rm -rf /var/lib/apt/lists/*
EXPOSE 13305
CMD ["lemonade-server", "serve", "--host", "0.0.0.0", "--port", "13305"]
```

Build with `docker build --platform linux/arm64`. Confirm the exact `.deb` asset
name against the v11.9.0 release assets before writing it in.

The container needs outbound internet — it downloads both the llama.cpp backend
and the model at runtime.

**Test that proves it:**

```text
curl -sS http://localhost:13305/api/v1/health | tee tests/discovery/lemonade/evidence/01-health.json
docker exec lemonade-spike lemonade-server --version
```

Health returns HTTP 200 and a JSON body. `01-startup.txt` records which route
was used and why, with the pull/build output.

---

## Step 2 — Load a small non-thinking instruct model on the CPU backend

**Files:**
- `tests/discovery/lemonade/evidence/02-models.json` (new)
- `tests/discovery/lemonade/evidence/02-load.json` (new)

Do not hard-code a model id from documentation. Ask the server:

```text
curl -sS http://localhost:13305/api/v1/models | tee tests/discovery/lemonade/evidence/02-models.json
```

Pick the **smallest non-reasoning instruct GGUF** in the catalog — prefer a
`Qwen2.5-*-Instruct-GGUF` or `Llama-3.2-1B-Instruct-GGUF` style entry. This is
not a stylistic preference: the closing comment on issue #1759 reports that
grammar constraints leak into `reasoning_content` on Qwen3-class *thinking*
models and send them into a garbage loop. Choosing a thinking model would
produce a grammar failure caused by an upstream llama.cpp bug and mislead the
whole project. If the catalog entry is gated on Hugging Face, pick an ungated
one rather than wiring a token into a throwaway container.

Then pull and load it pinned to CPU:

```text
curl -sS -X POST http://localhost:13305/api/v1/pull \
  -H 'Content-Type: application/json' -d '{"model_name":"<ID>"}'
curl -sS -X POST http://localhost:13305/api/v1/load \
  -H 'Content-Type: application/json' \
  -d '{"model_name":"<ID>","llamacpp_backend":"cpu"}' \
  | tee tests/discovery/lemonade/evidence/02-load.json
```

**Test that proves it:** a non-streaming chat completion returns real text:

```text
curl -sS -X POST http://localhost:13305/api/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"<ID>","messages":[{"role":"user","content":"Say hello."}],"max_tokens":16}'
```

Nothing after this step is meaningful until this returns a completion.

---

## Step 3 — Question 3: does it report model identity?

**Files:**
- `tests/discovery/lemonade/probe.py` (new — created here, extended in steps 4
  and 5)
- `tests/discovery/lemonade/evidence/03-identity.json` (new)

Collect three identity surfaces and compare them:

1. `GET /api/v1/models` — `id`, `checkpoint`, `size`, `max_context_window`
2. `GET /api/v1/health` — `model`, `recipe`, `device`, `backend_url`, `pid`,
   `launch_command`
3. the `model` field on a chat completion response, streaming and non-streaming

**The discriminator that matters:** is the response's `model` field the loaded
checkpoint, or a verbatim echo of the request string? Test it by sending a
request whose `model` value differs in case or uses an alias, and comparing the
response against `/health`. Record separately whether *anything* exposes the
GGUF file's quantisation or hash — if identity is only a human-chosen label with
no content hash, say so, because
[SPECIFICATION.md:490](SPECIFICATION.md#L490) asks for a "deterministic shipping
configuration" and a label alone will not pin one.

**Test that proves it:** `probe.py --identity` writes `03-identity.json`
containing all three surfaces plus an `echo_test` block, and prints a verdict
line: `Q3 MODEL IDENTITY: YES | PARTIAL | NO`.

---

## Step 4 — Question 1: can it enforce a supplied grammar per request?

This is the highest-value step and the one most likely to come back "no". Budget
the most time here.

**Files:**
- `tests/discovery/lemonade/probe.py` (extended)
- `tests/discovery/lemonade/forbid_paris.gbnf` (new)
- `tests/discovery/lemonade/evidence/04-grammar-r1..r4.json` (new)

**The proof design.** The master plan requires "a grammar that forbids a token
the model would otherwise emit", so use a case with exactly one natural answer:

- Prompt: `"What is the capital of France? Answer with one word."`
- Grammar: `root ::= "Berlin" | "Madrid" | "Rome"`

"Paris" is not merely deprioritised — it is unreachable in that grammar. So the
result is binary and needs no token counting.

**Control run first.** Same prompt, no grammar, `temperature: 0`, three
repetitions. All three must return "Paris". Without this control the grammar
result proves nothing. Save as `04-grammar-r0-control.json`.

**Then four routes, each recorded with its full HTTP status and body:**

| Route | Request | Prior expectation |
|---|---|---|
| R1 | `grammar` field in the `/api/v1/chat/completions` body (the issue #1759 shape) | Unknown — the contradiction to settle |
| R2 | `response_format: {"type":"json_schema", ...}` with a schema whose enum excludes Paris | Undocumented for chat; likely ignored or 400 |
| R3 | `POST /api/v1/load` with `llamacpp_args` carrying a grammar flag | Expected 400 — issue #2018's allow-list names `-grammar-file` as blocked |
| R4 | POST directly to the llama-server `backend_url` read from `/api/v1/health`, with `grammar` | Expected YES — llama.cpp supports GBNF natively |

R4 is not optional. It separates *"llama.cpp cannot do this"* from *"Lemonade's
façade does not pass it through"*, and those two answers lead to completely
different week-four decisions: the first kills grammar-constrained generation,
the second is a patch, a fork, or talking to the backend port directly.

**Classify every route into exactly one of three verdicts:**

- **ENFORCED** — output is one of Berlin/Madrid/Rome. Grammar works.
- **REJECTED** — HTTP 4xx naming the unsupported parameter. Grammar does not
  work, but a startup capability probe *can* detect it.
- **SILENTLY IGNORED** — HTTP 200 and the output is "Paris". Grammar does not
  work *and* nothing distinguishes a constrained request from an unconstrained
  one.

That third outcome is the one the project must not discover late.
[docs/master_plan.md:222-236](docs/master_plan.md#L222-L236) instructs item 9 to
"treat silently-ignored grammar as a hard engine failure, not a warning" — and
if R1 lands there, the only mechanism that can detect it is a canary request of
exactly this shape at startup. If that is what happens, say so in FINDINGS.md
and hand item 9 the canary as a concrete design output.

**Test that proves it:** `probe.py --grammar` prints the control result, then
one line per route, then `Q1 GRAMMAR: YES | NO (rejected) | NO (silently
ignored) | PARTIAL (backend only)`.

---

## Step 5 — Question 2: can a request be cancelled mid-generation?

**Files:**
- `tests/discovery/lemonade/probe.py` (extended)
- `tests/discovery/lemonade/evidence/05-cancel.json` (new)

There is no documented cancel endpoint, so the mechanism under test is client
disconnect. Confirm that first by re-reading `/api/v1/docs` or the OpenAPI
schema on the running container and recording that no cancel route exists.

Cancellation means the *compute stops*, not that the client stops listening.
Measure it:

1. Start a long generation — a prompt like `"Write a 2000 word essay about
   protein folding."` with `max_tokens: 2000`, `stream: true`.
2. Read a handful of SSE chunks, then **close the socket** (`http.client`
   connection `.close()`; with `curl`, send SIGKILL rather than letting it
   drain).
3. Sample container CPU for 15 seconds:
   `docker stats --no-stream lemonade-spike` in a loop, plus
   `docker logs --since 20s lemonade-spike`.
4. Verdict: CPU falls to idle within a couple of seconds → cancelled. CPU stays
   pegged until the full 2000 tokens would have completed → **not** cancelled,
   which is issue #119's original symptom.

Repeat the same disconnect for a **non-streaming** request. These can differ,
and item 9's interface needs both — the agent will not always be streaming.

Also record the **latency to cancel** and whether a *subsequent* request is
blocked while the abandoned one drains. A cancellation that takes twenty seconds
to take effect is functionally a "no" for an interactive PyMOL copilot, and
should be written down as such rather than scored as a pass.

**Test that proves it:** `probe.py --cancel` writes `05-cancel.json` with the
CPU timeline for both modes and prints
`Q2 CANCELLATION: YES (streaming) / YES|NO (non-streaming), latency Xs`.

---

## Step 6 — Question 4: CPU and integrated GPU

**Files:**
- `tests/discovery/lemonade/evidence/06-cpu.json` (new)
- `tests/discovery/lemonade/evidence/06-gpu-absent.txt` (new)

**CPU half — prove it, do not assume it.** With the model loaded via
`llamacpp_backend: "cpu"` from step 2:

```text
curl -sS http://localhost:13305/api/v1/health | tee tests/discovery/lemonade/evidence/06-cpu.json
```

`device` must read `cpu`, and `launch_command` must show no GPU offload (no
`-ngl`/`--n-gpu-layers` with a non-zero value). Record tokens/sec from
`/api/v1/stats` for a fixed prompt, so week four has a baseline. Under emulation
(route A) this number is meaningless for planning — label it if so.

**iGPU half — prove the absence.** Per the decision above, the answer is NOT
PROVEN ON THIS MACHINE, and the evidence file must make that a demonstrated
fact rather than an assertion:

```text
docker exec lemonade-spike ls -la /dev/dri   # expect: No such file or directory
docker exec lemonade-spike ls -la /dev/kfd   # expect: No such file or directory
docker exec lemonade-spike vulkaninfo --summary 2>&1 | head -30
curl -sS http://localhost:13305/api/v1/system-info
```

`/api/v1/system-info` enumerates detected devices and per-recipe support — save
it; it is the server's own statement that it sees no GPU. Then write down what
*would* close the question, so it is an hour's work on the right host and not a
fresh investigation:

- an x86-64 Linux host with an AMD iGPU, `--device=/dev/kfd --device=/dev/dri
  --group-add video --group-add render`, `llamacpp_backend: "rocm"`, verified by
  `device` reading `gpu` in `/api/v1/health`;
- or Vulkan on an Intel/AMD iGPU with `--device=/dev/dri` and
  `llamacpp_backend: "vulkan"`;
- and the note that Lemonade's own auto-selection tries Vulkan first and falls
  back to CPU silently, so `device` in `/health` must be asserted rather than
  trusted.

**Test that proves it:** `06-cpu.json` shows `device: cpu` with a recorded
tokens/sec; `06-gpu-absent.txt` contains the four command outputs above.

---

## Step 7 — Write the four answers

**Files:**
- `tests/discovery/lemonade/FINDINGS.md` (new) — the deliverable
- `tests/discovery/lemonade/README.md` (updated)

`FINDINGS.md` opens with a verdict table and nothing else above it:

| # | Question | Verdict | Evidence |
|---|---|---|---|
| 1 | Enforce a supplied grammar per request | YES / NO / NO (silently ignored) / PARTIAL (backend only) | `evidence/04-*` |
| 2 | Cancel a request mid-generation | YES / NO, latency | `evidence/05-cancel.json` |
| 3 | Report model identity | YES / PARTIAL / NO | `evidence/03-identity.json` |
| 4 | Run on CPU | YES / NO | `evidence/06-cpu.json` |
| 4 | Run on this machine's integrated GPU | **NOT PROVEN — Docker on Apple M2 Pro has no GPU passthrough** | `evidence/06-gpu-absent.txt` |

Then one section per question: what was asked, the exact command, the exact
response, the verdict, and — the part that earns the day — **what it means for
`src/pmc_agent/inference/` in item 9**. For any "no", state the consequence in
one sentence and name the options, without choosing one.

A final **Environment** section pins every version: Lemonade version, image
digest or `.deb` name, whether route A or B was used, host arch, emulation
status, llama.cpp backend build, model id and checkpoint. Every verdict above is
a claim about that exact configuration.

Update `README.md` to state, in the manner of
[tests/discovery/h02/README.md](tests/discovery/h02/README.md), that this
directory is a disposable prototype, that nothing in it is a production
contract, and that it is outside the Bazel graph by design.

---

## Verification (end to end)

From a clean checkout of the branch, with Docker running:

```text
# 1. The rig comes up and serves
docker compose -f tests/discovery/lemonade/compose.yaml up -d
curl -sS http://localhost:13305/api/v1/health

# 2. All four questions, from scratch
python tests/discovery/lemonade/probe.py --all

# 3. The repository gates stay green -- this is the part that is easy to miss
bazel test //...
bazel run //tools/quality:ruff -- check .
bazel run //tools/quality:ruff -- format --check .
bazel run //tools/quality:pyrefly -- check
```

`probe.py --all` prints exactly four verdict lines and exits non-zero only on a
*rig* failure — never on a capability answering "no", because "no" is a valid
result and must not read as a broken script.

The three gate commands are non-negotiable. `probe.py` sits inside pyrefly's
`tests` include at strict preset and inside ruff's tree, and `bazel test //...`
must be unaffected because the directory has no `BUILD.bazel`. Confirm that last
point explicitly with `bazel query 'tests/discovery/lemonade/...'`, which should
report no such package.

Finally, a human reads `FINDINGS.md` cold and can tell, without running
anything, whether item 9's engine interface is buildable as specified.

---

## Risks

| Risk | Where it shows | Mitigation |
|---|---|---|
| Rosetta has no AVX2; the amd64 llama.cpp binary dies with SIGILL | Step 1 route A, at first model load, not at server start | Route B: build `linux/arm64` from the Debian 13 arm64 `.deb`. Record route A's failure as evidence rather than retrying it |
| Grammar is silently ignored (HTTP 200, "Paris") | Step 4, R1 | This is the finding, not a bug in the spike. R4 against the raw backend separates a llama.cpp limit from a Lemonade passthrough gap; the canary request becomes a design output for item 9 |
| A thinking model is chosen and grammar fails for an unrelated upstream reason | Step 2 | Explicitly pick a non-reasoning instruct GGUF; issue #1759's closing comment documents the Qwen3 leak into `reasoning_content` |
| `probe.py` trips `CPY001`, `D`, `ANN` or pyrefly strict | Step 7's gate run, after all the interesting work is done | Copy the copyright header and docstring style from `tests/discovery/h02/harness.py` at the moment the file is created, and run ruff once at the end of step 3 rather than only at the end |
| Adding a `BUILD.bazel` out of habit drags the rig into the three-OS CI matrix | `bazel build //...` on ubuntu/macos/windows | Do not create one. Verify with `bazel query` in the verification block |
| The container cannot reach the internet and the model or backend never downloads | Step 2 | Check `docker logs` for the download; the rig needs outbound network by design |
| `device: cpu` is trusted rather than asserted | Step 6 | Lemonade auto-selects Vulkan first and falls back silently; assert on `/api/v1/health` `device` and `launch_command`, not on the absence of an error |
| The spike sprawls past a day chasing the grammar question | Step 4 | Four routes, time-boxed. If R1 and R4 disagree, that *is* the finding; do not start patching Lemonade |
