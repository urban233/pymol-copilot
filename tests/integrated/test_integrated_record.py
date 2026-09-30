# Copyright 2026 PyMOL Copilot contributors.
"""The committed integrated report is what its evidence says.

docs/master_plan.md item 19: "Measure integrated TaskSuccess against the
offline number and explain any gap rather than averaging it away." This
test recomputes `docs/integration/report.json` and `REPORT.md` from the
committed integrated records and the published offline ones, and holds
every sample whose outcome differs to an explanation: one the evidence
decides, or, where it decides none, a hand-written note.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from pmc_eval.integrated import GAP_UNEXPLAINED
from pmc_eval.integrated import GAPS
from pmc_eval.integrated import compare_condition
from pmc_eval.integrated import read_offline
from pmc_eval.integrated import read_records
from pmc_eval.integrated import render_report

ROOT = Path(__file__).resolve().parents[2]
INTEGRATION = ROOT / "docs" / "integration"
OFFLINE = ROOT / "docs" / "evaluation" / "finetuned" / "test_gold"
CONFIG = ROOT / "configs" / "evaluation" / "finetuned.json"
CONDITIONS = ("grammar", "no-grammar")
TITLE = "Integrated TaskSuccess against offline"


def _read(path: Path) -> Any:
    """Read one JSON file.

    Args:
        path: The file.

    Returns:
        Its decoded JSON.
    """
    return json.loads(path.read_text(encoding="utf-8"))


def _comparison() -> dict[str, Any]:
    """Recompute the comparison from the committed records.

    Returns:
        `compare_condition`'s result per condition.
    """
    return {
        condition: compare_condition(
            read_records(
                INTEGRATION / "test_gold" / condition / "samples.jsonl"
            ),
            read_offline(OFFLINE / condition / "samples.jsonl"),
        )
        for condition in CONDITIONS
    }


COMPARISON = _comparison()
NOTES: dict[str, str] = (
    _read(INTEGRATION / "notes.json")
    if (INTEGRATION / "notes.json").exists()
    else {}
)


def test_the_report_is_its_evidence_recomputed() -> None:
    """report.json and REPORT.md are exactly what the records give."""
    assert _read(INTEGRATION / "report.json") == json.loads(
        json.dumps(COMPARISON)
    )
    assert (INTEGRATION / "REPORT.md").read_text(
        encoding="utf-8"
    ) == render_report(COMPARISON, title=TITLE, notes=NOTES)


@pytest.mark.parametrize("condition", CONDITIONS)
def test_every_gold_sample_ran_once(condition: str) -> None:
    """All 68 samples, each once, under the evaluated model."""
    records = read_records(
        INTEGRATION / "test_gold" / condition / "samples.jsonl"
    )
    assert len(records) == 68
    assert len({record.sample_id for record in records}) == 68
    assert {record.condition for record in records} == {condition}


@pytest.mark.parametrize("condition", CONDITIONS)
def test_the_run_served_the_evaluated_config(condition: str) -> None:
    """The server ran from the committed config, on the evaluated model."""
    run = _read(INTEGRATION / "test_gold" / condition / "run.json")
    config = _read(CONFIG)["engine"]

    assert run["mode"] == "model"
    assert (
        run["config_sha256"] == hashlib.sha256(CONFIG.read_bytes()).hexdigest()
    )
    (health,) = run["health"]
    assert "engine:    ready" in health
    assert f"{config['model_name']}@{config['checkpoint']}" in health
    assert "all match this client" in health


@pytest.mark.parametrize("condition", CONDITIONS)
def test_every_difference_is_explained(condition: str) -> None:
    """No discordant sample is averaged away or left unexplained."""
    for row in COMPARISON[condition]["discordant"]:
        assert row["explanation"] in GAPS, row
        if row["explanation"] == GAP_UNEXPLAINED:
            assert NOTES.get(row["sample_id"]), (
                f"{row['sample_id']} is unexplained and has no note"
            )


@pytest.mark.parametrize("condition", CONDITIONS)
def test_the_offline_side_is_the_published_result(condition: str) -> None:
    """The pairing is against item 17's 32/68 and 19/68, unchanged."""
    expected = {"grammar": 32, "no-grammar": 19}[condition]

    assert COMPARISON[condition]["offline"]["k"] == expected


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
