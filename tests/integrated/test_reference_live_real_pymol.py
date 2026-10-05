# Copyright 2026 PyMOL Copilot contributors.
"""A correct plan scores through the live path; a wrong one does not.

docs/master_plan.md item 19. Before the integrated measurement grades a
model, it has to grade the product itself correctly. Here the real
server (`pmc_server.main.serve`) runs with a scripted engine that
answers each sample's own gold plan, the real client sends each intent
from a real headless PyMOL session, and every preview is applied and
graded on the live session. One sample of every held-out structure and
every assertion shape must succeed, and its prompt must be byte for
byte the offline evaluation's. One sample answered with a wrong plan
must fail, so the grade can fail.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import integrated_cli
from pmc_agent.inference.base import STOP_END
from pmc_agent.inference.base import CancelToken
from pmc_agent.inference.base import CompletionRequest
from pmc_agent.inference.base import CompletionResult
from pmc_data.sample import ASSERTION_RESULTING_SNAPSHOT
from pmc_data.sample import ASSERTION_SELECTION_COUNTS
from pmc_eval.integrated import OUTCOME_APPLIED
from pmc_eval.integrated import read_records

ROOT = Path(__file__).resolve().parents[2]
OFFLINE = ROOT / "docs" / "evaluation" / "finetuned" / "test_gold" / "grammar"

#: The gold plan the sabotaged sample is answered with instead of its own.
WRONG_PLAN = "color red, chain B\n"


def _subset() -> tuple[list[str], str]:
    """Choose one sample per structure and per assertion shape.

    Returns:
        The chosen sample ids, and the one to answer wrongly.
    """
    samples = integrated_cli.gold_samples()
    chosen: dict[str, None] = {}
    for spec in sorted({s.structure.spec_id for s in samples}):
        first = next(s for s in samples if s.structure.spec_id == spec)
        chosen.setdefault(first.sample_id, None)
    shapes = {
        tuple(sorted(a.kind for a in s.assertions)): s.sample_id
        for s in reversed(samples)
    }
    for sample_id in shapes.values():
        chosen.setdefault(sample_id, None)
    sabotaged = next(
        s.sample_id
        for s in samples
        if s.sample_id in chosen
        and any(a.kind == ASSERTION_RESULTING_SNAPSHOT for a in s.assertions)
        and s.plan_pml != WRONG_PLAN
    )
    assert any(
        {a.kind for a in s.assertions}
        == {
            ASSERTION_SELECTION_COUNTS,
            "commands_succeeded",
        }
        for s in samples
        if s.sample_id in chosen
    ), "an orient sample, graded on counts alone, must be in the subset"
    return list(chosen), sabotaged


def test_gold_plans_succeed_live_and_a_wrong_plan_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every gold plan grades as a success on the live session."""
    chosen, sabotaged = _subset()
    sabotaged_intent = next(
        s.intent
        for s in integrated_cli.gold_samples()
        if s.sample_id == sabotaged
    )
    real_complete = integrated_cli.ReferenceEngine.complete

    def complete(
        self: integrated_cli.ReferenceEngine,
        request: CompletionRequest,
        *,
        cancel: CancelToken,
    ) -> CompletionResult:
        if sabotaged_intent in request.prompt:
            return CompletionResult(WRONG_PLAN, self.model_identity, STOP_END)
        return real_complete(self, request, cancel=cancel)

    monkeypatch.setattr(integrated_cli.ReferenceEngine, "complete", complete)

    status = integrated_cli.main(
        [
            "run",
            "--reference",
            "--conditions",
            "grammar",
            "--samples",
            ",".join(chosen),
            "--out",
            str(tmp_path),
        ]
    )

    assert status == 0
    records = {
        r.sample_id: r
        for r in read_records(
            tmp_path / "test_gold" / "grammar" / "samples.jsonl"
        )
    }
    assert set(records) == set(chosen)
    offline: dict[str, dict[str, Any]] = {
        (row := json.loads(line))["sample_id"]: row
        for line in (OFFLINE / "samples.jsonl").read_text().splitlines()
    }
    for sample_id, record in records.items():
        assert record.outcome == OUTCOME_APPLIED, (sample_id, record.output)
        assert not record.prompt_skew, sample_id
        assert (
            record.attempts[0]["prompt_sha256"]
            == offline[sample_id]["attempts"][0]["prompt_sha256"]
        ), f"{sample_id}: the live prompt is not the offline one"
        assert record.attempts[0]["grammar"] is True
        expected = sample_id != sabotaged
        assert record.task_success is expected, (sample_id, record.assertions)
    assert integrated_cli.main(["summarize", "--out", str(tmp_path)]) == 1


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
