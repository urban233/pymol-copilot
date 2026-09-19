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

Also owns the real-PyMOL half of the error envelope. `pymol_error_cases.py`
holds the deliberately broken commands, shared as a bare sibling module by
`capture_pymol_errors.py` (which regenerates
`tests/contract/testdata/pymol_errors/`) and `test_errors_real_pymol.py`
(which re-drives them and fails when the checked-in strings stop matching),
so the two can never disagree about what was driven. The hermetic
normalization evidence stays in `tests/contract`.
