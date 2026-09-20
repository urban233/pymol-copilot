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
