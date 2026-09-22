# Recovery tests

Owned by approval, apply, and recovery evidence (master-plan item 10).
This directory proves the recovery-point lifecycle, approval verification,
apply/rollback behavior, and that every refusal path leaves the live PyMOL
session unchanged. It also contains the sabotage proof that the suite detects
a missing automatic restore.

The fidelity gate's own real-process evidence remains in `tests/integration`;
policy-denial evidence remains in `tests/adversarial`.
