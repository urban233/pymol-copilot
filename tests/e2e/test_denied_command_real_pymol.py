# Copyright 2026 PyMOL Copilot contributors.
"""docs/master_plan.md item 12, scenario 4: denied before any sidecar spawn.

`pmc_agent.graph._validating`'s fixed order is cancellation -> hostile
screen -> parse -> policy -> executor. This module proves that order is
load-bearing: the real `pmc_core.executor.execute` is wrapped in a counting
proxy (never a fake -- the spawn that would happen is the real one, and the
count is the evidence that it did not), and a second, independent observable
(no `pmc-executor-*` scratch directory ever appears) rules out a spawn this
module's own count could somehow miss.

Confirmed empirically (not merely assumed) which gate actually denies this
module's own completion: `parse_pml` itself rejects a reference to a
selection no earlier command created, before `pmc_core.policy` is ever
called. `pmc_core.policy`'s own re-checks (SPECIFICATION.md-mandated
defense in depth) exist for a plan a dataclass could be reconstructed into
by bypassing `__post_init__` -- not reachable through ordinary completion
text, which the parser validates structurally to begin with. Either gate
denying before the executor runs satisfies this scenario's own claim, and
the sabotage that proves it targets the gate this completion actually
passes through: the parse-rejection branch in `_validating`, not the
policy one.

Everything here is real except the inference engine (`FakeEngine`, scripted
with three denied completions -- one per attempt, since
`MAX_REPAIR_ATTEMPTS = 2`) and the client's own fidelity probe
(`scenario_support.fake_exact_probe`: this scenario never reaches apply, so
the fidelity gate is not its subject).
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import pytest

from pmc_agent.graph import MAX_REPAIR_ATTEMPTS
from pmc_agent.inference.base import STOP_END
from pmc_agent.inference.base import CompletionResult
from pmc_agent.inference.fake import FakeEngine
from pmc_agent.session import RequestGraphSession
from pmc_client.command import register_copilot
from pmc_client.messages import ACTIONS
from pmc_client.recovery import RecoveryStore
from pmc_client.transport import LoopbackPlanClient
from pmc_core.executor import SCRATCH_DIR_PREFIX
from pmc_core.executor import execute
from pmc_server.lifecycle import RequestGraphLifecycle
from pmc_server.transport import LoopbackPlanServer
from scenario_support import CREDENTIAL
from scenario_support import ConsoleDriver
from scenario_support import assert_unchanged
from scenario_support import build_lifecycle
from scenario_support import capture_fingerprint
from scenario_support import counting
from scenario_support import fake_exact_probe

#: A prefix-legal selection name that no earlier command in the completion
#: creates: `parse_pml` itself rejects this, category `undefined_selection`
#: (confirmed empirically -- see the module docstring). The distinctive
#: suffix is this module's own leak sentinel: if it ever showed up in
#: captured console output, some bounded failure line let raw plan text
#: through.
_LEAK_SENTINEL = "leak9f3a"
_DENIED_COMPLETION = f"color red, copilot_undef{_LEAK_SENTINEL}\n"

#: A completion the hostile screen itself must catch, at zero repair
#: attempts -- the lone single quote has no legitimate use in this
#: restricted command language (`src/pmc_core/screen.py`).
_HOSTILE_COMPLETION = "color red, 'x'\n"

INTENT = "Color chain A red."


def test_a_denied_plan_never_reaches_the_real_executor(
    loaded_fixture: Any, tmp_path: Path
) -> None:
    """Scenario 4: the plan is denied before the real sidecar is spawned."""
    output: list[str] = []
    executor, calls = counting(execute)
    lifecycle = build_lifecycle(
        completions=[
            CompletionResult(_DENIED_COMPLETION, "m-1", STOP_END)
            for _ in range(MAX_REPAIR_ATTEMPTS + 1)
        ],
        executor=executor,
    )
    server = LoopbackPlanServer(
        CREDENTIAL,
        lifecycle,
        apply_handler=lifecycle.apply,
        apply_outcome_handler=lifecycle.report_apply_outcome,
    )
    driver = ConsoleDriver(loaded_fixture)
    scratch_root = tmp_path / "scratch"
    scratch_root.mkdir()
    before = capture_fingerprint(loaded_fixture)
    try:
        server.start()
        register_copilot(
            # pyrefly: ignore.  __getattr__ delegates the query surface at
            # runtime, but pyrefly cannot verify that structurally.
            driver,
            LoopbackPlanClient(server.port, CREDENTIAL),
            output.append,
            probe=fake_exact_probe,
            recovery_store=RecoveryStore(tmp_path),
        )
        original_tempdir = tempfile.tempdir
        tempfile.tempdir = str(scratch_root)
        try:
            driver.run(f"copilot {INTENT}")
        finally:
            tempfile.tempdir = original_tempdir
    finally:
        server.close()

    after = capture_fingerprint(loaded_fixture)

    # 1. The real executor was wrapped, and never called.
    assert calls == []

    # 2. Independently: no sidecar scratch directory was ever created.
    assert list(scratch_root.glob(f"{SCRATCH_DIR_PREFIX}*")) == []

    # 3. One bounded, actionable line naming a real next step; no plan id;
    #    no leak of the denied plan's own text.
    assert len(output) == 1
    line = output[0]
    assert line.startswith("copilot:")
    assert len(line.encode()) < 400
    assert "Traceback" not in line
    assert any(action in line for action in ACTIONS.values())
    assert "p-" not in line
    assert _LEAK_SENTINEL not in line

    # 4. Nothing was mutated, and no recovery point was ever created.
    assert_unchanged(before, after)
    recovery_dir = tmp_path / ".pymol-copilot" / "recovery"
    assert not recovery_dir.exists()

    # 5. Nothing pending: apply on any id is refused for lack of one.
    output.clear()
    driver.run("copilot_apply p-00000000-0000-0000-0000-000000000000")
    assert output == [
        "copilot_apply: no pending plan for this session. Nothing was applied."
    ]


def test_a_hostile_completion_is_rejected_at_zero_repair_attempts(
    loaded_fixture: Any, tmp_path: Path
) -> None:
    """A hostile completion never reaches the real executor.

    The screen terminates the request on the first attempt, before the
    repair loop ever runs.
    """
    output: list[str] = []
    executor, calls = counting(execute)
    engine = FakeEngine(
        [CompletionResult(_HOSTILE_COMPLETION, "m-1", STOP_END)]
    )
    session = RequestGraphSession(engine=engine, executor=executor)
    lifecycle = RequestGraphLifecycle(session=session)
    server = LoopbackPlanServer(
        CREDENTIAL,
        lifecycle,
        apply_handler=lifecycle.apply,
        apply_outcome_handler=lifecycle.report_apply_outcome,
    )
    driver = ConsoleDriver(loaded_fixture)
    before = capture_fingerprint(loaded_fixture)
    try:
        server.start()
        register_copilot(
            # pyrefly: ignore.  __getattr__ delegates the query surface at
            # runtime, but pyrefly cannot verify that structurally.
            driver,
            LoopbackPlanClient(server.port, CREDENTIAL),
            output.append,
            probe=fake_exact_probe,
            recovery_store=RecoveryStore(tmp_path),
        )
        driver.run(f"copilot {INTENT}")
    finally:
        server.close()
    after = capture_fingerprint(loaded_fixture)

    # The hostile screen terminates the request at zero repair attempts:
    # the engine is asked exactly once, not up to MAX_REPAIR_ATTEMPTS + 1
    # times.
    assert len(engine.calls) == 1
    assert calls == []
    assert len(output) == 1
    assert "'" not in output[0]
    assert_unchanged(before, after)


if __name__ == "__main__":
    import os
    import sys

    # Real PyMOL's headless launch leaves behind cleanup that can complete
    # after this process would otherwise exit, overriding a genuine pytest
    # failure with process exit code 0 (see the same __main__ block in
    # tests/integration/test_real_pymol_command.py). os._exit bypasses that
    # window, and the explicit flushes keep a real failure's traceback from
    # being lost from the captured test log.
    _exit_code = pytest.main([__file__])
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(_exit_code)
