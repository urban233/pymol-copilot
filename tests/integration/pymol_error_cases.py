# Copyright 2026 PyMOL Copilot contributors.
"""The deliberately broken commands behind the captured error corpus.

Shared by the two targets that must never disagree about what was driven:
`capture_pymol_errors.py`, which writes
`tests/contract/testdata/pymol_errors/`, and `test_errors_real_pymol.py`,
which re-drives the same commands against a live PyMOL and fails when the
checked-in strings stop matching. Holding one case table means a case
added to the capture is automatically covered by the conformance test.

This module imports no PyMOL. Every case takes the live `cmd` module as a
parameter, the same discipline `pmc_core.snapshot` follows, so importing
it costs nothing and a PyMOL-free test can still read the table.

Some cases cannot be reached through a policy-valid plan: an unknown
color and an unknown representation are both denied by `pmc_core.parser`
before PyMOL ever sees them, and a command referencing an undefined
selection is denied by `pmc_core.policy`. They are captured anyway and
marked `reachable: false`. `pmc_core.errors` is a boundary, and a boundary
is tested against the input the boundary above it is supposed to have
stopped.

`orient` is the one verb with no selection failure that raises. Measured
against PyMOL 3.2.0a, `cmd.orient` returns None for an undefined selection
name, for a malformed selector and for None itself, writing its complaint
to the output stream and continuing. Its only raising failure is an
argument PyMOL cannot coerce. That is recorded here rather than worked
around, and it matters to item 4 of the master plan: a sidecar executor
cannot learn from an exception whether an orient did anything.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pmc_core.errors import exception_type_name
from pmc_core.errors import normalize

#: The object every case acts on, loaded once before the cases run so that
#: a failure is the command's own and not an empty-session artifact.
FIXTURE_OBJECT = "copilot_fixture"


@dataclass(frozen=True)
class Case:
    """One deliberately broken command.

    Attributes:
        case: A stable identifier for this case within its verb's file.
        verb: The supported verb being driven.
        command_index: The index this case's envelope records.
        reachable: Whether a policy-valid plan could produce this failure.
        drive: Calls the typed PyMOL API in the way that fails. Takes
            the live `cmd` module, which carries no type information of
            its own, so it is annotated Any as everywhere else that
            touches real PyMOL.
    """

    case: str
    verb: str
    command_index: int
    reachable: bool
    drive: Callable[[Any], object]


def cases() -> tuple[Case, ...]:
    """Build the case table.

    Returns:
        Every case, grouped by verb in the order they are written out.
    """
    return (
        Case(
            case="malformed_selector",
            verb="select",
            command_index=0,
            reachable=False,
            drive=lambda cmd: cmd.select("copilot_broken", "chain"),
        ),
        Case(
            case="unparsable_selector",
            verb="select",
            command_index=0,
            reachable=False,
            drive=lambda cmd: cmd.select("copilot_broken", "resi and and"),
        ),
        Case(
            case="unknown_color",
            verb="color",
            command_index=1,
            reachable=False,
            drive=lambda cmd: cmd.color("notacolor", FIXTURE_OBJECT),
        ),
        Case(
            case="undefined_selection",
            verb="color",
            command_index=1,
            reachable=False,
            drive=lambda cmd: cmd.color("red", "copilot_undefined"),
        ),
        Case(
            case="malformed_selector",
            verb="color",
            command_index=1,
            reachable=False,
            drive=lambda cmd: cmd.color("red", "chain"),
        ),
        Case(
            case="unknown_representation",
            verb="show",
            command_index=2,
            reachable=False,
            drive=lambda cmd: cmd.show("notarep", FIXTURE_OBJECT),
        ),
        Case(
            case="undefined_selection",
            verb="show",
            command_index=2,
            reachable=False,
            drive=lambda cmd: cmd.show("cartoon", "copilot_undefined"),
        ),
        Case(
            case="unknown_representation",
            verb="hide",
            command_index=3,
            reachable=False,
            drive=lambda cmd: cmd.hide("notarep", FIXTURE_OBJECT),
        ),
        Case(
            case="undefined_selection",
            verb="hide",
            command_index=3,
            reachable=False,
            drive=lambda cmd: cmd.hide("cartoon", "copilot_undefined"),
        ),
        # orient raises for no selection problem at all -- see this
        # module's docstring. Its only raising failure is an argument
        # PyMOL cannot coerce, which is a caller defect rather than
        # anything a model could produce, and which lands in the
        # `unknown` catch-all. It is captured because it is the one case
        # that proves the catch-all against a real failure.
        Case(
            case="uncoercible_state",
            verb="orient",
            command_index=4,
            reachable=False,
            drive=lambda cmd: cmd.orient(FIXTURE_OBJECT, state="notanint"),
        ),
    )


def capture_case(cmd: Any, case: Case) -> dict[str, object] | None:
    """Drive one case and record what it raised.

    Args:
        cmd: The live PyMOL command module.
        case: The case to drive.

    Returns:
        The recorded case, or None if the command did not fail at all --
        a case that stops failing is reported rather than recorded, since
        a corpus entry with no failure behind it would be a fiction.
    """
    try:
        case.drive(cmd)
    except BaseException as error:  # Any raised type is the point.
        envelope = normalize(
            error, command_index=case.command_index, verb=case.verb
        )
        return {
            "case": case.case,
            "verb": case.verb,
            "reachable": case.reachable,
            "exception_type": exception_type_name(error),
            "raw_message": str(error),
            "expected": envelope.to_dict(),
        }
    return None
