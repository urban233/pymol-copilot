# `pmc_client`

`copilot <intent>` resolves the one loaded molecular object, extracts its
canonical snapshot, and submits it for planning. It never mutates the live
PyMOL session itself; the plan it prints is always the immutable one the
server validated, gated on the client's own independently observed fidelity
(`pmc_client.fidelity.check_fidelity`) reconstructing that same snapshot in a
fresh sidecar. Neither side's own verdict is trusted alone: `copilot_apply`
refuses whenever the server's `applicable` and the client's own fidelity
outcome disagree.

## The preview block

One `_output()` call prints the entire preview SPECIFICATION.md:503-511
requires, in a fixed order: the plan id and its expiry (absolute and
relative to the injected clock), the resolved object and its atom/state
counts, every canonical command numbered, with the atom count of each
`select` from the server's own `selectionCounts` where available;
validation warnings, or `none`; the fidelity status; a `checked`/`NOT
checked` statement; and the exact `copilot_apply`/`copilot_reject` commands
to type, character for character, including the plan id's own `p-` display
prefix. Every one of these prints every time, whether or not the plan turns
out to be applicable — a plan gated as inspectable-only still shows counts,
warnings, and both commands, with `apply:` reading
`unavailable (inspectable only)` instead of the command to type.

`checked` is deliberately specific about what actually ran. The sidecar
executor runs the plan on every preview, regardless of fidelity — the
request graph's own `validating` node never reads the request's fidelity
outcome before doing so — so the printed counts and warnings are always
real numbers from a real dispatch, never placeholders. What differs by
fidelity is only whether that dispatch ran against a reconstruction known to
match the live session:

- **Exact fidelity:** the sidecar rebuilt the session's declared state
  exactly, then ran the plan against it; the counts above describe this
  session. `NOT checked`: whether this is scientifically what you meant.
- **Not exact, or fidelity unavailable:** the sidecar still ran the plan and
  the counts are still real, but against a reconstruction that did not
  match (or could not be confirmed to match) the live session; the counts
  describe that reconstruction, not necessarily this session, and the plan
  cannot be applied. `NOT checked`: whether this reconstruction is the
  current session.

Neither case's `checked` line ever claims the plan "was never executed" —
that would be false regardless of fidelity, since the executor always runs
it. `tests/integration/preview_support.py`'s `section()` reads one named
line of the block by label, so a test never indexes the block positionally.

## `copilot_apply` and recovery

`copilot_apply p-<plan-id>` is the only mutation path: it re-checks the
entered plan and session IDs, applicability, expiry, current snapshot
digest, and contract versions, then obtains the server's canonical plan. The
reply must retain the preview's model identity and exact canonical PML
text; local policy is checked again before anything is saved.

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

## `copilot_health`

`copilot_health` reports client, server, engine, and contract-version facts
in one fixed block: this build's own application and protocol version; the
server's reachability and application version; the engine's health (ready,
with its own engine name, version, and device, or unavailable, with its own
bounded failure and action); the model identity; every contract version
this client and the responding server agree on, with a dedicated `<key>
server X / client Y -- MISMATCH` line for each one that disagrees; and
whether Copilot itself is halted. It is the one registered command that
never checks the halted latch before running — a user needs this
diagnostic precisely when something else has already gone wrong, so the
halt is reported on the block's own last line instead of refusing outright.
It sends no `/v1/plan` request and changes no client state: a pending plan
survives a `copilot_health` call untouched.

When the server cannot be reached at all, `server:` reads
`unavailable (<description>)` with its own next step, and `engine:`,
`model:`, and `contracts:` all read `unknown` — there is nothing to report
because nothing but the transport failure is known.

## Every failure is bounded and actionable

`pmc_client.messages` is the one place a failure line is built, so a future
change to wording changes it in one place. `describe_failure` renders a
server's own typed failure envelope; `describe_transport` renders a
transport-layer failure, recognizing the HTTP statuses `pmc_client.transport`
can raise; `describe_unexpected` renders a genuine internal defect by
exception type name only, never `str(error)` — a raw PyMOL or Python
exception can carry a selection expression, which SPECIFICATION.md:503-511
already prints elsewhere, never through an error. `ACTIONS` maps every
category in `pmc_core.protocol.FAILURE_CATEGORIES` to its own next step;
`tests/unit/test_client_messages.py` proves `ACTIONS` covers that whole set,
and `tests/integration/test_failure_messages.py` drives one row per failure
path this module has, proving each one actually reaches one of these three
functions rather than some other, unguarded `_output()` call.

A last-resort `_guarded()` wrapper sits around every registered command, for
a genuine defect in this module's own code that no other catch anticipates.
For `copilot`, `copilot_reject`, and `copilot_health`, which never mutate,
it reports the defect's type name and that nothing was applied. For
`copilot_apply` and `copilot_rollback`, which can, it cannot tell whether a
mutation already began; if a recovery point is retained when the defect is
caught, it halts Copilot and preserves that point instead of merely
reporting nothing was applied — the same conservative failure mode a
verified-failed restore already uses.

`copilot`, `copilot_apply`, `copilot_reject`, and `copilot_rollback` all
take an optional argument: PyMOL dispatches a bare invocation with zero
arguments, and each then prints a usage line rather than raising.
`copilot`'s own intent is registered under PyMOL's `parsing.LITERAL` mode
(`register()`'s own doing, since `pmc_client` keeps no dependency on
`pymol`) so a comma, `x=y`, or `;` inside it reaches this module as one
literal string, never split into PyMOL argument syntax; an intent past
`pmc_core.protocol.MAX_INTENT_LENGTH` is refused before a request is ever
built.
