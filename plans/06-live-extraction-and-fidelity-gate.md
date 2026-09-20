# Live extraction and fidelity gate

## Context

This is item 7 of
[docs/master_plan.md:190-203](docs/master_plan.md#L190-L203), Hannah's, sized
at ~3 days. It is the item that makes the `copilot` command tell the truth
about the session it is planning against.

Today [src/pmc_client/command.py:22-24](src/pmc_client/command.py#L22-L24)
ships a literal:

```python
FIXTURE_SNAPSHOT = StructureSnapshotV1(
    "1", "sha256:example-chain-a-digest", "one-object-chain-a-v1"
)
```

and the command's own closing line
([command.py:163-169](src/pmc_client/command.py#L163-L169)) admits it: *"The
snapshot value above is a fixture placeholder, not a computed structure
checksum."* The client never reads the live session, never computes a digest,
and holds no pending-plan state at all — `CopilotCommandClient` stores only a
transport, an output sink, two factories and a session id
([command.py:87-91](src/pmc_client/command.py#L87-L91)).

Everything this item needs already exists as proven, shipped machinery:

- [`pmc_core.snapshot`](src/pmc_core/snapshot.py) — `extract()` (:180),
  `reconstruct()` (:268), `to_json`/`from_json` (:404, :457),
  `structure_digest()` (:510) and `diff()` (:546), with
  `DECLARED_UNSUPPORTED` (:76) riding on every snapshot as an explicit
  marker.
- [`pmc_core.executor`](src/pmc_core/executor.py) — the fresh-process
  boundary: finite input size, finite deadline, SIGTERM→SIGKILL escalation,
  reap, scratch cleanup, typed reasons, no internal retry.
- [`pmc_sidecar.child`](src/pmc_sidecar/child.py) — the one module that
  imports real PyMOL.
- [tests/integration/test_snapshot_round_trip.py:202-235](tests/integration/test_snapshot_round_trip.py#L202-L235)
  already proves, in a genuinely separate process that never opens the source
  `.pdb`, that `diff(original, reconstructed)` is empty and the two structure
  digests agree for a fixture carrying two states, altlocs, a HETATM zinc and
  an insertion code.

What is missing is the wiring in `src/pmc_client/`, a sidecar entry point
that reconstructs *without* executing a plan, and the gate itself.

### What the specification requires

[SPECIFICATION.md:539-540](SPECIFICATION.md#L539-L540), orchestration rule 9:

> Exact relevant-state fidelity is mandatory for `pending_approval`. Static
> validation may produce an inspectable plan but never an applicable plan.

[SPECIFICATION.md:615](SPECIFICATION.md#L615), failure-mode table:

> Snapshot export or digest mismatch | Full validation unavailable |
> Differential fidelity check | **Apply command unavailable; plan may be
> copied only**

[SPECIFICATION.md:484](SPECIFICATION.md#L484), the snapshot contract row,
names the evidence this item owes: *"Differential fixtures including moved
atoms, altlocs, and multiple states"*, with the guarantee *"Equal digest means
equality for all state defined as relevant to V1 validation"* and the
consequence *"Export or comparison failure disables apply"*.

[SPECIFICATION.md:349](SPECIFICATION.md#L349) is the architecture diagram edge
this item finally draws: `B -->|exact live-state snapshot| S[Fresh
Open-Source PyMOL sidecar]`.

**Outcome:** `copilot` extracts the live object, computes a real digest, runs
a fidelity probe in a fresh sidecar, diffs the reconstruction against live on
the declared state scope, records the outcome on the request, and refuses to
mark the resulting plan applicable unless the diff is empty.
`copilot_apply <plan-id>` exists and refuses. Nothing mutates the live
session on any path.

### Decisions taken (from the clarifying questions)

- **The snapshot's *identity* rides `/v1/plan`; its bytes do not.** The
  64 KiB `MAX_MESSAGE_BYTES` cap on
  [src/pmc_client/transport.py:21](src/pmc_client/transport.py#L21) stays
  exactly as it is. `StructureSnapshotV1` stops being a fixture placeholder
  and carries a computed digest, the resolved object name, and atom/state
  counts; the fidelity outcome rides alongside it as its own typed
  sub-object. The full canonical JSON — up to the executor's 4 MiB budget —
  travels only where a sidecar actually needs it: locally, to the client's
  own fidelity probe in this item, and over `/v1/validate` (which already
  accepts `MAX_EXECUTION_REQUEST_BYTES`,
  [src/pmc_server/transport.py:38](src/pmc_server/transport.py#L38)) when
  item 8 wires server-side plan validation. **This item does not call
  `/v1/validate` from the client.**

  Be honest about the wording this trades away: master_plan says *"send it
  with the plan request"*, and what is sent is the canonical snapshot's
  identity plus the fidelity verdict, not its bytes. The bytes never leave
  the machine, and never cross a socket twice.

- **The client spawns the fidelity sidecar.** `pmc_client` calls
  `pmc_core.executor` directly, matching
  [SPECIFICATION.md:349](SPECIFICATION.md#L349) and orchestration rule 5
  (*"The client exports relevant live state"*). `//src/pmc_client:pmc_client`
  gains a Bazel `deps` edge on `//src/pmc_sidecar:pmc_sidecar` so the child
  module is in the client's runfiles. The comparison has to happen in
  PyMOL's process regardless — it is the only process holding the live
  session — so routing the spawn through the server would put the snapshot
  on the wire twice for nothing.

- **`copilot_apply` is refusal-only in this item.** Item 10
  ([docs/master_plan.md:238-258](docs/master_plan.md#L238-L258), ~5 days)
  owns the real approval path: identity re-verification, the `.pse` recovery
  point, the live dispatcher, restore-and-verify. This item registers
  `copilot_apply <plan-id>` and gives it exactly two outcomes, both with zero
  live mutation: it refuses a non-applicable plan with the fidelity reason,
  and for an applicable plan it reports that apply is not implemented yet.
  Item 10 replaces the second branch with a body; the first branch is already
  its gate.

- **The sidecar hands back its re-extraction; the client runs
  `snapshot.diff`.** Not a bare fingerprint comparison. A mismatch has to be
  inspectable — `state0.atom6.q expected=0.6 actual=0.4` is what makes the
  four required test categories assertable per-category and what the console
  can show a user. The existing `diff()` already produces exactly these
  strings and already carries the right tolerances (`1e-3` on coordinates and
  the view, exact on everything else).

### Decisions I took, stated so you can overrule them

- **"Declared state scope" means precisely what `pmc_core.snapshot.diff`
  compares.** There is no `state_scope` identifier anywhere in the repository
  today and this item does not invent one. The scope is: `schema_version`,
  `name`, `enabled`, every `AtomRecord` field across every state, `bonds`,
  `view`, `settings`, and `unsupported`. Everything outside it —
  measurement objects, representations outside `MOLECULE_REP_NAMES`, settings
  outside `SAFE_SETTINGS` — is outside the claim, which is exactly why
  `DECLARED_UNSUPPORTED` rides on every snapshot. The plan's user-facing
  output must say "exact on the declared scope", never "exact".

- **Target resolution is deterministic and fails closed.** `copilot` resolves
  exactly one molecular object: `cmd.get_names("objects")` filtered to
  `cmd.get_type(name) == "object:molecule"`. Zero or more than one is a
  bounded client-side failure with no request sent — no model call, no
  guessing which object the user meant. This is
  [SPECIFICATION.md:216](SPECIFICATION.md#L216) (*"One explicitly resolved
  active molecular object for normal planning"*); the controlled-fetch
  proposal for the zero case is preparation's job, not this item's.

- **The server also refuses to mark a plan applicable.** Belt and braces:
  `ValidationReportV1` gains an `applicable` boolean that
  `PlanRequestLifecycle` derives from the request's fidelity status, and the
  client's own `PendingPlan.applicable` is the **AND** of that flag and its
  own locally observed outcome. Either side saying no is enough. The client
  check alone would be sufficient today, but item 8 moves pending-plan
  ownership to the server graph, and a response type that cannot express
  "inspectable but not applicable" would have to be changed then anyway.

- **`execute()`'s process-management body is extracted, not duplicated.**
  `probe_fidelity()` needs the same spawn, deadline, kill, reap and scratch
  discipline `execute()` already has, and a second copy of that loop is the
  kind of code that rots apart. Step 2 moves it into one private helper both
  call. The twelve existing negative tests are the regression net, and they
  must pass **unchanged** — see that step's stop condition.

- **`src/pmc_client` joins pyrefly's `project-includes`.** It is absent from
  [pyproject.toml:101](pyproject.toml#L101) today, so the entire client ships
  unchecked. Step 1 adds it, with the same explicit stop condition plan 05
  step 8 used for `src/pmc_server`.

- **`//src/pmc_client:pmc_client` becomes a third dependency-boundary root.**
  [tools/bazel/check_dependency_boundaries.py:80](tools/bazel/check_dependency_boundaries.py#L80)
  checks only `pmc_core` and `pmc_agent`. The client runs *inside PyMOL's
  own interpreter*, which is the one process where the training stack or
  LangGraph must never appear — a stronger argument than either existing
  root has. Its forbidden set is `FORBIDDEN` minus the two entries this item
  deliberately adds (`pmc_sidecar`, and `winstage` transitively behind it).

- **`copilot` becomes slow, and that is not hidden.** Every invocation now
  launches a fresh headless PyMOL process. On the two-chain fixture that is
  seconds, not milliseconds. `INVOCATION_DEADLINE_SECONDS = 5.0` in
  [tests/integration/test_real_pymol_command.py:74](tests/integration/test_real_pymol_command.py#L74)
  is raised accordingly, and the probe carries the executor's own
  `DEFAULT_DEADLINE_SECONDS` so a hung child cannot wedge the user's PyMOL.
  No sidecar pooling — [SPECIFICATION.md:636-638](SPECIFICATION.md#L636-L638)
  forbids it until state-reset equivalence is proven.

---

## Delivery: one branch, one PR

Item 4 (the sidecar executor) merged to `main` as PR #33 while this item was
being planned — `origin/main` is now a strict superset of
`feat/sidecar-executor` (`pmc_core/executor.py` and `pmc_sidecar/child.py`
are unchanged; only `docs/master_plan.md`'s status table moved). Branch
directly from an updated `main`, not from the now-obsolete feature branch:

```text
git checkout main && git pull --ff-only
git checkout -b feat/live-extraction-fidelity-gate
```

Steps 1–10 ship together. They are not independently mergeable: step 2 adds
a parent with no child to spawn, step 6 is untestable before steps 2–3, and
step 7 rewrites output text that step 9's tests assert. One commit per step,
in order, so the PR reads as the sequence it is. Link the PR to an issue per
[CONTRIBUTING.md](CONTRIBUTING.md).

Note [.github/CODEOWNERS](.github/CODEOWNERS): every `**/BUILD.bazel` and
`pyproject.toml` is `@urban233`, so steps 1 and 3 pull Martin in as a
required reviewer. `/src/pmc_core/` is `@kullik01`.

---

## Step 1 — Wire the gates before writing any client code

**Files**

- `plans/06-live-extraction-and-fidelity-gate.md` (new) — this document,
  verbatim.
- [pyproject.toml:101](pyproject.toml#L101) — add `"src/pmc_client"` to
  pyrefly's `project-includes`.
- [tools/bazel/check_dependency_boundaries.py:25-35](tools/bazel/check_dependency_boundaries.py#L25-L35)
  — add `"//src/pmc_client:pmc_client"` to `FORBIDDEN_BY_ROOT` and
  `NAMES_BY_ROOT`, with forbidden set
  `FORBIDDEN - {"//src/pmc_sidecar:pmc_sidecar", "//tools/winstage:winstage"}`
  and names `TRAINING_NAMES + RUNTIME_NAMES` (the client is in PyMOL's
  interpreter; neither the training stack nor LangGraph belongs there).
  Extend the loop at :80 to three roots. Also correct the now-stale comment
  at :29 — `pmc_server` is no longer the only package that depends on the
  sidecar.
- [src/pmc_client/BUILD.bazel](src/pmc_client/BUILD.bazel) — add
  `"//src/pmc_sidecar:pmc_sidecar"` to `deps`, with a comment saying why
  (the client spawns the fidelity probe's child; `pmc_sidecar`'s visibility
  is already `//src:subsystems`, which covers this package).

Do this first and alone. A visibility or boundary mistake is far cheaper to
find against today's 191-line client than against the one step 7 leaves
behind.

**Stop condition on the pyrefly change.** `src/pmc_client` has never been
type checked. Add it, run pyrefly, look at what falls out. A handful of
annotations in `command.py`/`transport.py` is in scope. If it surfaces more
than that, revert the `project-includes` edit, keep the new modules
annotated to strict preset anyway, and say so in the PR.

**Test that proves it**

```text
bazel build //src/pmc_client:pmc_client --lockfile_mode=error
bazel run //tools/bazel:check_dependency_boundaries --lockfile_mode=error
bazel query 'deps(//src/pmc_core:pmc_core)' | grep pmc_client   # expect no output
bazel run //tools/quality:pyrefly -- check
```

The `grep` is the load-bearing assertion in the other direction: the new edge
runs client→sidecar only, and `pmc_core` must not acquire the client.

---

## Step 2 — `probe_fidelity()` in `pmc_core.executor`, sharing one spawn body

**Files**

- [src/pmc_core/executor.py](src/pmc_core/executor.py) — extract the
  post-validation body of `execute()` (everything from `mkdtemp` at ~:660 to
  the outer `finally` at :829) into one private helper, and add the new
  public request/report pair plus `probe_fidelity()`.

`ActionPlan.__post_init__` rejects an empty plan outright
([src/pmc_core/plan.py:1046-1047](src/pmc_core/plan.py#L1046-L1047):
*"plan must contain at least one command"*), and every real verb mutates
state, so a fidelity probe cannot be expressed as "run `execute()` with a
no-op plan". It needs its own entry point.

New shape:

```text
REASON_RECONSTRUCTION_FAILURE = "reconstruction_failure"   # new

FidelityRequest(
    executor_version: int,
    snapshot_json: str,
    max_snapshot_bytes: int = DEFAULT_MAX_SNAPSHOT_BYTES,
    deadline_seconds: float = DEFAULT_DEADLINE_SECONDS,
)

FidelityReport(
    executor_version: int,
    status: str,                              # STATUS_OK/REJECTED/FAILED
    reason: str,                              # a REASON_* constant
    input_digest: str | None,
    reconstructed_snapshot_json: str | None,  # None unless STATUS_OK
    child_pid: int | None,
    child_terminated: bool | None,
    elapsed_seconds: float,
    warnings: tuple[str, ...] = (),
)

def probe_fidelity(
    request: FidelityRequest,
    *,
    runner_module: str = "pmc_sidecar.fidelity",
    on_process_spawned: Callable[[subprocess.Popen[str]], None] | None = None,
) -> FidelityReport
```

The shared private helper takes the scratch inputs to write, the child's
argv tail, and the deadline, and returns the raw decoded child output plus
process evidence (`child_pid`, `child_terminated`, `elapsed_seconds`,
`warnings`) or a typed failure. `execute()` and `probe_fidelity()` each keep
their **own** pre-spawn validation and their own report mapping —
`probe_fidelity` has no plan, so it runs no policy evaluation and has no
`expected_snapshot_digest` or `expected_resulting_fingerprint`; its
validation is version → UTF-8 → size → `from_json` → `structure_digest`, in
that order, with the same three-clause except ladder `execute()` uses
(ordering matters: `JSONDecodeError` and `SnapshotDecodeError` are both
`ValueError` subclasses).

`probe_fidelity` never raises for a documented failure mode, exactly as
`execute()` does not. A child that reconstructs but cannot re-extract is
`STATUS_FAILED` / `REASON_RECONSTRUCTION_FAILURE`, distinct from
`REASON_SPAWN_OR_LOAD_FAILURE` (the child never got as far as a live object)
and from `REASON_CHILD_CRASH` (no trustworthy output file at all).

While here, promote `_bounded_diagnostic` to a public `bounded_diagnostic`
and update its two existing callers —
[src/pmc_sidecar/child.py:55](src/pmc_sidecar/child.py#L55) already reaches
across packages for the private name, and step 6 needs it too.

**Stop condition on the extraction.** The twelve ported negative tests in
`tests/contract/test_executor.py` and
`tests/integration/test_executor_boundary.py` must pass **unchanged** — not
adapted, not re-parameterized. If the helper cannot be carved out without
editing them, the extraction is wrong: stop, restore `execute()` byte for
byte, give `probe_fidelity` its own copy of the loop, and record the
duplication as a named follow-up in the PR rather than reshaping item 4's
evidence to fit item 7.

**Test that proves it:** `tests/contract/test_executor.py` (extend),
PyMOL-free.

```text
bazel test //tests/contract:executor --lockfile_mode=error
```

Adds `probe_fidelity`'s own pre-spawn rejections against a stub runner
module that is never reached — unsupported version, oversized snapshot,
malformed JSON, a non-object snapshot, a missing key, an incompatible
`schema_version` — each asserting the typed reason, `child_pid is None`,
`child_terminated is None`, `reconstructed_snapshot_json is None`, and an
unchanged `pmc-executor-*` scratch set.

---

## Step 3 — `src/pmc_sidecar/fidelity.py`: reconstruct, re-extract, report

**Files**

- `src/pmc_sidecar/fidelity.py` (new) — a real module with `main()` and an
  `if __name__ == "__main__":` guard, run as `python -m pmc_sidecar.fidelity`.
- [src/pmc_sidecar/BUILD.bazel](src/pmc_sidecar/BUILD.bazel) — add it to
  `srcs`.

A second runner module rather than a mode flag on
[child.py](src/pmc_sidecar/child.py): `child.main()`'s positional argv
contract `[snapshot_path, plan_path, output_path]` is shared with
[tests/integration/sabotage_child.py](tests/integration/sabotage_child.py)
and is proven by item 4's evidence. Widening it to carry a mode would
reshape that contract for every existing caller to serve a path that needs
neither a plan nor a dispatcher.

It reads two paths — snapshot JSON in, report JSON out — and follows
`child.py`'s startup order exactly: `winstage.ensure_importable()`, then
`import pymol` / `from pymol import cmd` (each with `# pyrefly: ignore.`),
then `pymol.finish_launching(["pymol", "-qc"])`. It writes with
`flush()` + `os.fsync()` and exits through `os._exit(0)` on every path, for
the same reason `child.py` does: PyMOL's headless shutdown can override a
real exit code, and the parent reads only the output file.

Body:

```text
parsed = from_json(snapshot_text)          # failure -> SPAWN_OR_LOAD_FAILURE
reconstruct(cmd, parsed)                   # failure -> SPAWN_OR_LOAD_FAILURE
reextracted = extract(cmd, parsed.name)    # failure -> RECONSTRUCTION_FAILURE
write {"status": STATUS_OK, "reason": REASON_OK,
       "reconstructed_snapshot_json": to_json(reextracted)}
```

It runs no plan, imports nothing from `pmc_core.plan` or `pmc_core.policy`,
and computes no diff — `diff()` runs in the parent, against the live
snapshot the child has never seen. The child's only job is to prove a fresh
PyMOL can be driven back to the state the snapshot describes.

**Test that proves it:** `tests/integration/test_sidecar_fidelity.py` (new)
— drives `fidelity.main()` **in-process** against the module-scoped
`real_pymol`/`loaded_fixture` fixtures from
[tests/integration/snapshot_support.py](tests/integration/snapshot_support.py),
with no subprocess at all, mirroring how
[test_sidecar_child.py](tests/integration/test_sidecar_child.py) proves the
five verbs.

```text
bazel test //tests/integration:sidecar_fidelity --lockfile_mode=error
```

`py_test(size = "large", timeout = "moderate", tags = ["exclusive"])`,
`data = ["conftest.py", "testdata/h02_full_v1_fixture.pdb"]`, deps on
`:snapshot_support`, `//src/pmc_core:pmc_core`, `//src/pmc_sidecar:pmc_sidecar`,
`@pypi//pymol_open_source_whl`, `@pypi//pytest`, and the
`pytest.main()` → flush → `os._exit(code)` `__main__` block.

Asserts: a faithful snapshot yields `STATUS_OK` and a
`reconstructed_snapshot_json` whose `from_json` round trip diffs clean
against the input; a snapshot with a non-numeric `coord` (survives
`from_json`, rejected by `pseudoatom`) yields `SPAWN_OR_LOAD_FAILURE`; an
object name that reconstruction produced under a different name yields
`RECONSTRUCTION_FAILURE` rather than an uncaught exception.

---

## Step 4 — The wire types: real snapshot identity and the fidelity outcome

**Files**

- [src/pmc_core/protocol.py:265-307](src/pmc_core/protocol.py#L265-L307) —
  rewrite `StructureSnapshotV1`; add `FidelityOutcomeV1`.
- [src/pmc_core/protocol.py:310-378](src/pmc_core/protocol.py#L310-L378) —
  add `fidelity` to `PlanRequestV1`.
- [src/pmc_core/protocol.py:603-610](src/pmc_core/protocol.py#L603-L610) —
  add `applicable` to `ValidationReportV1`.
- [tests/contract/test_protocol.py](tests/contract/test_protocol.py) — extend.

```text
StructureSnapshotV1(
    schema_version: str,   # str(pmc_core.snapshot.SNAPSHOT_VERSION)
    digest: str,           # "sha256:..." from structure_digest()
    object_name: str,      # the resolved live object
    atom_count: int,       # first state's atom count
    state_count: int,
)                          # wire: schemaVersion/digest/objectName/
                           #       atomCount/stateCount

FidelityOutcomeV1(
    status: str,                    # "exact" | "not_exact" | "unavailable"
    reason: str,                    # a pmc_core.executor REASON_* constant
    mismatch_count: int,            # total, before truncation
    mismatches: tuple[str, ...],    # at most MAX_FIDELITY_MISMATCHES
)                                   # wire: status/reason/mismatchCount/
                                    #       mismatches

PlanRequestV1(..., snapshot: StructureSnapshotV1,
                   fidelity: FidelityOutcomeV1, ...)

ValidationReportV1(status, snapshot_digest, applicable: bool, warnings)
```

`fixture_id` is **deleted**, not deprecated. It has exactly one producer
(the literal at [command.py:22](src/pmc_client/command.py#L22)) and both
ends of this protocol version in this repository.

New bounds beside the existing ones, so a hostile or pathological mismatch
list cannot push a request past the untouched 64 KiB transport cap:

```text
MAX_FIDELITY_MISMATCHES = 10          # carried; mismatch_count is the truth
MAX_FIDELITY_MISMATCH_BYTES = 200     # per string, via bounded_diagnostic
```

Three invariants `from_dict` enforces, because a fail-open decode here is the
whole gate:

1. `status` is one of the three literals; anything else is
   `ProtocolDecodeError`.
2. `status == "exact"` requires `mismatch_count == 0` and `mismatches == ()`.
3. `len(mismatches) <= MAX_FIDELITY_MISMATCHES` and
   `mismatch_count >= len(mismatches)`.

`ValidationReportV1` keeps its `"passed"`-only status decode
([protocol.py:647](src/pmc_core/protocol.py#L647)) — `applicable` is the
orthogonal axis rule 9 describes, and conflating the two is what makes
"inspectable but not applicable" unrepresentable.

**Test that proves it**

```text
bazel test //tests/contract:protocol --lockfile_mode=error
```

Round-trip fixtures for each of the three fidelity statuses; each of the
three invariants above rejected with `ProtocolDecodeError`; an unknown field
rejected by `_strict_object`; `applicable` round-tripping both ways; and a
`PlanRequestV1` carrying a full ten-mismatch outcome encoding to well under
`MAX_MESSAGE_BYTES`.

---

## Step 5 — `src/pmc_client/session.py`: resolve one object, extract it

**Files**

- `src/pmc_client/session.py` (new).
- [src/pmc_client/BUILD.bazel](src/pmc_client/BUILD.bazel) — add to `srcs`.

```text
class PyMOLSession(Protocol):    # the query surface extract() actually uses
    get_names, get_type, count_states, get_model, iterate, get_view, get

class TargetResolutionError(RuntimeError)

def resolve_target_object(cmd: PyMOLSession) -> str
def extract_live_snapshot(cmd: PyMOLSession, object_name: str)
        -> tuple[ObjectSnapshot, str]        # snapshot, structure digest
```

`resolve_target_object` filters `cmd.get_names("objects")` by
`cmd.get_type(name) == "object:molecule"` and raises
`TargetResolutionError` with a bounded message on zero
(*"no molecular object is loaded"*) or more than one (*"more than one
molecular object is loaded: a, b — load or delete objects so exactly one
remains"*). No fallback, no "first one wins", no model involvement.

The `Protocol` is structural and PyMOL-free, exactly like
[src/pmc_data/verifier.py:36](src/pmc_data/verifier.py#L36)'s — this module
must stay importable without PyMOL, since the wider client is, and every
`pmc_core.snapshot` entry point takes `cmd` as an untyped parameter anyway.

**Test that proves it:** `tests/contract/test_client_session.py` (new),
PyMOL-free, against a small hand-written fake `cmd` in the repository's
existing double style (frozen dataclass or plain class, no `unittest.mock`).

```text
bazel test //tests/contract:client_session --lockfile_mode=error
```

Asserts: exactly one molecule resolves to its name; zero molecules raises
with the bounded zero-message; two molecules raises and names both; a
session holding one molecule plus a measurement object
(`object:measurement`) resolves to the molecule, since `get_type` is what
separates them; and `extract_live_snapshot` returns a digest equal to
`structure_digest` of the snapshot it returns.

---

## Step 6 — `src/pmc_client/fidelity.py`: the gate

**Files**

- `src/pmc_client/fidelity.py` (new).
- [src/pmc_client/BUILD.bazel](src/pmc_client/BUILD.bazel) — add to `srcs`.

```text
FIDELITY_EXACT = "exact"
FIDELITY_NOT_EXACT = "not_exact"
FIDELITY_UNAVAILABLE = "unavailable"

@dataclass(frozen=True)
class FidelityOutcome:
    status: str
    reason: str                     # a pmc_core.executor REASON_* constant
    mismatches: tuple[str, ...]     # complete, unbounded, for the console
    live_digest: str
    reconstructed_digest: str | None

    @property
    def is_exact(self) -> bool:     # status == FIDELITY_EXACT

def check_fidelity(
    live: ObjectSnapshot,
    *,
    probe: Callable[[FidelityRequest], FidelityReport] = probe_fidelity,
    deadline_seconds: float = DEFAULT_DEADLINE_SECONDS,
) -> FidelityOutcome

def to_wire(outcome: FidelityOutcome) -> FidelityOutcomeV1   # truncates
```

`check_fidelity` serializes `live` with `to_json`, probes, and then:

- report status is not `STATUS_OK` → `FIDELITY_UNAVAILABLE`, carrying the
  report's own typed `reason`, no mismatches. A timeout, a crash, a spawn
  failure and a reconstruction failure all land here: *the check could not
  be performed*, which rule 9 treats identically to a failed check.
- report is `STATUS_OK` but its JSON will not decode → `FIDELITY_UNAVAILABLE`
  with `REASON_MALFORMED_INPUT`.
- decoded → `mismatches = diff(live, reconstructed)`; empty **and**
  `structure_digest` equal on both sides → `FIDELITY_EXACT`; otherwise
  `FIDELITY_NOT_EXACT`.

The digest check is deliberately redundant with the empty diff: they are
computed by different code over different field sets (`structure_digest`
excludes `view`/`settings`/`enabled`;
[snapshot.py:531](src/pmc_core/snapshot.py#L531)), and
[test_snapshot_round_trip.py:230-233](tests/integration/test_snapshot_round_trip.py#L230-L233)
already treats their agreement as the load-bearing cross-process claim. A
disagreement between them is itself a fidelity failure, reported as
`FIDELITY_NOT_EXACT` with a synthesized `digest disagreement` mismatch
string rather than silently trusting whichever ran last.

`probe` is a defaulted keyword seam so every branch above is testable
without spawning anything — the same shape
[PlanValidationService](src/pmc_server/validation.py)'s `executor` seam has.

`to_wire` truncates to `MAX_FIDELITY_MISMATCHES` entries, each through
`bounded_diagnostic(..., maximum_bytes=MAX_FIDELITY_MISMATCH_BYTES)`, and
sets `mismatch_count` to the **untruncated** length. The console gets the
full list; the wire gets a bounded one.

**Test that proves it:** `tests/contract/test_client_fidelity.py` (new),
PyMOL-free, with a fake probe.

```text
bazel test //tests/contract:client_fidelity --lockfile_mode=error
```

Asserts: an identical re-extraction is `FIDELITY_EXACT` with no mismatches;
a perturbed re-extraction (one atom's `q`, one coordinate, one extra state)
is `FIDELITY_NOT_EXACT` with the field-level strings `diff` produces; each
of `STATUS_REJECTED`, `REASON_TIMEOUT`, `REASON_CHILD_CRASH`,
`REASON_SPAWN_OR_LOAD_FAILURE` and `REASON_RECONSTRUCTION_FAILURE` becomes
`FIDELITY_UNAVAILABLE` carrying that reason; undecodable JSON becomes
`FIDELITY_UNAVAILABLE`; a re-extraction that diffs clean but digests
differently is `FIDELITY_NOT_EXACT`, not exact; and `to_wire` on a
50-mismatch outcome carries 10 strings with `mismatch_count == 50`, each
within the byte bound.

---

## Step 7 — `command.py`: a real request, a pending plan, and `copilot_apply`

**Files**

- [src/pmc_client/command.py](src/pmc_client/command.py) — substantially
  rewritten.

`register()` gains a second registration and `CopilotCommandClient` gains
the live `cmd` and one slot of pending-plan state:

```text
cmd.extend("copilot", self.copilot)
cmd.extend("copilot_apply", self.copilot_apply)

@dataclass(frozen=True)
class PendingPlan:
    plan_id: str
    session_id: str
    snapshot_digest: str
    applicable: bool
    fidelity: FidelityOutcome
```

`copilot(intent)` becomes:

1. `resolve_target_object` — `TargetResolutionError` prints a bounded
   diagnostic and returns. Nothing is sent.
2. `extract_live_snapshot` — an exception here prints a bounded diagnostic
   and returns. Nothing is sent.
3. `check_fidelity` — always runs, whatever it returns.
4. Build `PlanRequestV1` with the real `StructureSnapshotV1` (computed
   digest, resolved object name, first-state atom count, state count) and
   `to_wire(outcome)`.
5. Submit, and on a validated response store exactly one `PendingPlan` with
   `applicable = response.validation.applicable and outcome.is_exact`.
   A new request replaces the previous pending plan
   ([SPECIFICATION.md:515](SPECIFICATION.md#L515)); expiry is item 8's.

Output. [SPECIFICATION.md:503-511](SPECIFICATION.md#L503-L511) lists what
`copilot` must print; item 11 owns the complete surface, and this item owns
the three lines that are now knowable — sidecar fidelity status, a concise
statement of what was and was not checked, and the exact approval command.
The disclaimer at
[command.py:163-169](src/pmc_client/command.py#L163-L169) is **deleted**: its
claim that the digest is a placeholder stops being true, and leaving it would
be the most misleading line in the product.

```text
copilot fidelity: exact on the declared state scope (object fx,
  13 atoms, 2 states)
copilot plan: p-<plan-id>
  1 | select copilot_selection, chain A
  2 | color red, copilot_selection
copilot checked: the plan parses, policy allows it, and a fresh PyMOL
  sidecar reconstructed this session's declared state exactly. Not
  checked: whether the plan is scientifically what you meant.
copilot apply with: copilot_apply p-<plan-id>
```

and on a non-exact outcome:

```text
copilot fidelity: NOT EXACT on the declared state scope (2 mismatches)
  state0.atom6.q expected=0.6 actual=0.4
  state1.atom12.coord expected=(20.0, 13.0, 2.5) actual=(20.0, 13.0, 0.0)
copilot plan: p-<plan-id>  (inspectable only — NOT applicable)
  1 | select copilot_selection, chain A
  2 | color red, copilot_selection
copilot checked: ... Not checked: this session could not be reconstructed
  exactly, so the plan was never executed anywhere. It cannot be applied.
```

`copilot_apply(plan_id)` refuses, always, with no live mutation:

| Condition | Output |
|---|---|
| no pending plan | `copilot_apply: no pending plan for this session` |
| id does not match the pending plan | `copilot_apply: plan <id> is not the pending plan` |
| pending but `applicable is False` | `copilot_apply: plan <id> is not applicable (<fidelity status>: <reason>). Nothing was applied.` |
| pending and applicable | `copilot_apply: plan <id> is applicable, but apply is not implemented yet (master plan item 10). Nothing was applied.` |

Item 10 replaces only the last row.

**Test that proves it:** [tests/integration/test_command.py](tests/integration/test_command.py)
(extend), PyMOL-free, with the existing `RecordingTransport`/`RecordingCmd`
doubles plus a fake session and a fake probe.

```text
bazel test //tests/integration:command --lockfile_mode=error
```

Asserts: the submitted `PlanRequestV1` carries the computed digest, the
resolved object name and the real counts — never a literal; an exact outcome
produces an applicable pending plan and the approval line; a non-exact
outcome still prints the numbered plan but marks it non-applicable; a
`applicable=False` response with an exact local outcome is still
non-applicable (the AND); every one of the four `copilot_apply` rows
verbatim; a second `copilot` call replaces the pending plan so the first
id is then refused; and a target-resolution failure sends nothing at all
(`RecordingTransport` records zero requests).

---

## Step 8 — The server refuses to mark a non-exact request applicable

**Files**

- [src/pmc_server/lifecycle.py](src/pmc_server/lifecycle.py) — set
  `ValidationReportV1.applicable` from `request.fidelity.status`.
- [tests/unit/test_server_lifecycle.py](tests/unit/test_server_lifecycle.py)
  — extend.

One rule, and it is the server's whole share of rule 9:
`applicable = request.fidelity.status == "exact"`. The server never upgrades
an outcome, and it does not re-derive one — it has no live session to compare
against. A request that claims `"exact"` while the client's own gate says
otherwise still fails at the client's AND.

This stays deliberately small. The pending-plan lifecycle, expiry and
supersession move to the LangGraph graph in item 8
([docs/master_plan.md:205-220](docs/master_plan.md#L205-L220)); adding them to
the fixture lifecycle now would be work item 8 deletes.

**Test that proves it**

```text
bazel test //tests/unit:server_lifecycle //tests/integration:client_server_command --lockfile_mode=error
```

Asserts each of the three fidelity statuses in produces the right
`applicable` out; that `applicable=False` travels intact through the real
loopback transport; and that the existing correlation and snapshot-identity
checks at
[src/pmc_client/transport.py:106-124](src/pmc_client/transport.py#L106-L124)
still hold against the rewritten `StructureSnapshotV1`.

---

## Step 9 — Real-PyMOL evidence for the four required categories

**Files**

- `tests/integration/test_client_fidelity_real_pymol.py` (new).
- `tests/integration/fidelity_sabotage_child.py` (new) — a `py_library`, not
  a test, in the same spirit as
  [sabotage_child.py](tests/integration/sabotage_child.py): a runner module
  honouring the fidelity child's two-path argv contract that returns a
  *deliberately perturbed* re-extraction, injected through
  `probe_fidelity(..., runner_module=...)`.
- [tests/integration/BUILD.bazel](tests/integration/BUILD.bazel) — the new
  `py_library` plus `py_test(name = "client_fidelity_real_pymol",
  size = "large", timeout = "moderate", tags = ["exclusive"])`, with
  `data = ["conftest.py", "testdata/h02_full_v1_fixture.pdb"]`.
- [tests/integration/test_real_pymol_command.py](tests/integration/test_real_pymol_command.py)
  — extend; raise `INVOCATION_DEADLINE_SECONDS` and replace
  `PREVIEW_DISCLAIMER`.

This is the step master_plan names: *"Test with modified coordinates,
multiple states, alternate locations and hetero atoms."*
[testdata/h02_full_v1_fixture.pdb](tests/integration/testdata/h02_full_v1_fixture.pdb)
already carries three of the four — two `MODEL` states, altlocs A/B on
`SER 2 OG` at occupancies 0.60/0.40, a `ZN` HETATM at resi 101, plus a `3A`
insertion code — so no new fixture is needed. The fourth is produced live,
which is the entire point: a snapshot that can only be reproduced from the
source file proves nothing about a *modified* session.

| # | Category | Live setup, on top of `loaded_fixture` | Asserts |
|---|---|---|---|
| 1 | Modified coordinates | `alter_state(1, "fx and name CA", "x = x + 3.5")`, then `sync()` | `FIDELITY_EXACT`; the live snapshot's moved coordinate is **not** the fixture file's, so the child could not have got it from disk |
| 2 | Multiple states | as loaded (2 states); also `alter_state(2, ...)` so the two states differ in more than the file's own offset | `FIDELITY_EXACT`; `len(snapshot.states) == 2`; state 1 and state 2 coordinates differ |
| 3 | Alternate locations | as loaded | `FIDELITY_EXACT`; the two `alt` `"A"`/`"B"` atoms survive with `q` 0.6/0.4 |
| 4 | Hetero atoms | as loaded, plus `show("spheres", "fx and resn ZN")` | `FIDELITY_EXACT`; the ZN atom's `hetatm is True` and `"spheres" in reps` |
| 5 | All four at once | 1+2 applied to the loaded fixture | `FIDELITY_EXACT`; `structure_digest` equal both sides |
| 6 | **Sabotage** | the real fixture, through `fidelity_sabotage_child` | `FIDELITY_NOT_EXACT`, and the mismatch strings name exactly the perturbed field |
| 7 | **Sabotage** | `probe` returning `REASON_TIMEOUT` | `FIDELITY_UNAVAILABLE`, `is_exact is False` |

Cases 1–5 each extract from the live session, run a **real** subprocess
probe, and assert `diff(live, reconstructed) == []`. Case 6 is what makes
1–5 meaningful: without it, a `check_fidelity` hard-wired to return
`FIDELITY_EXACT` would pass all five.

Then the end-to-end path in `test_real_pymol_command.py`: a real headless
PyMOL, the real loopback server, `copilot <intent>` followed by
`copilot_apply <plan-id>`, asserting the request carried a computed digest,
the console printed the fidelity line, `copilot_apply` refused, and
`assert_session_unchanged(before, after)` holds across both commands. The
existing `test_sabotage_mutation_is_detected_by_state_comparison` already
proves that helper can fail, and stays.

`INVOCATION_DEADLINE_SECONDS = 5.0` must rise —
`copilot` now launches a real PyMOL child. Measure it on the two-chain
fixture and set the constant from the measurement with headroom, with a
comment recording the observed value; do not pick a round number blind.

```text
bazel test //tests/integration:client_fidelity_real_pymol //tests/integration:real_pymol_command --lockfile_mode=error
```

---

## Step 10 — READMEs and the master plan

**Files**

- [tests/integration/README.md](tests/integration/README.md) — add the
  fidelity child, the client fidelity gate and the fidelity sabotage child
  to its charter paragraph.
- [tests/contract/README.md](tests/contract/README.md) — add the client's
  PyMOL-free session-resolution and fidelity-gate evidence.
- [src/pmc_sidecar/BUILD.bazel](src/pmc_sidecar/BUILD.bazel) — extend the
  package comment: two runner modules now, one of which the client spawns.
- [docs/master_plan.md:190-203](docs/master_plan.md#L190-L203) — leave the
  item text alone; it is the brief, not a status board.

Every README in this repository states what its directory owns, and plan 05
step 9 names leaving them stale as the failure mode to avoid.

**Test that proves it**

```text
bazel test //... --lockfile_mode=error
grep -rn "fixture placeholder\|fixtureId\|FIXTURE_SNAPSHOT" . \
  --include=*.py --include=*.md --include=*.bazel
```

The `grep` should return only intentional prose in `docs/` and `plans/` —
never a live identifier.

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

1. `grep -rn "example-chain-a-digest" src/` returns nothing. No request
   carries a literal digest.
2. `bazel query 'deps(//src/pmc_client:pmc_client)'` contains
   `//src/pmc_sidecar:pmc_sidecar` and does **not** contain `langgraph`,
   `torch` or `//src/pmc_agent`.
3. `bazel query 'deps(//src/pmc_core:pmc_core)'` still contains neither
   `//src/pmc_client` nor `//src/pmc_sidecar` nor `//tools/winstage`.
4. The twelve item-4 negative tests pass unchanged after step 2's
   extraction — `git diff` on `tests/contract/test_executor.py` shows
   additions only, and none inside an existing test function.
5. All five real-PyMOL fidelity categories report `FIDELITY_EXACT` with an
   empty diff and equal structure digests, and both sabotage cases report
   a non-exact or unavailable outcome. Then prove the gate can fail: hard-wire
   `check_fidelity` to return `FIDELITY_EXACT` and re-run — exactly cases 6
   and 7 must fail, and `copilot_apply`'s non-applicable refusal test in
   `test_command.py` must fail with them. Restore.
6. `copilot_apply` never mutates. Run the real-PyMOL end-to-end test with
   `assert_session_unchanged` on both the exact and non-exact paths; then
   sabotage it by adding `cmd.color("blue", "chain A")` inside
   `copilot_apply` and confirm those tests go red. Restore.
7. `ls $TMPDIR | grep pmc-executor-` is empty after the whole suite, and on
   POSIX `ps -eo pid,ppid,command | grep -c pymol` is unchanged before and
   after `bazel test //tests/integration:client_fidelity_real_pymol`.
8. CI green on all three operating systems before the PR is marked ready.
   Windows is where the process-spawning and `exclusive`-tag issues have
   historically surfaced, and neither reproduces on Linux.

Finally, by hand, the thing no test asserts: run `copilot` in a real
interactive PyMOL against a structure you have deliberately moved atoms in,
and read the output cold. If a user could come away believing the plan was
checked for scientific correctness, or that "fidelity: exact" is a claim
about the whole session rather than the declared scope, the wording is wrong
regardless of what is green.

---

## Risks

| Risk | Where it shows | Mitigation |
|---|---|---|
| Extracting `execute()`'s spawn body breaks item 4's process guarantees subtly | Step 2, possibly only on Windows CI | The twelve ported negative tests must pass **unchanged**; step 2's stop condition is to abandon the extraction and duplicate rather than reshape that evidence |
| `copilot` becomes unusably slow — a full PyMOL launch per invocation | Step 7, first real interactive use | Measured, not guessed, in step 9; bounded by the executor's own deadline so PyMOL can never wedge. If it is intolerable, the fix is item 8's territory (probe once per request, not per command), not a sidecar pool — [SPECIFICATION.md:636-638](SPECIFICATION.md#L636-L638) forbids pooling until state-reset equivalence is proven |
| The client's new `pmc_sidecar` edge drags PyMOL or `winstage` somewhere they must not go | Step 1, or silently later | `//src/pmc_client:pmc_client` becomes a checked boundary root in step 1, before any code depends on the edge |
| All five fidelity categories pass because reconstruction is faithful *and* because the check is vacuous | Never — that is the danger | Sabotage cases 6 and 7 are part of step 9, not an afterthought, and verification item 5 requires hard-wiring the gate open and watching exactly those two fail |
| "Fidelity: exact" is read as a whole-session or scientific guarantee | In the user's head, silently | The output says "on the declared state scope" everywhere and states what was *not* checked; verification closes with a cold read of that wording |
| A real structure's snapshot exceeds the executor's 4 MiB budget and every plan becomes non-applicable | Step 9 or first real use, as `REASON_OVERSIZED_INPUT` → `FIDELITY_UNAVAILABLE` | That is the correct fail-closed behaviour and it is reported with its typed reason rather than silently downgraded. Measure the JSON size for a representative PDB entry during step 9 and record it; raising `DEFAULT_MAX_SNAPSHOT_BYTES` is a one-constant follow-up with its own evidence, not a change to smuggle in here |
| `applicable` on `ValidationReportV1` is dead weight once item 8 rewrites the lifecycle | Item 8 | It is four lines on the server and the wire field item 8 needs anyway; the client's own AND is the load-bearing half and does not depend on it |
| Adding `src/pmc_client` to pyrefly surfaces a pile of pre-existing errors | Step 1, before the interesting work | Explicit stop condition in step 1: revert the include, keep the new modules strict, report it. Bringing an unchecked package up to preset is its own change |

---

## What implementation changed

Recorded after the fact, as `plans/05` and `plans/04` record their own
divergences. Nothing here contradicts the four answered questions; each is
something driving real PyMOL settled that the plan had guessed at.

- **Step 2's spawn extraction surfaced a real gap in the original inline
  code, not introduced by the extraction.** `_run_child()`'s stricter
  separation between "JSON decoded" and "JSON decoded to an object" showed
  that a child writing a syntactically valid but non-object payload (a bare
  `null`, which `tests/integration/test_executor_boundary.py`'s own
  `test_malformed_child_output_fails_closed_like_a_crash` sabotage produces)
  had been falling through to `AttributeError`, caught only because the
  original code's single broad `except` clause happened to include it.
  `_run_child()` now explicitly checks `isinstance(payload, dict)` and
  treats a non-dict payload as `REASON_CHILD_CRASH`, closing the gap for
  both `execute()` and `probe_fidelity()`. Found because the plan's own stop
  condition — the twelve ported negative tests must pass unchanged — caught
  it immediately; no behavior was left silently wrong.
- **Step 3's own test description was wrong, and the fix follows the
  precedent the plan itself named.** The plan said `test_sidecar_fidelity.py`
  should "drive `fidelity.main()` in-process" — but `main()` calls
  `pymol.finish_launching()` unconditionally, and PyMOL supports only one
  such call per interpreter. The already-launched `real_pymol`/
  `loaded_fixture` fixtures the test needs would make that second call fail.
  `src/pmc_sidecar/fidelity.py` splits its reconstruct-and-re-extract logic
  into a separate `probe(cmd, snapshot_text)` that assumes a live session
  already exists, with `main()` as a thin wrapper that launches PyMOL once
  and calls it — exactly the shape `src/pmc_sidecar/child.py`'s own
  `run_plan()`/`main()` split already has, which the plan's own step 3 text
  cited as the pattern to mirror ("mirroring how test_sidecar_child.py
  proves the five verbs") without noticing that test drives `run_plan()`,
  not `child.main()`. Nothing about what the test proves changed; only
  which function it calls.
- **The in-process fidelity tests reconstruct under a renamed object, not
  under `loaded_fixture`'s own name.** `probe()` reconstructs into the same
  live session `loaded_fixture` already populated as `"fx"`; a candidate
  snapshot also named `"fx"` would silently double the already-loaded
  object's atoms rather than build an independent copy to diff against it.
  Every test that drives a real `reconstruct()` renames its candidate to
  `"fx_probe"` first (`dataclasses.replace(snapshot, name=...)`) and deletes
  it in a `finally`. This is purely a test-construction detail; step 9's
  real-PyMOL categories (client-owned, one object per test) are unaffected.

- **Step 4's actual footprint is wider than its own "Files" list.**
  `StructureSnapshotV1`, `PlanRequestV1`, and `ValidationReportV1` are
  constructed directly (not only decoded) by `src/pmc_client/command.py`,
  `src/pmc_server/lifecycle.py`, and four test modules
  (`tests/integration/test_command.py`, `tests/integration/
  test_loopback_transport.py`, `tests/unit/test_server_lifecycle.py`, and
  `tests/contract/test_protocol.py` itself). Hannah's own standing
  instruction for this session is that `bazel test //...` must pass after
  every step, not only each step's own named target, so step 4 updates
  every one of those construction sites to the new required fields rather
  than leaving the tree red until step 7. Each fixture literal keeps its
  existing values under the new field names (`object_name` in place of
  `fixture_id`, plus placeholder `atom_count`/`state_count`, plus a
  `FidelityOutcomeV1` fixed at `FIDELITY_EXACT`); nothing about what any
  existing test asserts was weakened.
- **`PlanRequestLifecycle._matches_fixture`'s exact snapshot-equality
  check is left alone in this step, on purpose.** It still compares
  `request.snapshot == FIXTURE_SNAPSHOT` byte-for-byte. That is fine as
  long as the client also sends a fixed literal (true through step 4-6),
  but it will reject every real request once step 7 makes the client send
  a genuine per-session snapshot identity -- since a real digest/atom
  count essentially never equals the fixture's placeholder values. That is
  step 7's own problem to solve where the client-side change actually
  happens, not step 4's; step 7's own section below records the fix.
