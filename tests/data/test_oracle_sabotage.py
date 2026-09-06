# Copyright 2026 PyMOL Copilot contributors.
"""Sabotage check proving a corrupted oracle fails its own conformance test.

The test runs the focused oracle suite against a disposable copy of the data
package after changing the independent chain-membership derivation to always
report no atoms. The suite must fail, proving that its assertions detect
this realistic oracle-correctness regression -- the exact risk this whole
task exists to retire (an oracle that stops actually deriving expectations
independently of the query it is meant to grade).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pmc_data


def test_oracle_suite_rejects_a_corrupted_chain_membership_derivation() -> None:
    """The oracle suite fails when independent derivation is disabled.

    Raises:
        AssertionError: If the expected derivation line is absent.
    """
    source_package = Path(pmc_data.__file__).parent
    source_test = Path(__file__).with_name("test_oracle.py")
    source_testdata = Path(__file__).with_name("testdata")

    with tempfile.TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        package = root / "pmc_data"
        shutil.copytree(source_package, package)
        test_file = root / "test_oracle.py"
        shutil.copy2(source_test, test_file)
        shutil.copytree(source_testdata, root / "testdata")

        oracle_file = package / "oracle.py"
        oracle_source = oracle_file.read_text(encoding="utf-8")
        original = "    atoms = read_atoms(pdb_path)\n    return atom_ids_for_chain(atoms, chain_id)\n"
        sabotaged = "    return frozenset()\n"
        if original not in oracle_source:
            raise AssertionError("independent derivation body was not found")
        oracle_file.write_text(
            oracle_source.replace(original, sabotaged, 1), encoding="utf-8"
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
    assert "test_expected_chain_a_atom_ids_match_the_known_fixture_layout" in (
        result.stdout + result.stderr
    )


if __name__ == "__main__":
    raise SystemExit(
        subprocess.call([sys.executable, "-m", "pytest", __file__])
    )
