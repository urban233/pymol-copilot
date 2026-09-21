# Copyright 2026 PyMOL Copilot contributors.
"""The generalized dataset sample record and its serialization.

Master plan item 14 requires each sample to record its source structure
identity and checksum, card version, plan, assertions, PyMOL version,
seed and verification result. This module is that record.

It sits beside `pmc_data.gold_case` rather than replacing it. A
`GoldCase` is pinned to the one hand-authored chain-A/red fixture and
its `__post_init__` asserts exactly that, which is a drift guard worth
keeping; a `Sample` carries an arbitrary verified plan.

Two deliberate choices about what is *not* recorded. Nothing
nondeterministic goes in -- no elapsed time, no child process id -- so
a corpus regenerated from the same seed is byte-identical to its
predecessor, which is what makes the seed worth recording at all. And
`plan_version` is gone: the wire's `planVersion` is just
`PROTOCOL_VERSION`, and what actually governs which plans are legal is
`POLICY_VERSION`. `pmc_core.policy` asks for exactly that join-up.

Every contract version is the real typed constant rather than a
free-form string, and `card_version` is read off the `PromptV1` that
`pmc_core.prompt.build_for_data()` returned -- not re-read from the
constant here, which would record agreement rather than prove it.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import json
from collections.abc import Iterable
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pmc_core.executor import EXECUTOR_VERSION
from pmc_core.grammar import GRAMMAR_VERSION
from pmc_core.policy import POLICY_VERSION
from pmc_core.protocol import PROTOCOL_VERSION
from pmc_core.snapshot import SNAPSHOT_VERSION

#: The Open-Source PyMOL build every sample is verified against, as
#: `requirements.in` pins it. Frozen here rather than read at runtime
#: because this module must import without PyMOL present;
#: `tests/data/test_conformance_real_pymol.py` asserts the live build
#: still matches, the same guard the frozen colour table carries.
PINNED_PYMOL_VERSION = "3.2.0.2"

#: The assertion kinds a sample can actually carry evidence for.
ASSERTION_RESULTING_SNAPSHOT = "resulting_snapshot"
ASSERTION_SELECTION_COUNTS = "selection_counts"
ASSERTION_COMMANDS_SUCCEEDED = "commands_succeeded"

SUPPORTED_ASSERTION_KINDS = frozenset(
    (
        ASSERTION_RESULTING_SNAPSHOT,
        ASSERTION_SELECTION_COUNTS,
        ASSERTION_COMMANDS_SUCCEEDED,
    )
)


class InvalidSampleError(ValueError):
    """Raised when a sample record is incomplete or self-contradictory.

    There is no default-filled or partially valid Sample: a record that
    cannot state its own provenance is not evidence of anything.
    """


def _required_string(data: Mapping[str, Any], key: str) -> str:
    """Read a required non-empty string field.

    Args:
        data: The raw mapping being decoded.
        key: The required field name.

    Returns:
        The field's string value.

    Raises:
        InvalidSampleError: If key is absent, not a string, or empty.
    """
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise InvalidSampleError(f"field {key!r} must be a non-empty string")
    return value


def _required_int(data: Mapping[str, Any], key: str) -> int:
    """Read a required integer field.

    Args:
        data: The raw mapping being decoded.
        key: The required field name.

    Returns:
        The field's integer value.

    Raises:
        InvalidSampleError: If key is absent or not an integer.
    """
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidSampleError(f"field {key!r} must be an integer")
    return value


def _required_mapping(data: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    """Read a required nested mapping field.

    Args:
        data: The raw mapping being decoded.
        key: The required field name.

    Returns:
        The nested mapping.

    Raises:
        InvalidSampleError: If key is absent or not a mapping.
    """
    value = data.get(key)
    if not isinstance(value, Mapping):
        raise InvalidSampleError(f"missing required field: {key!r}")
    return value


@dataclass(frozen=True)
class StructureIdentity:
    """Which structure a sample was generated against, and its checksum.

    Attributes:
        spec_id: The controlled structure spec's identity.
        seed: The seed the structure was built from, so it can be
            rebuilt exactly.
        snapshot_sha256: SHA-256 of the structure's canonical snapshot
            JSON -- the bytes actually handed to the executor.
        structure_digest: `pmc_core.snapshot.structure_digest` of the
            same structure, the digest the plan was bound to.
    """

    spec_id: str
    seed: int
    snapshot_sha256: str
    structure_digest: str

    def to_dict(self) -> dict[str, Any]:
        """Render this identity as a JSON-safe mapping.

        Returns:
            A plain dict with this record's fields.
        """
        return {
            "spec_id": self.spec_id,
            "seed": self.seed,
            "snapshot_sha256": self.snapshot_sha256,
            "structure_digest": self.structure_digest,
        }

    @staticmethod
    def from_dict(data: Mapping[str, Any]) -> StructureIdentity:
        """Decode a StructureIdentity, rejecting incomplete input.

        Args:
            data: The raw mapping.

        Returns:
            The decoded identity.

        Raises:
            InvalidSampleError: If a required field is missing or empty.
        """
        return StructureIdentity(
            spec_id=_required_string(data, "spec_id"),
            seed=_required_int(data, "seed"),
            snapshot_sha256=_required_string(data, "snapshot_sha256"),
            structure_digest=_required_string(data, "structure_digest"),
        )


@dataclass(frozen=True)
class SampleVersions:
    """Every contract version in force when a sample was made.

    Attributes:
        card_version: The structure-card contract version, read off the
            prompt the dataset seam actually built.
        prompt_version: The prompt contract version.
        grammar_version: The grammar contract version.
        policy_version: The policy contract version -- what decides
            which plans are legal.
        snapshot_version: The snapshot schema version.
        executor_version: The execution request/report shape version.
        protocol_version: The wire protocol version.
        pymol_version: The Open-Source PyMOL build used to verify.
    """

    card_version: int
    prompt_version: int
    grammar_version: int
    policy_version: int
    snapshot_version: int
    executor_version: int
    protocol_version: str
    pymol_version: str

    def to_dict(self) -> dict[str, Any]:
        """Render these versions as a JSON-safe mapping.

        Returns:
            A plain dict with this record's fields.
        """
        return {
            "card_version": self.card_version,
            "prompt_version": self.prompt_version,
            "grammar_version": self.grammar_version,
            "policy_version": self.policy_version,
            "snapshot_version": self.snapshot_version,
            "executor_version": self.executor_version,
            "protocol_version": self.protocol_version,
            "pymol_version": self.pymol_version,
        }

    @staticmethod
    def from_dict(data: Mapping[str, Any]) -> SampleVersions:
        """Decode SampleVersions, rejecting incomplete input.

        Args:
            data: The raw mapping.

        Returns:
            The decoded versions.

        Raises:
            InvalidSampleError: If a required field is missing.
        """
        return SampleVersions(
            card_version=_required_int(data, "card_version"),
            prompt_version=_required_int(data, "prompt_version"),
            grammar_version=_required_int(data, "grammar_version"),
            policy_version=_required_int(data, "policy_version"),
            snapshot_version=_required_int(data, "snapshot_version"),
            executor_version=_required_int(data, "executor_version"),
            protocol_version=_required_string(data, "protocol_version"),
            pymol_version=_required_string(data, "pymol_version"),
        )


def current_versions(
    *, card_version: int, prompt_version: int
) -> SampleVersions:
    """Assemble the contract versions in force in this process.

    The card and prompt versions are passed in rather than read from
    their constants, because the meaningful record is what the prompt
    the sample actually carries declared.

    Args:
        card_version: The card version the built prompt declared.
        prompt_version: The prompt version the built prompt declared.

    Returns:
        The assembled versions.
    """
    return SampleVersions(
        card_version=card_version,
        prompt_version=prompt_version,
        grammar_version=GRAMMAR_VERSION,
        policy_version=POLICY_VERSION,
        snapshot_version=SNAPSHOT_VERSION,
        executor_version=EXECUTOR_VERSION,
        protocol_version=PROTOCOL_VERSION,
        pymol_version=PINNED_PYMOL_VERSION,
    )


@dataclass(frozen=True)
class Assertion:
    """One machine-checkable claim a sample's verification established.

    Attributes:
        kind: One of SUPPORTED_ASSERTION_KINDS.
        detail: What was compared, in a form a reader can audit.
    """

    kind: str
    detail: str

    def __post_init__(self) -> None:
        """Reject an assertion kind this schema does not support.

        Raises:
            InvalidSampleError: If kind is outside the supported set.
        """
        if self.kind not in SUPPORTED_ASSERTION_KINDS:
            raise InvalidSampleError(
                f"unsupported assertion kind: {self.kind!r}"
            )

    def to_dict(self) -> dict[str, Any]:
        """Render this assertion as a JSON-safe mapping.

        Returns:
            A plain dict with this record's fields.
        """
        return {"kind": self.kind, "detail": self.detail}

    @staticmethod
    def from_dict(data: Mapping[str, Any]) -> Assertion:
        """Decode an Assertion, rejecting an unsupported kind.

        Args:
            data: The raw mapping.

        Returns:
            The decoded assertion.

        Raises:
            InvalidSampleError: If kind is missing or unsupported.
        """
        return Assertion(
            kind=_required_string(data, "kind"),
            detail=_required_string(data, "detail"),
        )


@dataclass(frozen=True)
class VerificationRecord:
    """What the executor reported, kept so a sample can be re-audited.

    Only deterministic fields are recorded. Elapsed time and the child
    process id are real parts of an ExecutionReport but would make two
    corpora built from the same seed differ, which would defeat the
    point of recording the seed.

    Attributes:
        status: The executor's status for the run.
        reason: The executor's reason code for the run.
        expected_fingerprint: The fingerprint the oracle predicted, or
            None when the result was not predictable.
        resulting_fingerprint: The fingerprint the run actually
            produced.
        selection_counts: The observed (name, atom count) pairs.
        command_verbs: The verbs that reported success, in order.
    """

    status: str
    reason: str
    expected_fingerprint: str | None
    resulting_fingerprint: str | None
    selection_counts: tuple[tuple[str, int], ...]
    command_verbs: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Render this verification record as a JSON-safe mapping.

        Returns:
            A plain dict with this record's fields.
        """
        return {
            "status": self.status,
            "reason": self.reason,
            "expected_fingerprint": self.expected_fingerprint,
            "resulting_fingerprint": self.resulting_fingerprint,
            "selection_counts": [
                [name, count] for name, count in self.selection_counts
            ],
            "command_verbs": list(self.command_verbs),
        }

    @staticmethod
    def from_dict(data: Mapping[str, Any]) -> VerificationRecord:
        """Decode a VerificationRecord, rejecting incomplete input.

        Args:
            data: The raw mapping.

        Returns:
            The decoded record.

        Raises:
            InvalidSampleError: If a required field is missing or the
                wrong shape.
        """
        counts = data.get("selection_counts")
        verbs = data.get("command_verbs")
        if not isinstance(counts, list) or not isinstance(verbs, list):
            raise InvalidSampleError(
                "selection_counts and command_verbs must both be lists"
            )
        return VerificationRecord(
            status=_required_string(data, "status"),
            reason=_required_string(data, "reason"),
            expected_fingerprint=data.get("expected_fingerprint"),
            resulting_fingerprint=data.get("resulting_fingerprint"),
            selection_counts=tuple(
                (str(name), int(count)) for name, count in counts
            ),
            command_verbs=tuple(str(verb) for verb in verbs),
        )


@dataclass(frozen=True)
class Sample:
    """One verified dataset sample, with everything needed to re-audit it.

    Attributes:
        sample_id: The stable identity of this sample.
        intent: The natural-language intent the prompt carries.
        category: The taxonomy category this sample belongs to.
        difficulty: The taxonomy difficulty label.
        structure: Which structure this was generated against.
        versions: The contract versions in force.
        plan_pml: The canonical .pml text of the verified plan.
        plan_json: The plan's canonical wire commands.
        prompt_text: The prompt exactly as a model would see it.
        assertions: The assertions actually evaluated. Never empty.
        unsupported_assertions: The assertions that could not be
            evaluated, named rather than silently omitted.
        verification: What the executor reported.
    """

    sample_id: str
    intent: str
    category: str
    difficulty: str
    structure: StructureIdentity
    versions: SampleVersions
    plan_pml: str
    plan_json: tuple[Mapping[str, Any], ...]
    prompt_text: str
    assertions: tuple[Assertion, ...]
    unsupported_assertions: tuple[str, ...]
    verification: VerificationRecord

    def __post_init__(self) -> None:
        """Reject a sample that establishes nothing.

        Raises:
            InvalidSampleError: If the sample carries no assertion. A
                record with no evaluated assertion is not a verified
                sample, whatever its verification status says.
        """
        if not self.assertions:
            raise InvalidSampleError(
                f"{self.sample_id!r}: a sample must carry at least one "
                "evaluated assertion"
            )

    def to_dict(self) -> dict[str, Any]:
        """Render this sample as a JSON-safe mapping.

        Returns:
            A plain dict suitable for json.dumps.
        """
        return {
            "sample_id": self.sample_id,
            "intent": self.intent,
            "category": self.category,
            "difficulty": self.difficulty,
            "structure": self.structure.to_dict(),
            "versions": self.versions.to_dict(),
            "plan_pml": self.plan_pml,
            "plan_json": [dict(command) for command in self.plan_json],
            "prompt_text": self.prompt_text,
            "assertions": [
                assertion.to_dict() for assertion in self.assertions
            ],
            "unsupported_assertions": list(self.unsupported_assertions),
            "verification": self.verification.to_dict(),
        }

    @staticmethod
    def from_dict(data: Mapping[str, Any]) -> Sample:
        """Decode a Sample, rejecting incomplete input.

        Args:
            data: The raw mapping, typically one JSONL line.

        Returns:
            The decoded, validated sample.

        Raises:
            InvalidSampleError: If a required field is missing, empty,
                or the wrong shape.
        """
        raw_assertions = data.get("assertions")
        if not isinstance(raw_assertions, list) or not raw_assertions:
            raise InvalidSampleError(
                "missing required non-empty field: 'assertions'"
            )
        raw_unsupported = data.get("unsupported_assertions")
        if not isinstance(raw_unsupported, list):
            raise InvalidSampleError(
                "missing required field: 'unsupported_assertions'"
            )
        raw_plan_json = data.get("plan_json")
        if not isinstance(raw_plan_json, list) or not raw_plan_json:
            raise InvalidSampleError(
                "missing required non-empty field: 'plan_json'"
            )
        return Sample(
            sample_id=_required_string(data, "sample_id"),
            intent=_required_string(data, "intent"),
            category=_required_string(data, "category"),
            difficulty=_required_string(data, "difficulty"),
            structure=StructureIdentity.from_dict(
                _required_mapping(data, "structure")
            ),
            versions=SampleVersions.from_dict(
                _required_mapping(data, "versions")
            ),
            plan_pml=_required_string(data, "plan_pml"),
            plan_json=tuple(dict(command) for command in raw_plan_json),
            prompt_text=_required_string(data, "prompt_text"),
            assertions=tuple(
                Assertion.from_dict(entry) for entry in raw_assertions
            ),
            unsupported_assertions=tuple(str(x) for x in raw_unsupported),
            verification=VerificationRecord.from_dict(
                _required_mapping(data, "verification")
            ),
        )


def to_json_line(sample: Sample) -> str:
    """Serialize one sample as a deterministic JSONL line.

    Keys are sorted and separators fixed, so a corpus regenerated from
    the same seed is byte-identical.

    Args:
        sample: The sample to serialize.

    Returns:
        The JSON text, without a trailing newline.
    """
    return json.dumps(sample.to_dict(), sort_keys=True, separators=(",", ":"))


def write_samples(path: Path, samples: Iterable[Sample]) -> int:
    """Write samples to a JSONL file, one per line.

    Args:
        path: The file to write.
        samples: The samples to write, in order.

    Returns:
        How many samples were written.
    """
    written = 0
    with path.open("w", encoding="utf-8") as handle:
        for sample in samples:
            handle.write(to_json_line(sample) + "\n")
            written += 1
    return written


def read_samples(path: Path) -> tuple[Sample, ...]:
    """Read a JSONL sample corpus back, validating every record.

    Args:
        path: The file to read.

    Returns:
        The decoded samples, in file order.

    Raises:
        InvalidSampleError: If any line is not a valid sample record.
    """
    samples: list[Sample] = []
    for number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        try:
            samples.append(Sample.from_dict(json.loads(line)))
        except json.JSONDecodeError as error:
            raise InvalidSampleError(
                f"{path}:{number}: line is not valid JSON"
            ) from error
    return tuple(samples)
