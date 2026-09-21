# Copyright 2026 PyMOL Copilot contributors.
"""The admission gate: every controlled structure is a fixed point.

The oracle predicts a plan's result against the snapshot it was handed,
while PyMOL runs the plan against the object
`pmc_core.snapshot.reconstruct` builds from that snapshot. If those two
differ before a single command runs, every sample built on the structure
fails the executor's fidelity gate for a reason that has nothing to do
with the plan under test.

This module rules that out per structure, through the real
`pmc_sidecar.fidelity` child that `pmc_core.executor.probe_fidelity()`
spawns -- the same production reconstruction path the dataset run uses,
not a test-local re-implementation. A structure that is not a fixed
point is excluded from the matrix here rather than silently poisoning
the corpus.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import functools

import pytest

from pmc_core.executor import EXECUTOR_VERSION
from pmc_core.executor import STATUS_OK
from pmc_core.executor import FidelityReport
from pmc_core.executor import FidelityRequest
from pmc_core.executor import probe_fidelity
from pmc_core.snapshot import diff
from pmc_core.snapshot import from_json
from pmc_core.snapshot import to_json
from pmc_data.structures import StructureSpec
from pmc_data.structures import build_structure
from pmc_data.structures import enumerate_structures

#: The seed the admission gate is run at. The corpus run uses the same
#: one, so a structure admitted here is the structure generated from.
SEED = 20260921

STRUCTURE_SPECS = enumerate_structures(SEED)


@functools.lru_cache(maxsize=None)
def _probe(spec: StructureSpec) -> FidelityReport:
    """Reconstruct one structure in real PyMOL, once per spec.

    Each call spawns a real `pmc_sidecar.fidelity` child, so the two
    assertions below share one probe rather than paying for the same
    PyMOL process twice. A StructureSpec is a frozen dataclass of
    plain scalars, so it is a sound cache key.

    Args:
        spec: The structure spec to probe.

    Returns:
        The fidelity report for that structure.
    """
    return probe_fidelity(
        FidelityRequest(
            executor_version=EXECUTOR_VERSION,
            snapshot_json=to_json(build_structure(spec)),
        )
    )


@pytest.mark.parametrize(
    "spec", STRUCTURE_SPECS, ids=[spec.spec_id for spec in STRUCTURE_SPECS]
)
def test_every_structure_is_a_reconstruction_fixed_point(spec: object) -> None:
    """A built structure must survive reconstruct-then-extract unchanged.

    Args:
        spec: The structure spec under test.
    """
    built = build_structure(spec)  # pyrefly: ignore.
    report = _probe(spec)

    assert report.status == STATUS_OK, (
        f"{spec.spec_id}: fidelity probe failed: "  # pyrefly: ignore.
        f"reason={report.reason} warnings={report.warnings}"
    )
    assert report.reconstructed_snapshot_json is not None

    reconstructed = from_json(report.reconstructed_snapshot_json)
    mismatches = diff(built, reconstructed)

    assert mismatches == [], (
        f"{spec.spec_id}: built structure is not a fixed point of "  # pyrefly: ignore.
        "reconstruct-then-extract; it cannot be graded by prediction"
    )


@pytest.mark.parametrize(
    "spec", STRUCTURE_SPECS, ids=[spec.spec_id for spec in STRUCTURE_SPECS]
)
def test_reconstruction_is_byte_identical_not_merely_equivalent(
    spec: object,
) -> None:
    """The fingerprint the executor compares is over bytes, not fields.

    `diff` reports field mismatches, but the executor's fidelity gate
    hashes `to_json` output. A structure that differs only in something
    `diff` does not cover would still be rejected at generation time, so
    the gate has to be the same byte equality.

    Args:
        spec: The structure spec under test.
    """
    built = build_structure(spec)  # pyrefly: ignore.
    report = _probe(spec)

    assert report.reconstructed_snapshot_json is not None
    assert to_json(from_json(report.reconstructed_snapshot_json)) == to_json(
        built
    )


if __name__ == "__main__":
    import os
    import sys

    code = pytest.main([__file__])
    sys.stdout.flush()
    sys.stderr.flush()
    # Real PyMOL runs in the spawned children, but this module exits the
    # same way its siblings do so a failing code cannot be clobbered.
    os._exit(code)
