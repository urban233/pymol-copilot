# Contract tests

Owned by shared-core contract evidence: the plan/policy/protocol fixtures,
and the canonical snapshot format's deterministic codec, declared-
unsupported marker, structure digest, and field-by-field diff (all
PyMOL-free -- the real-PyMOL extraction/reconstruction round trip lives in
`tests/integration`).

Also owns the error envelope's evidence. `test_errors.py` proves
`pmc_core.errors` against `testdata/pymol_errors/`, a corpus of real PyMOL
failure strings captured by
`//tests/integration:capture_pymol_errors` and checked in. That test
launches no PyMOL; the target that re-drives the same broken commands
against a live PyMOL, and so fails when an upgrade rewords a message, is
`//tests/integration:errors_real_pymol`. The corpus is exported to it by
the `pymol_error_corpus` filegroup, since Bazel's `glob` cannot reach
across a package boundary.
