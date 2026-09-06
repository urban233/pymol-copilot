# Copyright 2026 PyMOL Copilot contributors.
"""Gold-case schema round-trip and fail-closed validation tests.

These tests never import PyMOL. They exercise `pmc_data.gold_case` directly
against the one hand-authored gold record, proving lossless serialization
and that missing provenance or an unsupported assertion kind invalidates the
record rather than being silently accepted or defaulted.
"""

from __future__ import annotations

import copy
import json

import pytest
from pmc_core.plan import initial_fixture_plan
from pmc_data.gold_case import DEFAULT_GOLD_CASE_PATH
from pmc_data.gold_case import Assertion
from pmc_data.gold_case import GoldCase
from pmc_data.gold_case import InvalidGoldCaseError

GOLD_CASE_PATH = DEFAULT_GOLD_CASE_PATH


def _load_raw_gold_case() -> dict:
    """Load the recorded gold case as a plain, mutable dict.

    Returns:
        A deep copy of the raw gold-case mapping, safe for tests to mutate.
    """
    return copy.deepcopy(json.loads(GOLD_CASE_PATH.read_text(encoding="utf-8")))


def test_gold_case_round_trip_preserves_provenance_assertions_and_plan() -> (
    None
):
    """to_dict/from_dict round-trips the record without losing content."""
    case = GoldCase.from_json_file(GOLD_CASE_PATH)

    restored = GoldCase.from_dict(case.to_dict())

    assert restored == case
    assert restored.provenance == case.provenance
    assert restored.assertions == case.assertions
    assert restored.canonical_plan_pml == initial_fixture_plan().render_pml()


@pytest.mark.parametrize(
    "missing_key",
    [
        "case_id",
        "intent",
        "provenance",
        "contract_versions",
        "canonical_plan_pml",
        "target_chain",
        "non_target_chains",
        "assertions",
    ],
)
def test_missing_required_field_is_rejected(missing_key: str) -> None:
    """A gold record missing any required top-level field is rejected rather than default-filled."""
    raw = _load_raw_gold_case()
    del raw[missing_key]

    with pytest.raises(InvalidGoldCaseError):
        GoldCase.from_dict(raw)


def test_missing_provenance_checksum_is_rejected() -> None:
    """A gold record whose provenance omits the checksum is rejected."""
    raw = _load_raw_gold_case()
    del raw["provenance"]["structure_sha256"]

    with pytest.raises(InvalidGoldCaseError):
        GoldCase.from_dict(raw)


def test_unsupported_assertion_kind_is_rejected() -> None:
    """A gold record naming an assertion kind outside the supported set is rejected rather than silently ignored."""
    raw = _load_raw_gold_case()
    raw["assertions"].append({"kind": "unsupported_kind", "params": {}})

    with pytest.raises(InvalidGoldCaseError):
        GoldCase.from_dict(raw)


def test_bare_assertion_construction_rejects_unsupported_kind() -> None:
    """Constructing an Assertion directly enforces the same closed kind set as decoding one from a mapping."""
    with pytest.raises(InvalidGoldCaseError):
        Assertion(kind="not_a_real_kind", params={})


def test_canonical_plan_drift_is_rejected() -> None:
    """A record whose canonical plan no longer matches pmc_core's own rendering is rejected rather than graded against stale bytes."""
    raw = _load_raw_gold_case()
    raw["canonical_plan_pml"] = "select copilot_selection, chain B\n"

    with pytest.raises(InvalidGoldCaseError):
        GoldCase.from_dict(raw)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
