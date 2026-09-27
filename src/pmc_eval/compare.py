# Copyright 2026 PyMOL Copilot contributors.
"""Compare a model's published evaluation with the untuned baseline's.

Item 17's comparison, as PREREGISTRATION.md fixed it before either
side's numbers existed: for each set and condition, the two models are
paired by sample, and TaskSuccess is compared with an exact two-sided
McNemar test on the discordant pairs. Every other rate, and every
breakout down to the single category, is set side by side as
descriptive evidence; most gold categories hold one or two items.

A comparison is only made when everything but the model is the same.
`compare` refuses two runs that differ in the split, the set's bytes,
the sample order, the harness, grader, repair-prompt, report or
normalization version, the grammar, the contract versions, the PyMOL
wheel, the engine release, its launch arguments, its image, host or
device, or the context -- and two configs that differ anywhere but in
the model (`ALLOWED_CONFIG_KEYS`). Whatever it finds, it reports: a
null or a worse result is a result.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import json
import math
from collections.abc import Callable
from collections.abc import Mapping
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pmc_data.manifest import sha256_of
from pmc_eval.metrics import _HEADLINE_ROWS
from pmc_eval.metrics import BREAKOUTS
from pmc_eval.metrics import _format_rate
from pmc_eval.metrics import _lookup
from pmc_eval.metrics import _table
from pmc_eval.record import OUTCOMES
from pmc_eval.record import SampleRecord

#: The version of the comparison's shape and its test. A change to
#: either is a bump.
COMPARE_VERSION = 1

#: The config leaves two compared runs may differ in: the model.
ALLOWED_CONFIG_KEYS = frozenset(
    {
        ("engine", "model_name"),
        ("engine", "checkpoint"),
        ("engine_provenance", "gguf_sha256"),
        ("engine_provenance", "hf_revision"),
    }
)

#: The run-identity fields two compared runs must share.
SHARED_IDENTITY = (
    "split_id",
    "set",
    "set_sha256",
    "condition",
    "harness_version",
    "grader_version",
    "repair_prompt_version",
    "report_version",
    "normalization",
    "grammar_sha256",
    "pymol_wheel",
    "versions",
    "limit",
)

#: The engine-capability fields two compared runs must share, as each
#: run's probe recorded them.
SHARED_CAPABILITIES = (
    "context_length",
    "device",
    "grammar_enforced",
    "llamacpp_args",
    "recipe",
)

#: The engine-provenance fields two compared runs must share, as each run
#: recorded them: everything but the model's own file.
SHARED_PROVENANCE = (
    "emulation",
    "host",
    "image",
    "lemonade_version",
    "llama_cpp_build",
    "llamacpp_args",
)


class ComparisonError(ValueError):
    """Two evaluations differ in something other than the model."""


def mcnemar_exact(b: int, c: int) -> float:
    """Compute the exact two-sided McNemar p-value.

    Under the null, each of the `b + c` discordant pairs is equally
    likely to go either way, so the smaller count is binomial with
    p = 1/2; the two-sided p-value doubles its lower tail.

    Args:
        b: Pairs where only the first model succeeded.
        c: Pairs where only the second model succeeded.

    Returns:
        The p-value, in [0, 1]; 1 when there are no discordant pairs.
    """
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, k) for k in range(min(b, c) + 1))
    return min(1.0, 2 * tail / 2**n)


def _flatten(
    data: Mapping[str, Any], prefix: tuple[str, ...] = ()
) -> dict[tuple[str, ...], Any]:
    """Flatten a config to its leaf values.

    Args:
        data: A decoded config.
        prefix: The path to `data`.

    Returns:
        Each leaf's value, by its path of keys.
    """
    leaves: dict[tuple[str, ...], Any] = {}
    for key, value in data.items():
        if isinstance(value, Mapping):
            leaves.update(_flatten(value, (*prefix, key)))
        else:
            leaves[(*prefix, key)] = value
    return leaves


def config_differences(
    first: Mapping[str, Any], second: Mapping[str, Any]
) -> set[tuple[str, ...]]:
    """Name every config leaf two configs disagree on.

    Args:
        first: One decoded config.
        second: The other.

    Returns:
        The paths of every leaf added, removed or changed.
    """
    ours, theirs = _flatten(first), _flatten(second)
    missing = object()
    return {
        key
        for key in set(ours) | set(theirs)
        if ours.get(key, missing) != theirs.get(key, missing)
    }


#: Reads one finished run directory and proves its report follows from
#: its samples: `pmc_eval.eval_cli.read_run`.
RunReader = Callable[
    [Path], tuple[dict[str, Any], list[SampleRecord], dict[str, Any]]
]


def _published_runs(
    directory: Path, read_run: RunReader
) -> dict[
    tuple[str, str], tuple[dict[str, Any], list[SampleRecord], dict[str, Any]]
]:
    """Read every run a published directory holds.

    Args:
        directory: A directory `eval_cli publish` wrote.
        read_run: Reads and checks one run directory.

    Returns:
        Each (set, condition)'s run.json, records and report.
    """
    manifest = json.loads((directory / "manifest.json").read_text("utf-8"))
    runs = {}
    for entry in manifest["runs"]:
        key = (entry["set"], entry["condition"])
        runs[key] = read_run(directory / entry["set"] / entry["condition"])
    return runs


def _check_pair(
    key: tuple[str, str],
    baseline: tuple[dict[str, Any], list[SampleRecord], dict[str, Any]],
    candidate: tuple[dict[str, Any], list[SampleRecord], dict[str, Any]],
) -> None:
    """Refuse a pair of runs that differ in anything but the model.

    Args:
        key: The pair's set and condition.
        baseline: The baseline run.
        candidate: The candidate run.

    Raises:
        ComparisonError: If they differ.
    """
    ours, theirs = baseline[0]["identity"], candidate[0]["identity"]
    for field in SHARED_IDENTITY:
        if ours.get(field) != theirs.get(field):
            raise ComparisonError(f"{key}: the runs differ in {field}")
    for field in SHARED_CAPABILITIES:
        if ours["engine_capabilities"].get(field) != theirs[
            "engine_capabilities"
        ].get(field):
            raise ComparisonError(f"{key}: the engines differ in {field}")
    for field in SHARED_PROVENANCE:
        if ours["engine_provenance"].get(field) != theirs[
            "engine_provenance"
        ].get(field):
            raise ComparisonError(f"{key}: the engines differ in {field}")
    if ours["git_dirty"] or theirs["git_dirty"]:
        raise ComparisonError(f"{key}: a run was made on a dirty tree")
    if [r.sample_id for r in baseline[1]] != [
        r.sample_id for r in candidate[1]
    ]:
        raise ComparisonError(f"{key}: the runs visit samples in another order")


def _side_by_side(
    first: Mapping[str, Any], second: Mapping[str, Any], path: tuple[str, ...]
) -> dict[str, Any]:
    """Pair one rate from two report blocks.

    Args:
        first: The baseline's block.
        second: The candidate's block.
        path: Where the rate is in a block.

    Returns:
        Both rates and the difference of their proportions.
    """
    ours, theirs = _lookup(first, path), _lookup(second, path)
    delta = None
    if ours.get("rate") is not None and theirs.get("rate") is not None:
        delta = round(theirs["rate"] - ours["rate"], 6)
    return {"baseline": ours, "candidate": theirs, "delta": delta}


def _pairing(
    baseline: Sequence[SampleRecord], candidate: Sequence[SampleRecord]
) -> dict[str, Any]:
    """Pair two runs' TaskSuccess by sample and test the difference.

    Args:
        baseline: The baseline's records.
        candidate: The candidate's records, in the same order.

    Returns:
        The 2x2 table, the McNemar p-value, and how many final outcomes
        changed class.
    """
    both = only_baseline = only_candidate = neither = flipped = 0
    for ours, theirs in zip(baseline, candidate, strict=True):
        if ours.task_success and theirs.task_success:
            both += 1
        elif ours.task_success:
            only_baseline += 1
        elif theirs.task_success:
            only_candidate += 1
        else:
            neither += 1
        flipped += ours.final_outcome != theirs.final_outcome
    return {
        "n": len(baseline),
        "both_succeed": both,
        "only_baseline_succeeds": only_baseline,
        "only_candidate_succeeds": only_candidate,
        "neither_succeeds": neither,
        "mcnemar_exact_p": round(
            mcnemar_exact(only_baseline, only_candidate), 12
        ),
        "final_outcome_changed": flipped,
    }


def compare(
    baseline_dir: Path,
    candidate_dir: Path,
    baseline_config: Path,
    candidate_config: Path,
    read_run: RunReader,
) -> dict[str, Any]:
    """Compare a candidate's published evaluation with the baseline's.

    Args:
        baseline_dir: The published baseline.
        candidate_dir: The published candidate; it may cover a subset
            of the baseline's sets and conditions.
        baseline_config: The config the baseline was run under.
        candidate_config: The config the candidate was run under.
        read_run: Reads and checks one run directory
            (`pmc_eval.eval_cli.read_run`).

    Returns:
        The comparison: for each set and condition, the paired test,
        every rate side by side, and every breakout side by side.

    Raises:
        ComparisonError: If the two differ in anything but the model.
    """
    configs = {}
    for name, directory, path in (
        ("baseline", baseline_dir, baseline_config),
        ("candidate", candidate_dir, candidate_config),
    ):
        manifest = json.loads((directory / "manifest.json").read_text("utf-8"))
        if manifest["config_sha256"] != sha256_of(path):
            raise ComparisonError(f"the {name} was not run under {path.name}")
        configs[name] = json.loads(path.read_text(encoding="utf-8"))
    changed = config_differences(configs["baseline"], configs["candidate"])
    if not changed <= ALLOWED_CONFIG_KEYS:
        raise ComparisonError(
            "the configs differ beyond the model: "
            + ", ".join(
                ".".join(key) for key in sorted(changed - ALLOWED_CONFIG_KEYS)
            )
        )
    baseline_runs = _published_runs(baseline_dir, read_run)
    candidate_runs = _published_runs(candidate_dir, read_run)
    missing = sorted(set(candidate_runs) - set(baseline_runs))
    if missing:
        raise ComparisonError(f"the baseline has no run of {missing}")
    pairs: dict[str, dict[str, Any]] = {}
    for key in sorted(candidate_runs):
        ours, theirs = baseline_runs[key], candidate_runs[key]
        _check_pair(key, ours, theirs)
        first, second = ours[2], theirs[2]
        pairs.setdefault(key[0], {})[key[1]] = {
            "paired_task_success": _pairing(ours[1], theirs[1]),
            "overall": {
                label: _side_by_side(first["overall"], second["overall"], path)
                for label, path in _HEADLINE_ROWS
            },
            "breakouts": {
                breakout: {
                    group: _side_by_side(
                        first["breakouts"][breakout],
                        second["breakouts"][breakout],
                        (group, "task_success"),
                    )
                    for group in first["breakouts"][breakout]
                }
                for breakout, _ in BREAKOUTS
            },
            "outcomes": {
                "baseline": first["outcomes"]["final"],
                "candidate": second["outcomes"]["final"],
            },
        }
    return {
        "compare_version": COMPARE_VERSION,
        "baseline": _describe(baseline_runs, baseline_config, baseline_dir),
        "candidate": _describe(candidate_runs, candidate_config, candidate_dir),
        "sets": pairs,
    }


def _describe(
    runs: Mapping[tuple[str, str], tuple[dict[str, Any], Any, Any]],
    config: Path,
    directory: Path,
) -> dict[str, Any]:
    """Name one side of a comparison.

    Args:
        runs: Its runs.
        config: Its config file.
        directory: Its published directory.

    Returns:
        Its model, commit, config, published directory and runs.
    """
    first = next(iter(runs.values()))[0]["identity"]
    return {
        "published": directory.name,
        "model_identity": first["model_identity"],
        "gguf_sha256": first["engine_provenance"]["gguf_sha256"],
        "git_commit": first["git_commit"],
        "config": config.name,
        "config_sha256": first["config_sha256"],
        "runs": {
            f"{set_name}/{condition}": run["run_id"]
            for (set_name, condition), (run, _, _) in sorted(runs.items())
        },
    }


def _delta(value: float | None) -> str:
    """Render a difference of proportions in percentage points.

    Args:
        value: The difference, or None.

    Returns:
        A signed percentage-point figure, or a dash.
    """
    return "-" if value is None else f"{100 * value:+.1f} pp"


def render_markdown(comparison: Mapping[str, Any], title: str) -> str:
    """Render a comparison as Markdown.

    Args:
        comparison: A result of `compare`.
        title: The page's title.

    Returns:
        The Markdown text.
    """
    baseline, candidate = comparison["baseline"], comparison["candidate"]
    lines = [
        f"# {title}",
        "",
        "Generated by `eval_cli compare`; do not edit by hand. The "
        "comparison and its test were fixed before either side's numbers "
        "existed ([../PREREGISTRATION.md](../PREREGISTRATION.md)): for each "
        "set and condition, TaskSuccess paired by sample, with an exact "
        "two-sided McNemar test on the discordant pairs. Everything else, "
        "and every breakout, is descriptive. The two sides differ only in "
        "the model: `compare` refuses anything else.",
        "",
        "| | Baseline | Candidate |",
        "| --- | --- | --- |",
        f"| Model | `{baseline['model_identity']}` | "
        f"`{candidate['model_identity']}` |",
        f"| GGUF SHA-256 | `{baseline['gguf_sha256']}` | "
        f"`{candidate['gguf_sha256']}` |",
        f"| Config | `{baseline['config']}` | `{candidate['config']}` |",
        f"| Commit | `{baseline['git_commit']}` | `{candidate['git_commit']}` |",
        "",
    ]
    # Iterate in fixed orders, never in a mapping's own: a comparison read
    # back from its sorted-key JSON must render the same page.
    for set_name in sorted(comparison["sets"]):
        by_condition = {
            condition: comparison["sets"][set_name][condition]
            for condition in sorted(comparison["sets"][set_name])
        }
        lines += [f"## {set_name}", "", "### Paired TaskSuccess", ""]
        rows = []
        for condition, block in by_condition.items():
            pair = block["paired_task_success"]
            first = block["overall"]["**TaskSuccess**"]
            rows.append(
                [
                    condition,
                    str(pair["n"]),
                    _format_rate(first["baseline"]),
                    _format_rate(first["candidate"]),
                    _delta(first["delta"]),
                    str(pair["only_baseline_succeeds"]),
                    str(pair["only_candidate_succeeds"]),
                    f"{pair['mcnemar_exact_p']:.4g}",
                    str(pair["final_outcome_changed"]),
                ]
            )
        lines += _table(
            [
                "Condition",
                "n",
                "Baseline",
                "Candidate",
                "Difference",
                "Only baseline",
                "Only candidate",
                "McNemar exact p",
                "Final outcome changed",
            ],
            rows,
        )
        lines.append("")
        for condition, block in by_condition.items():
            lines += [f"### {condition}: every rate", ""]
            lines += _table(
                ["Metric", "Baseline", "Candidate", "Difference"],
                [
                    [
                        label,
                        _format_rate(block["overall"][label]["baseline"]),
                        _format_rate(block["overall"][label]["candidate"]),
                        _delta(block["overall"][label]["delta"]),
                    ]
                    for label, _ in _HEADLINE_ROWS
                ],
            )
            lines += ["", f"Final outcomes, {condition}:", ""]
            outcomes = block["outcomes"]
            lines += _table(
                ["Outcome", "Baseline", "Candidate"],
                [
                    [
                        name,
                        str(outcomes["baseline"][name]),
                        str(outcomes["candidate"][name]),
                    ]
                    for name in OUTCOMES
                ],
            )
            lines.append("")
        for breakout, heading in BREAKOUTS:
            lines += [f"### TaskSuccess by {heading} (descriptive)", ""]
            conditions = list(by_condition)
            groups = by_condition[conditions[0]]["breakouts"][breakout]
            header = [heading.capitalize(), "n"]
            for condition in conditions:
                header += [
                    f"{condition} baseline",
                    f"{condition} candidate",
                    f"{condition} difference",
                ]
            rows = []
            for group in sorted(groups):
                row = [f"`{group}`", str(groups[group]["baseline"]["n"])]
                for condition in conditions:
                    rate = by_condition[condition]["breakouts"][breakout][group]
                    row += [
                        _format_rate(rate["baseline"]),
                        _format_rate(rate["candidate"]),
                        _delta(rate["delta"]),
                    ]
                rows.append(row)
            lines += _table(header, rows)
            lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"
