# Copyright 2026 PyMOL Copilot contributors.
"""Deterministic validation warnings, derived only from executor evidence.

docs/master_plan.md item 11: `copilot` must print "selection counts and
validation warnings where available"
([SPECIFICATION.md:503-511](../../SPECIFICATION.md)). Until this module
existed, the server always sent an empty `warnings` tuple
(`pmc_server.lifecycle`'s two report builders both hard-coded `()`) even
though the sidecar had already computed selection counts a warning could be
built from. `derive_warnings` is that missing computation: a pure function
of the sidecar's own `ExecutionReport` evidence and the attempt count
`validating` already tracks, never of the model's raw completion text.

That purity is deliberate and load-bearing, not incidental.
SPECIFICATION.md:551-552 forbids model output from influencing anything
this system treats as authoritative; a warning is user-facing text, and a
warning whose wording could be steered by a hostile completion would be
exactly the kind of influence that invariant exists to rule out. Every
parameter below traces back to `pmc_core.executor.ExecutionReport` (via
`pmc_agent.graph`'s own call to `execute()`) or to `RequestState["attempt"]`
(incremented once per `generating` call, by `generating` itself, never by
anything the model returns) -- nothing here reads
`RequestState["completion"]`. `tests/adversarial/test_model_authority.py`
proves this with a hostile fake engine whose completion embeds a forged
`# selection copilot_selection: 999 atoms` comment: the derived warnings
must be identical to a benign run's.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

from collections.abc import Sequence

from pmc_core.errors import normalize_message
from pmc_core.executor import SelectionCount
from pmc_core.executor import bounded_diagnostic
from pmc_core.protocol import MAX_VALIDATION_WARNINGS
from pmc_core.protocol import MAX_VALIDATION_WARNING_BYTES

#: `derive_warnings`'s own fixed template for a selection that matched no
#: atoms -- scientifically useful information (SPECIFICATION.md:503-511
#: wants "validation warnings where available"), not a failure: the plan
#: still validated and may still be applied.
_ZERO_MATCH_TEMPLATE = "selection {name} matched 0 atoms"

#: `derive_warnings`'s own fixed template for a selection that matched
#: every atom of the target object -- often a sign the user meant a
#: narrower selection than the one actually generated.
_FULL_MATCH_TEMPLATE = (
    "selection {name} matches every atom of the target object"
)

#: `derive_warnings`'s own fixed template naming how many repair attempts a
#: plan needed before it validated. Singular and plural forms differ only
#: in the noun, kept as two literals rather than a pluralization helper
#: this module would otherwise be the only caller of.
_REPAIR_TEMPLATE_SINGULAR = (
    "this plan needed 1 repair attempt before it validated"
)
_REPAIR_TEMPLATE_PLURAL = (
    "this plan needed {count} repair attempts before it validated"
)

#: The fixed prefix a captured sidecar stderr warning is reported under, so
#: it reads as infrastructure diagnostic text rather than a claim about the
#: plan itself.
_SIDECAR_PREFIX = "sidecar: "


def _bounded_warning(text: str) -> str:
    """Bound one already-ASCII warning string to the wire's own limit.

    Args:
        text: A warning string built from this module's own fixed
            templates and already-constrained identifiers (a selection
            name, an integer). Never raw PyMOL or model text.

    Returns:
        `text`, truncated if it somehow exceeds
        `MAX_VALIDATION_WARNING_BYTES`.
    """
    return bounded_diagnostic(text, maximum_bytes=MAX_VALIDATION_WARNING_BYTES)


def derive_warnings(
    *,
    selection_counts: Sequence[SelectionCount],
    target_atom_count: int,
    repair_attempts: int,
    sidecar_warnings: Sequence[str],
) -> tuple[str, ...]:
    """Derive bounded, deterministic warnings from one validated attempt.

    Args:
        selection_counts: The sidecar's own per-selection atom counts, in
            the plan's own command order
            (`pmc_core.executor.ExecutionReport.selection_counts`).
        target_atom_count: The target object's own declared atom count
            (`StructureSnapshotV1.atom_count`), the client's own count of
            the whole object before any command ran.
        repair_attempts: How many repair attempts this plan needed before
            it validated -- `RequestState["attempt"] - 1` at the point
            `validating` succeeds. Zero for a plan that validated on its
            first generation.
        sidecar_warnings: Bounded diagnostic text the executor itself
            already captured (`ExecutionReport.warnings`), such as
            non-fatal captured child stderr.

    Returns:
        At most `MAX_VALIDATION_WARNINGS` warning strings, each at most
        `MAX_VALIDATION_WARNING_BYTES`, in a fixed order: one entry per
        selection that warrants one (zero-match or full-match, never
        both), then the repair-attempt warning if any repairs were needed,
        then every sidecar warning.
    """
    warnings: list[str] = []
    for count in selection_counts:
        if count.atom_count == 0:
            warnings.append(
                _bounded_warning(_ZERO_MATCH_TEMPLATE.format(name=count.name))
            )
        elif target_atom_count > 0 and count.atom_count == target_atom_count:
            warnings.append(
                _bounded_warning(_FULL_MATCH_TEMPLATE.format(name=count.name))
            )
    if repair_attempts > 0:
        template = (
            _REPAIR_TEMPLATE_SINGULAR
            if repair_attempts == 1
            else _REPAIR_TEMPLATE_PLURAL.format(count=repair_attempts)
        )
        warnings.append(_bounded_warning(template))
    for stderr in sidecar_warnings:
        warnings.append(
            _bounded_warning(_SIDECAR_PREFIX + normalize_message(stderr))
        )
    return tuple(warnings[:MAX_VALIDATION_WARNINGS])
