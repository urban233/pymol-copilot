# Integration tests

Owned by cross-subsystem evidence: the non-mutating copilot command seam,
the loopback transport, the real client-server round trip, and the
real-PyMOL conformance suite that drives the two-chain fixture through a
real server. Also owns `pmc_core.snapshot`'s real-PyMOL evidence --
`snapshot_support.py` (the shared `real_pymol`/`loaded_fixture` fixtures
and the nested-subprocess-via-environment-variable technique), the
extraction/reconstruction round trip, and the nested-runner regression
guard -- promoted from `tests/discovery/h02` once that candidate
comparison shipped as production code. The snapshot format's own
PyMOL-free codec/digest/diff evidence stays in `tests/contract` instead.

Also owns the sidecar executor's own real-process evidence
(docs/master_plan.md item 4), promoted from that same `tests/discovery/h02`
prototype once it shipped as `src/pmc_core/executor.py` and
`src/pmc_sidecar/child.py`: `test_sidecar_child.py` (the closed verb
dispatch and bounded command diagnostics against real PyMOL, no subprocess),
`test_executor_boundary.py` (the spawn/deadline/kill/reap/cleanup and bounded
stderr/error sabotage suite, built on this directory's own test-owned
`sabotage_child.py`), and
`test_executor_round_trip.py` (the positive path, against an
independently computed expected value). `tests/discovery/h02` no longer
exists; its differential evidence and its execution-boundary prototype are
both fully promoted.

Also owns the real-PyMOL half of the error envelope. `pymol_error_cases.py`
holds the deliberately broken commands, shared as a bare sibling module by
`capture_pymol_errors.py` (which regenerates
`tests/contract/testdata/pymol_errors/`) and `test_errors_real_pymol.py`
(which re-drives them and fails when the checked-in strings stop matching),
so the two can never disagree about what was driven, and by
`//tests/contract:errors`, which checks each captured envelope's command
index and verb against it. The hermetic normalization evidence stays in
`tests/contract`.

Also owns the live-extraction-and-fidelity-gate's real-process evidence
(docs/master_plan.md item 7): `test_sidecar_fidelity.py` (`src/pmc_sidecar
/fidelity.py`'s reconstruct-and-re-extract logic against real PyMOL, no
subprocess -- the fresh-process spawn evidence for that same child lives
here too, in `test_client_fidelity_real_pymol.py` below) and
`test_client_fidelity_real_pymol.py` (`pmc_client.fidelity.check_fidelity()`
gated on a real sidecar spawn: modified coordinates, multiple states,
alternate locations, hetero atoms, and all four combined, each asserting an
exact reconstruction with an empty diff and equal structure digest, built on
this directory's own test-owned `fidelity_sabotage_child.py` -- unlike
`sabotage_child.py` above, a real-PyMOL-touching sabotage that reconstructs
and re-extracts honestly, then perturbs one field of its own re-extraction,
so the fidelity gate is proven to catch a real, named discrepancy rather
than merely to pass when nothing is checked). `test_client_fidelity_real
_pymol.py` also covers a fake timeout probe becoming `FIDELITY_UNAVAILABLE`,
with no subprocess involved. `test_command.py` and `test_client_server
_command.py` cover `pmc_client.command`'s own real request, pending plan,
and `copilot_apply` refusal logic against fake sessions and fake probes,
never spawning anything; `test_real_pymol_command.py`'s own happy-path test
covers the full real-PyMOL, real-server, real-sidecar `copilot` then
`copilot_apply` round trip, with a recording lifecycle proving the request
carried a computed digest and `assert_session_unchanged` held across both
commands. The client's own PyMOL-free session-resolution and fidelity-gate
adjudication logic stays in `tests/contract` instead, matching how the
snapshot format's codec/digest/diff evidence is split above.
