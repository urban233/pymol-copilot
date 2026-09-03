# Copyright 2026 PyMOL Copilot contributors.
"""Sabotage check for the default-deny policy contract.

The test runs the focused policy suite against a disposable copy of the core
package after changing the unsupported-operation branch to allow. The suite
must fail, proving that its assertions detect this realistic safety regression.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pmc_core


def test_policy_suite_rejects_allowing_unsupported_operations() -> None:
    """The policy suite fails when default deny is deliberately disabled.

    Raises:
        AssertionError: If the expected default-deny branch is absent.
    """
    source_package = Path(pmc_core.__file__).parent
    source_test = Path(__file__).with_name("test_policy.py")

    with tempfile.TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        package = root / "pmc_core"
        shutil.copytree(source_package, package)
        test_file = root / "test_policy.py"
        shutil.copy2(source_test, test_file)

        policy_file = package / "policy.py"
        policy_source = policy_file.read_text(encoding="utf-8")
        original = """        case _:
            return PolicyDecision(
                operation_index=operation_index,
                allowed=False,
                reason=REASON_UNSUPPORTED_OPERATION_TYPE,
            )
"""
        sabotaged = original.replace("allowed=False", "allowed=True", 1)
        if original not in policy_source:
            raise AssertionError("default-deny branch was not found")
        policy_file.write_text(
            policy_source.replace(original, sabotaged, 1), encoding="utf-8"
        )

        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(root)
        result = subprocess.run(
            [sys.executable, "-m", "pytest", str(test_file), "-q"],
            cwd=root,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )

    assert result.returncode != 0, result.stdout + result.stderr
    assert "test_non_operation_value_is_denied_by_default" in (
        result.stdout + result.stderr
    )


if __name__ == "__main__":
    raise SystemExit(
        subprocess.call([sys.executable, "-m", "pytest", __file__])
    )
