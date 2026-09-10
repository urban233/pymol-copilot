# Copyright 2026 PyMOL Copilot contributors.
"""H-02 discovery: candidate C (PyMOL session serialization) differential.

Candidate C exports the loaded fixture with `cmd.save(..., format="pse")`
-- PyMOL's own native session format -- and reconstructs in a genuinely
fresh second process with nothing but `cmd.load()` of that one `.pse`
file: no manifest, since session serialization already carries every
field this differential harness tracks (and, unlike candidates A and B,
measurement objects too). Re-extraction and diffing reuse the same shared
`extract()`/`_diff()` from harness.py candidates A and B already use.

Real, empirically confirmed facts this candidate depends on, each of which
cost a probe to discover:

- `cmd.save(path, format="pse")` -- called with no `selection` argument at
  all -- captures the whole session, every loaded object included.
  Passing an explicit `selection="all"` argument was tried first and
  produces a broken, effectively empty session file for this fixture
  (confirmed empirically: a file a fraction of the size of the default
  save, and reloading it yields zero objects) -- "all" is not a safe
  stand-in for PyMOL's own true default selection in `cmd.save`'s pse
  handling. This candidate therefore always calls `cmd.save` with no
  selection argument, matching what H-02 asked for in the first place.
- `cmd.load()` of a `.pse` file does not accept a target object name the
  way it does for a plain structure file: the object argument is not
  meaningful for a whole-session format, and every object regains
  whatever name it was saved under (confirmed empirically). Reconstruction
  therefore calls `cmd.load(pse_path)` with no name argument and then
  refers to the fixture by its original name, "fx", exactly as saved.
- Unlike candidates A and B, a `cmd.distance` measurement object *does*
  survive this candidate's round trip: reloading a `.pse` file that was
  saved while "d1" existed restores "d1" as a real
  `object:measurement` again (confirmed empirically) -- this candidate's
  positive result, in direct contrast to A's and B's negative one.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import pytest

from harness import _diff
from harness import extract
from harness import from_json
from harness import run_nested_snapshot_process
from harness import to_json

# real_pymol/loaded_fixture (pytest fixtures defined in harness.py) are not
# imported here: this directory's conftest.py re-exports them once so
# pytest's directory-scoped fixture discovery makes them available to every
# test below without a same-named import that every test function's
# loaded_fixture parameter would otherwise shadow (ruff's F811, confirmed
# empirically -- see conftest.py's own docstring).

PSE_PATH_ENV_VAR = "H02_CANDIDATE_C_PSE_PATH"
SNAPSHOT_ENV_VAR = "H02_CANDIDATE_C_SNAPSHOT_JSON"


def test_pse_export_preserves_the_whole_session_including_measurements(
    loaded_fixture: Any, tmp_path: Path
) -> None:
    """Positive result: a measurement object survives this candidate's save.

    Contrasts directly with candidate A's
    test_measurement_objects_are_not_recoverable_via_query_apis and
    candidate B's test_measurement_objects_are_not_recoverable_via_pdb_export:
    session serialization is native, so it is not limited to an atom-based
    selection the way a query API or a structure-file export is.

    Args:
        loaded_fixture: The real PyMOL cmd module with the fixture loaded.
        tmp_path: A pytest-provided temporary directory for the exported
            session file.
    """
    loaded_fixture.distance(
        "d1",
        "fx and chain A and resi 1 and name CA",
        "fx and chain A and resi 2 and name CA",
    )
    loaded_fixture.sync()
    assert loaded_fixture.get_type("d1") == "object:measurement"

    pse_path = tmp_path / "fx_and_d1.pse"
    # No selection argument: see the module docstring's empirical finding
    # that an explicit selection="all" breaks this candidate's session
    # export for this fixture.
    loaded_fixture.save(str(pse_path), format="pse")
    loaded_fixture.sync()

    loaded_fixture.delete("all")
    loaded_fixture.sync()
    try:
        # A .pse load restores every object under its own saved name; no
        # target-name argument is meaningful here (see module docstring).
        loaded_fixture.load(str(pse_path))
        loaded_fixture.sync()

        assert sorted(loaded_fixture.get_names("objects")) == ["d1", "fx"]
        assert loaded_fixture.get_type("d1") == "object:measurement"
    finally:
        # Restore the ordinary loaded_fixture teardown's expectations: the
        # fixture teardown deletes "fx" by name, so leave that name loaded.
        loaded_fixture.delete("d1")
        loaded_fixture.sync()


def test_candidate_c_round_trips_through_a_fresh_process(
    loaded_fixture: Any, tmp_path: Path
) -> None:
    """Candidate C reconstructs via a bare `.pse` load in a fresh process.

    Extracts the loaded fixture's canonical snapshot in this process, then
    spawns a genuinely fresh nested pytest process -- one that launches its
    own real PyMOL and never opens h02_full_v1_fixture.pdb -- to load the
    exported session file alone and diff the result against the original
    extraction.

    Args:
        loaded_fixture: The real PyMOL cmd module with the fixture loaded.
        tmp_path: A pytest-provided temporary directory for the exported
            session file.

    Raises:
        AssertionError: If reconstruction was not faithful, with every
            field-level mismatch the nested process reported.
    """
    original = extract(loaded_fixture, "fx")

    pse_path = tmp_path / "fx.pse"
    loaded_fixture.save(str(pse_path), format="pse")
    loaded_fixture.sync()

    snapshot_path = tmp_path / "snapshot.json"
    snapshot_path.write_text(to_json(original))

    result = run_nested_snapshot_process(
        __file__,
        "test_reconstruct_from_env_pse_matches_original",
        {
            PSE_PATH_ENV_VAR: str(pse_path),
            SNAPSHOT_ENV_VAR: str(snapshot_path),
        },
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_reconstruct_from_env_pse_matches_original() -> None:
    """Reconstruct from an externally supplied `.pse` file and diff it.

    Only meaningful when invoked as the nested subprocess spawned by
    test_candidate_c_round_trips_through_a_fresh_process, which sets
    PSE_PATH_ENV_VAR and SNAPSHOT_ENV_VAR. Skips when run any other way,
    since it has nothing to reconstruct from and no assertion to make.

    Raises:
        AssertionError: If the re-extracted snapshot differs from the
            original in any recorded field.
    """
    pse_path = os.environ.get(PSE_PATH_ENV_VAR)
    snapshot_path = os.environ.get(SNAPSHOT_ENV_VAR)
    if not (pse_path and snapshot_path):
        pytest.skip(
            f"{PSE_PATH_ENV_VAR}/{SNAPSHOT_ENV_VAR} not set; not the "
            "nested invocation"
        )

    import pymol  # pyrefly: ignore.
    from pymol import cmd  # pyrefly: ignore.

    pymol.finish_launching(["pymol", "-qc"])
    try:
        original = from_json(Path(snapshot_path).read_text())

        # A .pse load restores every object under its own saved name; no
        # target-name argument is meaningful here (see module docstring).
        cmd.load(pse_path)
        cmd.sync()

        reconstructed = extract(cmd, original.name)
        mismatches = _diff(original, reconstructed)
        assert not mismatches, "\n".join(mismatches)
    finally:
        cmd.do("quit")


if __name__ == "__main__":
    # Real PyMOL's headless launch leaves behind cleanup that can complete
    # after this process would otherwise exit, overriding a genuine pytest
    # failure with process exit code 0 (the same defect documented and
    # fixed the same way in tests/integration/test_real_pymol_command.py
    # and candidate A's own __main__ block). os._exit bypasses that
    # interpreter-shutdown window entirely, so pytest's real result is what
    # Bazel actually sees. os._exit skips the normal stdio flush, so flush
    # explicitly first -- otherwise a real failure's traceback and summary
    # can be silently lost from the captured test log.
    _exit_code = pytest.main([__file__])
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(_exit_code)
