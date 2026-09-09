# W2-00: Restore Trust in H-01 and Close the Previous Wave

**Status:** Accepted — accepted by Hannah Kullik (`kullik01`), 2026-09-09
**Owner:** Hannah Kullik (`kullik01`)
**Reviewer:** Martin Urban (`urban233`)
**Risk:** Normal
**Containment:** N/A -- test and documentation changes only. No runtime
behavior, snapshot schema, executor, policy, or dataset code is touched, so
there is nothing to flag-guard; reverting the one changed `__main__` block
restores the prior behavior exactly.
**Slices:** One pull request, behavior-vertical: the runner fix, its
two-direction proof, the combined-snapshot re-run, and the evidence
reconciliation that re-run authorizes. Splitting them would publish a
combined receipt whose real-PyMOL numbers came from an untrusted runner.
**Base commit:** `bd4e5190f4fc25a75dcfe00878b2ecd3d6fe5d09` (`main`)
**Issue/work item:** [#14](https://github.com/urban233/pymol-copilot/issues/14)
**Brief/design/API:** [Wave plan § W2-00](../../wave/pymol-copilot-full-v1-contracts.md#w2-00-restore-trust-and-close-the-previous-wave),
  [M-01 exit-code finding](../../wave/evidence/M-01.md#outer-loop-finding-real-pymol-test-targets-exit-code-could-not-be-trusted-fixed),
  [previous wave's final validation checkpoint](../../wave/pymol-copilot.md#final-validation-checkpoint)

## Focus card

- **Change:** Make `//tests/integration:real_pymol_command` report pytest's
  real exit code and complete output to Bazel, then re-run the previous
  wave's combined checks on one integration snapshot and reconcile the
  M-01, H-01, and combined receipts against what that run actually showed.
- **Success:** A temporary failing assertion in the target makes Bazel
  report `FAILED` with the full pytest traceback present in the captured
  log; removing it reports `PASSED`, 5/5. The combined receipt records one
  exact tested commit, the two merged pull requests and their reciprocal
  human approvals, every exact command with its real result, and a joint
  verdict whose outstanding parts are named rather than assumed.
- **Non-goals:** No runtime, protocol, snapshot, executor, policy, or
  dataset change. No refactor of the now-four duplicated `os._exit` blocks
  into a shared helper (it would reach into Martin's `pmc_data`/`tests/data`
  lane for no behavior gain; recorded as a follow-up instead). No work on
  Windows issue #12. No change to the `raise SystemExit(pytest.main(...))`
  entry points in test modules that never launch PyMOL -- the defect needs
  PyMOL's teardown to exist. No rewriting of historical per-item evidence as
  if it had run on a different commit.
- **Allowed scope:** `tests/integration/test_real_pymol_command.py`;
  `docs/codev/wave/evidence/{H-01,M-01,combined}.md`;
  `docs/codev/wave/pymol-copilot.md` (final-validation-checkpoint state
  only); `docs/codev/wave/pymol-copilot-full-v1-contracts.md` (W2-00 status
  row only); `docs/codev/task/W2-00/`.
- **Validation:** The two-direction probe on
  `//tests/integration:real_pymol_command`; H-01's and M-01's affected
  targets; and repository-wide build, test, dependency-boundary, lint,
  format, and type checks -- all on the one integration snapshot recorded in
  the combined receipt.
- **Stop if:** The pre-fix probe reports `FAILED` correctly (the defect's
  premise would be wrong for this target, and the whole item needs
  rethinking); any combined-snapshot check fails, which returns the affected
  item to its owner instead of being written up as green; or the checkpoint
  needs a coordination decision that is Martin's to make.
- **Work style:** Bounded delegate -- the change is isolated to one
  `__main__` block plus evidence prose, empirically testable in both
  directions, trivially reversible, and independently reviewed afterwards.

## Repository evidence

- `tests/integration/test_real_pymol_command.py:416`: ends
  `raise SystemExit(pytest.main([__file__]))`. Its module-scoped
  `real_pymol` fixture calls `pymol.finish_launching(["pymol", "-qc"])` and
  `cmd.do("quit")`, so it has exactly the teardown path M-01 identified.
- `tests/data/test_gold_case_verifier.py:449-457`,
  `tests/data/test_generate_real_pymol.py:211-216`, and
  `src/pmc_data/generate_cli.py:86-93`: the accepted fix is
  `_exit_code = pytest.main([__file__])`, `sys.stdout.flush()`,
  `sys.stderr.flush()`, `os._exit(_exit_code)`, preceded by a comment
  explaining both halves. All three were verified empirically in both
  directions by M-01. This item copies that pattern rather than inventing
  one.
- A repository-wide grep for `SystemExit`/`os._exit` confirms
  `test_real_pymol_command.py` is the last PyMOL-launching entry point still
  on the unsafe pattern. Every other `raise SystemExit(pytest.main(...))`
  site is in a module that never launches PyMOL.
- `tests/integration/test_gold_case_verifier.py`-style imports: `os` and
  `sys` are plain `import` lines in the stdlib block, after
  `from __future__ import annotations  # noqa: I001, RUF100`. The target
  file currently imports neither.
- `tests/integration/BUILD.bazel`: `real_pymol_command` is
  `size = "large"`, `timeout = "moderate"`, and
  `target_compatible_with`-excluded on Windows (issue #12). Unchanged by
  this item.
- `git merge-base --is-ancestor`: both `1a188ec` (PR #11, H-01) and
  `59748e6` (PR #13, M-01) are ancestors of `bd4e519`, so `main` already is
  the combined snapshot C-2 asks for, modulo this item's own fix.
- `gh pr view`: PR #11 was approved by `urban233` at head `2217679`; PR #13
  was approved by `kullik01` at head `8cce4ca`, after two
  `CHANGES_REQUESTED` rounds. These are the reciprocal approvals C-1 needs.
- `docs/codev/wave/evidence/combined.md`: every field is still `TBD`.
  `H-01.md`'s Review section and `H-R1` are unfilled; `M-01.md`'s verdict is
  `TBD` pending exactly the approval that GitHub now records.
- `.github/workflows/`: the CI gate runs `bazel mod graph`, `build //...`,
  `test //...`, dependency boundaries, ruff check, ruff format, and pyrefly
  on `ubuntu-24.04`, `macos-15`, and `windows-2025`.

## Proposed change

1. **Reproduce the defect first.** Add a temporary failing assertion to one
   test in `tests/integration/test_real_pymol_command.py`, run
   `bazel test //tests/integration:real_pymol_command --lockfile_mode=error
   --cache_test_results=no --test_output=all`, and capture the verbatim
   result. Expect Bazel `PASSED` alongside a pytest log reporting the
   failure. If Bazel instead reports `FAILED`, stop and report -- the
   premise does not hold for this target.
2. **Apply the fix.** Add `import os` and `import sys` to the stdlib import
   block and replace the `__main__` body with the flush-then-`os._exit`
   pattern, carrying a comment that states both why `os._exit` is needed and
   why the explicit flush is needed. Match the sibling files' wording rather
   than paraphrasing it.
3. **Prove the failing direction.** Re-run the same command with the probe
   still present. Expect Bazel `FAILED` and, in the captured log, the
   probe's full traceback and pytest summary line -- the flush half of the
   fix is what that second check proves.
4. **Prove the passing direction.** Remove the probe and re-run. Expect
   `PASSED`, 5/5, with no test silently skipped.
5. **Re-run the previous wave's combined checks** on the resulting head:
   H-01's `//tests/contract:protocol`, `//tests/integration:command`,
   `//tests/integration:loopback_transport`,
   `//tests/integration:client_server_command`, and
   `//tests/integration:real_pymol_command`; M-01's `//tests/data:...`
   targets including `gold_case_verifier`, `generate`, and
   `generate_real_pymol`; then `bazel build //...`, `bazel test //...`,
   dependency boundaries, ruff check, ruff format, and pyrefly. Record each
   command and its real result, including counts.
6. **Reconcile the evidence.** Fill `combined.md`'s Snapshot, Fixture,
   C-1..C-7, command table, and joint verdict from step 5's actual output;
   fill `H-01.md`'s Review section and `H-R1` from PR #11's merge and
   Martin's recorded approval; update `M-01.md`'s status header and verdict
   from PR #13's merge and Hannah's recorded approval. Append new results as
   the combined snapshot's own run -- never edit a historical per-item
   number to match. Anything that genuinely requires Martin's own
   environment or his coordinating acceptance stays explicitly outstanding
   with the reason, per the wave's own "record both environments
   separately" rule.
7. **Update statuses.** Mark the previous wave plan's final validation
   checkpoint against what the combined receipt actually shows, and move
   W2-00's row in the current wave plan.

## Validation

- `bazel test //tests/integration:real_pymol_command --lockfile_mode=error
  --cache_test_results=no --test_output=all`, with the probe, before the
  fix -> Bazel `PASSED` despite a failing pytest assertion (defect
  reproduced).
- Same command, with the probe, after the fix -> Bazel `FAILED`, and the
  captured log contains the probe's traceback and pytest's summary line.
- Same command, without the probe, after the fix -> `PASSED`, 5/5.
- `bazel test //tests/contract:protocol //tests/integration:command
  //tests/integration:loopback_transport
  //tests/integration:client_server_command --lockfile_mode=error` ->
  H-01's non-PyMOL regressions still pass.
- `bazel test //tests/data/... --lockfile_mode=error` -> M-01's oracle,
  verifier, generation, and sabotage evidence still passes on this snapshot.
- `bazel build //... --lockfile_mode=error` -> build completes.
- `bazel test //... --lockfile_mode=error` -> all targets pass; record the
  count.
- `bazel run //tools/bazel:check_dependency_boundaries --lockfile_mode=error`
  -> exit 0.
- `bazel run //tools/quality:ruff --lockfile_mode=error -- check .` and
  `-- format --check .` -> clean.
- `bazel run //tools/quality:pyrefly --lockfile_mode=error -- check` -> 0
  errors.
- CI on the pull request -> green on `ubuntu-24.04`, `macos-15`, and
  `windows-2025`, with `real_pymol_command` excluded on Windows as before.

## Risks and rollout

- **The green history this item repairs may not have been green.** The whole
  point of the fix is that `real_pymol_command`'s prior `PASSED` results
  cannot be trusted. If step 4 shows a genuine, previously-masked failure,
  that is a finding, not a blocker to work around: stop, report it, and
  return H-01 to its owner rather than adjusting the test to keep the
  checkpoint green.
- **`os._exit` skips `atexit` and normal interpreter shutdown.** That is
  deliberate -- it is what steps past PyMOL's exit-code override -- and step
  3's log check is what keeps its known cost (lost buffered output) covered.
  It is confined to a `__main__` block Bazel is the only caller of.
- **Four copies of the same block now exist.** Recorded as a non-blocking
  follow-up rather than fixed here; a shared helper would cross into
  Martin's lane and change nothing observable.
- **Rollback:** revert the one commit. No data, schema, or interface is
  migrated.
- **The combined snapshot is an integration snapshot, not yet `main`.** The
  previous wave's C-2 explicitly permits a human-approved integration
  snapshot before merge. The receipt records the exact commit and its
  ancestry to both merges; merging this pull request is what makes it
  `main`.

## Decisions needed

- None blocking. One assumption stated rather than asked: C-5 names Martin
  as the person who reruns H-01's checks and C-7 needs his coordinating
  verdict, and neither can be produced from this environment. This item
  records Hannah's environment in full, cites the GitHub-recorded reciprocal
  approvals for C-1, and leaves Martin's own environment rerun and
  coordinating acceptance explicitly outstanding with the reason -- matching
  the wave's "record both environments separately without a multi-platform
  support claim" rule. Tell me if you would rather the receipt claim the
  checkpoint complete on one environment.

## Completion evidence

**Status:** Implemented, awaiting independent review.

- **Delivered:** `tests/integration/test_real_pymol_command.py`'s
  `__main__` entry point now reports pytest's real exit code and complete
  output to Bazel (`os._exit(pytest.main(...))` with an explicit
  `sys.stdout`/`sys.stderr` flush first, matching
  `tests/data/test_gold_case_verifier.py`'s pattern), instead of the prior
  `raise SystemExit(pytest.main([__file__]))`, which real headless PyMOL's
  process-teardown path could override to exit code 0 even after a genuine
  test failure. Reproduced the defect empirically before fixing it, proved
  both post-fix directions (failing probe -> Bazel `FAILED` with the
  traceback preserved in the log; probe removed -> `PASSED`, 5/5), re-ran
  the previous wave's combined checks on the resulting working tree, and
  reconciled the M-01, H-01, and combined evidence receipts against what
  that re-run actually showed.
- **Changed:** `tests/integration/test_real_pymol_command.py` (the fix);
  `docs/codev/wave/evidence/H-01.md` (Review section, H-R1 checkbox, new
  "W2-00 follow-up" section); `docs/codev/wave/evidence/M-01.md` (Status
  header, Review Verdict, M-R1 checkbox, new "W2-00 discharges this item's
  cross-cutting flag" section); `docs/codev/wave/evidence/combined.md`
  (fully filled from this task's own re-run); `docs/codev/wave/pymol-copilot.md`
  (final-validation-checkpoint state); `docs/codev/wave/pymol-copilot-full-v1-contracts.md`
  (W2-00's status row); this plan's own Completion evidence.
- **Head commit/snapshot:** `a181ccea4d00966c80c0da91b9de5fb3ee29b575` on branch
  `codev/W2-00`, base `bd4e5190f4fc25a75dcfe00878b2ecd3d6fe5d09`. This is the
  exact code snapshot every command below ran against; the evidence prose
  itself lands in a later commit that changes no tested code.
- **Validation actually run:** (1) Probe, pre-fix:
  `bazel test //tests/integration:real_pymol_command --lockfile_mode=error
  --cache_test_results=no --test_output=all` -> Bazel `PASSED` despite
  pytest "1 failed, 4 passed in 1.52s" (defect reproduced). (2) Same
  command, probe still present, post-fix -> Bazel `FAILED` (`Exit 1`);
  `bazel-testlogs/tests/integration/real_pymol_command/test.log` retained
  the full traceback and pytest's "1 failed, 4 passed in 1.51s" summary
  line. (3) Same command, probe removed -> `PASSED`, "5 passed in 1.38s";
  `git diff` confirmed the file differs from pre-probe by exactly the
  intended fix. (4)
  `bazel test //tests/contract:protocol //tests/integration:command
  //tests/integration:loopback_transport //tests/integration:client_server_command
  --lockfile_mode=error` -> PASSED, 4/4. (5)
  `bazel test //tests/data/... --lockfile_mode=error` -> PASSED, 7/7. (6)
  `bazel test //tests/integration:real_pymol_command --lockfile_mode=error
  --cache_test_results=no` -> PASSED, 1/1. (7) `bazel build //...
  --lockfile_mode=error` -> build completed, 29 targets. (8)
  `bazel test //... --lockfile_mode=error` -> PASSED, 18/18 test targets.
  (9) `bazel run //tools/bazel:check_dependency_boundaries --lockfile_mode=error`
  -> exit 0, no violation. (10)
  `bazel run //tools/quality:ruff --lockfile_mode=error -- check .` -> "All
  checks passed!". (11)
  `bazel run //tools/quality:ruff --lockfile_mode=error -- format --check .`
  -> "90 files already formatted". (12)
  `bazel run //tools/quality:pyrefly --lockfile_mode=error -- check` -> "0
  errors (12 suppressed)". Environment: Linux x86_64, openSUSE Tumbleweed
  20260908, Bazelisk 1.29.0 / Bazel 9.2.0, pinned
  `pymol-open-source-whl==3.2.0.2` (`requirements.in`).
- **Acceptance evidence:** The two-direction probe (validation items 1-3,
  above) is the plan's own Success criterion, met exactly as specified.
  H-01's and M-01's affected targets and the full repository build/test/
  dependency-boundary/lint/format/type checks (items 4-12) all pass on the
  working-tree snapshot, per the plan's Validation section and recorded in
  `combined.md`. `combined.md`'s C-1, C-4, and C-6 are satisfied on this
  snapshot; C-2 and C-3 are only half-recorded (Martin's checkout, and no
  fixture was ever jointly exchanged between the two lanes -- a genuine
  gap against that checklist's own premise, not a code defect); C-5 and
  Martin's half of C-7 explicitly require Martin's own environment and
  coordinating acceptance and remain outstanding, per this plan's own
  Decisions-needed assumption.
- **Scope deviations:** None from the plan's Proposed change or Allowed
  scope. One clarification: C-3's fixture-exchange gap was not previously
  named in this plan as a specific outstanding item (only C-5 and Martin's
  half of C-7 were); it surfaced while reconciling `combined.md` against
  what the two merged items actually delivered (each item uses its own
  separate self-authored fixture, not one Martin exchanged with Hannah),
  and is recorded honestly in `combined.md`/`pymol-copilot.md` rather than
  checked or silently dropped.
- **Known limitations:** (1) The tested snapshot is a branch commit, not
  yet `main`; the previous wave's C-2 explicitly permits a human-approved
  integration snapshot before merge. (2) C-2, C-3, C-5, and Martin's half of C-7 remain outstanding for the
  reasons stated above and in `combined.md`; the previous wave's final
  validation checkpoint is partially complete, not passed. (3) Issue #8's
  generation obligation remains open, unaffected by this item. (4) The
  four now-duplicated `os._exit`+flush blocks (`test_gold_case_verifier.py`,
  `test_generate_real_pymol.py`, `generate_cli.py`, and now
  `test_real_pymol_command.py`) are not refactored into a shared helper,
  per this plan's stated non-goal.
- **Review state:** AWAITING INDEPENDENT REVIEW.

## Style audit

CoDev's Build execution step 5 dispatches `code-audit-gate` against the head
snapshot before the pull request opens. That dispatch was attempted and its
result discarded: the agent edited 27 files, reaching well outside this
task's diff into production source under `src/` and the repository's own
`.claude/hooks/`, and applied the `import-class-not-module` rewrite this
repository deliberately tolerates -- introducing a duplicate
`from pmc_core import plan` in `src/pmc_core/parser.py` while doing so.
Nothing was committed; the working tree was restored to
`59a894b49db60ad71c5770aa798864ae66975644` and `ruff check`, `ruff format
--check`, `pyrefly check`, and `//tests/integration:real_pymol_command` were
all re-run clean afterwards.

The audit was then performed directly instead, running the same checker the
agent uses
(`.agents/skills/audit-google-python-style/scripts/check_google_rules.py`)
against `tests/integration/test_real_pymol_command.py`, the one Python file
this task changes. It reports 20 findings. Nineteen fall in categories this
repository already tolerates repo-wide, on lines W2-00 never edited:
`import-class-not-module` (lines 50, 57, 59-61), `docstring-args` on
fixture-taking test functions (lines 303, 312, 343, 375, 402),
`docstring-markup` (lines 1, 81), and `line-length` on the pre-existing
`from __future__` noqa line (line 42). M-01's own style audit records the
same decision for the first two categories.

The one category this task's diff does touch is `comment-punctuation`, seven
hits on the new `__main__` comment block (lines 418-425), which the rule
flags because a wrapped multi-line prose comment does not end every physical
line with a period. That rule fires 60 times across this repository,
including seven times on the sibling block at
`tests/data/test_gold_case_verifier.py:445-452` that this fix was
deliberately copied from. Rewriting only this block to satisfy it would make
the file diverge from the sibling it is meant to match, which is the
specific outcome M-01's audit warned against. No style change is therefore
applied, and the repository's enforced gates -- `ruff check`, `ruff format
--check`, and `pyrefly check` -- all pass clean at this head.
