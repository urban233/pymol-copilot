# Copyright 2026 PyMOL Copilot contributors.
"""Integrated TaskSuccess: the gold set through the running product.

docs/master_plan.md item 19: "Measure integrated TaskSuccess against the
offline number and explain any gap rather than averaging it away."

The offline evaluation (`pmc_eval.runner`) drives the runtime's own
request graph against a rebuilt structure and grades what a fresh
sidecar reports. The integrated measurement runs each gold sample the
way a user would: the structure is rebuilt in a live PyMOL session, the
intent goes through the PyMOL command `copilot`, the real client and the
real server (`pmc_server.main`), the preview is approved with
`copilot_apply`, and the live session is graded afterwards.

This module is the part that needs neither PyMOL nor a server: the
record of one sample, the grader that turns what the live session shows
into an `ExecutionReport` so `pmc_eval.grade.grade` grades it unchanged,
the reading of the client's console output, the classification of every
sample whose integrated outcome differs from its offline one, and the
report. `tests/integrated/integrated_cli.py` drives PyMOL and the server.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import dataclasses
import json
import math
import re
from collections.abc import Mapping
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pmc_agent.graph import with_final_newline
from pmc_core.executor import EXECUTOR_VERSION
from pmc_core.executor import OUTCOME_OK
from pmc_core.executor import REASON_OK
from pmc_core.executor import STATUS_OK
from pmc_core.executor import CommandOutcome
from pmc_core.executor import ExecutionReport
from pmc_core.executor import SelectionCount
from pmc_core.plan import ActionPlan
from pmc_core.snapshot import ObjectSnapshot
from pmc_data.audit import wilson_interval
from pmc_data.sample import Sample
from pmc_eval.compare import mcnemar_exact
from pmc_eval.grade import Grade
from pmc_eval.grade import grade
from pmc_eval.metrics import category_parts

#: The version of one integrated record's shape and of the report.
INTEGRATED_VERSION = 1

#: How one sample's run through the product ended.
#: The preview was approved and applied; the live session was graded.
OUTCOME_APPLIED = "applied"
#: A preview came back, but not approvable: the client's own fidelity
#: check or the sidecar said the session could not be reproduced.
OUTCOME_NOT_APPLICABLE = "not_applicable"
#: Apply ran, a command failed, and the session was restored.
OUTCOME_APPLY_RESTORED = "apply_restored"
#: Apply was refused before anything ran (drift, expiry, a mismatch).
OUTCOME_APPLY_REFUSED = "apply_refused"
#: The server returned no plan: a question, or a failure.
OUTCOME_NO_PLAN = "no_plan"
#: The console command did not finish in time.
OUTCOME_TIMEOUT = "timeout"
OUTCOMES = (
    OUTCOME_APPLIED,
    OUTCOME_NOT_APPLICABLE,
    OUTCOME_APPLY_RESTORED,
    OUTCOME_APPLY_REFUSED,
    OUTCOME_NO_PLAN,
    OUTCOME_TIMEOUT,
)

#: Why a sample's integrated TaskSuccess differs from its offline one,
#: in the order `explain` tests them: the first that the evidence
#: decides is the explanation.
#: The structure rebuilt in the live session is not the recorded one,
#: so the prompt was not either.
GAP_PROMPT_SKEW = "prompt_skew"
#: The console command did not finish.
GAP_TIMEOUT = "timeout"
#: The first prompt differs although the structure is the recorded
#: one: the intent reached the server changed.
GAP_INTENT_TRANSPORT = "intent_transport"
#: The same prompt produced a different completion.
GAP_ENGINE_DRIFT = "engine_drift"
#: A repair prompt differs, or the attempts do: a sidecar validation
#: came out differently, and the repair loop took another path.
GAP_VALIDATION_DRIFT = "validation_drift"
#: The same plan was not approvable live.
GAP_FIDELITY = "fidelity_not_exact"
#: The same plan failed to apply live.
GAP_APPLY_FAILED = "apply_failed"
#: The same plan was applied, but the live session ended in another
#: state than the sidecar's rehearsal of it.
GAP_APPLY_VS_SIDECAR = "apply_vs_sidecar"
#: Nothing above; investigated and explained by hand in the report.
GAP_UNEXPLAINED = "unexplained"
GAPS = (
    GAP_PROMPT_SKEW,
    GAP_TIMEOUT,
    GAP_INTENT_TRANSPORT,
    GAP_ENGINE_DRIFT,
    GAP_VALIDATION_DRIFT,
    GAP_FIDELITY,
    GAP_APPLY_FAILED,
    GAP_APPLY_VS_SIDECAR,
    GAP_UNEXPLAINED,
)

_PLAN_PREFIX = "copilot plan "
_NOT_APPLICABLE_LINE = "apply:     unavailable (inspectable only)"


@dataclass(frozen=True)
class IntegratedRecord:
    """One gold sample's run through the product, and its grade.

    Attributes:
        sample_id: The gold sample.
        condition: `grammar` or `no-grammar`.
        category: The sample's taxonomy category.
        spec_id: The held-out structure it runs on.
        outcome: One of `OUTCOMES`.
        task_success: Whether every assertion held on the live session.
        assertions: Each assertion's result, as `pmc_eval.grade` states
            it; empty unless the plan was applied.
        live_snapshot_sha256: The SHA-256 of the rebuilt live structure,
            before the request.
        prompt_skew: Whether that differs from the sample's recorded one.
        attempts: The server's trace lines for this request, one per
            completion call, in order.
        plan_pml: The previewed plan's canonical text, or None.
        live_fingerprint: The live structure's fingerprint after apply,
            in the sidecar's own form, or None.
        live_selection_counts: `[name, atom count]` for each selection
            the plan names, read from the live session after apply.
        output: The client's console lines, preview and apply.
        preview_seconds: How long `copilot <intent>` took.
        apply_seconds: How long `copilot_apply` took, or None.
    """

    sample_id: str
    condition: str
    category: str
    spec_id: str
    outcome: str
    task_success: bool
    assertions: tuple[Mapping[str, Any], ...]
    live_snapshot_sha256: str
    prompt_skew: bool
    attempts: tuple[Mapping[str, Any], ...]
    plan_pml: str | None
    live_fingerprint: str | None
    live_selection_counts: tuple[tuple[str, int], ...]
    output: tuple[str, ...]
    preview_seconds: float | None
    apply_seconds: float | None

    def to_dict(self) -> dict[str, Any]:
        """Serialize the record as one JSON-safe mapping.

        Returns:
            The record, with `integrated_version` first.
        """
        data = dataclasses.asdict(self)
        data["live_selection_counts"] = [
            list(pair) for pair in self.live_selection_counts
        ]
        return {"integrated_version": INTEGRATED_VERSION, **data}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> IntegratedRecord:
        """Read a record `to_dict` wrote.

        Args:
            data: The decoded mapping.

        Returns:
            The record.

        Raises:
            ValueError: If it is another version, or a field is missing.
        """
        if data.get("integrated_version") != INTEGRATED_VERSION:
            raise ValueError(
                f"not an integrated record v{INTEGRATED_VERSION}: "
                f"{data.get('integrated_version')!r}"
            )
        fields = {field.name for field in dataclasses.fields(cls)}
        missing = fields - set(data)
        if missing:
            raise ValueError(f"missing fields {sorted(missing)}")
        values = {name: data[name] for name in fields}
        values["assertions"] = tuple(data["assertions"])
        values["attempts"] = tuple(data["attempts"])
        values["output"] = tuple(data["output"])
        values["live_selection_counts"] = tuple(
            (str(name), int(count))
            for name, count in data["live_selection_counts"]
        )
        return cls(**values)


def live_report(
    plan: ActionPlan,
    *,
    fingerprint: str,
    selection_counts: Sequence[tuple[str, int]],
) -> ExecutionReport:
    """State what an applied plan left in the live session as a report.

    The client reports an apply as applied only when every command
    succeeded, so every outcome is `OUTCOME_OK`; a failed apply is never
    graded (`OUTCOME_APPLY_RESTORED`).

    Args:
        plan: The applied plan.
        fingerprint: The live structure's fingerprint after apply.
        selection_counts: `(name, atom count)` for
            `pmc_core.plan.selection_names`.

    Returns:
        A successful report carrying the live readings.
    """
    return ExecutionReport(
        executor_version=EXECUTOR_VERSION,
        status=STATUS_OK,
        reason=REASON_OK,
        input_digest="live-session",
        resulting_fingerprint=fingerprint,
        selection_counts=tuple(
            SelectionCount(name, count) for name, count in selection_counts
        ),
        command_outcomes=tuple(
            CommandOutcome(
                index=index,
                verb=operation.render().split(" ", 1)[0],
                status=OUTCOME_OK,
                error=None,
            )
            for index, operation in enumerate(plan.operations)
        ),
        child_pid=0,
        child_terminated=True,
        elapsed_seconds=0.0,
    )


def grade_live(
    sample: Sample,
    plan: ActionPlan,
    snapshot: ObjectSnapshot,
    *,
    fingerprint: str,
    selection_counts: Sequence[tuple[str, int]],
) -> Grade:
    """Grade an applied plan on what the live session shows.

    Args:
        sample: The gold sample.
        plan: The applied plan.
        snapshot: The structure it was applied to.
        fingerprint: The live structure's fingerprint after apply.
        selection_counts: `(name, atom count)` for
            `pmc_core.plan.selection_names`.

    Returns:
        `pmc_eval.grade.grade`'s grade, unchanged.
    """
    report = live_report(
        plan, fingerprint=fingerprint, selection_counts=selection_counts
    )
    return grade(sample, report, plan, snapshot)


@dataclass(frozen=True)
class Preview:
    """What the client's console said about one `copilot <intent>`.

    Attributes:
        plan_id: The plan's displayed identifier, or None when no plan
            came back.
        applicable: Whether the preview offers `copilot_apply`.
    """

    plan_id: str | None
    applicable: bool


def read_preview(lines: Sequence[str]) -> Preview:
    """Read the plan identifier and approvability from console output.

    Args:
        lines: Everything the client printed for one `copilot <intent>`.

    Returns:
        What the preview said.
    """
    text = "\n".join(lines)
    for line in text.splitlines():
        if line.startswith(_PLAN_PREFIX):
            plan_id = line[len(_PLAN_PREFIX) :].split(" ", 1)[0]
            applicable = _NOT_APPLICABLE_LINE not in text
            return Preview(plan_id=plan_id, applicable=applicable)
    return Preview(plan_id=None, applicable=False)


#: One numbered command in a preview: `    2 | color silver, x`, with an
#: optional `   -> 2 atoms` count after it.
_PREVIEW_COMMAND = re.compile(r"^\s+\d+ \| (?P<command>.+?)(?:\s+-> .*)?$")


def previewed_commands(lines: Sequence[str]) -> tuple[str, ...]:
    """Read the numbered commands a preview showed, in order.

    Args:
        lines: Everything the client printed for one `copilot <intent>`.

    Returns:
        Each command's canonical text.
    """
    return tuple(
        match["command"]
        for line in "\n".join(lines).splitlines()
        if (match := _PREVIEW_COMMAND.match(line))
    )


def read_apply(lines: Sequence[str], plan_id: str) -> str:
    """Classify what `copilot_apply` printed.

    Args:
        lines: Everything the client printed for one `copilot_apply`.
        plan_id: The displayed plan identifier.

    Returns:
        `OUTCOME_APPLIED`, `OUTCOME_APPLY_RESTORED`, or
        `OUTCOME_APPLY_REFUSED`.
    """
    text = "\n".join(lines)
    if f"copilot_apply: plan {plan_id} applied." in text:
        return OUTCOME_APPLIED
    if f"copilot_apply: plan {plan_id} failed and the complete" in text:
        return OUTCOME_APPLY_RESTORED
    return OUTCOME_APPLY_REFUSED


def _text(attempt: Mapping[str, Any], key: str) -> str | None:
    """Read an attempt's completion text, its final newline ensured.

    Args:
        attempt: A trace line or an offline attempt record.
        key: The field holding the text.

    Returns:
        The text, or None for an engine failure.
    """
    value = attempt.get(key)
    return with_final_newline(value) if isinstance(value, str) else None


def explain(record: IntegratedRecord, offline: Mapping[str, Any]) -> str:
    """Say why a sample's integrated outcome differs from its offline one.

    Walks the evidence in the order a request does: the structure, the
    console, the prompt of each attempt and what the model wrote to it,
    the preview, the apply, and the resulting state. The first place
    the two runs part is the explanation.

    Args:
        record: The integrated record.
        offline: The same sample's offline record, as published
            (`docs/evaluation/finetuned/test_gold/<condition>/`).

    Returns:
        One of `GAPS`.
    """
    if record.prompt_skew:
        return GAP_PROMPT_SKEW
    if record.outcome == OUTCOME_TIMEOUT:
        return GAP_TIMEOUT
    offline_attempts = offline["attempts"]
    for index, (live, recorded) in enumerate(
        zip(record.attempts, offline_attempts, strict=False)
    ):
        if live["prompt_sha256"] != recorded["prompt_sha256"]:
            return GAP_INTENT_TRANSPORT if index == 0 else GAP_VALIDATION_DRIFT
        if _text(live, "text") != _text(recorded, "completion"):
            return GAP_ENGINE_DRIFT
    if len(record.attempts) != len(offline_attempts):
        return GAP_VALIDATION_DRIFT
    if record.outcome == OUTCOME_NOT_APPLICABLE:
        return GAP_FIDELITY
    if record.outcome in (OUTCOME_APPLY_RESTORED, OUTCOME_APPLY_REFUSED):
        return GAP_APPLY_FAILED
    if record.outcome == OUTCOME_APPLIED:
        return GAP_APPLY_VS_SIDECAR
    return GAP_UNEXPLAINED


def read_records(path: Path) -> tuple[IntegratedRecord, ...]:
    """Read an integrated `samples.jsonl`.

    Args:
        path: The file.

    Returns:
        Its records, in file order.
    """
    return tuple(
        IntegratedRecord.from_dict(json.loads(line))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )


def read_offline(path: Path) -> dict[str, Mapping[str, Any]]:
    """Read a published offline `samples.jsonl`, keyed by sample.

    Args:
        path: The file.

    Returns:
        Each sample's record.
    """
    records: dict[str, Mapping[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            data = json.loads(line)
            records[data["sample_id"]] = data
    return records


def _rate(k: int, n: int) -> dict[str, Any]:
    """State one proportion with its Wilson 95% interval.

    Args:
        k: Successes.
        n: Trials.

    Returns:
        `k`, `n`, the rate, and the interval.
    """
    low, high = wilson_interval(k, n) if n else (0.0, 1.0)
    return {
        "k": k,
        "n": n,
        "rate": k / n if n else None,
        "wilson_low": low,
        "wilson_high": high,
    }


def _percentile(values: Sequence[float], fraction: float) -> float | None:
    """Take one nearest-rank percentile.

    Args:
        values: The measurements.
        fraction: The percentile, in (0, 1].

    Returns:
        The value, or None when there is none.
    """
    if not values:
        return None
    ordered = sorted(values)
    rank = math.ceil(fraction * len(ordered))
    return ordered[max(0, min(len(ordered), rank) - 1)]


def compare_condition(
    records: Sequence[IntegratedRecord],
    offline: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Pair one condition's integrated records with the offline ones.

    Args:
        records: The integrated records.
        offline: The offline records, keyed by sample.

    Returns:
        The paired comparison: both TaskSuccess rates, the exact
        McNemar test, the outcomes, the per-category and per-shape
        breakouts, every discordant sample with its explanation, and
        the live latency.

    Raises:
        ValueError: If a record has no offline counterpart, or the two
            sets differ.
    """
    by_id = {record.sample_id: record for record in records}
    if set(by_id) != set(offline):
        missing = sorted(set(offline) ^ set(by_id))
        raise ValueError(f"the two runs cover different samples: {missing}")
    integrated_k = sum(record.task_success for record in records)
    offline_k = sum(bool(offline[sid]["task_success"]) for sid in by_id)
    only_offline = [
        sid
        for sid, record in sorted(by_id.items())
        if offline[sid]["task_success"] and not record.task_success
    ]
    only_integrated = [
        sid
        for sid, record in sorted(by_id.items())
        if record.task_success and not offline[sid]["task_success"]
    ]
    breakouts: dict[str, dict[str, dict[str, Any]]] = {
        "category": {},
        "shape": {},
    }
    for sid, record in sorted(by_id.items()):
        shape = category_parts(record.category)[2]
        for breakout, key in (("category", record.category), ("shape", shape)):
            group = breakouts[breakout].setdefault(
                key, {"n": 0, "integrated": 0, "offline": 0}
            )
            group["n"] += 1
            group["integrated"] += int(record.task_success)
            group["offline"] += int(bool(offline[sid]["task_success"]))
    discordant = [
        {
            "sample_id": sid,
            "offline": bool(offline[sid]["task_success"]),
            "integrated": by_id[sid].task_success,
            "outcome": by_id[sid].outcome,
            "offline_outcome": offline[sid]["final_outcome"],
            "explanation": explain(by_id[sid], offline[sid]),
        }
        for sid in sorted(only_offline + only_integrated)
    ]
    preview = [
        record.preview_seconds
        for record in records
        if record.preview_seconds is not None
    ]
    apply = [
        record.apply_seconds
        for record in records
        if record.apply_seconds is not None
    ]
    return {
        "n": len(records),
        "integrated": _rate(integrated_k, len(records)),
        "offline": _rate(offline_k, len(records)),
        "only_offline": len(only_offline),
        "only_integrated": len(only_integrated),
        "mcnemar_exact_p": mcnemar_exact(
            len(only_offline), len(only_integrated)
        ),
        "outcomes": {
            outcome: sum(record.outcome == outcome for record in records)
            for outcome in OUTCOMES
        },
        "prompt_skew": sum(record.prompt_skew for record in records),
        "breakouts": breakouts,
        "discordant": discordant,
        "latency_seconds": {
            "preview_p50": _percentile(preview, 0.5),
            "preview_p90": _percentile(preview, 0.9),
            "apply_p50": _percentile(apply, 0.5),
            "apply_p90": _percentile(apply, 0.9),
        },
    }


def _format(rate: Mapping[str, Any]) -> str:
    """Render one rate as `k/n (r%, low-high%)`.

    Args:
        rate: A `_rate` mapping.

    Returns:
        The text.
    """
    if not rate["n"]:
        return "0/0"
    return (
        f"{rate['k']}/{rate['n']} ({100 * rate['rate']:.1f}%, "
        f"{100 * rate['wilson_low']:.1f}-{100 * rate['wilson_high']:.1f}%)"
    )


def _seconds(value: float | None) -> str:
    """Render a duration in seconds.

    Args:
        value: The duration, or None.

    Returns:
        The text.
    """
    return "—" if value is None else f"{value:.1f} s"


def render_report(
    comparison: Mapping[str, Mapping[str, Any]],
    *,
    title: str,
    notes: Mapping[str, str] | None = None,
) -> str:
    """Render the integrated comparison as a Markdown page.

    Args:
        comparison: `compare_condition`'s result per condition.
        title: The page title.
        notes: A hand-written explanation for each sample the evidence
            left `GAP_UNEXPLAINED`, keyed by sample.

    Returns:
        The page.
    """
    notes = notes or {}
    lines = [f"# {title}", ""]
    lines += [
        "| Condition | Offline TaskSuccess | Integrated TaskSuccess "
        "| Only offline | Only integrated | Exact McNemar p |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for condition, block in comparison.items():
        lines.append(
            f"| {condition} | {_format(block['offline'])} "
            f"| {_format(block['integrated'])} | {block['only_offline']} "
            f"| {block['only_integrated']} "
            f"| {block['mcnemar_exact_p']:.4g} |"
        )
    for condition, block in comparison.items():
        lines += ["", f"## {condition}", ""]
        outcomes = ", ".join(
            f"{name} {count}" for name, count in block["outcomes"].items()
        )
        latency = block["latency_seconds"]
        lines += [
            f"- Outcomes: {outcomes}.",
            f"- Prompt skew (live structure not the recorded one): "
            f"{block['prompt_skew']} of {block['n']}.",
            f"- Latency: preview p50 {_seconds(latency['preview_p50'])}, "
            f"p90 {_seconds(latency['preview_p90'])}; apply p50 "
            f"{_seconds(latency['apply_p50'])}, p90 "
            f"{_seconds(latency['apply_p90'])}.",
            "",
            "### Every sample whose outcome differs",
            "",
        ]
        if not block["discordant"]:
            lines.append("None: every sample has the offline outcome.")
        else:
            lines += [
                "| Sample | Offline | Integrated | Live outcome "
                "| Offline outcome | Explanation |",
                "| --- | --- | --- | --- | --- | --- |",
            ]
            for row in block["discordant"]:
                explanation = row["explanation"]
                note = notes.get(row["sample_id"])
                if note:
                    explanation = f"{explanation}: {note}"
                lines.append(
                    f"| {row['sample_id']} | {row['offline']} "
                    f"| {row['integrated']} | {row['outcome']} "
                    f"| {row['offline_outcome']} | {explanation} |"
                )
        for breakout in ("shape", "category"):
            lines += [
                "",
                f"### By {breakout}",
                "",
                f"| {breakout.capitalize()} | n | Offline | Integrated |",
                "| --- | --- | --- | --- |",
            ]
            for key, group in sorted(block["breakouts"][breakout].items()):
                lines.append(
                    f"| {key} | {group['n']} | {group['offline']} "
                    f"| {group['integrated']} |"
                )
    return "\n".join(lines) + "\n"
