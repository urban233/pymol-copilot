# End-to-end tests

Owned by docs/master_plan.md item 12: the five scenarios its brief names,
each driven from `cmd.do("copilot ...")` against a real headless PyMOL and a
real loopback server, plus the sabotage matrix that proves the suite's own
mutation check can fail, plus the per-stage latency record.

- `test_scenarios_real_pymol.py` -- scenario 1 (one intent through preview,
  approve and apply), scenario 2 (a mid-apply failure through automatic
  recovery) and scenario 3 (a stale plan rejected after the session
  changed). One module, one PyMOL launch, because scenarios 1 and 2 spawn a
  real sidecar per preview and the module docstring says exactly where the
  real/fake line falls for each.
- `test_denied_command_real_pymol.py` -- scenario 4: a denied command
  rejected before any sidecar execution, proved by a counting wrapper around
  the real `pmc_core.executor.execute` and by the absence of any
  `pmc-executor-*` scratch directory.
- `test_server_unavailable_real_pymol.py` -- scenario 5: a real
  `//src/pmc_server:server` process, started and then killed, covering never
  started, died mid-session, and up-with-the-engine-down.
- `test_fingerprint_sabotage.py` -- the sabotage test
  [SPECIFICATION.md:723](../../SPECIFICATION.md#L723) asks for by name:
  a real PyMOL mutation of every field this directory's own fingerprint
  compares, proving the check can fail, plus the negative that a genuine
  no-op does not trip it.
- `test_harness.py` -- proves `scenario_support.py`'s own fixtures and
  fingerprint before any scenario relies on them.
- `test_latency.py`, `record_latency.py` -- the p50-per-stage record. The
  arithmetic is checked hermetically; the record itself is a `py_binary`
  run by hand, writing `results/latency-<platform>-<node>.md` (ignored) and
  feeding the tracked table in `docs/latency.md`.

**This directory keeps its own fingerprint, deliberately separate from
`tests/recovery/session_fingerprint.py`.** That module reuses
`pmc_core.snapshot.extract`, which is the right choice for a test whose
subject is `pmc_client.apply.apply_plan` -- it is testing what the product
does with its own extraction. It is the wrong choice for this directory's
own job, which is proving *nothing PyMOL-visible* moved: if `extract()`
itself lost a field, a fingerprint built on it would silently agree with the
bug. `scenario_support.SessionFingerprint` is captured with PyMOL's own
query APIs only (`iterate`, `iterate_state`, `get_names("all")`,
`get_view()`) and never imports `pmc_core.snapshot`. It also includes the
camera view, which `pmc_core.snapshot.structure_digest` deliberately
excludes -- a refusal path that silently re-oriented the camera is still an
unapproved mutation of the user's session, even though it would never make
a plan stale.

Component-level recovery evidence (`apply_plan`, `verify_approval`,
`RecoveryStore` called directly) stays in [tests/recovery/](../recovery/).
Fidelity-process evidence (differential hashes, sabotaged children) stays in
[tests/integration/](../integration/). This directory is the one place all
of it is driven together, end to end, exactly as a user would type it.
