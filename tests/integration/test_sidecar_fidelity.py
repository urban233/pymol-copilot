# Copyright 2026 PyMOL Copilot contributors.
"""Real-PyMOL evidence for the fidelity probe's reconstruct-and-re-extract.

Drives `pmc_sidecar.fidelity.probe()` directly against the module-scoped
`real_pymol`/`loaded_fixture` fixtures re-exported by this directory's
`conftest.py`, with no subprocess and no second
`pymol.finish_launching()` call: `probe()` assumes a live PyMOL session
already exists in the `cmd` it is given, exactly as
`pmc_sidecar.child.run_plan()` does, and for the same reason --
PyMOL supports only one `finish_launching()` call per interpreter, and
`loaded_fixture` already made that call. The fresh-process spawn,
deadline, kill, and reap evidence -- and `fidelity.main()`'s own
read-reconstruct-report sequence -- lives in
tests/integration/test_executor_boundary.py and
tests/integration/test_client_fidelity_real_pymol.py, since proving those
needs the boundary genuinely spawning this module as a subprocess.

Every test that drives a real `reconstruct()` renames its candidate
snapshot away from `loaded_fixture`'s own object name ("fx") first:
`probe()` reconstructs into the very same live session these tests read
from, so reconstructing under "fx" again would silently double the
already-loaded object's own atoms rather than build an independent copy
to compare against it. The renamed object is deleted after each such
test so it never leaks into the next.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import contextlib
import dataclasses
import json
from typing import Any

import pytest  # noqa: I001, RUF100  # Keep imports split for Google style.

from pmc_core.executor import REASON_OK
from pmc_core.executor import REASON_RECONSTRUCTION_FAILURE
from pmc_core.executor import REASON_SPAWN_OR_LOAD_FAILURE
from pmc_core.executor import STATUS_FAILED
from pmc_core.executor import STATUS_OK
from pmc_core.snapshot import ObjectSnapshot
from pmc_core.snapshot import diff
from pmc_core.snapshot import extract
from pmc_core.snapshot import from_json
from pmc_core.snapshot import structure_digest
from pmc_core.snapshot import to_json
from pmc_sidecar.fidelity import probe

_PROBE_TARGET = "fx_probe"


def _renamed(snapshot: ObjectSnapshot, name: str) -> ObjectSnapshot:
    """Return a copy of a snapshot bound to a different object name.

    Args:
        snapshot: The snapshot to copy.
        name: The new object name.

    Returns:
        An equivalent snapshot targeting `name` instead of its own.
    """
    return dataclasses.replace(snapshot, name=name)


def test_a_faithful_snapshot_round_trips_with_an_empty_diff(
    loaded_fixture: Any,
) -> None:
    """A snapshot extracted from the live fixture reconstructs exactly.

    Args:
        loaded_fixture: The real PyMOL cmd module with "fx" loaded.
    """
    candidate = _renamed(extract(loaded_fixture, "fx"), _PROBE_TARGET)
    try:
        result = probe(loaded_fixture, to_json(candidate))

        assert result.status == STATUS_OK
        assert result.reason == REASON_OK
        assert result.reconstructed_snapshot_json is not None
        reconstructed = from_json(result.reconstructed_snapshot_json)
        assert diff(candidate, reconstructed) == []
        assert structure_digest(candidate) == structure_digest(reconstructed)
    finally:
        with contextlib.suppress(Exception):
            loaded_fixture.delete(_PROBE_TARGET)


def test_a_snapshot_that_survives_parsing_but_not_pseudoatom_fails_closed(
    loaded_fixture: Any,
) -> None:
    """A structurally invalid coordinate fails as SPAWN_OR_LOAD_FAILURE.

    Same sabotage `tests/integration/test_executor_boundary.py`'s own
    `test_spawn_or_load_failure_fails_closed_with_no_leak` uses:
    `from_json` performs no type validation on a field's own contents, so
    a non-numeric coordinate survives parsing and is only rejected by
    PyMOL's own `pseudoatom` call inside `reconstruct()`.

    Args:
        loaded_fixture: The real PyMOL cmd module with "fx" loaded.
    """
    candidate = _renamed(extract(loaded_fixture, "fx"), _PROBE_TARGET)
    payload = json.loads(to_json(candidate))
    payload["states"][0]["atoms"][0]["coord"] = ["a", "b", "c"]
    try:
        result = probe(loaded_fixture, json.dumps(payload))

        assert result.status == STATUS_FAILED
        assert result.reason == REASON_SPAWN_OR_LOAD_FAILURE
        assert result.reconstructed_snapshot_json is None
    finally:
        with contextlib.suppress(Exception):
            loaded_fixture.delete(_PROBE_TARGET)


def test_malformed_snapshot_json_fails_closed_the_same_way(
    loaded_fixture: Any,
) -> None:
    """Snapshot text that does not even parse is SPAWN_OR_LOAD_FAILURE too.

    No object is ever named, let alone created, so this test needs no
    renaming and no cleanup.

    Args:
        loaded_fixture: The real PyMOL cmd module with "fx" loaded.
    """
    result = probe(loaded_fixture, "{not valid json")

    assert result.status == STATUS_FAILED
    assert result.reason == REASON_SPAWN_OR_LOAD_FAILURE
    assert result.reconstructed_snapshot_json is None


def test_reconstruction_failure_is_distinct_from_spawn_or_load_failure(
    loaded_fixture: Any,
) -> None:
    """A re-extraction failure after a real reconstruction reports its own reason.

    Reconstructs a genuine (renamed) snapshot, then wraps `cmd` so the one
    call `probe()` makes after `reconstruct()` succeeds -- `extract()`'s
    own `count_states` -- raises, simulating a re-extraction failure the
    module must distinguish from a reconstruction failure.

    Args:
        loaded_fixture: The real PyMOL cmd module with "fx" loaded.
    """
    candidate = _renamed(extract(loaded_fixture, "fx"), _PROBE_TARGET)

    class _FailingExtractCmd:
        """Wrap a real cmd so its first count_states call raises."""

        def __init__(self, real_cmd: Any) -> None:
            """Store the wrapped cmd.

            Args:
                real_cmd: The real PyMOL cmd module to wrap.
            """
            self._real_cmd = real_cmd

        def __getattr__(self, name: str) -> Any:
            """Forward every attribute except a failing count_states.

            Args:
                name: The attribute name being accessed.

            Returns:
                The wrapped cmd's own attribute, or a failing stand-in for
                count_states.
            """
            if name == "count_states":

                def _fail(*_args: object, **_kwargs: object) -> int:
                    raise RuntimeError("simulated re-extraction failure")

                return _fail
            return getattr(self._real_cmd, name)

    try:
        result = probe(_FailingExtractCmd(loaded_fixture), to_json(candidate))

        assert result.status == STATUS_FAILED
        assert result.reason == REASON_RECONSTRUCTION_FAILURE
        assert result.reconstructed_snapshot_json is None
    finally:
        with contextlib.suppress(Exception):
            loaded_fixture.delete(_PROBE_TARGET)


if __name__ == "__main__":
    import os
    import sys

    _exit_code = pytest.main([__file__])
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(_exit_code)
