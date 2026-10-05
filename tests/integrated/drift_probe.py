# Copyright 2026 PyMOL Copilot contributors.
"""Probe whether the engine's completion depends on the request before it.

docs/master_plan.md item 19. The integrated measurement found samples
whose prompt is byte for byte the offline one but whose completion is
not (`engine_drift`). Both runs send the same prompts in the same order
at temperature 0. Where they differ is what came before the first
sample: offline, the harness's preflight sends the longest prompt
first. llama.cpp reuses the previous prompt's cached prefix, which
changes how the new prompt is split into batches, and so the floating
point sums a near-tie between two tokens can turn on.

This probe tests exactly that, on the engine the evaluation recorded
(`pmc_server.main.build_engine` refuses any other): each target prompt
is sent after several different predecessors, each sequence twice.
If the completion changes with the predecessor, and repeats exactly
when the predecessor repeats, the drift is the engine's dependence on
its history, not randomness and not the product.

Not a test: it needs the GPU engine and runs only when a person has
agreed to it. It writes `docs/integration/drift_probe.json`.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import json
import os
import sys
from pathlib import Path
from typing import Any

from pmc_agent.inference.base import CancelToken
from pmc_agent.inference.base import CompletionRequest
from pmc_agent.inference.base import CompletionResult
from pmc_agent.inference.base import InferenceEngine
from pmc_agent.inference.unavailable import UnavailableEngine
from pmc_core.grammar import build_grammar
from pmc_data.gold_set import DEFAULT_GOLD_SAMPLES_PATH
from pmc_data.sample import read_samples
from pmc_server.config import load_runtime_config
from pmc_server.main import build_engine

REPO_ROOT = Path(
    os.environ.get(
        "BUILD_WORKSPACE_DIRECTORY", Path(__file__).resolve().parents[2]
    )
)
CONFIG = REPO_ROOT / "configs" / "evaluation" / "finetuned.json"
OUT = REPO_ROOT / "docs" / "integration" / "drift_probe.json"

#: The samples whose completion drifted with the grammar and whose
#: drift is not only a selection name's number: an extra command
#: (gold_001), and the one that flipped its grade (gold_044).
TARGETS = ("gold_001", "gold_044")

#: How many times each sequence is sent.
REPEATS = 2


def _complete(engine: InferenceEngine, prompt: str) -> str:
    """Complete one prompt under the grammar condition's bounds.

    Args:
        engine: The connected engine.
        prompt: The prompt.

    Returns:
        The completion text, or the failure's category.
    """
    outcome = engine.complete(
        CompletionRequest(
            prompt=prompt,
            grammar=build_grammar(),
            max_tokens=256,
            deadline_seconds=600.0,
        ),
        cancel=CancelToken(),
    )
    if isinstance(outcome, CompletionResult):
        return outcome.text
    return f"<failure: {outcome.category}>"


def main() -> int:
    """Send each target after each predecessor, twice, and record it.

    Returns:
        Zero once the record is written, one if the engine is not the
        evaluated one.
    """
    config = load_runtime_config(CONFIG)
    engine = build_engine(
        base_url=config.base_url, options=config.engine, expected=config
    )
    if isinstance(engine, UnavailableEngine):
        print(engine.health().failure, file=sys.stderr)
        return 1
    samples = {s.sample_id: s for s in read_samples(DEFAULT_GOLD_SAMPLES_PATH)}
    ordered = list(samples.values())
    longest = max(ordered, key=lambda s: len(s.prompt_text))
    offline = {
        json.loads(line)["sample_id"]: json.loads(line)
        for line in (
            REPO_ROOT
            / "docs/evaluation/finetuned/test_gold/grammar/samples.jsonl"
        )
        .read_text(encoding="utf-8")
        .splitlines()
    }
    live = {
        json.loads(line)["sample_id"]: json.loads(line)
        for line in (
            REPO_ROOT / "docs/integration/test_gold/grammar/samples.jsonl"
        )
        .read_text(encoding="utf-8")
        .splitlines()
    }
    results: list[dict[str, Any]] = []
    for target in TARGETS:
        index = ordered.index(samples[target])
        predecessors = {
            "the preflight's longest prompt (offline's first request)": (
                longest.sample_id
            ),
            "the previous gold sample (both runs' order)": (
                ordered[index - 1].sample_id if index else longest.sample_id
            ),
            "itself": target,
            "gold_056 (Gate A's last prompt)": "gold_056",
        }
        for label, predecessor in predecessors.items():
            for repeat in range(1, REPEATS + 1):
                _complete(engine, samples[predecessor].prompt_text)
                text = _complete(engine, samples[target].prompt_text)
                results.append(
                    {
                        "target": target,
                        "predecessor": predecessor,
                        "predecessor_label": label,
                        "repeat": repeat,
                        "completion": text,
                        "is_offline": text
                        == offline[target]["attempts"][0]["completion"],
                        "is_live": text == live[target]["attempts"][0]["text"],
                    }
                )
                print(f"{target} after {predecessor} #{repeat}: {text!r}")
    close = getattr(engine, "close", None)
    if callable(close):
        close()
    record = {
        "probe_version": 1,
        "config": "configs/evaluation/finetuned.json",
        "offline_completion": {
            t: offline[t]["attempts"][0]["completion"] for t in TARGETS
        },
        "live_completion": {t: live[t]["attempts"][0]["text"] for t in TARGETS},
        "results": results,
    }
    OUT.write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
