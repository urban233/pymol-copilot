# Copyright 2026 PyMOL Copilot contributors.
"""Sabotage checks proving a corrupted oracle fails its own conformance tests.

Each check runs the focused oracle suite against a disposable copy of the
data package after breaking one independent derivation. The suite must
fail, proving its assertions detect a realistic oracle-correctness
regression -- the exact risk this whole task exists to retire: an oracle
that stops actually deriving expectations independently of the query it
is meant to grade.

Two derivations are covered, because the oracle now has two. The
original chain-membership derivation reads a controlled PDB file and
serves the chain-A gold case. The generalized selection evaluator reads
a typed expression against an authored snapshot and is what the dataset
pipeline predicts with; a corruption there would silently mislabel every
generated sample rather than fail loudly.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pmc_data


def _run_oracle_suite_against_a_corrupted_copy(
    original: str, sabotaged: str
) -> str:
    """Break one derivation in a package copy and run the oracle suite.

    Args:
        original: The exact source text to replace in oracle.py.
        sabotaged: The text to replace it with.

    Returns:
        The combined stdout and stderr of the nested pytest run.

    Raises:
        AssertionError: If original is absent from oracle.py -- the
            derivation this check aims at has moved, so the check would
            otherwise silently stop testing anything.
    """
    source_package = Path(pmc_data.__file__).parent
    source_test = Path(__file__).with_name("test_oracle.py")
    source_testdata = Path(__file__).with_name("testdata")

    # Bazel serializes this target against every other test (BUILD.bazel's
    # tags = ["exclusive"]) so the shutil.copytree below never races another
    # process writing into the shared source package's __pycache__; that
    # protection lives in the build graph, not here, so it does not apply
    # when this module is run outside `bazel test` (direct invocation, an
    # IDE runner, or future pytest-xdist parallelism).
    with tempfile.TemporaryDirectory(
        ignore_cleanup_errors=True
    ) as temporary_directory:
        root = Path(temporary_directory)
        package = root / "pmc_data"
        shutil.copytree(source_package, package)
        test_file = root / "test_oracle.py"
        shutil.copy2(source_test, test_file)
        shutil.copytree(source_testdata, root / "testdata")

        oracle_file = package / "oracle.py"
        oracle_source = oracle_file.read_text(encoding="utf-8")
        if original not in oracle_source:
            raise AssertionError(
                f"independent derivation body was not found: {original!r}"
            )
        oracle_file.write_text(
            oracle_source.replace(original, sabotaged, 1), encoding="utf-8"
        )

        environment = os.environ.copy()
        # The sabotaged copy must win over the real package, but the rest
        # of the interpreter's own import path has to survive: oracle.py
        # imports pmc_core, which Bazel puts on sys.path rather than in
        # PYTHONPATH, so replacing PYTHONPATH outright would turn this
        # check into an ImportError that passes for the wrong reason.
        environment["PYTHONPATH"] = os.pathsep.join([str(root), *sys.path])
        result = subprocess.run(
            [sys.executable, "-m", "pytest", str(test_file), "-q"],
            cwd=root,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )

    output = result.stdout + result.stderr
    assert result.returncode != 0, output
    return output


def test_oracle_suite_rejects_a_corrupted_chain_membership_derivation() -> None:
    """The oracle suite fails when independent chain derivation is disabled."""
    output = _run_oracle_suite_against_a_corrupted_copy(
        original=(
            "    atoms = read_atoms(pdb_path)\n"
            "    return atom_ids_for_chain(atoms, chain_id)\n"
        ),
        sabotaged="    return frozenset()\n",
    )

    assert "test_expected_chain_a_atom_ids_match_the_known_fixture_layout" in (
        output
    )


def test_oracle_suite_rejects_a_corrupted_selection_evaluator() -> None:
    """The oracle suite fails when a term stops reading the field it names.

    A chain term that matches every atom is the realistic shape of this
    regression: it still returns a plausible non-empty set, so nothing
    but a real assertion about membership would notice.
    """
    output = _run_oracle_suite_against_a_corrupted_copy(
        original=(
            "        case ChainTerm():\n"
            "            return atom.chain == term.chain_id\n"
        ),
        sabotaged="        case ChainTerm():\n            return True\n",
    )

    assert "test_each_term_kind_selects_what_the_structure_declares" in output


if __name__ == "__main__":
    raise SystemExit(
        subprocess.call([sys.executable, "-m", "pytest", __file__])
    )
