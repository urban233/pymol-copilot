# Combined evidence — final validation checkpoint

**Status:** Partially complete. [W2-00](../../task/W2-00/implementation-plan.md)
fixed the untrusted real-PyMOL exit code, re-ran the previous wave's
combined checks in Hannah's environment, and recorded C-1, C-4, and C-6
below. C-2 and C-3 are only half-recorded (Martin's checkout and a jointly
exchanged fixture are both missing, the latter a genuine gap against this
checklist's own premise -- see Fixture, below). C-5 and Martin's half of
C-7 require Martin's own environment and coordinating acceptance and stay
explicitly outstanding. This is not a passed checkpoint.
**Coordinator:** Martin Urban (`urban233`)
**Wave plan:** [PyMOL-Copilot wave plan](../pymol-copilot.md#final-validation-checkpoint)
**Inputs:** [M-01 receipt](M-01.md) and [H-01 receipt](H-01.md), both handoffs complete

## Snapshot

- Combined commit SHA: `a181ccea4d00966c80c0da91b9de5fb3ee29b575` (branch
  `codev/W2-00`: base `bd4e5190f4fc25a75dcfe00878b2ecd3d6fe5d09` plus the
  one-file exit-code fix in `tests/integration/test_real_pymol_command.py`
  this task made, and nothing else). Every command below ran against
  exactly this code snapshot, as the working tree, immediately before it
  was committed unchanged. This receipt's own prose sits in a later
  commit on top and changes no tested code, test, or configuration --
  the same convention H-01.md's Snapshot section already uses.
- M-01 reviewed SHA: `8cce4cac2e21b85b8fd5c1db5a6895edf66e535b` (PR #13,
  approved by `kullik01`, 2026-09-07T22:50:28Z); merged as
  `59748e677a97b54432e857c4307d78369badeec7`
- H-01 reviewed SHA: `221767903d60554c23b5293a435ddad4138f8bfb` (PR #11,
  approved by `urban233`, 2026-09-06T17:42:16Z); merged as
  `1a188ec13cd9701ac36c56dc03b95b666aaf5b7e`
- Integration diff / ancestry mapping: `git merge-base --is-ancestor
  1a188ec13cd9701ac36c56dc03b95b666aaf5b7e bd4e5190f4fc25a75dcfe00878b2ecd3d6fe5d09`
  and the same check for `59748e677a97b54432e857c4307d78369badeec7` both
  confirmed true -- both merges are ancestors of the base commit. `a181ccea4d00966c80c0da91b9de5fb3ee29b575`
  is that base plus this task's single-file fix (`git diff --stat`: 1 file
  changed, 15 insertions(+), 1 deletion(-)), so both merged items are
  present unmodified.
- Martin checkout `git rev-parse HEAD`: outstanding -- not recorded from
  this environment; see C-2/C-5.
- Hannah checkout `git rev-parse HEAD`: `bd4e5190f4fc25a75dcfe00878b2ecd3d6fe5d09`
  (branch `codev/W2-00`) at the time every command below ran, with this
  task's one-file fix present as an uncommitted working-tree
  modification; that same tree is now committed as
  `a181ccea4d00966c80c0da91b9de5fb3ee29b575`, the Combined commit SHA
  above and the tested code snapshot itself.
- `git status --short` (both checkouts): Hannah's, at the moment the
  commands below ran: ` M tests/integration/test_real_pymol_command.py`
  (the fix, since committed as `a181ccea4d00966c80c0da91b9de5fb3ee29b575`;
  no other source, test, or configuration change) plus this evidence set's
  own prose and the untracked `docs/codev/task/W2-00/` planning directory,
  neither of which is tested code. Martin's: outstanding.

## Fixture

- Frozen structure path: none was ever exchanged between the two lanes.
  H-01's runtime preview uses its own self-authored
  `tests/integration/testdata/two_chain_fixture.pdb`; M-01's oracle/verifier
  uses its own separately self-authored
  `tests/data/testdata/chain_a_gold_fixture.pdb` (plus
  `second_gold_fixture.pdb`/`no_chain_a_fixture.pdb` for its generation
  work). Neither developer ever verified the other's fixture bytes. This is
  a genuine gap against this checklist's own premise ("Martin's frozen
  structure", verified by both developers), not a defect introduced by
  either item -- recorded honestly rather than checked against a comparison
  that never happened.
- SHA-256 verification output (both developers): not applicable -- see
  above. Each item's own SHA-256 is recorded separately in its own receipt
  (H-01.md's and M-01.md's own Fixture sections).
- Fixture identity: as recorded separately in H-01.md/M-01.md; no joint
  identity check was performed.
- Canonical plan bytes (both suites agree): both independently produce
  `select copilot_selection, chain A\ncolor red, copilot_selection\n` from
  the same unchanged `pmc_core.plan.initial_fixture_plan().render_pml()`,
  per both receipts' own Fixture sections; not independently re-diffed
  across lanes in this task.
- Contract versions (both suites agree): both use plan/policy/protocol
  version `"1"` and the pinned `pymol-open-source-whl==3.2.0.2`
  (`requirements.in`, unchanged by this task).
- Disposable session separation (oracle reference vs. preview test): each
  lane already isolates its own PyMOL session per test function (see
  H-01.md/M-01.md); there is no joint reference/preview pairing to separate
  since no fixture was ever exchanged.

## Checklist

Complete in order. Map every C-entry to commands, logs, and reports on the
combined snapshot. Branch-level results are not combined evidence.

- [x] **C-1: Both handoffs are complete.** M-A1 through M-A8 and M-R1 are
  satisfied (M-01.md); H-A1 through H-A8 and H-R1 are satisfied (H-01.md).
  Reciprocal GitHub-recorded approvals: PR #11 approved by `urban233` at
  `221767903d60554c23b5293a435ddad4138f8bfb` (2026-09-06T17:42:16Z); PR #13
  approved by `kullik01` at `8cce4cac2e21b85b8fd5c1db5a6895edf66e535b`
  (2026-09-07T22:50:28Z, after two `CHANGES_REQUESTED` rounds, both
  addressed). No unresolved blocking review finding on either PR.
- [ ] **C-2: One exact combined code snapshot.** Hannah's side is fully
  recorded above (`git rev-parse HEAD` = `bd4e5190f4fc25a75dcfe00878b2ecd3d6fe5d09`,
  `git status --short` showing exactly the one intended fix). Martin's
  `git rev-parse HEAD` and `git status --short` from his own checkout are
  outstanding. Left unchecked because this entry explicitly requires both.
- [ ] **C-3: One verified input fixture.** Not satisfied -- see Fixture,
  above. No single frozen structure was ever exchanged and checksum-verified
  by both developers; each item uses its own separate controlled fixture.
- [x] **C-4: Oracle revalidated on the combined snapshot.** Correction: the
  first pass at this entry checked the box on
  `bazel test //tests/data/... --lockfile_mode=error` alone, which confirms
  counts only. Re-run fresh and verbose, uncached, on `a181ccea4d00966c80c0da91b9de5fb3ee29b575`:
  `bazel test //tests/data/... --lockfile_mode=error --cache_test_results=no
  --test_output=all`. Bazel confirmed all 7 test *actions* actually
  executed on this snapshot (no `(cached)` tag on any of the 7 `PASSED`
  lines; `INFO: 8 processes: 77 action cache hit, 1 internal, 14
  linux-sandbox` -- the 77 cache hits are build/runfiles-preparation
  actions, not test executions) and each target's own pytest session
  printed its full collected-item count and pass count in the captured
  log:
  - `//tests/data:oracle` -- `collected 3 items` / `3 passed in 0.01s`
    (M-A3's independent-oracle target).
  - `//tests/data:pdb` -- `collected 5 items` / `5 passed in 0.03s`.
  - `//tests/data:gold_case` -- `collected 13 items` / `13 passed in 0.03s`
    -- includes the round-trip check
    (`test_gold_case_round_trip_preserves_provenance_assertions_and_plan`,
    confirmed present by source inspection) and the 8 missing-field/
    provenance/kind/drift invalid-record cases (M-A2/M-A6).
  - `//tests/data:generate` -- `collected 11 items` / `11 passed in 0.05s`.
  - `//tests/data:generate_real_pymol` -- `collected 2 items` /
    `2 passed in 1.39s`.
  - `//tests/data:gold_case_verifier` -- `collected 10 items` /
    `10 passed in 10.45s` -- by source inspection (`grep '^def test_'`),
    these 10 are exactly: the positive case
    (`test_true_gold_case_passes_every_assertion`) plus a real-serial vs.
    session-ordinal regression
    (`test_chain_membership_matches_by_real_serial_not_session_ordinal`);
    the three semantic-negative cases
    (`test_wrong_chain_case_fails_chain_membership`,
    `test_wrong_color_case_fails_color_state`,
    `test_unintended_change_is_detected`); and five invalid-record cases
    (`test_chain_membership_assertion_for_an_absent_chain_invalidates_the_result`,
    `test_no_unintended_change_assertion_for_an_absent_chain_invalidates_the_result`,
    `test_structure_checksum_mismatch_invalidates_the_result`,
    `test_missing_assertion_param_invalidates_the_result`,
    `test_real_pymol_evaluator_error_invalidates_the_result`).
  - `//tests/data:oracle_sabotage` -- `collected 1 item` / `1 passed in
    0.22s` (`test_oracle_suite_rejects_a_corrupted_chain_membership_derivation`,
    confirmed present by source inspection -- M-A7's sabotage case).

  What this run does **not** show, stated plainly rather than invented:
  pytest's default output (this repository's `addopts = "-ra
  --strict-markers --strict-config --tb=short"`, no `-v`/`-s`) collapses
  every passing test to a `.` and never prints captured stdout for a
  passing test; `test_gold_case_verifier.py` itself contains no `print()`
  calls. So even at `--test_output=all`, an all-passing run's log does not
  surface the per-assertion expected/actual atom sets or color/
  no-unintended-change observations C-4's text names (those `AssertionResult.detail`
  values exist inside the test's own data, not on stdout) -- that
  observational detail remains only as originally captured in M-01.md's
  own receipt (which used a differently-flagged invocation to surface it)
  and is not re-demonstrated by this rerun. This rerun's evidence is: all
  7 targets' full test suites genuinely re-executed (not cache-served) on
  this exact snapshot and every one of the named positive,
  semantic-negative, invalid-record, round-trip, and sabotage tests, named
  above by source-confirmed identity, passed.
- [ ] **C-5: Runtime revalidated with the exchanged fixture.** Outstanding.
  This entry explicitly names Martin's own rerun in his own environment,
  which has not happened, and is additionally blocked on C-3 (there is no
  "verified structure" to use). As supporting evidence only, Hannah reran
  H-01's own regression and real-PyMOL targets on `a181ccea4d00966c80c0da91b9de5fb3ee29b575` in her
  environment (see Commands and results, below) -- all PASSED -- but this
  does not substitute for C-5's Martin-specific requirement.
- [x] **C-6: Repository-wide checks pass on that same snapshot.** This
  entry's original text names Martin as the one who runs it; per this
  task's explicit instruction, Hannah ran every command in Validation on
  `a181ccea4d00966c80c0da91b9de5fb3ee29b575` in her own environment (Linux x86_64, openSUSE Tumbleweed):
  build, full test suite (18/18), dependency boundaries (exit 0), lint,
  format, and type checks all pass -- see Commands and results, below. No
  required check was skipped. A separate confirmation in Martin's own
  environment has not happened and is not claimed here.
- [ ] **C-7: Joint verdict is recorded.** Hannah's half is recorded below.
  Martin's runtime and repository-check verdicts, against this exact
  combined SHA, are outstanding -- his own environment and coordinating
  acceptance were not available to this task. Checkpoint recorded as
  incomplete rather than passed; no check that actually ran failed.

## Commands and results

| Checklist ID | Test target / test name | Exact command | Result | Cache status | Log / artifact |
|---|---|---|---|---|---|
| W2-00 probe, pre-fix | `//tests/integration:real_pymol_command` (temporary failing assertion added) | `bazel test //tests/integration:real_pymol_command --lockfile_mode=error --cache_test_results=no --test_output=all` | Bazel `PASSED` ("Executed 1 out of 1 test: 1 test passes.") despite pytest reporting "1 failed, 4 passed in 1.52s" -- defect reproduced | Fresh (forced by `--cache_test_results=no`) | Bazel test log, this session |
| W2-00 probe, post-fix (still present) | same, after applying the `os._exit`+flush fix | same command | Bazel `FAILED` (`Exit 1`); captured `bazel-testlogs/tests/integration/real_pymol_command/test.log` retained the probe's full traceback and pytest's "1 failed, 4 passed in 1.51s" summary line | Fresh (forced) | `bazel-testlogs/tests/integration/real_pymol_command/test.log`, this session |
| W2-00 probe removed | same, probe deleted | same command | `PASSED`, "5 passed in 1.38s" ("Executed 1 out of 1 test: 1 test passes."), no test silently skipped; `git diff` confirms the file differs from the pre-probe version by exactly the intended import/`__main__` fix | Fresh (forced) | Bazel test log, this session |
| H-01 non-PyMOL regressions | `//tests/contract:protocol //tests/integration:command //tests/integration:loopback_transport //tests/integration:client_server_command` | `bazel test //tests/contract:protocol //tests/integration:command //tests/integration:loopback_transport //tests/integration:client_server_command --lockfile_mode=error` | PASSED, 4/4 | All 4 cache hits (Bazel printed `(cached) PASSED` for each; `Executed 0 out of 4 tests: 4 tests pass.`) | Bazel test log, this session |
| C-4, first pass (counts only) | `//tests/data/...` (7 targets) | `bazel test //tests/data/... --lockfile_mode=error` | PASSED, 7/7 | Fresh (`Executed 7 out of 7 tests: 7 tests pass.`, no `(cached)` tags), but not forced and not verbose -- superseded by the row below per the correction, above | Bazel test log, this session |
| C-4, corrected: fresh and verbose | `//tests/data/...` (7 targets: `oracle`, `pdb`, `gold_case`, `generate`, `generate_real_pymol`, `gold_case_verifier`, `oracle_sabotage`) | `bazel test //tests/data/... --lockfile_mode=error --cache_test_results=no --test_output=all` | PASSED, 7/7; per-target collected/passed counts captured verbatim in the log (see C-4, above, for the full breakdown and named tests) | Fresh (forced by `--cache_test_results=no`; log shows no `(cached)` tag on any of the 7 `PASSED` lines; `8 processes: 77 action cache hit` refers to build/runfiles actions, not test executions) | Bazel test log, this session |
| C-5 (Hannah's supporting rerun only) | `//tests/integration:real_pymol_command` | `bazel test //tests/integration:real_pymol_command --lockfile_mode=error --cache_test_results=no` | PASSED, 1/1 (5 sub-tests) | Fresh (forced) | Bazel test log, this session |
| C-6 | `//...` build | `bazel build //... --lockfile_mode=error` | Build completed successfully, 29 targets analyzed, 17 actions | Mostly cache hits at the action level (`17 processes: 226 action cache hit, 16 internal, 1 linux-sandbox`) -- normal incremental-build behavior, not a test-result cache | Bazel log, this session |
| C-6 | `//...` test | `bazel test //... --lockfile_mode=error` | PASSED, 18/18 test targets | 16 cache hits, 2 fresh (`policy_sabotage`, `subsystem_imports`; `Executed 2 out of 18 tests: 18 tests pass.`) -- the 16 cache hits are exact replays of the fresh runs already recorded in this same table for the same snapshot (H-01's 4 targets and `//tests/data/...`'s 7, plus `real_pymol_command`, `plan`, `policy`, `parser_rejections`, `server_lifecycle`), not results from a different snapshot | Bazel log, this session |
| C-6 | dependency boundaries | `bazel run //tools/bazel:check_dependency_boundaries --lockfile_mode=error` | exit 0, no violation reported | `bazel run` always re-executes the target binary regardless of build-action caching | command log, this session |
| C-6 | lint | `bazel run //tools/quality:ruff --lockfile_mode=error -- check .` | "All checks passed!" | `bazel run`, always re-executed | command log, this session |
| C-6 | format | `bazel run //tools/quality:ruff --lockfile_mode=error -- format --check .` | "90 files already formatted" | `bazel run`, always re-executed | command log, this session |
| C-6 | types | `bazel run //tools/quality:pyrefly --lockfile_mode=error -- check` | "0 errors (12 suppressed)" | `bazel run`, always re-executed | command log, this session |

All commands above ran from the repository root on branch `codev/W2-00`,
working tree `a181ccea4d00966c80c0da91b9de5fb3ee29b575`, in this session. No test was skipped.

**On cache hits as evidence for this snapshot:** this task's only source
change is confined to `tests/integration:real_pymol_command`'s one file;
`git status --short` confirms no other tracked file differs from what
each cache-hit target was last actually executed against. Bazel's test
cache keys on the exact content hash of a target's full transitive input
closure, so a cache hit for a target whose closure does not include the
changed file is a byte-exact replay of a result already computed for these
identical inputs -- not evidence carried over from a genuinely different
snapshot (the failure mode C-6's own text warns against). That said, a
cache hit is honestly weaker evidence than a fresh execution for this
task's specific concern: it does not re-invoke the interpreter, PyMOL, or
pytest just now, so it cannot catch newly-introduced flakiness,
environment drift, or (for a real-PyMOL target) exactly the kind of
runner-trustworthiness question this task exists to fix. That is why every
invocation of the one target actually under test in this task
(`real_pymol_command`) was forced fresh with `--cache_test_results=no` at
every step, and why C-4 was corrected to a forced-fresh, verbose rerun
rather than resting on the first pass's cache-eligible counts. The
remaining cache hits above (H-01's four non-PyMOL targets, and 16 of the
18 in the full-repo test run) are accepted as same-snapshot replay
evidence for targets this task did not touch and does not have reason to
distrust, not as a substitute for re-verifying the target this task
actually changed.

## Environment (Hannah)

- OS/architecture: Linux x86_64, openSUSE Tumbleweed 20260908.
- Bazel: Bazelisk 1.29.0, Bazel 9.2.0 (`Build label: 9.2.0`).
- Open-Source PyMOL (pinned): `pymol-open-source-whl==3.2.0.2`
  (`requirements.in`), matching H-01.md's/M-01.md's own recorded pin; real
  reported version via `cmd.get_version()` already recorded in H-01.md:
  `('3.2.0a', 3.0, 3000000, 1788190265, 'e84604a3a0b265f57c7985c83ce3e05f8a91764b', 0)`
  -- not independently re-queried in this task.
- Martin's environment: outstanding (see C-2/C-5/C-7). His previously
  recorded environment for M-01 (macOS, darwin/arm64) is in M-01.md, not
  reconfirmed here.

## Joint verdict

- Hannah's oracle verdict (combined SHA `a181ccea4d00966c80c0da91b9de5fb3ee29b575`): M-01's oracle,
  verifier, generation, and sabotage targets all pass unchanged on this
  snapshot (7/7, see C-4). The cross-cutting exit-code defect M-01 flagged
  against H-01's file is now fixed and empirically proven in both
  directions (see Commands and results, above, and H-01.md's "W2-00
  follow-up" section). No new oracle disagreement observed.
- Martin's runtime and repository-check verdicts (combined SHA): outstanding
  -- not recorded from this environment; see C-5/C-6/C-7.
- Limitations and outstanding issue #8 generation work: issue #8 remains
  open per M-01.md (its generation portion is not fully closed by this
  item). C-2 (Martin's checkout facts), C-3 (no fixture was ever jointly
  exchanged -- a genuine gap in this checklist's own premise, not a code
  defect), C-5, and Martin's half of C-7 remain outstanding.
- Blocking findings: none. Every check actually run in this task passed;
  the items above are missing evidence, not failures. This checkpoint is
  recorded as incomplete, not passed, per the wave plan's own rule that a
  missing required result leaves it so.
