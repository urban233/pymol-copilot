# Copyright 2026 PyMOL Copilot contributors.
"""One place that names every contract version this system agrees on.

Every module in this package that owns a wire-relevant contract stamps its
own `*_VERSION` constant: `PROTOCOL_VERSION`, `POLICY_VERSION`,
`SNAPSHOT_VERSION`, `CARD_VERSION`, `PROMPT_VERSION`, `GRAMMAR_VERSION`,
`ERROR_ENVELOPE_VERSION`, and `EXECUTOR_VERSION`. Until now nothing read
all of them at once, so a health report or a diagnostic command had nowhere
to ask "what does this build actually agree to." `contract_versions()` is
that place: a frozen mapping of wire-field name to version string, built
directly from those existing constants rather than from a second,
independently maintained list.

`pmc_core.plan` has no version constant of its own -- its compatibility is
carried by `pmc_core.protocol.CURRENT_CONTRACT_MANIFEST.plan_version`
instead, which is why that one field is read from the manifest rather than
from a module constant. `tests/contract/test_versions.py` proves this
mapping cannot silently fall behind: it walks every `pmc_core` module with
`ast` and asserts each `*_VERSION` constant it finds is represented here
under its expected key, with the same value.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

from types import MappingProxyType

from pmc_core.card import CARD_VERSION
from pmc_core.errors import ERROR_ENVELOPE_VERSION
from pmc_core.executor import EXECUTOR_VERSION
from pmc_core.grammar import GRAMMAR_VERSION
from pmc_core.policy import POLICY_VERSION
from pmc_core.prompt import PROMPT_VERSION
from pmc_core.protocol import CURRENT_CONTRACT_MANIFEST
from pmc_core.protocol import PROTOCOL_VERSION
from pmc_core.snapshot import SNAPSHOT_VERSION

#: This application's own release version. Kept in sync with
#: `pyproject.toml`'s `[project].version` by hand; `test_versions.py`
#: reads that file and fails if the two ever diverge.
APPLICATION_VERSION = "0.0.0"


def contract_versions() -> MappingProxyType[str, str]:
    """Return every contract version this build agrees to, by wire name.

    Returns:
        A frozen mapping from wire-field name to version string, covering
        the protocol, the immutable plan manifest, the command policy, the
        structure snapshot, the structure card, the prompt, the grammar,
        the error envelope, and the sidecar executor. Every value is a
        string, even where the underlying module constant is an int, so a
        caller never has to special-case one field's type.
    """
    return MappingProxyType(
        {
            "protocol": PROTOCOL_VERSION,
            "plan": CURRENT_CONTRACT_MANIFEST.plan_version,
            "policy": str(POLICY_VERSION),
            "snapshot": str(SNAPSHOT_VERSION),
            "card": str(CARD_VERSION),
            "prompt": str(PROMPT_VERSION),
            "grammar": str(GRAMMAR_VERSION),
            "errorEnvelope": str(ERROR_ENVELOPE_VERSION),
            "executor": str(EXECUTOR_VERSION),
        }
    )
