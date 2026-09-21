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

import pytest

from pmc_data.sample import ASSERTION_COMMANDS_SUCCEEDED
from pmc_data.sample import ASSERTION_RESULTING_SNAPSHOT
from pmc_data.sample import Assertion
from pmc_data.sample import InvalidSampleError
from pmc_data.sample import Sample
from pmc_data.sample import SampleVersions
from pmc_data.sample import StructureIdentity
from pmc_data.sample import VerificationRecord
from pmc_data.sample import read_samples
from pmc_data.sample import to_json_line
from pmc_data.sample import write_samples


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
            spec_id="everything_small",
            seed=20260921,
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
            pymol_version="3.2.0.2",
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


def test_a_corpus_round_trips_through_jsonl(tmp_path: object) -> None:
    """Reading a written corpus back must validate every record.

    Args:
        tmp_path: pytest's per-test temporary directory.
    """
    path = tmp_path / "samples.jsonl"  # pyrefly: ignore.
    samples = (_sample(), _sample(sample_id="everything_small_0002"))

    assert write_samples(path, samples) == 2
    assert read_samples(path) == samples


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
