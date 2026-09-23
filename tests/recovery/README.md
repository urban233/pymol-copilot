# Recovery tests

Owned by approval, apply, and recovery evidence (master-plan item 10).
This directory proves the recovery-point lifecycle, approval verification,
apply/rollback behavior, and real-PyMOL mid-plan recovery. `apply_engine`,
`approval_verification`, `recovery_point`, `rollback`, and
`apply_real_pymol` are the focused Bazel targets. The unit recovery tests
also sabotage the restore comparison and require the result to latch rather
than silently consume an untrustworthy point.

The fidelity gate's own real-process evidence remains in `tests/integration`;
policy-denial evidence remains in `tests/adversarial`.
