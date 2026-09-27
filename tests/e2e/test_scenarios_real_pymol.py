# Copyright 2026 PyMOL Copilot contributors.
"""docs/master_plan.md item 12: scenarios 1-3, one real PyMOL launch.

Real here: headless Open-Source PyMOL (`pymol.finish_launching(["pymol",
"-qc"])`), PyMOL's own command registry (`cmd.extend`/`cmd.do`), the real
authenticated loopback server (`pmc_server.transport.LoopbackPlanServer`)
driven by the real `pmc_server.lifecycle.RequestGraphLifecycle` and the real
LangGraph request graph (`pmc_agent.graph`), the real
`pmc_client.transport.LoopbackPlanClient` and `pmc_client.command
.register_copilot`, and, for scenarios 1 and 2, the real
`pmc_core.executor.execute` (a genuine second headless PyMOL spawned per
preview) and the real `pmc_core.executor.probe_fidelity` (a third, for the
fidelity gate) -- both left at their defaults. Only the inference engine is
faked (`pmc_agent.inference.fake.FakeEngine`, scripted): no local model is
available in this environment, and a scripted engine is what keeps a
scenario's expected plan text deterministic.

Scenario 3 (the stale-plan scenario) never reaches apply, so it fakes both
the client's own fidelity probe and the server's own executor
(`scenario_support.fake_exact_probe`, `scenario_support.fake_ok_executor`) to
keep it fast; its subject is `pmc_client.approval.verify_approval`, not the
fidelity gate.

Every scenario is proved against `scenario_support.SessionFingerprint`, not
`pmc_core.snapshot` -- see this package's own README for why.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import os
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from preview_support import find_preview
from preview_support import plan_id_from
from preview_support import section
from pmc_agent.graph import PLAN_TTL_SECONDS
from pmc_agent.inference.base import STOP_END
from pmc_agent.inference.base import CompletionResult
from pmc_client.approval import normalize_plan_id
from pmc_client.command import CopilotCommandClient
from pmc_client.command import register_copilot
from pmc_client.recovery import RecoveryStore
from pmc_client.transport import LoopbackPlanClient
from pmc_core.protocol import PlanRequestV1
from pmc_server.transport import LoopbackPlanServer
from scenario_support import CREDENTIAL
from scenario_support import FIXTURE_PATH
from scenario_support import OBJECT_NAME
from scenario_support import ConsoleDriver
from scenario_support import FailColorProxy
from scenario_support import assert_unchanged
from scenario_support import build_lifecycle
from scenario_support import capture_fingerprint
from scenario_support import fake_exact_probe
from scenario_support import fake_ok_executor

INTENT = "Select chain A, color it red, show it as spheres, and orient on it."


def test_one_intent_through_preview_approve_and_apply(
    loaded_fixture: Any, tmp_path: Path
) -> None:
    """Scenario 1: a real preview mutates nothing.

    An approved apply mutates exactly the fields the approved plan named,
    and nothing else.
    """
    requests: list[PlanRequestV1] = []
    output: list[str] = []
    lifecycle = build_lifecycle()

    def record_lifecycle(request: PlanRequestV1) -> Any:
        requests.append(request)
        return lifecycle(request)

    server = LoopbackPlanServer(
        CREDENTIAL,
        record_lifecycle,
        apply_handler=lifecycle.apply,
        apply_outcome_handler=lifecycle.report_apply_outcome,
    )
    driver = ConsoleDriver(loaded_fixture)
    try:
        server.start()
        register_copilot(
            # pyrefly: ignore.  __getattr__ delegates the query surface at
            # runtime, but pyrefly cannot verify that structurally.
            driver,
            LoopbackPlanClient(server.port, CREDENTIAL),
            output.append,
            recovery_store=RecoveryStore(tmp_path),
        )
        before = capture_fingerprint(loaded_fixture)

        driver.run(f"copilot {INTENT}")
        after_preview = capture_fingerprint(loaded_fixture)

        plan_id = plan_id_from(output)
        driver.run(f"copilot_apply {plan_id}")
        after_apply = capture_fingerprint(loaded_fixture)
        apply_output = list(output)

        # 6a. The server-side request was recorded exactly once:
        #     `copilot_apply` uses its own separate `apply_handler`, so
        #     approving and applying a plan does not generate a second
        #     lifecycle request. Checked before the follow-up preview
        #     below, which legitimately adds a second one of its own.
        assert len(requests) == 1

        # 6b. Copilot is not blocked on an unconfirmed apply outcome: a
        #     fresh preview still comes back. Checked here, before the
        #     server closes, not after -- the same reasoning as scenario
        #     2's own `still_works` check: a `copilot` call issued once
        #     the server is already closed fails on the loopback
        #     connection for an unrelated reason, and the follow-up
        #     request would never reach the real handler at all.
        output.clear()
        driver.run(f"copilot {INTENT}")
        still_works = find_preview(output)
    finally:
        server.close()

    output = apply_output
    assert still_works

    # 1. Preview mutated nothing, including the view.
    assert_unchanged(before, after_preview)

    # 2. The preview block names the resolved object, the real selection
    #    counts, exact fidelity, and both approval commands.
    preview = find_preview(output)
    assert OBJECT_NAME in section(output, "object")
    assert section(output, "fidelity") == "exact on the declared state scope"
    assert "NOT applicable" not in preview
    commands = section(output, "commands")
    assert "1 | select copilot_selection, chain A" in commands
    assert "-> 2 atoms" in commands
    assert "2 | color red, copilot_selection" in commands
    assert "3 | show spheres, copilot_selection" in commands
    assert "4 | orient copilot_selection" in commands
    assert section(output, "apply").startswith("copilot_apply ")

    # 3. The apply outcome was reported as applied, with a retained
    #    recovery point.
    apply_lines = [line for line in output if line.startswith("copilot_apply:")]
    assert len(apply_lines) == 1
    assert apply_lines[0].startswith(f"copilot_apply: plan {plan_id} applied.")

    # 4. Approval changed the colour, the representations, and the view
    #    (the plan ends in orient) -- and nothing on chain B.
    assert after_apply.colors != before.colors
    assert after_apply.representations != before.representations
    assert after_apply.view != before.view
    assert after_apply.chain_b_atom_count == before.chain_b_atom_count
    # Coordinates are unchanged; only colour, representations, and view move.
    assert after_apply.coordinates == before.coordinates
    # A successful apply legitimately leaves its own created selection in
    # the session -- unlike scenario 2's automatic recovery, nothing here
    # is supposed to undo it.
    assert after_apply.object_names == tuple(
        sorted((*before.object_names, "copilot_selection"))
    )

    # 5. Exactly one recovery point exists, with the expected permissions
    #    on POSIX (Windows relies on the user profile ACL instead, the
    #    same distinction pmc_client.recovery's own module documents).
    recovery_dir = tmp_path / ".pymol-copilot" / "recovery"
    points = list(recovery_dir.glob(f"plan-{normalize_plan_id(plan_id)}.pse"))
    assert len(points) == 1
    if os.name != "nt":
        assert oct(points[0].stat().st_mode & 0o777) == oct(0o600)


def test_color_on_a_selection_whose_object_was_deleted_does_not_raise(
    loaded_fixture: Any,
) -> None:
    """Document why scenario 2 below uses a synthetic failure trigger.

    The obvious real trigger for a mid-apply failure -- delete the plan's
    target object between two live commands, so the second one (`color`,
    on a selection the first one just created) fails against real PyMOL --
    does not work: a `select()`-created name stays registered in PyMOL's
    own name table even after its source object is deleted, matching zero
    atoms rather than becoming undefined, so `color` on it silently no-ops.
    That differs from `tests/integration/pymol_error_cases.py`'s own
    `undefined_selection` case, which is a name that was never passed to
    `select()` at all, and does raise. Confirmed here, once, before
    scenario 2 relies on the alternative: `scenario_support.FailColorProxy`,
    which raises synthetically for its second command, the same shape as
    `tests/recovery/test_apply_real_pymol.py`'s own `_FailColorProxy`.
    """
    loaded_fixture.select("copilot_probe", "chain A")
    loaded_fixture.delete(OBJECT_NAME)

    loaded_fixture.color("red", "copilot_probe")  # does not raise

    # Leave the fixture exactly as `loaded_fixture`'s own teardown expects,
    # and remove `copilot_probe` too: this real_pymol session is shared by
    # every test in this module, and a leftover selection here would
    # pollute a later test's own `copilot_`-prefix name-list assertion.
    loaded_fixture.load(str(FIXTURE_PATH), OBJECT_NAME)
    loaded_fixture.delete("copilot_probe")


def test_a_mid_apply_failure_is_restored_through_automatic_recovery(
    loaded_fixture: Any, tmp_path: Path
) -> None:
    """Scenario 2: a real second command fails mid-apply.

    The whole session is restored automatically, and Copilot is not
    halted.
    """
    output: list[str] = []
    lifecycle = build_lifecycle(
        completions=[
            # Two, not one: the test itself issues two separate `copilot`
            # requests against this one scripted engine -- the mid-apply
            # failure, and the later "not halted" check.
            CompletionResult(
                "select copilot_selection, chain A\n"
                "color red, copilot_selection\n",
                "m-1",
                STOP_END,
            )
            for _ in range(2)
        ],
        max_repair_attempts=0,
    )
    server = LoopbackPlanServer(
        CREDENTIAL,
        lifecycle,
        apply_handler=lifecycle.apply,
        apply_outcome_handler=lifecycle.report_apply_outcome,
    )
    proxy = FailColorProxy(loaded_fixture)
    driver = ConsoleDriver(proxy)
    try:
        server.start()
        register_copilot(
            # pyrefly: ignore.  __getattr__ delegates the query surface at
            # runtime, but pyrefly cannot verify that structurally.
            driver,
            LoopbackPlanClient(server.port, CREDENTIAL),
            output.append,
            recovery_store=RecoveryStore(tmp_path),
        )
        before = capture_fingerprint(loaded_fixture)

        driver.run(f"copilot {INTENT}")
        plan_id = plan_id_from(output)
        driver.run(f"copilot_apply {plan_id}")

        after = capture_fingerprint(loaded_fixture)
        apply_output = list(output)

        # 6. Copilot is not halted: a fresh preview still works. Checked
        #    here, before the server closes, not after.
        output.clear()
        driver.run(f"copilot {INTENT}")
        still_works = find_preview(output)
    finally:
        server.close()

    assert still_works
    output = apply_output

    # 1 & 2. Command 1 (`select`) really mutated real PyMOL -- it created
    #    `copilot_selection` -- and the whole session was restored to
    #    exactly what it was before the apply began, undoing that real
    #    mutation along with command 2's synthetic failure.
    assert_unchanged(before, after)
    assert OBJECT_NAME in after.object_names

    # 3. No copilot_-prefixed selection survives the restore.
    assert not any(name.startswith("copilot_") for name in after.object_names)

    # 4. The console reported a clean automatic restore, bounded and with
    #    no plan text leaking through.
    restored_lines = [
        line for line in output if line.startswith("copilot_apply:")
    ]
    assert len(restored_lines) == 1
    assert "restored cleanly" in restored_lines[0]
    assert len(restored_lines[0].encode()) < 400
    assert "Traceback" not in restored_lines[0]
    assert "copilot_selection" not in restored_lines[0]

    # 5. The recovery point was consumed, not preserved.
    recovery_dir = tmp_path / ".pymol-copilot" / "recovery"
    assert (
        list(recovery_dir.glob(f"plan-{normalize_plan_id(plan_id)}.pse")) == []
    )


def test_stale_plan_digest_drift_is_rejected(
    loaded_fixture: Any, tmp_path: Path
) -> None:
    """Scenario 3a: the session changing after preview stales the plan."""
    output: list[str] = []
    lifecycle = build_lifecycle(executor=fake_ok_executor)
    server = LoopbackPlanServer(
        CREDENTIAL,
        lifecycle,
        apply_handler=lifecycle.apply,
        apply_outcome_handler=lifecycle.report_apply_outcome,
    )
    driver = ConsoleDriver(loaded_fixture)
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
        plan_id = plan_id_from(output)

        # The user changes chain B directly -- a real mutation, on a chain
        # the plan never touches, so only the digest differs.
        loaded_fixture.color("blue", "chain B")
        after_user_change = capture_fingerprint(loaded_fixture)

        output.clear()
        driver.run(f"copilot_apply {plan_id}")
        after_refusal = capture_fingerprint(loaded_fixture)
    finally:
        server.close()

    assert len(output) == 1
    assert output[0] == (
        f"copilot_apply: the session changed since plan {plan_id} was "
        "made. Nothing was applied."
    )
    # Copilot added nothing of its own on top of the user's own change.
    assert_unchanged(after_user_change, after_refusal)

    recovery_dir = tmp_path / ".pymol-copilot" / "recovery"
    assert not recovery_dir.exists()


def test_stale_plan_expiry_is_rejected_before_querying_pymol(
    loaded_fixture: Any, tmp_path: Path
) -> None:
    """Scenario 3b: an expired plan is refused before any live PyMOL query.

    The preliminary check alone settles it.
    """
    output: list[str] = []
    lifecycle = build_lifecycle(executor=fake_ok_executor)
    server = LoopbackPlanServer(
        CREDENTIAL,
        lifecycle,
        apply_handler=lifecycle.apply,
        apply_outcome_handler=lifecycle.report_apply_outcome,
    )

    get_names_calls: list[str] = []
    real_get_names = loaded_fixture.get_names

    def counting_get_names(*args: Any, **kwargs: Any) -> Any:
        get_names_calls.append(args[0] if args else "objects")
        return real_get_names(*args, **kwargs)

    driver = ConsoleDriver(loaded_fixture)
    driver.get_names = counting_get_names  # pyrefly: ignore.

    client = CopilotCommandClient(
        LoopbackPlanClient(server.port, CREDENTIAL),
        output.append,
        probe=fake_exact_probe,
        recovery_store=RecoveryStore(tmp_path),
        now_factory=lambda: (
            datetime.now(UTC) + timedelta(seconds=PLAN_TTL_SECONDS + 30)
        ),
    )
    try:
        server.start()
        # pyrefly: ignore.  __getattr__ delegates the query surface at
        # runtime, but pyrefly cannot verify that structurally.
        client.register(driver)
        driver.run(f"copilot {INTENT}")
        plan_id = plan_id_from(output)
        before_calls = len(get_names_calls)

        output.clear()
        driver.run(f"copilot_apply {plan_id}")
    finally:
        server.close()

    assert len(output) == 1
    assert output[0].startswith(f"copilot_apply: plan {plan_id} expired at ")
    assert output[0].endswith(". Nothing was applied.")
    # The preliminary check settles an expired plan without ever touching
    # PyMOL: no further get_names call happened after the plan was minted.
    assert len(get_names_calls) == before_calls

    recovery_dir = tmp_path / ".pymol-copilot" / "recovery"
    assert not recovery_dir.exists()


if __name__ == "__main__":
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
