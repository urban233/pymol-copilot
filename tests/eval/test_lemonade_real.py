# Copyright 2026 PyMOL Copilot contributors.
"""Opt-in: the harness against a real local Lemonade server and PyMOL.

Skipped unless `PMC_LEMONADE_BASE_URL` names a local Lemonade origin
serving the model `configs/evaluation/baseline.json` names. Two gold
samples run under each condition, end to end: the engine's capability
probe, the request graph, the real sidecar and the grader. This proves
the pieces a hermetic test fakes -- the engine and the sidecar -- fit
together before hours of inference are spent on a full run. It asserts
that every sample is scored, not how well: the model's answers are the
baseline's business, not this test's.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import dataclasses
import os
from pathlib import Path

import pytest

from pmc_agent.inference.base import EngineFailure
from pmc_agent.inference.lemonade import _local_origin
from pmc_core.executor import execute
from pmc_data.gold_set import DEFAULT_GOLD_SAMPLES_PATH
from pmc_data.sample import read_samples
from pmc_eval.config import load_config
from pmc_eval.eval_cli import ConnectedEngine
from pmc_eval.eval_cli import connect_engine
from pmc_eval.record import SampleRecord
from pmc_eval.runner import run_sample

_BASE_URL_ENVIRONMENT_VARIABLE = "PMC_LEMONADE_BASE_URL"

#: The committed config, a data dependency of this target.
CONFIG = Path(__file__).resolve().parents[2] / (
    "configs/evaluation/baseline.json"
)

#: A short gold prompt, and the longest one (everything_bonded, about
#: 14,800 characters).
SAMPLE_IDS = ("gold_001", "gold_061")


@pytest.fixture(scope="module")
def connected() -> ConnectedEngine:
    """Connect the configured model at the explicitly enabled origin.

    Returns:
        The connected engine.
    """
    base_url = os.environ.get(_BASE_URL_ENVIRONMENT_VARIABLE)
    if base_url is None:
        pytest.skip(f"{_BASE_URL_ENVIRONMENT_VARIABLE} is unset; opt-in only")
    try:
        _local_origin(base_url)
    except ValueError as error:
        pytest.fail(f"{_BASE_URL_ENVIRONMENT_VARIABLE} is not local: {error}")
    config = load_config(CONFIG)
    engine = connect_engine(
        dataclasses.replace(config.engine, base_url=base_url)
    )
    if isinstance(engine, EngineFailure):
        pytest.fail(f"the engine did not connect: {engine}")
    return engine


@pytest.mark.parametrize("condition_name", ["no-grammar", "grammar"])
@pytest.mark.parametrize("sample_id", SAMPLE_IDS)
def test_a_gold_sample_is_scored_end_to_end(
    connected: ConnectedEngine, condition_name: str, sample_id: str
) -> None:
    """A real model's answer to a gold sample is scored, not left unscored.

    Args:
        connected: The connected engine.
        condition_name: The condition to run under.
        sample_id: The gold sample.
    """
    config = load_config(CONFIG)
    sample = next(
        s
        for s in read_samples(DEFAULT_GOLD_SAMPLES_PATH)
        if s.sample_id == sample_id
    )

    result = run_sample(
        sample,
        engine=connected.engine,
        condition=config.condition(condition_name),
        executor=execute,
        validation_deadline_seconds=config.sidecar_deadline_seconds,
    )

    assert isinstance(result, SampleRecord), result
    assert connected.engine.model_identity == config.engine.model_identity
    assert all(
        a.grammar_sent == (condition_name == "grammar") for a in result.attempts
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
