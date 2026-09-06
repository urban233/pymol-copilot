# H-01: Hardened PyMOL Preview Implementation Plan

**Status:** Draft
**Owner:** Hannah Kullik (`kullik01`)
**Reviewer:** Martin Urban (`urban233`)
**Risk:** Normal
**Containment:** N/A — no flag; all changes are either strictly stricter
validation, a caught failure path, or additive test/dependency wiring; valid
existing V1 payloads keep decoding successfully.
**Slices:** One pull request, two internal steps each independently testable:
  1. *Behavior-vertical* — codec/command hardening (H-A2–H-A5) against the
     existing test-double suite; no new dependency.
  2. *Behavior-vertical* — real-PyMOL dependency, fixture, and integration
     harness (H-A1, H-A6, H-A7).
**Base commit:** `6d8f012951356d8460243d24e193a24a79ca0eff` (branch `codev/H-01`)
**Issue/work item:** [#10](https://github.com/urban233/pymol-copilot/issues/10)
**Brief/design/API:** [Wave plan § H-01](../../wave/pymol-copilot.md#h-01-implement-the-hardened-pymol-preview),
[client-server contract](../../../../SPECIFICATION.md#apis-protocols-and-contracts),
[failure behavior](../../../../SPECIFICATION.md#failure-modes-and-resilience),
[process architecture](../../design/runtime-application/process-architecture.md)

## Focus card

- **Change:** Close the two known failure-boundary gaps in the V1 codec/command
  seam, make `copilot`'s success output honest about what it did (and didn't)
  do, and add automated real-PyMOL registration/invocation evidence proving
  the preview never mutates a session.
- **Success:** All H-A1–H-A8 acceptance criteria in the wave plan pass with
  linked evidence in `docs/codev/wave/evidence/H-01.md`.
- **Non-goals:** No new shared executor/snapshot API, no apply/fetch/rollback,
  no sidecar/inference wiring, no edits to `pmc_data`/`pmc_train`/`pmc_agent`.
- **Allowed scope:** `src/pmc_client/`, `src/pmc_core/protocol.py`, existing
  protocol/command/loopback/client-server tests, one new real-PyMOL
  integration test target and its fixture, `requirements.in`,
  `requirements_lock.txt` (root files, Martin-owned per CODEOWENRS — flagged
  explicitly for his review), and the H-01 evidence note.
- **Validation:** Existing focused Bazel targets, the new real-PyMOL target,
  and the repository-wide checks listed below.
- **Stop if:** The lock regeneration changes an existing pin (pytest/ruff/
  pyrefly) beyond adding the new package, or the real-PyMOL wheel fails to
  import under Bazel's hermetic CPython 3.13.13 toolchain (it imported cleanly
  in a disposable non-Bazel venv — see Repository evidence).
- **Work style:** Pair — the human (Hannah) is directing specific technical
  choices (the `pymol-open-source-whl` package, Bazel wiring) as we go.

## Repository evidence

- [`src/pmc_core/protocol.py:500-544`](../../../../src/pmc_core/protocol.py#L500-L544):
  `ValidatedPlanResponseV1.from_dict()` decodes `action_plan.snapshotDigest`
  and `validation.snapshotDigest` independently and never compares them to
  each other; only `LoopbackPlanClient.submit()` cross-checks both against
  the *request's* digest (`src/pmc_client/transport.py:106-117`).
- [`src/pmc_core/plan.py:42-56,79-91`](../../../../src/pmc_core/plan.py#L42-L91):
  `SelectOperation`/`ColorOperation.__post_init__` raise plain `ValueError`
  for any out-of-fixture value; [`src/pmc_core/protocol.py:376-404`](../../../../src/pmc_core/protocol.py#L376-L404)'s
  `_decode_command` constructs them directly from wire data, so a decoded
  out-of-fixture `select`/`color` command leaks that `ValueError` instead of
  `ProtocolDecodeError`.
- [`src/pmc_client/command.py:109-129`](../../../../src/pmc_client/command.py#L109-L129):
  `CopilotCommandClient.copilot()` calls `self._transport.submit(request)`
  with no exception handling; `LoopbackPlanClient.submit()`
  (`src/pmc_client/transport.py`) can raise `TransportError` from several
  paths (HTTP failure, oversized payload, decode failure, digest/correlation
  mismatch), and today that propagates uncaught out of the registered PyMOL
  command callback.
- [`src/pmc_client/command.py:143-157`](../../../../src/pmc_client/command.py#L143-L157):
  `_report_validated()` prints only `"copilot validation: passed"` and the
  rendered PML — no statement that this is an unexecuted, policy-checked
  preview.
- Environment probe (this session, disposable, non-Bazel venv,
  Python 3.13.12 host / target 3.13.13 hermetic toolchain, Linux x86_64,
  glibc 2.44): `pymol-open-source-whl==3.2.0.2`'s
  `cp313-manylinux_2_28_x86_64` wheel installs and imports; headless launch
  (`pymol.finish_launching(['pymol', '-qc'])`) succeeds; `cmd.extend()` +
  `cmd.do()` match the existing `CmdExtension` protocol
  (`src/pmc_client/command.py:26-36`) that `register_copilot()` already
  targets, so no adapter shim is needed. No PyMOL install exists anywhere
  else on the machine (checked PATH and all three local conda envs).
- `requirements.in`/`requirements_lock.txt`/`MODULE.bazel`/`pyproject.toml`
  are CODEOWNERS-assigned to `@urban233`; the wave plan states "Martin
  handles root dependency/lock changes if required" and "stop and coordinate
  if either lane requires shared API or root build changes that affect the
  other." Hannah was explicitly directed by the human to add this dependency
  and wire it into Bazel herself for this task; the PR will still route
  through Martin's CODEOWNERS review before merge.

## Proposed change

### Step 1 — codec/command hardening (no new dependency)

1. `src/pmc_core/protocol.py`: in `ValidatedPlanResponseV1.from_dict()`,
   after decoding both digests, raise `ProtocolDecodeError` when
   `action_plan_data["snapshotDigest"] != data["validation"]["snapshotDigest"]`.
   Test: `tests/contract/test_protocol.py` — new case builds a response with
   a diverging plan/report digest and asserts `ProtocolDecodeError`; existing
   round-trip test proves the matching case still decodes.
2. `src/pmc_core/protocol.py`: in `_decode_command()`, wrap the
   `SelectOperation(...)`/`ColorOperation(...)` constructor calls in
   `try/except ValueError as error: raise ProtocolDecodeError(...) from error`.
   Test: new case decodes a `select`/`color` command with an out-of-fixture
   value and asserts `ProtocolDecodeError` (not bare `ValueError`).
3. `src/pmc_client/command.py`: in `copilot()`, wrap
   `self._transport.submit(request)` in `try/except TransportError as error`
   and report a bounded diagnostic via `self._output` (no traceback, no plan
   text), mirroring the existing `_report_failure` message shape. Import
   `TransportError` from `pmc_client.transport`.
   Test: `tests/integration/test_command.py` — a transport double that
   raises `TransportError` produces one bounded output line and no
   exception escapes `copilot()`.
4. `src/pmc_client/command.py`: update `_report_validated()`'s success text
   to state this is a fixed, policy-checked preview, that loaded-state
   fidelity/execution/scientific intent were not validated, and that nothing
   was applied; do not describe the snapshot digest as a computed checksum.
   Update the existing output-shape assertions in `test_command.py`
   accordingly.

### Step 2 — real-PyMOL dependency and integration harness

5. `requirements.in`: add `pymol-open-source-whl==3.2.0.2`.
6. Regenerate `requirements_lock.txt`:
   `uvx --from uv==0.12.5 uv pip compile requirements.in --python-version 3.13.13 --universal --generate-hashes --output-file requirements_lock.txt`,
   then `bazel mod deps --lockfile_mode=update`, `bazel mod tidy --lockfile_mode=update`,
   `bazel mod graph --lockfile_mode=error`. Diff-check that the existing
   pytest/ruff/pyrefly pins are unchanged.
7. Add a small controlled two-chain fixture structure (a synthetic minimal
   PDB with a handful of atoms on chain A and chain B, checked into
   `tests/integration/testdata/`) so the real-PyMOL check can assert
   selection membership and color without depending on Martin's fixture.
   Record its provenance (synthetic, authored for this task) and SHA-256 in
   the evidence note.
8. New test file (e.g. `tests/integration/test_real_pymol_command.py`) that,
   under a finite deadline: starts the real `pmc_server` loopback process,
   launches headless real PyMOL (`pymol.finish_launching(['pymol', '-qc'])`),
   loads the fixture, registers `copilot` via `register_copilot()` against a
   real `LoopbackPlanClient`, and covers:
   - success path: invoke, assert bounded/honest output, and that object
     names, atom coordinates, `chain A` selection membership, and colors are
     byte-for-byte unchanged pre/post;
   - typed-rejection path (server-returned failure) — same state check;
   - unavailable-server path (server not started / wrong port) — same state
     check;
   - sabotage case: deliberately mutate the loaded object between snapshots
     to prove the comparison actually detects a real change (this asserts
     the *test's* detection works, not the command — matches the wave plan's
     "deliberate mutation fails the comparison" requirement).
   Always terminate the PyMOL/server processes in a `finally` block; record
   cleanup evidence.
9. New `BUILD.bazel` target for the new test file, depending on
   `@pypi//pymol_open_source_whl` (exact normalized target name confirmed
   after lock regeneration), `//src/pmc_client`, `//src/pmc_core`, and
   `//src/pmc_server`; add it to the H-01 validation command list once named.
10. Write `docs/codev/wave/evidence/H-01.md` mapping H-A1–H-A8 to the exact
    commands, logs, and observations above.

## Validation

- `bazel test //tests/contract:protocol //tests/integration:command //tests/integration:loopback_transport //tests/integration:client_server_command --lockfile_mode=error` -> all pass, including new cases.
- `bazel test //tests/integration:real_pymol_command --lockfile_mode=error` (new target) -> real-PyMOL success/rejection/unavailable/sabotage evidence.
- `bazel build //... --lockfile_mode=error`
- `bazel test //... --lockfile_mode=error`
- `bazel run //tools/bazel:check_dependency_boundaries --lockfile_mode=error`
- `bazel run //tools/quality:ruff --lockfile_mode=error -- check .`
- `bazel run //tools/quality:ruff --lockfile_mode=error -- format --check .`
- `bazel run //tools/quality:pyrefly --lockfile_mode=error -- check`

## Risks and rollout

- Root dependency/lock/BUILD changes touch Martin-owned files; flagged above
  and will be visible as an explicit diff in the PR for his review.
- The wheel imported cleanly outside Bazel; it is not yet proven inside
  Bazel's hermetic CPython 3.13.13 sandbox (network/library isolation could
  differ). If it fails there, fall back to the plan's originally allowed
  path: document a separate, non-Bazel integration environment and keep the
  real-PyMOL suite explicitly outside `bazel test //...`, per the wave plan's
  "Real-PyMOL validation stays explicitly separate if it cannot run inside
  Bazel."
- No flag or rollout concern: this is local-only, non-mutating, preview-only
  behavior; nothing is exposed to production.

## Decisions needed

- None outstanding — the human already decided the dependency and Bazel-wiring
  approach. Only the "Stop if" condition above (Bazel-hermetic import
  failure, or an unexpected lock-pin change) would return here for a decision.

## Completion evidence

- **Delivered:** TBD
- **Changed:** TBD
- **Head commit/snapshot:** TBD
- **Validation actually run:** TBD
- **Acceptance evidence:** TBD
- **Scope deviations:** TBD
- **Known limitations:** TBD
- **Review state:** TBD
