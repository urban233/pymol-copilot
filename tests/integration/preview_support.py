# Copyright 2026 PyMOL Copilot contributors.
"""Read a `copilot` preview block without indexing captured output lines.

docs/master_plan.md item 11 replaces the four separate `_output` calls
`copilot` used to make (fidelity, plan, checked, apply) with one block. A
test that indexed `output[0]`, `output[1]`, ... against the old four-line
shape breaks the moment a section is added, reordered, or merged -- this
module is what those tests read from instead: by section name, not
position, so a wording or ordering change inside the block does not by
itself break a test that only cares whether a section exists and what it
says.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

#: A top-level section line inside a preview block: two leading spaces,
#: then a label of letters and spaces, a colon, then the rest of the line.
#: Matches both `"  object:    ..."` and `"  NOT checked: ..."` -- every
#: label `pmc_client.command._preview_block` emits is letters and spaces
#: only. A continuation or detail line (a numbered command, a bulleted
#: warning or mismatch) is indented four or more spaces and never matches.
_SECTION_LINE = re.compile(r"^  ([A-Za-z ]+):[ ]?(.*)$")


def find_preview(output: Sequence[str]) -> str:
    """Return the one complete preview block from captured console output.

    Args:
        output: Every line a test's fake `output.append` callback
            recorded, in the order `copilot` printed them.

    Returns:
        The single multi-line preview block: the one entry beginning with
        `"copilot plan "`.

    Raises:
        AssertionError: If no such entry exists, or more than one does --
            `copilot` prints at most one preview per invocation, so either
            case means the test itself is looking at the wrong output.
    """
    previews = [line for line in output if line.startswith("copilot plan ")]
    assert len(previews) == 1, (
        f"expected exactly one preview block in output, found "
        f"{len(previews)}: {output!r}"
    )
    return previews[0]


def plan_id_from(output: Sequence[str]) -> str:
    """Extract the displayed plan id from a preview block's own first line.

    Args:
        output: Every line a test's fake `output.append` callback
            recorded.

    Returns:
        The plan id exactly as a user would type it back to
        `copilot_apply` or `copilot_reject` (the `"p-<uuid>"` form), read
        from `"copilot plan p-<id> (expires ...)"`.
    """
    first_line = find_preview(output).splitlines()[0]
    return first_line.removeprefix("copilot plan ").split(" ", 1)[0]


def section(output: Sequence[str], name: str) -> str:
    """Return one named section's own text from the preview block.

    Args:
        output: Every line a test's fake `output.append` callback
            recorded.
        name: The section label, case-insensitive, e.g. `"object"`,
            `"commands"`, `"warnings"`, `"fidelity"`, `"checked"`,
            `"NOT checked"`, `"apply"`, or `"reject"`.

    Returns:
        That section's text, with its own label and leading indentation
        stripped. For a multi-line section (`"commands"`, `"warnings"`, a
        non-exact `"fidelity"`), every line belonging to it, joined with
        newlines.

    Raises:
        AssertionError: If no preview block exists, or `name` does not
            name a section in it.
    """
    lines = find_preview(output).splitlines()
    collected: list[str] = []
    capturing = False
    for line in lines:
        match = _SECTION_LINE.match(line)
        if match is not None:
            if capturing:
                break
            if match.group(1).strip().lower() == name.strip().lower():
                capturing = True
                collected.append(match.group(2))
            continue
        if capturing:
            collected.append(line)
    assert capturing, f"no {name!r} section found in preview block: {lines!r}"
    return "\n".join(collected).strip()
