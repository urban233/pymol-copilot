# Copyright 2026 PyMOL Copilot contributors.
"""Resolve the one live molecular object and extract its canonical snapshot.

docs/master_plan.md item 7's first half: before a plan request can carry a
real snapshot identity, the client must know which loaded object it
describes. `resolve_target_object()` and `extract_live_snapshot()` are the
two calls `pmc_client.command` makes to get there.

This module never imports `pymol`: every method it needs from a live PyMOL
session is named structurally on `PyMOLSession`, exactly the discipline
`pmc_core.snapshot.extract()` and `src/pmc_data/verifier.py`'s own
`PyMOLCmd` already follow, so the wider client package stays importable
without PyMOL installed.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

from typing import Any
from typing import Protocol

from pmc_core.snapshot import ObjectSnapshot
from pmc_core.snapshot import extract
from pmc_core.snapshot import structure_digest

#: The PyMOL type string `cmd.get_type()` returns for a molecular object,
#: as opposed to `"object:measurement"` or any other kind PyMOL supports.
#: See tests/integration/test_snapshot_round_trip.py's own
#: `test_measurement_objects_are_not_recoverable_via_query_apis` for why a
#: measurement object must never be resolved as a target: `extract()`'s
#: own query APIs cannot read one back as atoms at all.
MOLECULE_OBJECT_TYPE = "object:molecule"


class PyMOLSession(Protocol):
    """The live query surface this module and `pmc_core.snapshot.extract()` use.

    A structural type, not an implementation: every method named here
    already exists on the real PyMOL `cmd` module. `extract()` itself
    still takes `cmd` as an untyped `Any` (it never imports `pymol`
    either), so this Protocol exists for this module's own two functions
    and for `pmc_client.command`'s callers, not to change `extract()`'s
    own signature.
    """

    def get_names(
        self, kind: str = "objects", *, enabled_only: int = 0
    ) -> list[str]:
        """Return the names of every loaded object of the given kind.

        Args:
            kind: The PyMOL name-kind selector, e.g. `"objects"`.
            enabled_only: When 1, list only enabled objects. Defaults to 0
                so a disabled-but-loaded object still resolves -- disabled
                is a display state `pmc_core.snapshot.ObjectSnapshot.enabled`
                tracks, not a reason to skip an object entirely.

        Returns:
            The list of matching names.
        """

    def get_type(self, name: str) -> str:
        """Return the PyMOL type string for one named object.

        Args:
            name: The object or selection name to query.

        Returns:
            The object's PyMOL type string, e.g. `"object:molecule"`.
        """

    def count_states(self, selection: str) -> int:
        """Return the number of coordinate states an object has.

        Args:
            selection: The object or selection to count states for.

        Returns:
            The number of coordinate states.
        """

    def get_model(self, selection: str, *, state: int) -> Any:
        """Return one coordinate state's atoms and bonds as a chempy model.

        Args:
            selection: The object or selection to query.
            state: The 1-based coordinate state to read.

        Returns:
            A chempy model exposing `.atom` and `.bond`. Untyped: this is
            PyMOL's own dynamic return shape, not one this module defines.
        """

    def iterate(
        self, selection: str, expression: str, *, space: dict[str, object]
    ) -> None:
        """Run a per-atom Python expression over a selection.

        Args:
            selection: The selection expression to iterate over.
            expression: The Python expression evaluated once per atom.
            space: The namespace exposed to the expression.
        """

    def get_view(self) -> tuple[float, ...]:
        """Return the current camera view.

        Returns:
            The 18-float view tuple PyMOL's own `get_view()` returns.
        """

    def get(self, setting: str, selection: str) -> str:
        """Return one object-scoped setting's current value.

        Args:
            setting: The PyMOL setting name.
            selection: The object to read the setting for.

        Returns:
            The setting's current value, as PyMOL's own `get()` returns it.
        """


class TargetResolutionError(RuntimeError):
    """Raised when no single molecular object can be resolved as the target."""


def resolve_target_object(cmd: PyMOLSession) -> str:
    """Resolve the one loaded molecular object a request should target.

    SPECIFICATION.md:216 requires "one explicitly resolved active molecular
    object for normal planning". Resolution is deterministic and fails
    closed: zero or more than one candidate is a bounded local failure,
    with no request ever sent and no guessing which object the user meant.
    A zero-object session is preparation's controlled-fetch territory, not
    this function's; it only reports the fact.

    Args:
        cmd: The live PyMOL `cmd` module (or a compatible stand-in).

    Returns:
        The name of the one loaded molecular object.

    Raises:
        TargetResolutionError: If zero or more than one molecular object is
            loaded.
    """
    molecules = tuple(
        name
        for name in cmd.get_names("objects")
        if cmd.get_type(name) == MOLECULE_OBJECT_TYPE
    )
    if not molecules:
        raise TargetResolutionError("no molecular object is loaded")
    if len(molecules) > 1:
        raise TargetResolutionError(
            "more than one molecular object is loaded: "
            f"{', '.join(molecules)} -- load or delete objects so exactly "
            "one remains"
        )
    return molecules[0]


def extract_live_snapshot(
    cmd: PyMOLSession, object_name: str
) -> tuple[ObjectSnapshot, str]:
    """Extract the resolved object's canonical snapshot and its digest.

    Args:
        cmd: The live PyMOL `cmd` module (or a compatible stand-in).
        object_name: The name of the object to extract, as
            `resolve_target_object()` returned it.

    Returns:
        The extracted snapshot and its `pmc_core.snapshot.structure_digest`.
    """
    snapshot = extract(cmd, object_name)
    return snapshot, structure_digest(snapshot)
