# `pmc_client`

`copilot` previews a validated immutable plan. It does not mutate the live
PyMOL session. `copilot_apply p-<plan-id>` is the only ordinary mutation
path: it re-checks the entered plan and session IDs, applicability, expiry,
current snapshot digest, and contract versions, then obtains the server's
canonical plan. The reply must retain the preview's model identity and exact
canonical PML text; local policy is checked again before anything is saved.

Before dispatching the plan, the client saves the entire session as
`~/.pymol-copilot/recovery/plan-<id>.pse`. The directory is mode 0700 and the
file is mode 0600 on POSIX (Windows relies on the current user profile ACL).
Plans run only through `pmc_sidecar.child.run_plan`'s closed typed dispatch.
The first failed command triggers immediate complete-session restoration;
the restored snapshot and the complete name list must match the pre-apply
evidence. A successful apply retains exactly one point for rollback. The next
apply replaces it; `close()` removes it when the owning client session ends.

`copilot_rollback p-<plan-id>` explicitly replaces the entire session with
that retained pre-apply point and removes the file only after the same full
comparison succeeds. It warns when later changes will be discarded. If an
automatic restore or rollback cannot be verified, Copilot is permanently
halted for that PyMOL process and preserves the recovery path. Restart PyMOL
and load that `.pse` manually; there is intentionally no in-process bypass.
