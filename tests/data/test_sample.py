# Copyright 2026 PyMOL Copilot contributors.
"""Schema evidence for the generalized dataset sample record.

A sample is the only durable account of how it was verified, so the
properties worth proving are that nothing can go missing from it: a
record that round-trips without loss, a record that cannot be decoded
with a required field absent, and -- the one that matters most for an
honest rejection report -- an unsupported assertion that survives
serialization instead of quietly disappearing into an absent field.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import json
from pathlib import Path

import pytest

from pmc_data.sample import ASSERTION_COMMANDS_SUCCEEDED
from pmc_data.sample import ASSERTION_RESULTING_SNAPSHOT
from pmc_data.sample import ASSERTION_SELECTION_COUNTS
from pmc_data.sample import FINGERPRINT_PREFIX
from pmc_data.sample import Assertion
from pmc_data.sample import InvalidSampleError
from pmc_data.sample import PINNED_PYMOL_VERSION
from pmc_data.sample import Sample
from pmc_data.sample import SampleVersions
from pmc_data.sample import StructureIdentity
from pmc_data.sample import VerificationRecord
from pmc_data.sample import read_samples
from pmc_data.sample import to_json_line
from pmc_data.sample import write_samples
from pmc_core.snapshot import structure_digest
from pmc_data.structures import StructureSpec
from pmc_data.structures import build_structure
from pmc_data.structures import enumerate_structures

#: A real spec from the standing matrix, so the recorded structure is
#: one that could actually be rebuilt from the record.
SPEC = next(
    spec
    for spec in enumerate_structures(20260921)
    if spec.spec_id == "everything_small"
)


def _sample(**overrides: object) -> Sample:
    """Build a well-formed sample, with fields overridden.

    Args:
        overrides: Field values replacing the defaults.

    Returns:
        The assembled sample.
    """
    fields: dict[str, object] = {
        "sample_id": "everything_small_0001",
        "intent": "Colour chain A red.",
        "category": "color.chain",
        "difficulty": "basic",
        "structure": StructureIdentity(
            spec_id=SPEC.spec_id,
            seed=SPEC.seed,
            spec=SPEC.to_dict(),
            snapshot_sha256="a" * 64,
            structure_digest="sha256:" + "b" * 64,
        ),
        "versions": SampleVersions(
            card_version=1,
            prompt_version=1,
            grammar_version=1,
            policy_version=1,
            snapshot_version=1,
            executor_version=1,
            protocol_version="1",
            pymol_version=PINNED_PYMOL_VERSION,
        ),
        "plan_pml": "select copilot_a, chain A\ncolor red, copilot_a\n",
        "plan_json": (
            {"verb": "select", "name": "copilot_a", "expression": "chain A"},
        ),
        "prompt_text": "prompt-version=1\ncard-version=1\n",
        "assertions": (
            Assertion(kind=ASSERTION_RESULTING_SNAPSHOT, detail="sha256:x"),
            Assertion(kind=ASSERTION_COMMANDS_SUCCEEDED, detail="2 commands"),
        ),
        "unsupported_assertions": (),
        "verification": VerificationRecord(
            status="ok",
            reason="ok",
            expected_fingerprint="sha256:x",
            resulting_fingerprint="sha256:x",
            selection_counts=(("copilot_a", 28),),
            command_verbs=("select", "color"),
        ),
    }
    fields.update(overrides)
    return Sample(**fields)  # pyrefly: ignore.


def test_round_trip_preserves_every_field() -> None:
    """A sample decoded from its own JSON must equal the original."""
    sample = _sample()

    assert Sample.from_dict(json.loads(to_json_line(sample))) == sample


@pytest.mark.parametrize(
    "field",
    [
        "sample_id",
        "intent",
        "category",
        "difficulty",
        "structure",
        "versions",
        "plan_pml",
        "plan_json",
        "prompt_text",
        "assertions",
        "unsupported_assertions",
        "verification",
    ],
)
def test_missing_required_field_is_rejected(field: str) -> None:
    """No field may default silently; a partial record is not evidence.

    Args:
        field: The top-level field to remove before decoding.
    """
    data = _sample().to_dict()
    del data[field]

    with pytest.raises(InvalidSampleError):
        Sample.from_dict(data)


def test_unsupported_assertions_survive_round_trip() -> None:
    """The honest rejection report depends on this field surviving.

    An unsupported marker that vanished in serialization would turn a
    sample whose camera assertion was never checked into one that looks
    fully verified.
    """
    sample = _sample(unsupported_assertions=("camera_view",))

    decoded = Sample.from_dict(json.loads(to_json_line(sample)))

    assert decoded.unsupported_assertions == ("camera_view",)


def test_a_sample_with_no_evaluated_assertion_is_rejected() -> None:
    """A record that established nothing must not be called a sample."""
    with pytest.raises(InvalidSampleError, match="at least one"):
        _sample(assertions=())


def test_a_failed_verification_cannot_be_recorded_as_a_sample() -> None:
    """A `Sample` is the type for an attempt that passed.

    An attempt that did not is a `Rejection`. Nothing enforced that,
    so a persisted record saying `status="failed"` decoded cleanly and
    `build_report` counted it among the kept -- a route by which a
    known failure could have become training data.
    """
    with pytest.raises(InvalidSampleError, match="successful verification"):
        _sample(
            verification=VerificationRecord(
                status="failed",
                reason="fidelity_mismatch",
                expected_fingerprint="sha256:x",
                resulting_fingerprint="sha256:x",
                selection_counts=(),
                command_verbs=("select", "color"),
            )
        )


def test_a_fingerprint_that_did_not_match_is_rejected() -> None:
    """A sample graded against one fingerprint must record that one.

    The status alone is not enough: a record can claim success while
    the two fingerprints beside it disagree, and that record is
    evidence of nothing.
    """
    with pytest.raises(InvalidSampleError, match="graded against"):
        _sample(
            verification=VerificationRecord(
                status="ok",
                reason="ok",
                expected_fingerprint="sha256:x",
                resulting_fingerprint="sha256:y",
                selection_counts=(),
                command_verbs=("select", "color"),
            )
        )


def test_an_assertion_contradicting_its_own_verification_is_rejected() -> None:
    """An assertion must state what the verification beside it recorded.

    The assertions are what a reader audits the sample by. One that
    names a fingerprint the run was never graded against describes a
    different comparison than the one that happened.
    """
    with pytest.raises(InvalidSampleError, match="resulting_snapshot"):
        _sample(
            assertions=(
                Assertion(
                    kind=ASSERTION_RESULTING_SNAPSHOT, detail="sha256:other"
                ),
            )
        )

    with pytest.raises(InvalidSampleError, match="selection_counts"):
        _sample(
            assertions=(
                Assertion(
                    kind=ASSERTION_SELECTION_COUNTS,
                    detail="[('copilot_a', 999)]",
                ),
            )
        )


def test_an_unsupported_assertion_kind_is_rejected() -> None:
    """Widening the closed set must be a deliberate edit, not a typo."""
    with pytest.raises(InvalidSampleError, match="unsupported assertion kind"):
        Assertion(kind="camera_view_checked", detail="")


def test_serialization_is_deterministic() -> None:
    """Two corpora built from the same seed must be byte-identical."""
    assert to_json_line(_sample()) == to_json_line(_sample())


def test_no_nondeterministic_field_is_recorded() -> None:
    """Elapsed time or a process id would break seed reproducibility."""
    rendered = to_json_line(_sample())

    for forbidden in ("elapsed", "pid", "timestamp"):
        assert forbidden not in rendered


def test_a_corpus_round_trips_through_jsonl(tmp_path: Path) -> None:
    """Reading a written corpus back must validate every record.

    Args:
        tmp_path: pytest's per-test temporary directory.
    """
    path = tmp_path / "samples.jsonl"
    samples = (_sample(), _sample(sample_id="everything_small_0002"))

    assert write_samples(path, samples) == 2
    assert read_samples(path) == samples


def test_a_structure_identity_that_contradicts_its_own_spec_is_rejected() -> (
    None
):
    """The convenience copy must not be able to drift from the spec.

    spec_id and seed are kept beside the full spec because they are
    what a reader and the per-category report group by. If they could
    disagree with the spec that actually rebuilds the structure, a
    sample could be filed under one structure and replayed as another.
    """
    with pytest.raises(InvalidSampleError, match="contradicts"):
        StructureIdentity(
            spec_id="some_other_structure",
            seed=SPEC.seed,
            spec=SPEC.to_dict(),
            snapshot_sha256="a" * 64,
            structure_digest="sha256:" + "b" * 64,
        )


def test_a_recorded_spec_rebuilds_the_structure_it_names() -> None:
    """A committed sample must be replayable without the standing matrix."""
    recorded = _sample().structure

    rebuilt = build_structure(StructureSpec.from_dict(recorded.spec))

    assert structure_digest(rebuilt) == structure_digest(build_structure(SPEC))


def test_a_sample_knows_when_it_predicted_no_change() -> None:
    """Both halves of the comparison are already recorded on the sample.

    Deriving this rather than storing a flag is what lets a corpus
    written before the distinction existed be measured for it.
    """
    unchanged = _sample(
        # The assertion moves with the verification: a sample states
        # in its assertions what it was actually graded against, and
        # Sample rejects one whose two halves disagree.
        assertions=(
            Assertion(
                kind=ASSERTION_RESULTING_SNAPSHOT,
                detail=FINGERPRINT_PREFIX + "a" * 64,
            ),
            Assertion(kind=ASSERTION_COMMANDS_SUCCEEDED, detail="1 commands"),
        ),
        verification=VerificationRecord(
            status="ok",
            reason="ok",
            # The same bytes the structure identity hashes, so the
            # oracle predicted the structure it was handed.
            expected_fingerprint=FINGERPRINT_PREFIX + "a" * 64,
            resulting_fingerprint=FINGERPRINT_PREFIX + "a" * 64,
            selection_counts=(),
            command_verbs=("hide",),
        ),
    )

    assert unchanged.structure.snapshot_sha256 == "a" * 64
    assert unchanged.predicted_no_change is True
    assert _sample().predicted_no_change is False


def test_a_sample_with_no_predicted_snapshot_did_not_predict_no_change() -> (
    None
):
    """An absent prediction is not a prediction that nothing happened."""
    unpredicted = _sample(
        # What an orienting plan actually records: no snapshot
        # assertion at all, because none was computed, and the
        # selection counts it was graded on instead.
        assertions=(
            Assertion(
                kind=ASSERTION_SELECTION_COUNTS,
                detail="[('copilot_a', 28)]",
            ),
            Assertion(kind=ASSERTION_COMMANDS_SUCCEEDED, detail="2 commands"),
        ),
        verification=VerificationRecord(
            status="ok",
            reason="ok",
            expected_fingerprint=None,
            resulting_fingerprint=None,
            selection_counts=(("copilot_a", 28),),
            command_verbs=("orient",),
        ),
    )

    assert unpredicted.predicted_no_change is False


def test_a_sample_knows_when_it_graded_an_empty_selection() -> None:
    """A zero expected count is met by zero whatever the oracle did."""
    empty = _sample(
        verification=VerificationRecord(
            status="ok",
            reason="ok",
            expected_fingerprint="sha256:x",
            resulting_fingerprint="sha256:x",
            selection_counts=(("copilot_a", 28), ("copilot_b", 0)),
            command_verbs=("select", "select"),
        )
    )

    assert empty.graded_empty_selection is True
    assert _sample().graded_empty_selection is False


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
