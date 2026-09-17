**Purpose:** the concrete sequence of work between the current code and V1, written as intents to hand to Claude Code sessions.

**Audience:** Martin Urban (urban233) and Hannah Kullik (kullik01).

**Authority:** [SPECIFICATION.md](https://github.com/urban233/pymol-copilot/blob/main/SPECIFICATION.md) defines V1. This document only sequences the work and sizes it.

**Written:** 2026-09-16

This plan assumes Opus for planning and Sonnet for implementation, with one developer owning the model and data half and the other owning the runtime half. Sizes are working days for one developer; they do not include calendar slack or review turnaround.

---

## Starting state

The repository implements one hard-coded fixture end to end — `select copilot_selection, chain A` followed by `color red, copilot_selection` — inside genuinely hardened safety scaffolding.

- **pmc_core** has a total parser, typed plan, default-deny policy and a strict wire protocol, but all of it is pinned to that one fixture. There is no general verb allowlist anywhere in the code.
- **pmc_client** and **pmc_server** run an authenticated loopback preview path that prints a plan and applies nothing. There is no `.pse`, no apply and no rollback.
- **pmc_data** has an independent oracle, a real-PyMOL verifier and a generator, covering two gold cases.
- **pmc_agent** and **pmc_train** are empty package boundaries.
- **tests/discovery/** holds working prototypes for the snapshot, the fresh-process executor and the structure card. They are prototypes by explicit policy, not production modules.
- The dependency closure is pytest, ruff, pyrefly, pymol-open-source-whl and numpy. There is no LangGraph, no Lemonade and no training stack.

---

## The session pattern

Two sessions per item. Opus plans, Sonnet builds, a fresh session each time.

**Opus** — plan mode, `shift+tab`:

```
<intent body from below>

Before planning: read the files I named and the tests around them.
Ask me about anything ambiguous instead of guessing.
Write the plan to plans/NN-name.md — numbered steps, the files each
step touches, and the test that proves each step works. Don't edit source.
```

**Sonnet** — fresh session:

```
Implement plans/NN-name.md exactly.
You may edit <paths> only. Stop and ask before touching anything else.
After each step run:
  bazel test //... && bazel run //tools/quality:ruff -- check . && bazel run //tools/quality:pyrefly -- check
A step isn't done until its test passes. If the plan turns out to be
wrong, stop and tell me — don't improvise around it.
```

**Cross-review** — the other developer, Sonnet, read-only:

```
Review this branch as a merge candidate: <branch>. Look for correctness
bugs, any path that could mutate the live PyMOL session without approval,
and tests that can't actually fail. Don't fix anything — just list findings
with file:line.
```

---

## Week 1 — everyone on the shared core

Nothing downstream is safe until these land. This is the one week that cannot be parallelized away.

----- PR#24 ### 0. Dependency split

**Owner:** Martin · **Size:** ~1 day

```
Split this repo's dependencies in two. Runtime: add langgraph and an HTTP
client to requirements.in and requirements_lock.txt so "bazel build //..."
and "bazel test //..." still pass on ubuntu-24.04, macos-15 and
windows-2025. Training: do NOT put torch, transformers or peft in the Bazel
closure — create a separate pinned requirements-train.txt plus a section in
docs/development_setup.md, and exclude src/pmc_train/ from the Bazel //...
closure and from pyrefly's project-includes. Verify CI is green on all three
operating systems before you stop.
```

### 1. Lemonade spike

**Owner:** Hannah · **Size:** ~1 day · **Do this on day one**

```
Throwaway spike, no production code. Install Lemonade locally, load any
small instruct model, and answer four questions in a markdown file: can it
enforce a supplied grammar per request, can a request be cancelled
mid-generation, does it report model identity, and does it run on CPU and on
this machine's integrated GPU. For grammar, prove it by supplying a grammar
that forbids a token the model would otherwise emit. If any answer is no,
say so plainly — I need to know now, not in week four.
```

This is the largest external unknown in the project. Find out before it is load-bearing.

### 2. Command language

**Owner:** Martin · **Size:** ~4–6 days · **Biggest single item**

```
Replace the fixture-literal plan language in src/pmc_core/plan.py,
parser.py and policy.py with a real restricted command language. Support
exactly these verbs: select, color, show, hide, orient. One typed operation
dataclass per verb; an explicit allowlist table mapping verb to permitted
argument forms; a total parser that never raises and returns either a typed
plan or a typed rejection carrying command index and category; and a
default-deny policy that re-checks the typed plan independently of the
parser.

Selection expressions: "chain X", "resi N" and "resi N-M", "resn XXX",
"name XX", "hetatm", "polymer", combined with and/or/not — nothing else.

Delete every FIXTURE_* constant. Keep render_pml() canonical and idempotent.
Add positive round-trip cases per verb, negative cases per rejection
category, and extend tests/adversarial/ with Python-evaluating forms, shell
metacharacters, file paths, load/save/fetch, and plugin invocations — every
one denied with zero execution. The existing policy sabotage test must still
pass.
```

### 3. Snapshot

**Owner:** Hannah · **Size:** ~3 days

```
Promote tests/discovery/h02/harness.py into src/pmc_core/snapshot.py as
production code: extract relevant live state from a PyMOL session into a
canonical structured snapshot, serialize deterministically, digest it,
reconstruct it in a fresh process. Candidate A is already the chosen
approach — don't re-litigate it. Carry the declared-unsupported set
(measurement objects, the polymer flag) forward as explicit markers, never
silent drops. Add a SNAPSHOT_VERSION constant. Move the differential tests
out of tests/discovery/ into a real test package, keeping their
real-PyMOL/exclusive Bazel tags.
```

### 4. Sidecar executor

**Owner:** Hannah · **Size:** ~3 days

```
Promote tests/discovery/h02/execution_boundary.py into
src/pmc_core/executor.py plus a server-side service. Contract: typed
ActionPlan plus canonical snapshot in, ValidationReport out. One fresh PyMOL
process per attempt, finite input size, finite wall-clock deadline, hard
kill and reap on timeout, scratch cleanup, no internal retry. Report
per-command outcome by index, resulting-state fingerprint, and selection
counts. Fail closed on malformed input, version mismatch, spawn failure,
crash, command failure and fidelity mismatch. Port the existing negative
tests — they're the valuable part of that prototype.
```

### 5. Structure card

**Owner:** Martin · **Size:** ~2 days

```
Promote tests/discovery/m02/card_candidate.py into src/pmc_core/card.py.
Keep it a pure function with no PyMOL import. Carry the golden-byte,
permutation-invariance, signed-zero, truncation and per-field-mutation tests
into tests/contract/. Add a CARD_VERSION constant that both the dataset
writer and the runtime prompt builder stamp into their output.
```

### 6. Error envelope

**Owner:** Martin · **Size:** ~2 days

```
Add src/pmc_core/errors.py: a normalizer turning a raw PyMOL execution
failure into a typed envelope — version, command index, verb, normalized
category, bounded normalized message — with "unknown" as a catch-all that
preserves bounded text rather than dropping it. Capture real error strings
by driving headless PyMOL with deliberately broken commands for each
supported verb, and check the captured corpus in as fixtures under
tests/data/. Add byte-equality tests so the same PyMOL failure normalizes
identically in the dataset pipeline and at runtime.
```

> **Hand-off after week 1.** Martin needs item 4 from Hannah before he can generate data. Hannah needs items 2 and 6 from Martin before her graph is meaningful. Everything after this runs in parallel.

---

## Hannah — the runtime

**Total:** ~18 days

### 7. Live extraction and fidelity gate

**Size:** ~3 days

```
In src/pmc_client/, extract the live PyMOL session into a canonical snapshot
via pmc_core.snapshot and send it with the plan request. Add a fidelity
check: reconstruct that snapshot in a sidecar, compare it against the live
session on the declared state scope, and record the outcome on the request.
If fidelity isn't exact, the request may still produce an inspectable plan,
but that plan must be marked non-applicable and copilot_apply must refuse
it. Test with modified coordinates, multiple states, alternate locations and
hetero atoms.
```

### 8. LangGraph request graph

**Size:** ~4 days

```
Build the request graph in src/pmc_agent/ using LangGraph. States: received,
preparing, generating, validating, pending_approval, plus terminal rejected,
expired, superseded, failed, cancelled and ask. Enforce at most one active
request and one pending plan per session; a new request supersedes the
pending one; pending plans expire. Allow one initial generation plus at most
two repair attempts, each fed the error envelope and each validated in a
FRESH sidecar. No model output may influence retry count, target object,
policy or approval. Replace the hardcoded fixture lifecycle in
src/pmc_server/lifecycle.py with this graph. Test every transition and
terminal state against a fake inference adapter.
```

### 9. Inference abstraction and Lemonade

**Size:** ~4 days

```
Add src/pmc_agent/inference/: a narrow engine interface — bounded completion
taking prompt, optional grammar, token limit, time limit, cancellation and
model identity — with two implementations, a fake adapter for tests and a
Lemonade adapter against a local Lemonade server. Probe capabilities at
startup using what the spike found; treat silently-ignored grammar as a hard
engine failure, not a warning. There is no remote fallback under any
condition. If the spike showed grammar can't be enforced, implement
syntax-only and record that limitation in the code and the readme rather
than pretending.
```

### 10. Approval, apply, recovery — the safety centerpiece

**Size:** ~5 days

```
Implement the approval path in src/pmc_client/: copilot_apply <plan-id>,
copilot_reject <plan-id>, copilot_rollback <plan-id>.

Apply re-verifies plan id, expiry, session id, current snapshot digest,
model identity and contract versions BEFORE doing anything. It saves a .pse
recovery point with user-only permissions before the first command executes,
then applies the canonical plan through the same dispatcher the sidecar
uses. It stops at the first failure, immediately restores the .pse, and
reports whether restoration itself compared clean; if restore fails, halt
Copilot and preserve the file. Rollback warns that it replaces the entire
session, then restores and consumes the snapshot.

Put the tests in tests/recovery/: a deliberate mid-plan failure restores
clean; every denial, expiry and rejection path makes zero live mutation; and
a deliberately injected mutation makes the no-mutation check fail.
```

### 11. Output and diagnostics

**Size:** ~2 days

```
Make copilot print what the specification promises: plan id and expiry,
resolved object, numbered canonical commands, selection counts, validation
warnings, fidelity status, an explicit statement of what was and wasn't
checked, and the exact approval and rejection commands to type. Add a health
command reporting server, engine, model and contract versions. Every failure
path must produce a bounded, actionable message — no tracebacks, no plan
text leaking through an error.
```

### 12. End-to-end suite

**Size:** ~3 days

```
Write end-to-end scenarios against real headless PyMOL: one intent through
preview, approve and apply; one deliberate mid-apply failure through
automatic recovery; a stale plan rejected after the session changed; a
denied command rejected before any sidecar execution; the server
unavailable. Every path asserts zero unapproved mutation. Include a sabotage
test proving the suite detects a mutation. Record p50 latency per stage on
this machine.
```

---

## Martin — data and model

**Total:** ~20 days

### 13. Prompt builder

**Size:** ~2 days

```
Add the prompt builder that turns a structure card plus a user intent into
the model prompt, and emits the grammar for the engine. Stamp card version,
grammar version and policy version into every prompt. The dataset generator
and the runtime must call this same code — add a parity test that fails if
they ever diverge.
```

### 14. Dataset generation

**Size:** ~5 days

```
Generalize src/pmc_data/ from the one chain-A/red fixture to the full
supported command surface. Program-first for each verb: emit a canonical
plan, compute the expected result independently without PyMOL (extend
oracle.py), execute the plan through pmc_core.executor, and keep the sample
only if every assertion passes. Record per sample: source structure identity
and checksum, card version, plan, assertions, PyMOL version, seed,
verification result. Build controlled structures covering multiple chains,
hetero atoms, multiple states and alternate locations. Aim for a few
thousand verified samples. Report the rejection rate per category honestly —
any category the oracle can't grade stays marked unsupported rather than
guessed.
```

### 15. Gold set, split, audit

**Size:** ~3 days

```
Hand-author a gold set spanning every supported category, with
natural-language intents a structural biologist would actually type. Build a
held-out split by source structure so no test structure appears in training.
Decontaminate: drop training samples whose intent is a near-duplicate of a
test intent. Write the manifest and datasheet — content hash, provenance,
license record, regeneration config. Spot-check fifty random labels by hand
and report the observed error rate as a number.
```

### 16. Eval harness and untuned baseline

**Size:** ~3 days

```
Build the offline eval harness: per sample, generate a plan, parse it,
policy-check it, execute it in a sidecar, grade against stored assertions.
Report TaskSuccess, syntax-valid rate, policy-denied rate, empty-selection
rate, abstention rate and repair success, broken out per category. Run it
against the UNTUNED BASE MODEL FIRST and commit those numbers before any
fine-tuning exists. That baseline is what the entire evaluation argument
rests on.
```

### 17. Fine-tuning

**Size:** ~5 days

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

### 18. Notebook

**Size:** ~3 days

```
Write the deliverable notebook: dataset generation, the oracle and its
conformance evidence, the label audit, the split, the untuned baseline, the
fine-tuning run, the per-category comparison, and the limits — every
deferred or unsupported category named, the exact operating system, PyMOL,
Python, Lemonade and model versions, and the licensing record. It has to
read standalone for someone who has never seen this repository.
```

---

## Joint

### 19. Integration

**Size:** ~3 days

```
Pair one trained model artifact with the runtime and run the end-to-end
suite against it. Measure integrated TaskSuccess against the offline number
and explain any gap rather than averaging it away. Then dry-run the demo:
one intent through apply, one deliberate failure through recovery, with the
other developer watching to check they can tell what's about to change
before apply is confirmed.
```

---

## Honest sizing

Nineteen items: about **30 working days for Martin** and about **28 for Hannah**. That is six weeks each of focused work; with five-day weeks and review turnaround it is seven or eight calendar weeks. If the course deadline is sooner than that, the schedule is short, and the lever is scope rather than speed.

**Already cut to reach this list** — all of which the specification permits reporting as deferred:

- the controlled PDB fetch flow
- the `label`, `set` and measurement command families
- quantization
- structure-conditioned grammar terminals
- multi-seed variance and ablations

**Not cuttable:**

- **Item 2, the real command language** — without it there is no product, only a hardcoded string.
- **Item 10, apply and recovery** — it *is* the safety story the presentation depends on.

If further compression is needed, the next cut is `orient`, `show` and `hide` from item 2, leaving `select` and `color`. That shrinks items 2, 14, 15 and 16 together, which is where the days actually are.
