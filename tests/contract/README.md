# Contract tests

Owned by shared-core contract evidence: the plan/policy/protocol fixtures,
and the canonical snapshot format's deterministic codec, declared-
unsupported marker, structure digest, and field-by-field diff (all
PyMOL-free -- the real-PyMOL extraction/reconstruction round trip lives in
`tests/integration`).

Also owns the sidecar executor's own PyMOL-free evidence
(docs/master_plan.md item 4): `test_executor.py` covers `execute()`'s
parent-side validation -- an unsupported executor version, an oversized or
malformed snapshot, a plan/snapshot digest mismatch, and a policy denial --
every one of which is rejected before any process is ever spawned. It also
covers typed handling of scratch-directory and OS-level spawn failures, and
`probe_fidelity()`'s own smaller pre-spawn validation (docs/master_plan.md
item 7): the same shape of checks minus the two that have no meaning
without a plan (policy, snapshot-digest binding). The deadline, kill, reap,
and positive-path evidence needs a real process and lives in
`tests/integration` instead.

Also owns the live-extraction-and-fidelity-gate's PyMOL-free evidence
(docs/master_plan.md item 7): `test_client_session.py` covers
`pmc_client.session.resolve_target_object()`'s deterministic, fail-closed
target resolution (zero, one, and more than one candidate, and a
measurement object never interfering) against a hand-written fake session,
plus one proof that `extract_live_snapshot()`'s returned digest matches
`structure_digest` of its returned snapshot. `test_client_fidelity.py`
covers every branch of `pmc_client.fidelity.check_fidelity()`'s own
adjudication (exact, not-exact, and every unavailable reason) against a
fake probe, and `to_wire()`'s truncation. The real-sidecar evidence that a
faithfully reconstructed live session actually reaches `FIDELITY_EXACT`
lives in `tests/integration` instead.

Also owns the error envelope's evidence. `test_errors.py` proves
`pmc_core.errors` against `testdata/pymol_errors/`, a corpus of real PyMOL
failure strings captured by
`//tests/integration:capture_pymol_errors` and checked in. That test
launches no PyMOL; the target that re-drives the same broken commands
against a live PyMOL, and so fails when an upgrade rewords a message, is
`//tests/integration:errors_real_pymol`. The corpus is exported to it by
the `pymol_error_corpus` filegroup, since Bazel's `glob` cannot reach
across a package boundary.

`test_errors.py` also imports `//tests/integration:pymol_error_cases`, the
broken-command table the capture drove. Each captured envelope's command
index and verb are checked against that table rather than read back out of
the envelope under test, which would make those two fields assert nothing.
The table imports no PyMOL, so the target stays hermetic.
