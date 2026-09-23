# Recovery tests

Owned by approval, apply, and recovery evidence (master-plan item 10).
This directory proves the recovery-point lifecycle, approval verification,
apply/rollback behavior, and real-PyMOL mid-plan recovery. `apply_engine`,
`approval_verification`, `recovery_point`, `rollback`, `apply_real_pymol`,
`no_live_mutation_real_pymol`, and `no_mutation_sabotage` are the focused
Bazel targets. The real-PyMOL refusal matrix captures coordinates, colors,
representations, labels, view, settings, and session names before every
refusal; it also proves no recovery directory is created. The sabotage target
requires both the restore call and the post-restore comparison to reject and
preserve a point when a mutation survives.

The fidelity gate's own real-process evidence remains in `tests/integration`;
policy-denial evidence remains in `tests/adversarial`.
