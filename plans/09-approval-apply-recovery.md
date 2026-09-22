# Approval, apply, recovery

**State:** Accepted · **Tracker:** GitHub issue #50

## Outcome

An approved, immutable pending plan may change the live PyMOL session exactly
once. Before mutation the client re-verifies plan/session identity, expiry,
fidelity digest, contract manifest, model identity, canonical plan text, and
policy. It writes a private recovery `.pse`, applies through the same closed
dispatcher as the sidecar, and restores plus compares the complete session on
the first execution failure. An explicit rollback restores and consumes the
retained recovery point.

## Fixed decisions

- The server owns the approval handshake and reports `applying`, `applied`,
  `apply_failed_restored`, and `rolled_back`; restoring is a client-only
  transient.
- Recovery lives at `~/.pymol-copilot/recovery/plan-<id>.pse`, with 0700
  directory and 0600 file modes on POSIX. One point is retained per session;
  it is replaced by apply, consumed by rollback, removed on close, and
  preserved only after a failed restore.
- A failed restore latches Copilot permanently for the PyMOL process and
  prints the preserved recovery path and manual instructions.
- `/v1/apply` returns the server's canonical plan. The client refuses if its
  rendered text or model identity differs from the printed pending plan.
- `PROTOCOL_VERSION` remains `1`; missing new fields fail closed.
- The feature ships as one linked PR, with one commit per implementation
  step. Its complete, review-approved design and detailed acceptance criteria
  are the authoritative body of GitHub issue #50.

## Delivery sequence

1. Add recovery-test wiring and this document.
2. Extend the wire protocol for approval and terminal outcomes.
3. Implement the private recovery-point lifecycle.
4. Add pure local approval verification.
5. Add graph applying/applied states and server-side expiry recheck.
6. Add authenticated apply and outcome endpoints.
7. Implement save, closed dispatch, restore, and full comparison.
8. Make `copilot_apply` perform the approved handshake.
9. Add explicit `copilot_rollback`.
10. Prove save/restore behavior with real PyMOL.
11. Prove no mutation on every refusal path and sabotage the restore path.
12. Complete user documentation and correct master-plan state.

## Required evidence

Every step runs the full repository gate. The final PR additionally runs the
recovery suite, dependency-boundary audit, source audits for legacy
"not implemented" text and `.pse` handling, plus the manual headless-PyMOL
exercise recorded in issue #50.
