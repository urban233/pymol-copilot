# End-to-end suite

## Context

This is item 12 of
[docs/master_plan.md:480-499](docs/master_plan.md#L480-L499). It is Hannah's,
sized at ~3 days, and `ready` now that PR #55 (item 11) has merged. It is the
last runtime item before item 19, the joint integration checkpoint.

The brief:

> Write end-to-end scenarios against real headless PyMOL: one intent through
> preview, approve and apply; one deliberate mid-apply failure through
> automatic recovery; a stale plan rejected after the session changed; a
> denied command rejected before any sidecar execution; the server
> unavailable. Every path asserts zero unapproved mutation. Include a sabotage
> test proving the suite detects a mutation. Record p50 latency per stage on
> this machine.

The brief carries its own caveat, and it is the largest single decision in
this plan:

> A production server entrypoint — process launch, the Lemonade probe falling
> back to `UnavailableEngine` (item 11) when it cannot connect, and the port
> and credential hand-off to PyMOL — is not built yet; this item's own "server
> unavailable" scenario needs one, and sizing it is this item's own job, not a
> silent assumption carried over from item 11.

### What the specification requires

Two of the deliverable's success measures are settled here, and both name
this item's evidence as their source
([SPECIFICATION.md:150-151](SPECIFICATION.md#L150-L151)):

> | Unapproved live-session mutation | Exercise every denial, failure,
> cancellation, expiry, and rejection path | **Zero mutations outside an
> approved apply or rollback operation** | Before the demo | Session
> fingerprints and end-to-end tests | Hannah |

> | Denied command execution | Adversarial command corpus with grammar
> disabled | **Zero denied commands reach sidecar or live execution** |
> Before the demo | Parser/policy contract suite | Joint |

A third is measured here and nowhere else
([SPECIFICATION.md:157](SPECIFICATION.md#L157)):

> | Runtime latency | Measure on the two developers' own laboratory/dev
> computers | **Report p50 stage latency; no fixed pass/fail budget** |
> Before the demo | Informal latency note | Hannah |

The five scenarios in the brief are five of the *"essential scenarios"*
([SPECIFICATION.md:166-196](SPECIFICATION.md#L166-L196)): preview with *"no
live-session change"*; `copilot_apply` rejecting *"stale or mismatched
plans"*; deterministic policy rejecting a denied plan *"before sidecar
execution"*; apply failing after one or more commands so that *"execution
stops and the client automatically restores the pre-apply `.pse` snapshot"*;
and a local, actionable failure when the engine is unavailable, with *"no
fallback to a remote or unconstrained model"*.

The evidence list ([SPECIFICATION.md:715-726](SPECIFICATION.md#L715-L726))
names three of this item's deliverables literally: *"no-live-mutation tests
over every rejection and failure path, including a sabotage test proving the
suite detects mutation"*; *"end-to-end loaded-object, controlled-fetch,
clarification, approval, stale plan, apply, automatic recovery, and manual
rollback scenarios"*; and *"latency and memory tests"*. Controlled fetch and
clarification are not in item 12's brief and are not built here.

Finally, the readiness ladder
([SPECIFICATION.md:789-796](SPECIFICATION.md#L789-L796)) makes this the item
that moves the deliverable from *"development only"* to *"locally
qualified"*, and names unapproved mutation, a command-policy escape and an
incorrect or failed restore as stop conditions that *"get fixed, not worked
around"*.

### What exists today (surveyed 2026-09-27 on `main` @ `3bd219b`)

The runtime is complete. What is missing is a suite that drives it from the
PyMOL console end to end, a way to start the server as a process, and any
latency number at all.

**The path a scenario has to drive.** `copilot <intent>` →
[src/pmc_client/command.py:905](src/pmc_client/command.py#L905)
`CopilotCommandClient.copilot` → `resolve_target_object` /
`extract_live_snapshot`
([src/pmc_client/session.py:127](src/pmc_client/session.py#L127),
[:163](src/pmc_client/session.py#L163)) → `check_fidelity`
([src/pmc_client/fidelity.py:85](src/pmc_client/fidelity.py#L85)), which
spawns a real sidecar through `probe_fidelity`
([src/pmc_core/executor.py:1296](src/pmc_core/executor.py#L1296)) →
`LoopbackPlanClient.submit` → `RequestGraphLifecycle`
([src/pmc_server/lifecycle.py:108](src/pmc_server/lifecycle.py#L108)) →
`_validating` ([src/pmc_agent/graph.py:836](src/pmc_agent/graph.py#L836)),
whose fixed order is cancellation → `screen_completion` → `parse_pml` →
`policy_validator` → `executor`, so a denied plan never reaches the spawn →
`_preview_block`
([src/pmc_client/command.py:398](src/pmc_client/command.py#L398)). Then
`copilot_apply` ([:1035](src/pmc_client/command.py#L1035)) runs
`verify_approval` twice, constructs the `RecoveryStore`, re-checks the
server's canonical plan and re-runs `evaluate_plan` locally, and only then
calls `apply_plan` ([src/pmc_client/apply.py:66](src/pmc_client/apply.py#L66)).

**Staleness is `structure_digest`, not a separate fingerprint.**
[src/pmc_core/snapshot.py:510](src/pmc_core/snapshot.py#L510) deliberately
excludes the view, settings and `enabled` from the digest, so `orient` does
not invalidate a plan while a colour or representation change does.
`verify_approval`
([src/pmc_client/approval.py:71](src/pmc_client/approval.py#L71)) is the
whole check table, in fixed order, and the digest branch produces exactly
`"the session changed since plan <id> was made"`.

**Recovery is whole-session `.pse` save and restore**, with
`compare_recovery` ([src/pmc_client/apply.py:46](src/pmc_client/apply.py#L46))
comparing the full snapshot diff *and* `cmd.get_names("all")`. A restore that
cannot be verified permanently halts Copilot for that PyMOL process
([src/pmc_client/command.py:829](src/pmc_client/command.py#L829)).
`RecoveryStore(root=...)` is injectable, so a test can root the real store in
a temporary home.

**The seams a test may use without touching production code.**
`register_copilot`
([src/pmc_client/command.py:1569](src/pmc_client/command.py#L1569)) and
`CopilotCommandClient.__init__` ([:576](src/pmc_client/command.py#L576))
accept `probe`, `dispatcher`, `recovery_store`, `now_factory`,
`uuid_factory`, `timestamp_factory` and `deadline_seconds`. Every one of
those is documented as existing for tests. There is no seam for
`extract_live_snapshot`, `to_json` or `_preview_block`; those are measured as
a residual (see the decisions below).

**What already covers part of this, and why it is not enough.**
[tests/integration/test_real_pymol_command.py](tests/integration/test_real_pymol_command.py)
(1018 lines) is the closest module: it holds the real-PyMOL happy path, a
typed rejection, an unavailable-server path and a state-comparison sabotage
test. It is not the suite this item asks for — it fakes the sidecar executor
*and* the fidelity probe, has no mid-apply failure, no stale-plan case, no
spawn-count evidence and no timing record, and its module docstring is
explicit that its subject is the client's live extraction and the transport
path, not a second real sidecar spawn. [tests/recovery/](tests/recovery/)
proves `apply_plan`, `verify_approval`, `RecoveryStore` and the refusal
matrix, but each at the component level: `apply_plan` is called directly and
the transport is a fake
([tests/recovery/test_no_live_mutation_real_pymol.py:61](tests/recovery/test_no_live_mutation_real_pymol.py#L61)).
The gap item 12 closes is the *whole* path, driven through `cmd.do("copilot
…")` against a real server, as five named scenarios.

Two existing pieces are worth reusing rather than reinventing:
[tests/integration/preview_support.py](tests/integration/preview_support.py)
reads the preview block by section name instead of line index, and
[tests/recovery/test_apply_real_pymol.py:31](tests/recovery/test_apply_real_pymol.py#L31)
`_FailColorProxy` is the precedent for a proxy that delegates to real PyMOL
and fails one operation.

**The server cannot be started.** `src/pmc_server/` has no `__main__.py` and
no `py_binary`; every wiring today happens inside a test. `connect_lemonade`
([src/pmc_agent/inference/lemonade.py:916](src/pmc_agent/inference/lemonade.py#L916))
returns a `LemonadeEngine` or an `EngineFailure`, and `UnavailableEngine`
([src/pmc_agent/inference/unavailable.py:29](src/pmc_agent/inference/unavailable.py#L29))
is the object item 11 built for the failure case, but nothing chooses between
them.

**There is no latency instrumentation.** The nearest thing is
`INVOCATION_DEADLINE_SECONDS = 15.0` and the elapsed-seconds returns in
`test_real_pymol_command.py:466-539`. [results/](results/) holds only a
README, and its contents are gitignored.

### Decisions you answered

- **Build a minimal production server entrypoint in this item.** The "server
  unavailable" scenario drives a real server process that is started and then
  killed, not only a closed port. Scope is process launch, the Lemonade probe
  falling back to `UnavailableEngine`, and the port and credential hand-off
  to PyMOL — nothing more.
- **The sidecar is real on the apply paths, faked elsewhere.** Scenarios 1
  and 2 and the latency harness call the real `probe_fidelity` and the real
  `execute`, so a genuine second headless PyMOL is spawned per preview. The
  stale-plan, denied-command and server-unavailable scenarios never reach
  apply and use a fake, keeping CI wall clock near today's while every
  measured path stays real.
- **Latency lands as a generator plus a tracked note.** A `py_binary` writes
  `results/latency-<platform>-<node>.md` on each machine (ignored,
  regenerated), and a tracked `docs/latency.md` holds the per-machine p50
  table. A small PyMOL-free test proves the stage timing and the percentile
  arithmetic.
- **The scenarios live in a new `tests/e2e/` package**, with its own README
  stating what evidence it owns, matching this repository's per-directory
  ownership convention. All five scenarios sit in one module so real PyMOL is
  launched once.

### Decisions I took, stated so you can overrule them

- **The e2e fingerprint is deliberately independent of
  `pmc_core.snapshot.extract`.** `tests/recovery/session_fingerprint.py`
  reuses the product's own extraction boundary on purpose, and that is right
  for a recovery test whose subject is `apply_plan`. It is the wrong choice
  for the measure that says *"zero unapproved mutation"*: if `extract()`
  itself lost a field, a fingerprint built on it would agree with the bug.
  `tests/e2e` captures coordinates, colours, representations, labels, the
  view and the complete name list using only PyMOL's own query APIs
  (`iterate`, `iterate_state`, `count_atoms`, `get_names("all")`,
  `get_view`). The two fingerprints stay separate and complementary.
- **The fingerprint includes the camera view**, even though `structure_digest`
  excludes it. A refusal path that silently re-oriented the camera is still an
  unapproved mutation of the user's session. The consequence is that the
  successful-apply scenario asserts the view *changed* (its plan ends in
  `orient`) while every refusal path asserts it did not.
- **The inference engine is `FakeEngine` by default, with an opt-in real
  Lemonade run.** No local model is available in CI, and a scripted engine is
  what makes a scenario's expected plan text deterministic. The latency
  binary takes `--lemonade-base-url` and, when given one, records a real
  `generate` stage; without it the note marks `generate` as *not measured*
  rather than printing a near-zero number that reads like a result. The
  opt-in target follows `//tests/integration:lemonade_real`'s precedent
  (`tags = ["external"]`, `env_inherit`).
- **No production code changes to make measurement possible.** Every stage is
  timed by wrapping a seam the client already exposes for tests (`probe`,
  `transport`, `dispatcher`, `recovery_store`) or by timing the console call
  itself; the un-instrumentable remainder is reported as one honest
  `client-local` residual row rather than by threading a timer through
  `command.py`. A harness that edits its subject to measure it is worse
  evidence than a coarser harness that does not.
- **The mid-apply failure is a real PyMOL failure, not a raised fake.** A
  proxy deletes the target object between command 1 and command 2, so command
  2 (`color`, on a selection whose object is gone) raises PyMOL's own
  exception — the `undefined_selection` case
  [tests/integration/pymol_error_cases.py](tests/integration/pymol_error_cases.py)
  records as raising against PyMOL 3.2.0a. Command 1 really mutated, the
  deletion really happened, and the `.pse` restore has to undo both.
  `_FailColorProxy`'s raised-exception approach is the fallback if the pinned
  wheel turns out not to raise; switching is a plan change to raise, not to
  improvise.
- **The port and credential reach PyMOL through a handoff file**, not
  environment variables: `~/.pymol-copilot/session.json`, mode `0600`, written
  atomically with the staging-then-`os.replace` pattern `RecoveryStore.save`
  already uses, unlinked on shutdown. An environment variable holding a live
  credential is visible to every child process and, on some platforms, to
  `ps`. The reader validates the origin is loopback before it builds a client.
- **`tests/e2e` reuses `tests/integration/testdata/two_chain_fixture.pdb`
  through a `filegroup`** rather than copying it, so the two real-PyMOL
  suites cannot drift apart about what "the fixture" is.
- **Eleven repetitions per scenario, the first discarded.** An odd count makes
  p50 an exact observed sample rather than an interpolation, and the first run
  pays for PyMOL's import and page-cache warm-up.

---

## Delivery: one branch, one PR

```text
git checkout main && git pull --ff-only
git checkout -b feat/end-to-end-suite
```

One commit per step, in order. Open a GitHub issue for item 12 first and link
the PR to it ([CONTRIBUTING.md](CONTRIBUTING.md) §1).

Step 6 adds files under `src/`, which no other step touches. Every
`**/BUILD.bazel`, `pyproject.toml` and `docs/development_setup.md` is
`@urban233` in [.github/CODEOWNERS](.github/CODEOWNERS), and steps 1, 6, 9 and
10 touch all four — tell Martin before step 1 lands. The handoff file in step
6 is a new local secret at rest; under
[SPECIFICATION.md:554](SPECIFICATION.md#L554) that makes step 6 a security
change requiring independent review, so raise it explicitly on the PR rather
than letting it pass as scaffolding.

**Sizing, honestly:** the brief says ~3 days, and that number was written
before the entrypoint was added to this item's scope. Five real scenarios and
a sabotage matrix are the ~3 days; the entrypoint and its bootstrap (step 6)
are about a day on their own, and the latency harness (step 9) most of
another. Call it ~5. The lever, if one is needed, is step 7(c): the
engine-unavailable sub-case could ship as a unit test against
`UnavailableEngine` instead of a real process pointed at a dead Lemonade
port. That is a plan change to raise, not to take silently.

Every step's gate is the repository's closing check:

```text
bazel test //... && bazel run //tools/quality:ruff -- check . && bazel run //tools/quality:pyrefly -- check
```

The test listed under each step is the one that proves *that* step. It runs
in addition to the gate, not instead of it. A step is not done until its named
test passes **and** that test has been sabotage-checked: break the thing it
covers, confirm exactly that test goes red and no other, restore. Do not pass
`BUILD.bazel` files to `ruff format`.

---

## Step 1 — The `tests/e2e` package and its scenario harness

**Files**

- `plans/12-end-to-end-suite.md` (new): this document, verbatim.
- `tests/e2e/README.md` (new): what this directory owns (the five end-to-end
  scenarios, the mutation sabotage matrix, the latency record) and what it
  deliberately does not (component-level recovery evidence stays in
  [tests/recovery/](tests/recovery/); fidelity-process evidence stays in
  [tests/integration/](tests/integration/)).
- `tests/e2e/conftest.py` (new): re-export `real_pymol` and `loaded_fixture`
  from `scenario_support`, and call `winstage.ensure_importable()` before any
  module in the directory can `import pymol` — the same arrangement and the
  same F811 reason as
  [tests/integration/conftest.py](tests/integration/conftest.py).
- `tests/e2e/scenario_support.py` (new), the whole harness:
  - `real_pymol` (module-scoped) and `loaded_fixture` fixtures, launching
    `pymol.finish_launching(["pymol", "-qc"])` once and loading the two-chain
    fixture fresh per test;
  - `SessionFingerprint` frozen dataclass and `capture_fingerprint(cmd)`,
    recording object and selection names from `cmd.get_names("all")`, per-atom
    `(index, x, y, z)` from `iterate_state`, per-atom
    `(index, color, reps, label)` from `iterate`, per-chain atom counts, and
    `cmd.get_view()` — PyMOL query APIs only, never `pmc_core.snapshot`;
  - `assert_unchanged(before, after)` and `assert_changed(before, after)`;
  - `ConsoleDriver`: the `_SynchronizingExtension` + `RealPyMOLCmdExtension`
    pattern from
    [tests/integration/test_real_pymol_command.py:395-611](tests/integration/test_real_pymol_command.py#L395-L611),
    exposing `run(command_text) -> float` that dispatches through PyMOL's own
    `cmd.do`, waits on a `threading.Event`, and returns elapsed seconds, plus
    `output` (the captured console lines);
  - `build_server(*, completions, policy_validator=evaluate_plan,
    executor=execute)` returning a started `LoopbackPlanServer`, its port and
    its credential, with the real `RequestGraphSession` /
    `RequestGraphLifecycle` behind it and a `FakeEngine` scripted from
    `completions`;
  - `counting(delegate)`, returning a wrapper that records every call so a
    scenario can assert an executor was never invoked (step 5).
- `tests/e2e/BUILD.bazel` (new): `py_library` `scenario_support` with
  `imports = ["."]`; `py_test` `harness`, `size = "large"`,
  `timeout = "moderate"`, `tags = ["exclusive"]`, `data` listing `conftest.py`
  and the fixture filegroup.
- [tests/integration/BUILD.bazel](tests/integration/BUILD.bazel): add a
  `filegroup` `two_chain_fixture` exporting
  `testdata/two_chain_fixture.pdb`, visible to `//tests/e2e:__pkg__` (Bazel's
  `glob` cannot cross packages; this is the
  `//tests/contract:pymol_error_corpus` pattern).
- [tools/winstage/BUILD.bazel](tools/winstage/BUILD.bazel): add
  `//tests/e2e:__pkg__` to `visibility`.
- [pyproject.toml](pyproject.toml): add `tests/e2e` to
  `[tool.pyrefly] search-path`.
- `tests/e2e/test_harness.py` (new).

**Test that proves it**

```text
bazel test //tests/e2e:harness
```

It asserts:

1. The fixture loads with the expected per-chain atom counts, so a later
   scenario's failure is the scenario's and not an empty session.
2. `ConsoleDriver.run("copilot")` really goes through PyMOL's own command
   registry: the captured output is the single `copilot: usage:` line, which
   only `command.py`'s registered callback can produce.
3. `capture_fingerprint` is sensitive in every field it claims: a
   `cmd.color`, a `cmd.show`, a `cmd.label`, a `cmd.set_view`, a
   `cmd.select` and a `cmd.delete` each make `assert_unchanged` raise, and a
   no-op does not. (Step 8 parametrizes this properly; here it is one smoke
   case per field.)
4. `capture_fingerprint` reaches no product extraction code:
   `pmc_core.snapshot` is absent from `sys.modules` after a capture in a
   subprocess that imported only `scenario_support`.

Sabotage: change `capture_fingerprint` to call `cmd.get_names()` instead of
`cmd.get_names("all")`, and assertion 3's selection case must go red naming
the names field. Restore. A fingerprint that cannot see a plan-created
selection is exactly how a partial restore would pass unnoticed.

---

## Step 2 — Scenario 1: one intent through preview, approve and apply

**Files**

- `tests/e2e/test_scenarios_real_pymol.py` (new): the module docstring
  enumerates which collaborators are real and which are not, in the style of
  [tests/integration/test_real_pymol_command.py](tests/integration/test_real_pymol_command.py)'s
  own header. Real here: headless PyMOL, `cmd.extend`/`cmd.do`,
  `LoopbackPlanServer`, `RequestGraphLifecycle`, `pmc_agent.graph`,
  `LoopbackPlanClient`, `register_copilot`, the real `probe_fidelity` and the
  real `execute` (two genuine extra PyMOL processes per preview), and a real
  `RecoveryStore` rooted in `tmp_path`. Faked: the inference engine only.
- [tests/e2e/BUILD.bazel](tests/e2e/BUILD.bazel): `py_test`
  `scenarios_real_pymol`, `size = "large"`, `timeout = "long"`,
  `tags = ["exclusive"]`, depending on `:scenario_support`,
  `@pypi//pymol_open_source_whl`, `@pypi//pytest`,
  `//tests/integration:preview_support`, `//src/pmc_agent:pmc_agent`,
  `//src/pmc_agent/inference:inference`, `//src/pmc_client:pmc_client`,
  `//src/pmc_core:pmc_core`, `//src/pmc_server:pmc_server`,
  `//tools/winstage:winstage`.
- [tests/integration/BUILD.bazel](tests/integration/BUILD.bazel): widen
  `preview_support`'s visibility, which is already `//tests:__subpackages__`
  — confirm rather than change.

**Test that proves it**

```text
bazel test //tests/e2e:scenarios_real_pymol --test_filter=test_one_intent
```

It asserts, in one test that walks the whole path:

1. After `copilot <intent>`, the fingerprint is byte-identical to the one
   captured before it. Preview mutates nothing, including the view.
2. The preview block, read by section with
   [preview_support.section](tests/integration/preview_support.py), names a
   plan id with the `p-` prefix, a relative expiry, the resolved object with
   its atom and state counts, the numbered canonical commands with a real
   atom count against each `select`, `fidelity: exact`, both `checked` and
   `NOT checked` lines, and the literal `copilot_apply p-…` and
   `copilot_reject p-…` commands.
3. The selection counts printed are the real sidecar's, not the client's
   guess: they equal what the same selection counts in the live session.
4. After `copilot_apply p-…`, the fingerprint changed in exactly the fields
   the plan names (the coloured chain's `color`, the shown representation's
   `reps`, and the view, because the plan ends in `orient`) and in no other
   field; the untouched chain's atoms are identical.
5. One `.pse` exists under the temporary home at
   `.pymol-copilot/recovery/plan-<id>.pse`, mode `0600` on POSIX.
6. The server-side graph reached `applied`, and `/v1/apply-outcome` was
   delivered — `copilot` again afterwards does not print the
   `previous apply outcome is still unconfirmed` line.

Sabotage: insert `cmd.color("blue", "chain A")` into `check_fidelity` so the
preview path mutates, and assertion 1 must go red. Restore. Then delete the
`store.save` call in `apply_plan` and assertion 5 must go red. Restore.

---

## Step 3 — Scenario 2: a mid-apply failure through automatic recovery

**Files**

- [tests/e2e/test_scenarios_real_pymol.py](tests/e2e/test_scenarios_real_pymol.py):
  add `_DeleteBetweenCommandsProxy`, a `cmd` wrapper that delegates every
  attribute to real PyMOL and, immediately after the plan's first command
  returns, really runs `cmd.delete(<object>)`. The plan's second command is a
  `color` on the selection that object carried, so it raises PyMOL's own
  exception inside `run_plan`'s `try`
  ([src/pmc_sidecar/child.py:168](src/pmc_sidecar/child.py#L168)) with no
  fake in the path.
- `tests/e2e/scenario_support.py`: nothing new beyond re-exporting the proxy
  if step 9 also needs it.

**Test that proves it**

```text
bazel test //tests/e2e:scenarios_real_pymol --test_filter=test_mid_apply_failure
```

It asserts, in order:

1. Real PyMOL genuinely raises for the second command — proved first, as its
   own assertion, before the scenario is wired, so a wheel that stopped
   raising fails here with a clear cause rather than by making the recovery
   look successful.
2. The first command really mutated: a fingerprint taken inside the proxy,
   between command 1 and the deletion, differs from the pre-apply one.
3. After `copilot_apply`, the fingerprint equals the pre-apply fingerprint
   exactly — every field, including the view, the labels and the complete
   name list. The deleted object is back and command 1's colour is gone.
4. No `copilot_`-prefixed selection survives in `cmd.get_names("all")`.
5. The console printed the restored outcome, naming the failing command's
   index and verb, in one bounded line under 400 bytes with no `Traceback`
   and no line of the plan's `render_pml()` in it.
6. Copilot is **not** halted: a following `copilot_health` reports no halt,
   and a following `copilot` produces a new plan.
7. The server-side graph reached `apply_failed_restored`.
8. The recovery point was consumed, not preserved: the `.pse` is gone and the
   recovery directory is empty.

Sabotage: make `RecoveryStore.restore` a no-op returning `None`, and
assertions 3 and 8 must go red, with `compare_recovery` reporting mismatches
and the status becoming `restore_failed`. Restore. This is the single most
important sabotage in the item: it is the difference between "recovery ran"
and "recovery worked".

---

## Step 4 — Scenario 3: a stale plan rejected after the session changed

**Files**

- [tests/e2e/test_scenarios_real_pymol.py](tests/e2e/test_scenarios_real_pymol.py):
  two tests, one per staleness axis. The digest case runs `copilot`, then has
  the *user* change the live session directly (`cmd.color("blue", "chain B")`
  — a real change to a chain the plan does not touch, so only the digest
  differs), then runs `copilot_apply`. The expiry case injects a
  `now_factory` that advances past `PLAN_TTL_SECONDS`
  ([src/pmc_agent/graph.py:155](src/pmc_agent/graph.py#L155)) without touching
  the session at all.
- This scenario uses the faked probe and executor: it never reaches apply, and
  the fidelity gate is not its subject.

**Test that proves it**

```text
bazel test //tests/e2e:scenarios_real_pymol --test_filter=test_stale_plan
```

It asserts:

1. The digest case prints exactly one line,
   `copilot_apply: the session changed since plan p-… was made. Nothing was
   applied.`
2. The expiry case prints exactly one line naming the expiry timestamp, and
   does so *without* querying PyMOL — the preliminary `verify_approval`
   settles it ([src/pmc_client/command.py:1054](src/pmc_client/command.py#L1054)),
   proved by a counting wrapper on the `cmd` surface recording zero
   `get_names` calls after the refusal begins.
3. In both cases the fingerprint after the refusal equals the fingerprint
   captured immediately *after* the user's own change — Copilot added nothing
   of its own. This is the correct formulation of "zero unapproved mutation"
   here, and stating it against the pre-`copilot` fingerprint instead would be
   a test that cannot fail for the right reason.
4. The recovery directory under the temporary home was never created:
   `_store_for_apply` is reached only after approval succeeds.
5. The server-side graph is still parked at `pending_approval`; it was never
   moved to `applying`.

Sabotage: delete the `live_digest != pending.snapshot_digest` branch from
`verify_approval` and the digest case must go red; delete the `now >=
expires_at` branch and the expiry case must go red, and no other test in the
repository may change. Restore both.

---

## Step 5 — Scenario 4: a denied command rejected before any sidecar execution

**Files**

- [tests/e2e/test_scenarios_real_pymol.py](tests/e2e/test_scenarios_real_pymol.py):
  the `FakeEngine` is scripted with three completions — the initial generation
  plus both repair attempts (`MAX_REPAIR_ATTEMPTS = 2`) — each carrying a
  plan the policy denies, and each carrying a `LEAK` sentinel string so the
  no-leak assertion has something to look for.
- `tests/e2e/scenario_support.py`: `counting()` from step 1 wraps the **real**
  `pmc_core.executor.execute`, so the spawn that would happen is the real one
  and the count is the evidence that it did not.

**Test that proves it**

```text
bazel test //tests/e2e:scenarios_real_pymol --test_filter=test_denied_command
```

It asserts:

1. The wrapped real executor was called **zero** times across all three
   attempts. `_validating`'s fixed order puts `policy_validator` before
   `executor` ([src/pmc_agent/graph.py:836](src/pmc_agent/graph.py#L836)); this
   is the test that the order is load-bearing and not incidental.
2. No sidecar process was created, by a second independent observable: with
   `TMPDIR` pointed at an empty directory for the duration, no
   `pmc-executor-*` scratch directory ever appears there
   ([src/pmc_core/executor.py:837](src/pmc_core/executor.py#L837)).
3. The console printed one bounded line whose failure category is a member of
   `pmc_core.protocol.FAILURE_CATEGORIES`, with a concrete next step from
   `pmc_client.messages.ACTIONS`, no plan id, no `Traceback`, and no
   occurrence of the `LEAK` sentinel anywhere in the captured output.
4. The fingerprint is unchanged and no recovery directory was created.
5. `copilot_apply` on any id afterwards reports `no pending plan for this
   session` — the denial left nothing approvable behind.
6. The same test runs a second, harsher case with a hostile completion, which
   `screen_completion` must terminate at zero repair attempts — the engine
   records exactly one request, not three.

Sabotage: swap the `policy_validator` and `executor` calls in `_validating` so
the sidecar runs first, and assertions 1 and 2 must both go red. Restore. A
denied command reaching a spawn is a stop condition under
[SPECIFICATION.md:796](SPECIFICATION.md#L796), so this ordering deserves a
test that fails loudly rather than a comment.

---

## Step 6 — A minimal production server entrypoint

**Files**

- `src/pmc_server/main.py` (new):
  - `build_engine(base_url, *, client=None)` calling `connect_lemonade` and
    returning `UnavailableEngine(failure)` when it returns an `EngineFailure`.
    There is no retry loop and no second engine
    ([SPECIFICATION.md:554](SPECIFICATION.md#L554): no remote fallback).
  - `serve(...)` building the real `RequestGraphSession` /
    `RequestGraphLifecycle`, starting `LoopbackPlanServer` on `127.0.0.1:0`
    with a `secrets.token_urlsafe(32)` credential, writing the handoff, and
    blocking until a signal.
  - `write_handoff(path, *, port, credential)`: stage to
    `.session-<uuid>.json`, `chmod 0600`, verify the mode, `os.replace` into
    place — the same sequence as
    [src/pmc_client/recovery.py:68](src/pmc_client/recovery.py#L68). Contents:
    `{"host": "127.0.0.1", "port": …, "credential": …, "pid": …,
    "startedAt": …}`.
  - `main(argv)` with `--lemonade-base-url`, `--handoff`, `--root`; prints one
    line naming host and port and the handoff path, never the credential;
    `SIGINT`/`SIGTERM` close the server and unlink the handoff in a `finally`.
- [src/pmc_server/BUILD.bazel](src/pmc_server/BUILD.bazel): add `main.py` to
  the library and a `py_binary` `server` with `main = "main.py"`, depending on
  `@pypi//httpx` for `connect_lemonade`.
- `src/pmc_client/bootstrap.py` (new): `connect_from_handoff(cmd, output, *,
  root=None) -> CopilotCommandClient | None`. Reads the handoff, refuses it
  unless the host is loopback, the port is an int in range and the credential
  has the expected length and alphabet, builds a `LoopbackPlanClient` and
  calls `register_copilot`. On any refusal it writes one bounded line through
  `pmc_client.messages` and returns `None` — it must never raise into PyMOL's
  dispatch.
- [src/pmc_client/BUILD.bazel](src/pmc_client/BUILD.bazel): add the source.
- `tests/unit/test_server_entrypoint.py` (new),
  [tests/unit/BUILD.bazel](tests/unit/BUILD.bazel): new `py_test`
  `server_entrypoint`, `size = "small"` — hermetic, no PyMOL, no real
  Lemonade.
- [tools/bazel/check_dependency_boundaries.py](tools/bazel/check_dependency_boundaries.py):
  confirm `//src/pmc_client:pmc_client`'s closure is unchanged by
  `bootstrap.py`. It must not acquire `httpx`, LangGraph or `pmc_agent`; if
  the query shows otherwise, that is a plan change to raise.

**Test that proves it**

```text
bazel test //tests/unit:server_entrypoint
bazel run //tools/bazel:check_dependency_boundaries
```

It asserts:

1. With an `httpx.MockTransport` that refuses every connection, `build_engine`
   returns an `UnavailableEngine` carrying the typed failure, and `serve`
   still starts and answers `/v1/health`. The server being up while the engine
   is down is exactly what item 11 built `UnavailableEngine` for.
2. With a mock transport that satisfies the capability probe, `build_engine`
   returns a `LemonadeEngine` and never an `UnavailableEngine`.
3. The handoff file exists with mode `0600` on POSIX, parses, and names the
   port the server actually bound; it is removed when `serve` returns, and it
   is removed even when `serve` raises.
4. The credential never appears on stdout or stderr.
5. `connect_from_handoff` refuses, with one bounded line and `None`, each of:
   a missing file, a non-loopback host, `0.0.0.0`, a port outside 1-65535, a
   short credential, a file that is not JSON, and a file larger than a small
   cap.
6. `//src/pmc_client:pmc_client`'s Bazel closure still contains no `langgraph`
   and no `httpx`.

Sabotage: widen the host check to accept any address, and assertion 5's
`0.0.0.0` case must go red — non-loopback listening is a configuration error
under [SPECIFICATION.md:554](SPECIFICATION.md#L554), and the reader is the
last place to catch it. Restore. Then make `build_engine` retry once on
failure and assertion 1 must go red on the request count.

---

## Step 7 — Scenario 5: the server unavailable

**Files**

- `tests/e2e/test_server_unavailable_real_pymol.py` (new): its own module, and
  its own PyMOL launch, because it spawns and kills a real server process and
  must not share a session with the five-scenario module.
- [tests/e2e/BUILD.bazel](tests/e2e/BUILD.bazel): `py_test`
  `server_unavailable_real_pymol`, `size = "large"`, `timeout = "moderate"`,
  `tags = ["exclusive"]`, with `data = ["//src/pmc_server:server"]` so the
  real binary is in runfiles.

**Test that proves it**

```text
bazel test //tests/e2e:server_unavailable_real_pymol
```

Three sub-cases, every one against a real process:

1. **Never started.** No handoff file exists. `connect_from_handoff` prints
   one bounded line, registers nothing, and the fingerprint is unchanged —
   there is no half-registered `copilot` that would fail later and more
   confusingly.
2. **Died after registration.** Spawn `//src/pmc_server:server` pointed at a
   closed Lemonade port, bootstrap PyMOL from its handoff, run one `copilot`
   and observe the engine-unavailable line, then kill the process and run
   `copilot` again. The second run prints exactly one line beginning
   `copilot: loopback request failed`, and the fingerprint is unchanged across
   both. `copilot_health` afterwards prints `server: unavailable (…)` with
   `engine`, `model` and `contracts` unknown, and does so *without* raising.
3. **Up, engine down.** The same real process; `copilot <intent>` produces one
   bounded actionable line whose category is `engine_unavailable`, no plan id,
   and no fallback of any kind — the engine is asked exactly once, proved by
   the server's own health line naming `UnavailableEngine`'s model identity.

All three additionally assert the recovery directory was never created and no
`.pse` exists.

Sabotage: remove the `except TransportError` around `self._transport.submit`
in `copilot`, and sub-case 2 must go red with a traceback reaching the console
instead of one line. Restore. Then make `main.py` fall through to a second
engine when the probe fails, and sub-case 3 must go red on the model identity.

---

## Step 8 — The sabotage test that proves the suite detects a mutation

**Files**

- `tests/e2e/test_fingerprint_sabotage.py` (new),
  [tests/e2e/BUILD.bazel](tests/e2e/BUILD.bazel): `py_test`
  `fingerprint_sabotage`, `size = "large"`, `timeout = "moderate"`,
  `tags = ["exclusive"]`.

**Test that proves it**

```text
bazel test //tests/e2e:fingerprint_sabotage
```

It is a parametrized matrix, one case per field `SessionFingerprint`
compares, each performing a *real* PyMOL mutation of exactly that field and
requiring `assert_unchanged` to raise:

| Mutation | Field it must be caught by |
|---|---|
| `cmd.color("blue", "chain A")` | per-atom colour |
| `cmd.show("spheres", "chain B")` | per-atom representations |
| `cmd.label("chain A and name CA", "'x'")` | per-atom label |
| `cmd.translate([1, 0, 0], "chain A")` | per-atom coordinates |
| `cmd.set_view(<a different view>)` | camera view |
| `cmd.select("copilot_leftover", "chain A")` | complete name list |
| `cmd.delete(<object>)` | object names and atom counts |
| `cmd.create("copy", <object>)` | object names |

It also asserts the negative: a genuine no-op (`cmd.sync()`, a query-only
`count_atoms`, a re-`color` to the colour already set) leaves
`assert_unchanged` silent, so the matrix is not passing because the
comparison rejects everything.

Sabotage: drop any one field from `SessionFingerprint` and exactly that row
must go red while every other row stays green. Restore, one field at a time,
for all eight. This step is the reason the other scenarios' "unchanged"
assertions mean anything, and it is what
[SPECIFICATION.md:723](SPECIFICATION.md#L723) asks for by name.

---

## Step 9 — p50 latency per stage

**Files**

- `tests/e2e/latency.py` (new): `Stage` (name, seconds), `StageTimer` with
  `measure(name)` as a context manager and an explicit declared-stage list so
  a missing or double-recorded stage is an error, `percentile(values, q)`
  computing p50 and p95 by the nearest-rank method on sorted samples, and
  `render_note(records, *, machine, engine, repetitions) -> str` producing the
  markdown table.
- `tests/e2e/record_latency.py` (new), `py_binary` `record_latency`: runs each
  scenario `--repetitions` times (default 11, first discarded), wrapping the
  injectable seams to time these stages —

  | Stage | Timed at |
  |---|---|
  | `fidelity probe` | the injected `probe`, the real `probe_fidelity` |
  | `submit` | the injected transport's `submit` |
  | `preview (client-local)` | `copilot` total minus the two above |
  | `approval re-verify` | `copilot_apply` up to the transport `apply` call |
  | `apply round trip` | the injected transport's `apply` |
  | `recovery save` | the injected `RecoveryStore.save` |
  | `live dispatch` | the injected `dispatcher` |
  | `restore + compare` | `RecoveryStore.restore` plus `compare_recovery` |
  | `outcome report` | the injected transport's `report_apply_outcome` |
  | `generate` | the engine, **only** under `--lemonade-base-url` |

  It writes `results/latency-<platform>-<node>.md` through
  `BUILD_WORKSPACE_DIRECTORY`, the same shape as
  [tests/integration/capture_color_indices.py](tests/integration/capture_color_indices.py),
  and prints the same table to stdout. Without `--lemonade-base-url` the note
  records `generate` as `not measured (scripted engine)` rather than a number.
- `tests/e2e/test_latency.py` (new), `py_test` `latency`, `size = "small"` —
  PyMOL-free, so the arithmetic is checked cheaply and on every CI run.
- `docs/latency.md` (new): the tracked note. One section per machine, each
  naming the OS, CPU, Python and PyMOL versions, the engine, the repetition
  count and the date, then the p50/p95 table. Filled from a real run on this
  machine in this step; Martin's machine is added when he runs it.
- [tests/e2e/BUILD.bazel](tests/e2e/BUILD.bazel),
  [docs/development_setup.md](docs/development_setup.md): the binary, and how
  to run it.

**Test that proves it**

```text
bazel test //tests/e2e:latency
bazel run //tests/e2e:record_latency -- --repetitions 11
```

`//tests/e2e:latency` asserts:

1. `percentile` returns an exact observed sample for an odd count and the
   documented nearest-rank value for an even one, matching a hand-computed
   table — not `statistics.median`, which interpolates.
2. `StageTimer` records each declared stage exactly once; an undeclared stage,
   a stage recorded twice, and a declared stage never recorded are each an
   error, so a silently-missing stage cannot become a silently-missing row.
3. `render_note` emits one row per declared stage, in declaration order, with
   a `p50` column, and marks an unmeasured stage explicitly rather than
   printing `0.000`.

The `bazel run` is the record itself: it must complete, write the file, and
its table must be pasted into `docs/latency.md` in this same step. A p50 table
with no number in it does not satisfy the brief.

Sabotage: make `percentile` return the arithmetic mean and assertion 1 must go
red. Restore. Then remove one stage from the declared list and assertion 2
must go red naming it.

---

## Step 10 — Documentation and the master plan

**Files**

- `tests/e2e/README.md`: finalize, now that the targets exist — name each one
  and the claim it owns, and state the two deliberate separations (the
  independent fingerprint, and why component-level recovery evidence stays in
  `tests/recovery`).
- [docs/development_setup.md](docs/development_setup.md): a new section on
  starting the server (`bazel run //src/pmc_server:server`), what the handoff
  file is and where it lives, how PyMOL bootstraps from it, and how to record
  latency. Note that killing the server never endangers the session.
- [docs/master_plan.md](docs/master_plan.md): item 12's `**State:**` line, the
  `### Blockers` table row, the mermaid `classDef` for `I12`, and
  `### What this graph says today`. Item 19 becomes `ready` if nothing else
  blocks it.
- [src/pmc_client/README.md](src/pmc_client/README.md): a paragraph on
  `bootstrap.py` as the client's entry point.
- `src/pmc_server/README.md` (new): what the entrypoint does, what the handoff
  contains, and why the credential is a file and not an environment variable.

**Test that proves it**

```text
bazel test //...
grep -rn 'session.json' docs/development_setup.md      # expect a hit
grep -rn 'credential' src/pmc_server/main.py | grep -i 'print\|stdout'   # expect no output
grep -rn 'e2e' pyproject.toml                          # expect the search-path entry
```

Plus a read-through against the brief: each of the five scenarios named in
[docs/master_plan.md:485-491](docs/master_plan.md#L485-L491) maps to a named
test in `tests/e2e/`, the sabotage matrix exists, and `docs/latency.md`
contains real numbers for this machine.

Sabotage: none — this step is documentation, and the grep assertions above are
its check.

---

## Verification (end to end)

The full gate from [docs/development_setup.md](docs/development_setup.md):

```text
bazel build //... --lockfile_mode=error
bazel test //... --lockfile_mode=error
bazel run //tools/bazel:check_dependency_boundaries --lockfile_mode=error
bazel run //tools/quality:ruff --lockfile_mode=error -- check .
bazel run //tools/quality:ruff --lockfile_mode=error -- format --check .
bazel run //tools/quality:pyrefly --lockfile_mode=error -- check
```

Then, specifically for this item:

1. **Every scenario in the brief has a test, and each asserts an unchanged
   fingerprint except where a mutation was approved.** Run
   `bazel test //tests/e2e:all` and read the test names against
   [docs/master_plan.md:485-491](docs/master_plan.md#L485-L491).
2. **The sabotage matrix has actually been sabotaged.** Each of step 8's eight
   fields has been dropped once, exactly its row went red, and it was
   restored. Record this in the commit body in the repository's usual
   `Sabotage-verified:` form.
3. **Zero denied commands reached a spawn.** Step 5's two independent
   observables — the executor call count and the absence of any
   `pmc-executor-*` scratch directory — both hold.
4. **The recovery beat works from the console.** Step 3's scenario restores a
   real partial mutation and does not halt Copilot.
5. **`docs/latency.md` contains real p50 numbers for this machine**, with the
   engine named, and `generate` either measured against real Lemonade or
   explicitly marked not measured.
6. CI is green on ubuntu-24.04, macos-15 and windows-2025, and the added
   real-PyMOL targets did not push the Windows job — which runs with
   `--local_test_jobs=1` — past its limit.

Finally, by hand, in an interactive PyMOL, because the demo is interactive and
the suite is not:

- `bazel run //src/pmc_server:server`, then bootstrap a real PyMOL from the
  handoff and run `copilot`, `copilot_apply`, `copilot_rollback` on a real
  structure;
- kill the server mid-session and confirm the next `copilot` prints one line
  and the session is untouched;
- run the failure-then-recovery beat once, as
  [SPECIFICATION.md:789-796](SPECIFICATION.md#L789-L796) requires before
  demo-ready.

---

## Risks

| Risk | Where it shows | Mitigation |
|---|---|---|
| Real `probe_fidelity` and real `execute` on the apply paths add two headless PyMOL launches per preview, and every real-PyMOL target is `exclusive`, so they serialize — on Windows behind `--local_test_jobs=1` this could push the CI job past its limit | Steps 2, 3, 9 | One PyMOL launch per module, not per test. If CI time becomes the constraint, the cut is step 2's real validation sidecar (the fidelity probe stays real, since it is what `applicable` depends on). That is a plan change to raise, not to take silently |
| Real PyMOL stops raising for a `color` against a selection whose object was deleted, so step 3 loses its genuine failure trigger | Step 3 | Assertion 1 proves the raise *before* the scenario is wired, so the failure is legible. `_FailColorProxy` ([tests/recovery/test_apply_real_pymol.py:31](tests/recovery/test_apply_real_pymol.py#L31)) is the documented fallback, at the cost of a synthetic trigger |
| The handoff file is a new local secret at rest, and a bug in it is a security bug, not a test-harness bug | Step 6 | Mode `0600` under `~/.pymol-copilot/`, atomic staging-then-replace, unlinked on shutdown and on exception, loopback-only validation on read, never printed. Flagged on the PR as a security-relevant change requiring independent review per [SPECIFICATION.md:554](SPECIFICATION.md#L554) |
| p50 measured against a scripted engine under-reports total latency by exactly the part everyone cares about | Step 9 | The note names the engine and marks `generate` *not measured* rather than printing a number. The `--lemonade-base-url` run is the honest one, and `docs/latency.md` says which kind of run produced each table |
| The e2e fingerprint and `tests/recovery`'s product-based one drift apart, and a reader cannot tell which is authoritative | Steps 1, 8, 10 | Both READMEs state the split and the reason. Step 8's matrix is what makes the e2e one checkable; `tests/recovery` keeps its own, unchanged |
| The entrypoint was added to this item after it was sized at ~3 days, and steps 6 and 7 are a genuinely separate subsystem from the scenarios | Whole item | Stated up front under Delivery. Step 7(c) is the named lever. If the item needs to be split, steps 1-5 and 8 are a coherent PR on their own and steps 6, 7, 9 a second |
| `pyproject.toml`, every `BUILD.bazel` and `docs/development_setup.md` are `@urban233`'s, and four steps touch them | Steps 1, 6, 9, 10 | Tell Martin before step 1 lands. None of the changes alter the data half's targets |
