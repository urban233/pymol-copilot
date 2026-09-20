# Sidecar executor

## Context

This is item 4 of [docs/master_plan.md:139-152](docs/master_plan.md#L139-L152),
Hannah's, sized at ~3 days, and it is the item the whole week-one hand-off waits
on: *"Martin needs item 4 from Hannah before he can generate data."* Item 14
(dataset generation) executes every generated plan through `pmc_core.executor`;
item 7 (live extraction and fidelity gate) and item 8 (the LangGraph graph) both
call it once per attempt.

[SPECIFICATION.md:385](SPECIFICATION.md#L385) already names this component — the
**validation sidecar**, whose job is to *"reconstruct exact relevant session
state and execute a plan without touching the live session"*, taking a session
snapshot and a typed plan and returning *"a validation report and resulting
state evidence"* from a *"fresh Open-Source PyMOL process"*.
[SPECIFICATION.md:406-408](SPECIFICATION.md#L406-L408) defines the report as
*"evidence about parsing, policy, execution, selection counts, resource use,
warnings, and sidecar fidelity"* — and states it *"contains no
`verified-scientifically` state"*. Orchestration rule 8
([SPECIFICATION.md:537-538](SPECIFICATION.md#L537-L538)) requires *"a fresh
sidecar per attempt"*.

The prototype that proves this is buildable is
[tests/discovery/h02/execution_boundary.py](tests/discovery/h02/execution_boundary.py)
(734 lines) and its 13 probes in
[tests/discovery/h02/test_execution_boundary.py](tests/discovery/h02/test_execution_boundary.py)
(707 lines, 17 cases, ~28 s). It genuinely works: fresh process, wall-clock
deadline, hard kill, reap, scratch cleanup, typed reasons, no internal retry.
Four of its own findings are already fixed in it (H02-S3-F1, F2, F3, F10), and
the tests that caught them are the reason this promotion is low-risk.

**Outcome:** `src/pmc_core/executor.py` owns the typed contract and the process
boundary; a new `src/pmc_sidecar/` package owns the one module that imports
PyMOL; `src/pmc_server/validation.py` exposes it as a service behind
`/v1/validate`. Every negative test survives, plus new ones for the two
capabilities the prototype never had — **selection counts** and a **closed
verb dispatch**.

### Start from an updated `main` — this branch is stale

The working branch `spike/promote-h02-snapshot` is **behind** `origin/main`.
`origin/main` has since merged both PR #28 (this branch's own snapshot work,
`5044a53`) and, critically, **PR #27, the real 5-verb command language**
(`260f287`). `src/pmc_core/plan.py` on `origin/main` is no longer the
fixture-literal module in the local working tree: it has `SelectOperation`,
`ColorOperation`, `ShowOperation`, `HideOperation`, `OrientOperation`, a
`COMMAND_ALLOWLIST` table of `VerbRule` rows, a `SelectionExpression` grammar,
a frozen `COLOR_ALLOWLIST`, `MAX_COMMANDS = 128`, and a
`referenced_selection_name()` helper.

Every file reference below is to `origin/main`, not to the local tree. Before
any file is touched:

```text
git checkout main && git pull --ff-only
git log --oneline -3          # expect 260f287 restricted-command-language at or near HEAD
git checkout -b feat/sidecar-executor
```

The first commit on the branch is this plan, copied verbatim to
`plans/05-sidecar-executor.md` — matching plan 01's convention. `03` and `04`
are already taken (`03-restricted-command-language.md` on `origin/main`,
`04-structure-card.md` on `origin/spike/promote-m02-card`), so **05** is the
next free number.

### Decisions taken (from the clarifying questions)

These were answered directly and are not open:

- **A new `src/pmc_sidecar/` package holds the PyMOL-touching child.**
  `pmc_core/executor.py` stays free of both `pymol` and `winstage` and launches
  `python -m pmc_sidecar.child` **by module name**, so there is no Bazel edge
  from `pmc_core` into it and the dependency-boundary gate stays green. The
  child stops being a string literal and becomes a real linted, type-checked,
  independently testable module (this closes H02-S3-F6).
- **Write against the 5-verb language now.** All of `select`, `color`, `show`,
  `hide`, `orient` are dispatched, off the typed operation dataclasses on
  `origin/main`. No `getattr(cmd, verb)` anywhere —
  [SPECIFICATION.md:486](SPECIFICATION.md#L486) requires *"no raw-text
  execution"*, and the prototype's `getattr` is the one line of it that must not
  be promoted.
- **Leave `ValidationReportV1` alone; add a new wire type.**
  [src/pmc_core/protocol.py:538](src/pmc_core/protocol.py#L538) keeps its
  `status`/`snapshotDigest`/`warnings` shape and its `"passed"`-only decode for
  the existing loopback path. The sidecar gets its own `ExecutionReportV1`.
- **Fault injection is a test-owned child module.** `execute()` takes the runner
  module as a defaulted, keyword-only seam. The production child has no
  `__crash__`/`__sleep__`/`__count_then_fail__` verbs at all; the sabotage
  runner lives in `tests/integration/`. This also closes H02-S3-F7.

### Decisions I took, stated so you can overrule them

- **Policy is re-evaluated before any process is spawned.** Orchestration rule 7
  ([SPECIFICATION.md:534-536](SPECIFICATION.md#L534-L536)) says *"Parsing and
  command policy run before every execution attempt."* The intent's fail-closed
  list does not name policy denial, but the check is one call to
  `pmc_core.policy.evaluate_plan` and the alternative is an execution boundary
  that trusts its caller. Adds `REASON_POLICY_DENIED`.
- **Two digests, not one.** `input_digest` reuses
  [`snapshot.structure_digest()`](src/pmc_core/snapshot.py#L510) so it matches
  the repository's existing `"sha256:<hex>"` `snapshotDigest` wire convention.
  `resulting_fingerprint` is a fresh SHA-256 over the **whole** canonical
  extraction (`to_json(extract(...))`), because `structure_digest` deliberately
  excludes `view`/`settings`/`enabled` and would therefore be blind to
  `orient`. Both are `"sha256:"`-prefixed, unlike the prototype's bare hex.
- **`input_digest` is populated on rejection whenever the snapshot parsed.** The
  prototype's `_rejected()` hardcodes `None` while its docstring promises
  otherwise — H02-S3-F8, a real docstring/implementation mismatch. Fixed here
  rather than carried forward.
- **Process-group teardown, and a bounded post-kill drain.**
  `start_new_session=True` on POSIX plus `os.killpg`; `CREATE_NEW_PROCESS_GROUP`
  on Windows. The post-kill `communicate()` gets its own timeout (H02-S3-F4 —
  today it is unbounded and only latent because this child never forks; a real
  PyMOL child may).
- **No memory bound.** The intent asks for finite input size and a finite
  wall-clock deadline, and names neither memory nor `RLIMIT_AS`. H02-S3-F14 stays
  open, recorded in the new module's docstring rather than silently dropped.
  `RLIMIT_AS` against a process that loads PyMOL plus NumPy is its own
  investigation and would not fit these three days honestly.
- **`src/pmc_server` joins pyrefly's `project-includes`.** It is absent today
  ([pyproject.toml:112](pyproject.toml#L112)), so the new service would ship
  unchecked. Step 8 adds it — see that step's stop condition if it surfaces more
  than a handful of pre-existing errors.

---

## Delivery: one branch, one PR

Steps 1–9 ship together. They are not independently mergeable: step 2 adds a
module with no child to spawn, step 4 is untestable before step 3, and step 9
deletes the prototype that steps 5–6 port their evidence out of. Splitting them
puts `main` through a knowingly red intermediate state.

One commit per step, in order, so the PR reads as the sequence it is. Link the
PR to an issue per [CONTRIBUTING.md](CONTRIBUTING.md).

Note [.github/CODEOWNERS](.github/CODEOWNERS): `/src/pmc_core/` is `@kullik01`,
but every `**/BUILD.bazel` and `pyproject.toml` is `@urban233` — steps 1 and 8
will pull Martin in as a required reviewer.

---

## Step 1 — Create the `src/pmc_sidecar/` package and wire all four gates

**Files**

- `src/pmc_sidecar/__init__.py` (new) — docstring only, matching
  [src/pmc_core/\_\_init\_\_.py](src/pmc_core/__init__.py)'s one-line form.
- `src/pmc_sidecar/BUILD.bazel` (new) — `py_library(name = "pmc_sidecar",
  imports = [".."], deps = ["//src/pmc_core:pmc_core",
  "//tools/winstage:winstage", "@pypi//pymol_open_source_whl"])`, visibility
  `["//src:subsystems", "//src:tests"]`.
- [tools/winstage/BUILD.bazel](tools/winstage/BUILD.bazel) — add
  `"//src/pmc_sidecar:__pkg__"` to the enumerated `visibility` list. That list is
  the primary guard; without this edit the package cannot build.
- [tools/bazel/check_dependency_boundaries.py:9-25](tools/bazel/check_dependency_boundaries.py#L9-L25)
  — add `"//src/pmc_sidecar:pmc_sidecar"` to `FORBIDDEN`. `pmc_sidecar` reaches
  both `winstage` and real PyMOL, so it must never enter the `pmc_core` or
  `pmc_agent` closure. This is the same defence-in-depth entry `winstage` itself
  has, and it is what makes step 4's "spawn by module name, never import" a
  gate rather than a convention.
- [pyproject.toml:112](pyproject.toml#L112) — add `"src/pmc_sidecar"` to
  pyrefly's `project-includes`.

Do this first and alone. Every later step depends on the package existing, and a
boundary or visibility mistake here is much cheaper to find against an empty
package than against 400 lines of new code.

**Test that proves it**

```text
bazel build //src/pmc_sidecar:pmc_sidecar --lockfile_mode=error
bazel run //tools/bazel:check_dependency_boundaries --lockfile_mode=error
bazel query 'deps(//src/pmc_core:pmc_core)' | grep pmc_sidecar   # expect no output
bazel run //tools/quality:pyrefly -- check
```

The `grep` returning nothing is the load-bearing assertion: `pmc_core` must not
acquire this package, now or by accident later.

---

## Step 2 — The typed contract and parent-side validation, with no spawn yet

**Files**

- `src/pmc_core/executor.py` (new).
- [src/pmc_core/BUILD.bazel](src/pmc_core/BUILD.bazel) — add `"executor.py"` to
  `srcs`. No new `deps`: this module imports only the standard library plus its
  own package's `plan`, `policy` and `snapshot`.

Constants, carried from the prototype with `REASON_POLICY_DENIED` added:

```text
EXECUTOR_VERSION = 1
DEFAULT_MAX_SNAPSHOT_BYTES = 4 * 1024 * 1024
DEFAULT_DEADLINE_SECONDS   = 30.0
DEFAULT_KILL_GRACE_SECONDS = 5.0

STATUS_OK / STATUS_REJECTED / STATUS_FAILED
REASON_OK, REASON_OVERSIZED_INPUT, REASON_MALFORMED_INPUT,
REASON_UNSUPPORTED_SCHEMA_VERSION, REASON_POLICY_DENIED,
REASON_SNAPSHOT_DIGEST_MISMATCH,
REASON_SPAWN_OR_LOAD_FAILURE, REASON_TIMEOUT, REASON_CHILD_CRASH,
REASON_COMMAND_FAILURE, REASON_FIDELITY_MISMATCH
OUTCOME_OK / OUTCOME_ERROR
```

Types — frozen dataclasses, `tuple` not `list`, per the repository convention:

```text
CommandOutcome(index: int, verb: str, status: str, error: str | None)
SelectionCount(name: str, atom_count: int)

ExecutionRequest(
    executor_version: int,
    plan: ActionPlan,                 # typed, already bounded by MAX_COMMANDS
    snapshot_json: str,
    expected_snapshot_digest: str | None = None,
    max_snapshot_bytes: int = DEFAULT_MAX_SNAPSHOT_BYTES,
    deadline_seconds: float = DEFAULT_DEADLINE_SECONDS,
    expected_resulting_fingerprint: str | None = None,
)

ExecutionReport(
    executor_version: int,
    status: str, reason: str,
    input_digest: str | None,             # "sha256:..." via structure_digest
    resulting_fingerprint: str | None,    # "sha256:..." over full extraction
    selection_counts: tuple[SelectionCount, ...],
    command_outcomes: tuple[CommandOutcome, ...],
    child_pid: int | None,
    child_terminated: bool | None,
    elapsed_seconds: float,
    warnings: tuple[str, ...] = (),
)
```

This step ships **only** the parent-side validation half of `execute()`, in this
exact order, each returning a `STATUS_REJECTED` report with no process spawned
and no scratch directory created:

1. `request.executor_version != EXECUTOR_VERSION` → `UNSUPPORTED_SCHEMA_VERSION`
2. `len(snapshot_json.encode("utf-8")) > max_snapshot_bytes` → `OVERSIZED_INPUT`
3. `snapshot.from_json(...)` inside a `try`, with the prototype's three except
   clauses **in this order** (ordering matters — `json.JSONDecodeError` and
   `SnapshotDecodeError` are both `ValueError` subclasses):
   `JSONDecodeError → MALFORMED_INPUT`;
   `SnapshotDecodeError → UNSUPPORTED_SCHEMA_VERSION`;
   `(KeyError, AttributeError, TypeError, ValueError) → MALFORMED_INPUT`
4. `input_digest = structure_digest(parsed)` — set from here on, including on
   every rejection below (H02-S3-F8)
5. A supplied `expected_snapshot_digest` differs from `input_digest` →
   `SNAPSHOT_DIGEST_MISMATCH`
6. `policy.evaluate_plan(request.plan).allowed` is false → `POLICY_DENIED`

`execute()` never raises for any documented failure mode; every one is reported
through the returned report.

**Test that proves it:** `tests/contract/test_executor.py` (new), PyMOL-free,
plus a `py_test(name = "executor", size = "small")` in
[tests/contract/BUILD.bazel](tests/contract/BUILD.bazel) added to its
`test_suite(name = "all")`.

```text
bazel test //tests/contract:executor --lockfile_mode=error
```

Ports negative tests 1–5 (see the table in step 5) against a stub runner module
that is never reached, each asserting the typed `reason`, `child_pid is None`,
`child_terminated is None`, `command_outcomes == ()`, and an unchanged scratch
directory set. Plus one new case: a plan that `evaluate_plan` denies is rejected
with `REASON_POLICY_DENIED` and nothing spawned.

---

## Step 3 — `src/pmc_sidecar/child.py`: closed dispatch over the five verbs

**Files**

- `src/pmc_sidecar/child.py` (new) — a real module with a `main()` and an
  `if __name__ == "__main__":` guard, run as `python -m pmc_sidecar.child`.
- `src/pmc_sidecar/BUILD.bazel` — add it to `srcs`.

Startup order is fixed and must match
[src/pmc_data/generate_cli.py:53-57](src/pmc_data/generate_cli.py#L53-L57)
exactly: `winstage.ensure_importable()`, then `import pymol` /
`from pymol import cmd` (each with a `# pyrefly: ignore.` comment), then
`pymol.finish_launching(["pymol", "-qc"])`.

It reads three paths from `sys.argv`, exactly as the prototype does — snapshot
JSON in, plan JSON in, report JSON out — and writes the output with
`flush()` + `os.fsync()`. It exits through `os._exit(0)` on every path, because
PyMOL's headless shutdown can override a real exit code; the parent never reads
the child's exit status, only the presence and content of the output file.

**The dispatch is closed.** One `match` over the operation dataclass, one branch
per verb, rendering each argument through the operation's own typed fields:

```text
match operation:
    case SelectOperation():  cmd.select(op.selection_name, op.expression.render())
    case ColorOperation():   cmd.color(op.color, op.target.render())
    case ShowOperation():    cmd.show(op.representation, op.target.render())
    case HideOperation():    cmd.hide(op.representation, op.target.render())
    case OrientOperation():  cmd.orient(op.target.render())
    case _:                  record OUTCOME_ERROR, stop        # unreachable
```

`cmd.sync()` after each. On any exception: record
`CommandOutcome(index, verb, OUTCOME_ERROR, str(exc))`, set
`REASON_COMMAND_FAILURE`, and **`break`** — no retry, no later command attempted.
The `case _` arm is unreachable while `OPERATION` stays exhaustive and exists so
a sixth verb added to `plan.py` without a branch here fails closed rather than
silently succeeding.

Reconstruction uses
[`pmc_core.snapshot.reconstruct`](src/pmc_core/snapshot.py#L268) — the shipped,
full-fidelity candidate-A implementation — not the prototype's own minimal
`reconstruct()`, which its docstring explicitly disclaims as "not a
full-fidelity contender". A failure here reports `SPAWN_OR_LOAD_FAILURE`.

Plan serialization across the process boundary: reuse `protocol.py`'s existing
`_plan_commands` / `_decode_plan` round trip rather than inventing a second
encoding. If those stay module-private, promote them to public
`encode_plan(plan) -> list[dict]` / `decode_plan(value) -> ActionPlan` in
`protocol.py` and have `_plan_commands`/`_decode_plan` call them, so there is
exactly one plan wire encoding in the repository.

**Test that proves it:** `tests/integration/test_sidecar_child.py` (new) — drives
`child.main()` **in-process** against the module-scoped `real_pymol` fixture from
[tests/integration/snapshot_support.py](tests/integration/snapshot_support.py),
with no subprocess at all. This is the only place the five verbs are proven
against real PyMOL one at a time.

```text
bazel test //tests/integration:sidecar_child --lockfile_mode=error
```

`size = "large"`, `timeout = "moderate"`, `tags = ["exclusive"]`, and the
`pytest.main()` → flush → `os._exit(code)` `__main__` block every real-PyMOL
module in this repository carries.

Asserts: each verb produces `OUTCOME_OK` and the expected observable change
(`get_color_index`, `atom.reps`, `count_atoms`, a changed `get_view()` for
`orient`); an unknown color raises and stops at that index; a sixth synthetic
operation type hits the `case _` arm and fails closed.

---

## Step 4 — `execute()`: spawn, deadline, hard kill, reap, scratch cleanup

**Files**

- [src/pmc_core/executor.py](src/pmc_core/executor.py) (continued).

Signature:

```text
def execute(
    request: ExecutionRequest,
    *,
    runner_module: str = "pmc_sidecar.child",
    on_process_spawned: Callable[[subprocess.Popen[str]], None] | None = None,
) -> ExecutionReport
```

`runner_module` is the injectable seam step 5's sabotage tests use.
`on_process_spawned` stays exactly as the prototype defines it — test-only, and
the *only* hook between `Popen` and `communicate()`, which is what makes the
H02-S3-F3 regression guard reproducible.

Preflight the module before spawning: `importlib.util.find_spec(runner_module)`
returning `None`, or raising, is `REASON_SPAWN_OR_LOAD_FAILURE` with no process
spawned. Build the child's `PYTHONPATH` from the parent's own `sys.path` (drop
empty entries), which under Bazel carries the runfiles directories for both
`pmc_core` and `pmc_sidecar`. This is the one place the two packages meet, and
it is a string, not an import.

Carry forward verbatim, because each already has a test that fails without it:

- `scratch_dir = Path(tempfile.mkdtemp(prefix="pmc-executor-"))`, removed in an
  outer `finally` with `shutil.rmtree(..., ignore_errors=True)` covering every
  exit path. An OS error from `mkdtemp`, scratch-file preparation, or `Popen`
  becomes a typed `REASON_SPAWN_OR_LOAD_FAILURE` report rather than escaping.
- Every scratch-file read/write and subprocess pipe uses UTF-8 explicitly, so
  non-ASCII snapshot names and labels do not depend on the platform locale.
- `communicate(timeout=request.deadline_seconds)`; on `TimeoutExpired`, kill,
  then `communicate()` again to reap and drain → `REASON_TIMEOUT`.
- Output file missing after a clean `communicate()` → `REASON_CHILD_CRASH`, with
  child stderr truncated to `MAX_WARNING_BYTES` in `warnings`. Every command
  error is likewise truncated to `MAX_COMMAND_ERROR_BYTES` in both the child
  and the parent-side decoder, keeping typed reports within the response cap.
- `_close_pipe` + `_terminate_and_reap` in an **inner** `finally` that wraps
  everything after `Popen`, so the child is stopped and reaped *before* the outer
  `finally` deletes the directory it may still be reading (H02-S3-F3), and both
  pipe objects are closed even on the path `communicate()` never reaches (the
  Windows `ResourceWarning` follow-up).
- Fidelity is adjudicated in the **parent**: status `ok` plus a supplied
  `expected_resulting_fingerprint` that differs from `resulting_fingerprint`
  becomes `STATUS_FAILED` / `REASON_FIDELITY_MISMATCH`, even though every command
  succeeded.

Two changes from the prototype:

- **Process group.** `start_new_session=True` on POSIX and
  `creationflags=CREATE_NEW_PROCESS_GROUP` on Windows, with the kill path using
  `os.killpg(os.getpgid(pid), SIGKILL)` on POSIX and falling back to
  `process.kill()` if the group is already gone. The prototype relies on Bazel's
  sandbox to clean up anything PyMOL forks (H02-S3-F5); a server that spawns this
  in production has no sandbox.
- **Bounded post-kill drain.** The second `communicate()` gets
  `timeout=DEFAULT_KILL_GRACE_SECONDS` inside a `contextlib.suppress`, so a child
  holding its pipes open cannot hang `execute()` past its own deadline
  (H02-S3-F4).

**Test that proves it:** step 5 is this step's test. Until then:

```text
bazel test //tests/contract:executor --lockfile_mode=error   # still green
bazel run //tools/quality:ruff -- check .
bazel run //tools/quality:pyrefly -- check
```

---

## Step 5 — Port the spawning negative tests, with a test-owned sabotage child

**Files**

- `tests/integration/sabotage_child.py` (new) — a `py_library`, not a test. A
  second runner module honouring three sentinel verbs the production child does
  not have: crash (`os._exit(1)` before writing output), sleep (longer than the
  deadline), and count-then-fail (increment and fsync a counter file, then
  raise). It shares nothing with `src/pmc_sidecar/child.py`.
- `tests/integration/test_executor_boundary.py` (new).
- [tests/integration/BUILD.bazel](tests/integration/BUILD.bazel) — the new
  `py_library` plus a `py_test(name = "executor_boundary", size = "large",
  timeout = "moderate", tags = ["exclusive"])` depending on
  `//src/pmc_core:pmc_core`, `//src/pmc_sidecar:pmc_sidecar`,
  `:sabotage_child`, `@pypi//pymol_open_source_whl`, `@pypi//pytest`.

`tags = ["exclusive"]` is not optional — it is the documented fix for a real
Windows CI race between subprocess-spawning targets, and every sibling target
carries the same comment.

The full port map. Every ported test keeps all four of its original assertions —
a typed `reason`, no internal retry, no live child process, no scratch data:

| # | Prototype test | Lands in | Sabotage in the port |
|---|---|---|---|
| 1 | `oversized_input` | contract | `max_snapshot_bytes=10` |
| 2 | `malformed_input` | contract | `"{not valid json"` |
| 3 | `non_object_snapshot_json` (×5 params) | contract | `42`, `null`, `[]`, `"hello"`, `true` |
| 4 | `snapshot_missing_a_key` | contract | `del payload["name"]` |
| 5 | `incompatible_schema_version` | contract | `SNAPSHOT_VERSION + 1` |
| 6 | `spawn_or_load_failure` | integration | `coord = ["a","b","c"]` — survives `from_json`, PyMOL's `pseudoatom` rejects it |
| 7 | `wall_clock_timeout` | integration | sabotage sleep verb, `deadline_seconds=1.0` |
| 8 | `forced_child_crash` | integration | sabotage crash verb |
| 9 | `child_escapes_before_communicate` | integration | `on_process_spawned` raising |
| 10 | `pymol_command_failure` | integration | real `ColorOperation` with an off-allowlist colour |
| 11 | `failing_command_attempted_exactly_once` | integration | sabotage counter file |
| 12 | `fidelity_mismatch` | integration | `expected_resulting_fingerprint="sha256:" + "0"*64` |

Three of these carry techniques that must not be paraphrased away:

- **#11 is the most valuable test in the prototype.** Its own docstring records
  that #10 alone *"a child runner silently retrying the same failing command some
  number of times before recording one final failure would still satisfy
  (confirmed empirically)"*. The load-bearing line is
  `assert counter_path.read_text().strip() == "1"` — one real invocation, not
  one recorded outcome. Port the counter file, not just the assertion count.
- **#9 is the only test that fails when `_terminate_and_reap` is reverted**
  (evidence: 1 failed / 16 passed). It is the regression guard for the entire
  inner-`finally` design.
- **`_assert_process_not_running`** ports verbatim, including its deliberate
  Windows weakening — `poll()` only, because `os.kill(pid, 0)` is POSIX
  semantics and Windows recycles PIDs aggressively enough that probing after a
  reap can pass spuriously against an unrelated process. Keep the explicit
  `stdout.closed` / `stderr.closed` assertions: `filterwarnings = ["error"]`
  ([pyproject.toml:18](pyproject.toml#L18)) only catches a leaked pipe if the GC
  happens to run inside pytest's window, which is exactly why that leak stayed
  silent on Linux for a whole slice while breaking Windows CI immediately.

Note the scratch-prefix glob changes with the directory name:
`pmc-executor-*`, not `h02-execution-boundary-*`.

**Test that proves it**

```text
bazel test //tests/contract:executor //tests/integration:executor_boundary --lockfile_mode=error
```

Then prove the ported tests can still fail — the prototype's own evidence gives
the expected counts. Temporarily revert `_terminate_and_reap` to a no-op and
re-run: exactly the escape test (#9) must fail. Temporarily make the child retry
a failing command three times: exactly #11 must fail, and #10 must still pass.
Restore both.

---

## Step 6 — Selection counts, the resulting fingerprint, and the positive path

**Files**

- [src/pmc_sidecar/child.py](src/pmc_sidecar/child.py) (continued).
- [src/pmc_core/executor.py](src/pmc_core/executor.py) (continued).
- `tests/integration/test_executor_round_trip.py` (new) + its `py_test`.

Selection counts are the one reporting capability the prototype never had, and
both [docs/master_plan.md:139-152](docs/master_plan.md#L139-L152) and
[SPECIFICATION.md:406-408](SPECIFICATION.md#L406-L408) require them.

After every command succeeds, and before extraction, the child walks the plan in
order and collects each distinct selection name — the `selection_name` a
`SelectOperation` creates, plus whatever
[`plan.referenced_selection_name(op)`](src/pmc_core/plan.py) reports for the
others — then records `SelectionCount(name, cmd.count_atoms(name))` for each, in
first-appearance order. That helper already exists on `origin/main` and returns
`None` for an operation whose target is an expression rather than a named
selection, which is exactly the right semantics: nothing is counted for a
command that references no selection.

A selection that matches zero atoms is reported as `0`, not omitted and not an
error — a plan that selects nothing is a scientifically useful thing for the user
to be told, and [SPECIFICATION.md:407](SPECIFICATION.md#L407) puts selection
counts in the report rather than in the pass/fail decision.

`resulting_fingerprint` is then `"sha256:" + sha256(to_json(extract(cmd, name)))`.

**Test that proves it:** the positive path, ported from prototype test #13 and
extended. It computes its expected values **independently** — launching real
PyMOL in the test process via the `real_pymol` fixture, reconstructing, running
the same operations and extracting there, entirely outside the boundary under
test — never by running `execute()` a second time and comparing it to itself.

```text
bazel test //tests/integration:executor_round_trip --lockfile_mode=error
```

Asserts `STATUS_OK` / `REASON_OK`; `resulting_fingerprint` equal to the
independently computed one; `command_outcomes` equal to one `OUTCOME_OK` per
operation with the right indices and verbs; `selection_counts` equal to
independently computed `count_atoms` values; and, running `execute()` twice,
that both reports agree **and** that `child_pid` differs between them while both
report `child_terminated is True` — the "one fresh PyMOL process per attempt"
evidence a real caller can see without the test-only hook (H02-S3-F10).

---

## Step 7 — `ExecutionReportV1` on the wire

**Files**

- [src/pmc_core/protocol.py](src/pmc_core/protocol.py) — add `CommandOutcomeV1`,
  `SelectionCountV1`, `ExecutionReportV1`, and the public
  `encode_plan`/`decode_plan` from step 3.
- [tests/contract/test_protocol.py](tests/contract/test_protocol.py) — extend.

[`ValidationReportV1`](src/pmc_core/protocol.py#L538) is **not** touched: it keeps
its three fields and its `"passed"`-only decode, and the existing loopback path
keeps working unchanged.

`ExecutionReportV1` follows the module's established convention exactly — frozen
dataclass with `snake_case` fields, a hand-written `to_dict()` emitting
`camelCase` wire names, and a `from_dict` classmethod validating through
`_strict_object` / `_string` and raising `ProtocolDecodeError`. Wire fields:
`executorVersion`, `status`, `reason`, `inputDigest`, `resultingFingerprint`,
`selectionCounts`, `commandOutcomes`, `elapsedSeconds`, `warnings`.

`child_pid` and `child_terminated` are deliberately **not** on the wire. They are
local process-identity evidence for the caller that spawned the child; a PID from
another machine's process table is meaningless to a client and is exactly the
kind of internal detail
[src/pmc_server/transport.py](src/pmc_server/transport.py)'s empty-bodied error
responses exist to avoid leaking.

Unlike `ValidationReportV1`, this type's `from_dict` **must** accept every
`STATUS_*` and `REASON_*` value — a report that cannot represent a failure is
not a fail-closed contract.

**Test that proves it**

```text
bazel test //tests/contract:protocol --lockfile_mode=error
```

Round-trip fixtures for a successful report and for one report per fail-closed
reason; `_strict_object` rejection of an unknown field; and a `decode_plan`
round trip for at least one plan per verb.

---

## Step 8 — The server-side service and its endpoint

**Files**

- `src/pmc_server/validation.py` (new) — `PlanValidationService`.
- [src/pmc_server/transport.py:22](src/pmc_server/transport.py#L22) — add
  `VALIDATE_PATH = "/v1/validate"` and turn the handler's single hard-coded path
  check into a small `{path: handler}` mapping.
- [src/pmc_server/BUILD.bazel](src/pmc_server/BUILD.bazel) — add
  `validation.py` to `srcs` and `//src/pmc_sidecar:pmc_sidecar` to `deps`. The
  server is the process that actually spawns the sidecar, so it is the process
  that needs the child in its runfiles.
- [pyproject.toml:112](pyproject.toml#L112) — add `"src/pmc_server"` to pyrefly's
  `project-includes`.
- `tests/unit/test_validation_service.py` (new) + its `py_test` — PyMOL-free,
  beside [tests/unit/test_server_lifecycle.py](tests/unit/test_server_lifecycle.py).

`PlanValidationService` copies `PlanRequestLifecycle`'s shape exactly: a callable
class whose `__init__` takes keyword-only, default-valued seams so tests inject
determinism —

```text
def __init__(self, *,
    executor: Callable[[ExecutionRequest], ExecutionReport] = execute,
    timestamp_source: TIMESTAMP_SOURCE = _server_timestamp,
    max_snapshot_bytes: int = DEFAULT_MAX_SNAPSHOT_BYTES,
    deadline_seconds: float = DEFAULT_DEADLINE_SECONDS,
) -> None
```

`__call__` builds an `ExecutionRequest`, calls the executor **once** — the
service performs no retry of its own, matching the boundary's own guarantee and
orchestration rule 8's "a fresh sidecar per attempt" — and maps the result to
`ExecutionReportV1`. It passes the wire action plan's `snapshotDigest` as the
executor's `expected_snapshot_digest`, so the executor rejects a mismatched
plan/snapshot pair before spawning.

The transport keeps the existing 64 KiB request cap for `/v1/plan`, while
`/v1/validate` uses `MAX_EXECUTION_REQUEST_BYTES`: twice the 4 MiB decoded
snapshot budget for JSON-string escaping, plus 64 KiB for the action-plan
envelope. This makes the executor's own `oversized_input` boundary reachable
over HTTP without weakening the established plan endpoint.

The unit test injects a fake executor and never spawns anything. That is the
point of the seam: the service's mapping and its no-retry guarantee are provable
without real PyMOL, and the boundary's process behaviour is already proven by
steps 5 and 6.

**Stop condition on the pyrefly change.** `src/pmc_server` has never been type
checked. Add it, run pyrefly, and look at what falls out. A handful of
annotations in `lifecycle.py`/`transport.py` is in scope. If it surfaces more
than that, revert the `project-includes` edit, keep `validation.py` as it is,
and say so in the PR — bringing an unchecked package up to strict preset is its
own change and does not belong inside item 4.

**Test that proves it**

```text
bazel test //tests/unit:validation_service //tests/integration:loopback_transport --lockfile_mode=error
bazel run //tools/quality:pyrefly -- check
```

Asserts the mapping for a successful report and for every fail-closed reason;
that the injected executor is called exactly once per request; that an
unroutable path still returns 404; that `/v1/plan` retains its original bound;
and that a validation body larger than 64 KiB reaches the executor's typed size
check.

---

## Step 9 — Retire the prototype

**Files**

- Delete `tests/discovery/h02/execution_boundary.py`,
  `tests/discovery/h02/test_execution_boundary.py`,
  `tests/discovery/h02/conftest.py`, `tests/discovery/h02/BUILD.bazel`, and the
  now-empty `tests/discovery/h02/` directory.
- [tools/winstage/BUILD.bazel](tools/winstage/BUILD.bazel) — drop
  `"//tests/discovery/h02:__pkg__"` from `visibility`.
- [pyproject.toml:130-135](pyproject.toml#L130-L135) — drop
  `"tests/discovery/h02"` from pyrefly's `search-path`.
- [tests/discovery/README.md](tests/discovery/README.md) — `h02/` is gone;
  `m02/` is all that remains.
- [tests/integration/README.md](tests/integration/README.md) — add the executor
  boundary, the sabotage child and the round trip to its charter paragraph.
- [tests/contract/README.md](tests/contract/README.md) — add the executor's
  PyMOL-free validation evidence.
- [tests/integration/snapshot_support.py](tests/integration/snapshot_support.py)
  and its `py_library` `visibility` — drop the `//tests/discovery/h02:__pkg__`
  entry and the sentences in its comment describing h02's use of `real_pymol`.

This mirrors exactly what item 3 did to `harness.py`, and every README in this
repository states what its directory *owns* — leaving them stale is the failure
mode to avoid.

**Test that proves it**

```text
bazel query 'tests/discovery/h02/...' --lockfile_mode=error   # expect: no such package
bazel test //... --lockfile_mode=error
grep -rn "execution_boundary" . --include=*.py --include=*.md --include=*.bazel --include=*.toml
```

The `grep` should return only intentional prose references in `docs/` and
`plans/`, never a live import or Bazel label.

---

## Verification (end to end)

From a clean checkout of the branch, the full gate sequence from
[docs/development_setup.md](docs/development_setup.md), which is also what CI
runs on ubuntu-24.04, macos-15 and windows-2025:

```text
bazel version
bazel mod graph --lockfile_mode=error
bazel build //... --lockfile_mode=error
bazel test //... --lockfile_mode=error
bazel run //tools/bazel:check_dependency_boundaries --lockfile_mode=error
bazel run //tools/quality:ruff --lockfile_mode=error -- check .
bazel run //tools/quality:ruff --lockfile_mode=error -- format --check .
bazel run //tools/quality:pyrefly --lockfile_mode=error -- check
```

Then, specifically for this item:

1. `bazel query 'deps(//src/pmc_core:pmc_core)'` contains neither
   `//src/pmc_sidecar` nor `//tools/winstage` nor `pymol`.
2. `grep -rn "getattr(cmd" src/` returns nothing. No verb reaches PyMOL as a
   free string.
3. Every one of the 12 ported negative tests passes, and the two deliberate
   sabotage runs described in step 5 fail exactly the expected single test each.
4. The positive path's `execute()` runs produce different `child_pid` values and
   identical fingerprints, outcomes and selection counts.
5. `ls $TMPDIR | grep pmc-executor-` is empty after the whole suite.
6. On POSIX, `ps -eo pid,ppid,command | grep -c pymol` is unchanged before and
   after `bazel test //tests/integration:executor_boundary`.
7. CI is green on all three operating systems before the PR is marked ready —
   Windows is where the pipe-leak and exclusive-tag issues have historically
   surfaced, and neither reproduces on Linux.

---

## Risks

| Risk | Where it shows | Mitigation |
|---|---|---|
| `pmc_sidecar` accidentally enters `pmc_core`'s closure via a convenience import | `check_dependency_boundaries` in CI, possibly not until a later item | Step 1 adds it to `FORBIDDEN` before any code exists; the spawn is by module-name string and `find_spec`, never an import |
| The child cannot import `pmc_sidecar` under Bazel's runfiles layout | Step 4, first real spawn — surfaces as `SPAWN_OR_LOAD_FAILURE` on the positive path | `PYTHONPATH` built from the parent's own `sys.path`; `find_spec` preflight turns it into a typed reason rather than a hang; test targets dep on both packages |
| Process-group teardown behaves differently on Windows | Step 4, Windows CI only | `CREATE_NEW_PROCESS_GROUP` plus a `process.kill()` fallback when the group is already gone; the `poll()`-only assertion in `_assert_process_not_running` stays as-is rather than being strengthened to something Windows cannot honour |
| Adding `src/pmc_server` to pyrefly surfaces a pile of pre-existing errors | Step 8, after the interesting work is done | Explicit stop condition in step 8: revert the include, keep the service, report it. Do not fix an unchecked package inside this item |
| The ported tests are paraphrased and quietly stop being able to fail | Never — that is the danger | Step 5's two deliberate sabotage runs are the check; #11's counter file and #9's escape hook are named as non-negotiable |
| `render()` output is not what `cmd.select`/`cmd.color` actually want as a selection string | Step 3, against real PyMOL | Step 3 tests each verb in-process against `real_pymol` before any subprocess is involved, so a rendering bug surfaces without the boundary in the way |
| Three days is optimistic once the new package, the wire type and the endpoint are counted | The end | Steps 7 and 8 are the separable tail. If time runs out, ship steps 1–6 and 9 — the executor and its evidence — and carry the wire type and endpoint as a named follow-up rather than thinning the negative tests |
| `orient` changes only the camera, so `structure_digest` cannot see it | Step 6, silently — a passing test that proves nothing | `resulting_fingerprint` is over the full canonical extraction, not `structure_digest`; the round-trip test asserts a changed `get_view()` for `orient` explicitly |
