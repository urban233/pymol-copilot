# Copyright 2026 PyMOL Copilot contributors.
"""H-02 discovery: the candidate-agnostic differential harness.

Slice 1 (`test_full_v1_snapshot_candidate_a.py`) proved the round-trip
method against candidate A (canonical structured data) alone, and defined
every piece of that method that does not depend on *how* a candidate got
its live PyMOL state onto disk and back: the canonical structured-data
extraction format itself (`ObjectSnapshot` and its nested dataclasses), the
`extract()` query that reads it out of a live PyMOL session, the JSON
round trip used to carry an extracted snapshot across a process boundary,
the field-by-field `_diff()` comparison, the shared fixture (`real_pymol`/
`loaded_fixture`), and the nested-subprocess-via-environment-variable
technique that spawns a genuinely fresh second PyMOL process reading only
whatever a path-bearing environment variable points it at -- never the
original source fixture file. Slice 2 factors all of that out here so
candidates B and C reuse it unchanged instead of duplicating it.

`to_json`/`from_json` were not separately named in slice 1's own module
docstring, but they move here too: every candidate needs the same
mechanism to hand its "expected" extraction across a process boundary for
the nested process to diff against (the reconstruction *input* differs per
candidate -- a snapshot for A, an exported file plus manifest for B, a
session file for C -- but the diff's *expected side* is always one of
these same JSON-encoded `ObjectSnapshot`s). Keeping that logic in one place
is exactly what avoids duplicating it three times over.

Candidate-specific pieces stay out of this module on purpose: candidate
A's own `reconstruct()` (object-construction API), and each candidate's own
manifest/export format and env-var names, since those really are what each
candidate uniquely contributes to this comparison.
"""

from __future__ import annotations

import dataclasses
import json
import os
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import asdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

FIXTURE_PATH = (
    Path(__file__).resolve().parent / "testdata" / "h02_full_v1_fixture.pdb"
)

#: PyMOL's named representations, in the order `cmd.count_atoms(f"rep {x}")`
#: is queried -- there is no documented Python-level bit layout for the raw
#: per-atom `reps` integer, so extraction records membership by name instead.
REP_NAMES = (
    "lines",
    "sticks",
    "spheres",
    "dots",
    "surface",
    "mesh",
    "nonbonded",
    "nb_spheres",
    "cartoon",
    "ribbon",
    "labels",
    "slice",
    "ellipsoids",
    "volume",
)

#: The bounded set of "safe" display settings this prototype exercises at
#: object scope. Not exhaustive -- H-02's contract-freeze checkpoint decides
#: the real accepted set; this proves the get/set/reconstruct path for a
#: representative non-view, non-atom-level setting.
SAFE_SETTINGS = ("sphere_scale", "cartoon_transparency")

#: This differential harness's own schema version for the canonical
#: extraction format below (`ObjectSnapshot` and its JSON encoding) -- not a
#: production `StructureSnapshotV1` contract, and not any one candidate's
#: own export or manifest format version (candidate B's manifest, for
#: example, carries its own independent schema version).
SNAPSHOT_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class AtomRecord:
    """One atom's full-V1 relevant state, as the harness represents it.

    Attributes:
        serial: The atom's stable serial number (PyMOL's uppercase `ID`).
        name: The atom name.
        alt: The alternate location indicator, or "" when not altloc-bearing.
        resn: The residue name.
        chain: The chain identifier.
        resv: The integer residue number, with any insertion code excluded.
        ins_code: The insertion code, or "" when absent.
        elem: The element symbol.
        hetatm: Whether PyMOL classifies this atom as HETATM.
        q: The occupancy.
        b: The temperature factor.
        color: The PyMOL color index.
        reps: The names of every representation this atom is shown in.
        label: The atom label text, or None when it is not labeled.
        coord: The (x, y, z) coordinate for this state.
    """

    serial: int
    name: str
    alt: str
    resn: str
    chain: str
    resv: int
    ins_code: str
    elem: str
    hetatm: bool
    q: float
    b: float
    color: int
    reps: tuple[str, ...]
    label: str | None
    coord: tuple[float, float, float]


@dataclass(frozen=True)
class BondRecord:
    """One bond between two atoms, addressed by their position in a state.

    Attributes:
        atom_index_a: The zero-based position of the bond's first atom.
        atom_index_b: The zero-based position of the bond's second atom.
        order: The bond order.
    """

    atom_index_a: int
    atom_index_b: int
    order: int


@dataclass(frozen=True)
class StateSnapshot:
    """The atoms present in one coordinate state.

    Attributes:
        atoms: The atoms in this state, in a fixed, comparable order.
    """

    atoms: tuple[AtomRecord, ...]


@dataclass(frozen=True)
class ObjectSnapshot:
    """A canonical structured snapshot of one live PyMOL object.

    Attributes:
        schema_version: This harness's shared extraction schema version; not
            a production StructureSnapshotV1 contract.
        name: The object's name.
        enabled: Whether the object is enabled in the PyMOL session.
        states: Every coordinate state, in order.
        bonds: Every bond, addressed by first-state atom position.
        view: The camera view, as `cmd.get_view()` returns it.
        settings: The (setting name, value) pairs this candidate tracks.
    """

    schema_version: int
    name: str
    enabled: bool
    states: tuple[StateSnapshot, ...]
    bonds: tuple[BondRecord, ...]
    view: tuple[float, ...]
    settings: tuple[tuple[str, str], ...]


def extract(cmd: Any, object_name: str) -> ObjectSnapshot:
    """Extract a canonical structured snapshot of one live PyMOL object.

    This is the candidate-agnostic extraction every candidate is diffed
    with: it only ever queries live PyMOL state through ordinary query APIs
    (`iterate`/`get_model`/`get_view`/`get`), regardless of whether that
    live state was built by candidate A's object-construction API,
    candidate B's PDB-plus-manifest reconstruction, or candidate C's
    session load.

    Args:
        cmd: The real PyMOL cmd module.
        object_name: Name of the loaded object to extract.

    Returns:
        The extracted canonical snapshot.
    """
    n_states = cmd.count_states(object_name)
    states: list[StateSnapshot] = []
    for state in range(1, n_states + 1):
        model = cmd.get_model(object_name, state=state)
        colors: list[int] = []
        labels: list[str | None] = []
        cmd.iterate(
            object_name,
            "colors.append(color); labels.append(label)",
            space={"colors": colors, "labels": labels},
        )
        # Per-atom membership in each named representation, keyed by ID
        # (stable regardless of atom-array order) rather than position.
        reps_by_id: dict[int, list[str]] = {}
        for rep_name in REP_NAMES:
            ids: list[int] = []
            cmd.iterate(
                f"{object_name} and rep {rep_name}",
                "ids.append(ID)",
                space={"ids": ids},
            )
            for atom_id in ids:
                reps_by_id.setdefault(atom_id, []).append(rep_name)

        atoms: list[AtomRecord] = []
        for index, atom in enumerate(model.atom):
            atoms.append(
                AtomRecord(
                    serial=atom.id,
                    name=atom.name,
                    alt=atom.alt,
                    resn=atom.resn,
                    chain=atom.chain,
                    resv=atom.resi_number,
                    ins_code=atom.ins_code,
                    elem=atom.symbol,
                    hetatm=bool(atom.hetatm),
                    q=atom.q,
                    b=atom.b,
                    color=colors[index],
                    reps=tuple(reps_by_id.get(atom.id, [])),
                    label=labels[index] or None,
                    coord=tuple(atom.coord),
                )
            )
        states.append(StateSnapshot(atoms=tuple(atoms)))

    model = cmd.get_model(object_name, state=1)
    bonds = tuple(
        BondRecord(
            atom_index_a=bond.index[0],
            atom_index_b=bond.index[1],
            order=bond.order,
        )
        for bond in model.bond
    )
    view = tuple(cmd.get_view())
    settings = tuple(
        (setting, cmd.get(setting, object_name)) for setting in SAFE_SETTINGS
    )

    return ObjectSnapshot(
        schema_version=SNAPSHOT_SCHEMA_VERSION,
        name=object_name,
        enabled=object_name in cmd.get_names("objects", enabled_only=1),
        states=tuple(states),
        bonds=bonds,
        view=view,
        settings=settings,
    )


def to_json(snapshot: ObjectSnapshot) -> str:
    """Serialize a canonical snapshot to JSON for cross-process comparison.

    Args:
        snapshot: The snapshot to serialize.

    Returns:
        The compact JSON text.
    """
    return json.dumps(asdict(snapshot))


def _atom_record_from_json(data: dict[str, Any]) -> AtomRecord:
    """Deserialize one atom record from its JSON object.

    Args:
        data: The JSON object for one atom, as to_json wrote it.

    Returns:
        The reconstructed AtomRecord.
    """
    return AtomRecord(
        serial=data["serial"],
        name=data["name"],
        alt=data["alt"],
        resn=data["resn"],
        chain=data["chain"],
        resv=data["resv"],
        ins_code=data["ins_code"],
        elem=data["elem"],
        hetatm=data["hetatm"],
        q=data["q"],
        b=data["b"],
        color=data["color"],
        reps=tuple(data["reps"]),
        label=data["label"],
        coord=tuple(data["coord"]),
    )


def from_json(text: str) -> ObjectSnapshot:
    """Deserialize a canonical snapshot from JSON.

    Args:
        text: JSON text produced by to_json.

    Returns:
        The reconstructed ObjectSnapshot dataclass tree.

    Raises:
        ValueError: If the JSON's schema_version does not match this
            harness's SNAPSHOT_SCHEMA_VERSION.
    """
    data = json.loads(text)
    if data.get("schema_version") != SNAPSHOT_SCHEMA_VERSION:
        raise ValueError(
            "unsupported snapshot schema version: "
            f"{data.get('schema_version')!r}; "
            f"expected {SNAPSHOT_SCHEMA_VERSION}"
        )
    return ObjectSnapshot(
        schema_version=data["schema_version"],
        name=data["name"],
        enabled=data["enabled"],
        states=tuple(
            StateSnapshot(
                atoms=tuple(_atom_record_from_json(a) for a in state["atoms"])
            )
            for state in data["states"]
        ),
        bonds=tuple(
            BondRecord(
                atom_index_a=b["atom_index_a"],
                atom_index_b=b["atom_index_b"],
                order=b["order"],
            )
            for b in data["bonds"]
        ),
        view=tuple(data["view"]),
        settings=tuple((s, v) for s, v in data["settings"]),
    )


def _diff(expected: ObjectSnapshot, actual: ObjectSnapshot) -> list[str]:
    """Compare two snapshots field by field.

    Args:
        expected: The snapshot taken before reconstruction.
        actual: The snapshot re-extracted after reconstruction.

    Returns:
        A human-readable mismatch for every field that differs; empty when
        the snapshots match exactly.
    """
    mismatches: list[str] = []

    if expected.schema_version != actual.schema_version:
        mismatches.append(
            "schema_version expected="
            f"{expected.schema_version!r} actual={actual.schema_version!r}"
        )
    if expected.name != actual.name:
        mismatches.append(
            f"object.name expected={expected.name!r} actual={actual.name!r}"
        )
    if expected.enabled != actual.enabled:
        mismatches.append(
            f"object.enabled expected={expected.enabled!r} "
            f"actual={actual.enabled!r}"
        )

    def compare_atom(
        label: str, exp_atom: AtomRecord, act_atom: AtomRecord
    ) -> None:
        for field in dataclasses.fields(AtomRecord):
            e = getattr(exp_atom, field.name)
            a = getattr(act_atom, field.name)
            if field.name == "coord":
                if not all(
                    abs(x - y) < 1e-3 for x, y in zip(e, a, strict=True)
                ):
                    mismatches.append(f"{label}.coord expected={e} actual={a}")
                continue
            if e != a:
                mismatches.append(
                    f"{label}.{field.name} expected={e!r} actual={a!r}"
                )

    if len(expected.states) != len(actual.states):
        mismatches.append(
            f"n_states expected={len(expected.states)} "
            f"actual={len(actual.states)}"
        )
    else:
        for s_idx, (exp_state, act_state) in enumerate(
            zip(expected.states, actual.states, strict=True)
        ):
            if len(exp_state.atoms) != len(act_state.atoms):
                mismatches.append(
                    f"state{s_idx}.n_atoms expected={len(exp_state.atoms)} "
                    f"actual={len(act_state.atoms)}"
                )
                continue
            for a_idx, (exp_atom, act_atom) in enumerate(
                zip(exp_state.atoms, act_state.atoms, strict=True)
            ):
                compare_atom(f"state{s_idx}.atom{a_idx}", exp_atom, act_atom)

    expected_bonds = sorted(
        (b.atom_index_a, b.atom_index_b, b.order) for b in expected.bonds
    )
    actual_bonds = sorted(
        (b.atom_index_a, b.atom_index_b, b.order) for b in actual.bonds
    )
    if expected_bonds != actual_bonds:
        mismatches.append(
            f"bonds expected={expected_bonds} actual={actual_bonds}"
        )

    if not all(
        abs(x - y) < 1e-3
        for x, y in zip(expected.view, actual.view, strict=True)
    ):
        mismatches.append(f"view expected={expected.view} actual={actual.view}")

    if expected.settings != actual.settings:
        mismatches.append(
            f"settings expected={expected.settings} actual={actual.settings}"
        )

    return mismatches


#: The nested child's own entire program, passed via `python -c`. Runs
#: pytest in-process exactly like each candidate module's own `__main__`
#: block does (`pytest.main()`, flush, `os._exit(code)`), instead of
#: `python -m pytest`, which runs the file as a module through pytest's own
#: runner and never reaches a `__main__` block -- see
#: run_nested_snapshot_process's docstring for why that distinction is not
#: cosmetic. `sys.argv[1]`/`sys.argv[2]` are the test file and `-k` filter,
#: appended after this source string in the child's argv.
_NESTED_RUNNER_SOURCE = (
    "import os, sys, pytest\n"
    "code = pytest.main([sys.argv[1], '-k', sys.argv[2], '-q'])\n"
    "sys.stdout.flush()\n"
    "sys.stderr.flush()\n"
    "os._exit(code)\n"
)


def run_nested_snapshot_process(
    test_file: Path | str,
    test_name_filter: str,
    env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    """Spawn a genuinely fresh nested pytest process for a round-trip test.

    This is the nested-subprocess-via-environment-variable technique every
    candidate's fresh-process round-trip test uses: run
    `pytest <test_file> -k <test_name_filter>` in a brand-new subprocess
    that inherits the current environment plus `env` -- the only channel
    this pattern uses to tell the nested process what to reconstruct (a
    snapshot JSON path for candidate A, an exported file and manifest path
    for candidate B, a session file path for candidate C). The nested
    process never receives the parent's live PyMOL objects directly, and
    never opens the original source fixture file; it only ever reads
    whatever `env` points it at.

    The child runs `python -c <_NESTED_RUNNER_SOURCE>` rather than
    `python -m pytest` on purpose. Real PyMOL's headless shutdown can
    complete after pytest's own process would otherwise exit, overriding a
    genuine failure's exit code with 0 -- the same defect every candidate
    module's own `__main__` block documents and works around by calling
    `os._exit` immediately after `pytest.main()` returns, once stdout and
    stderr are flushed. `python -m pytest` imports the file as a module and
    runs pytest's own runner directly, so it never reaches that `__main__`
    block and the workaround never applies to the child -- confirmed
    empirically: an unconditional `raise AssertionError` substituted into a
    nested test still produced a zero exit code through `-m pytest`.
    `_NESTED_RUNNER_SOURCE` reproduces the exact same
    `pytest.main()` -> flush -> `os._exit()` sequence directly as the
    child's whole program, so this function's caller observes the child's
    real result.

    Args:
        test_file: The test module to re-invoke (normally the caller's own
            `__file__`), so the nested process re-collects that same
            module and can select just its own reconstruction test.
        test_name_filter: A `pytest -k` expression selecting only the
            nested reconstruction test, so the parent invocation's own
            tests are not re-run recursively inside the child.
        env: Extra environment variables the nested process reads to learn
            what to reconstruct from.

    Returns:
        The completed nested pytest subprocess, with captured stdout and
        stderr for the caller to report on failure.
    """
    environment = os.environ.copy()
    environment.update(env)
    return subprocess.run(
        [
            sys.executable,
            "-c",
            _NESTED_RUNNER_SOURCE,
            str(test_file),
            test_name_filter,
        ],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture(scope="module")
def real_pymol() -> Iterator[Any]:
    """Launch real headless PyMOL exactly once for this test module.

    Yields:
        The real PyMOL cmd module.
    """
    import pymol  # pyrefly: ignore.
    from pymol import cmd  # pyrefly: ignore.

    pymol.finish_launching(["pymol", "-qc"])
    try:
        yield cmd
    finally:
        cmd.do("quit")


@pytest.fixture
def loaded_fixture(real_pymol: Any) -> Iterator[Any]:
    """Load the full-V1 discovery fixture fresh for one test and delete it.

    Args:
        real_pymol: The real PyMOL cmd module.

    Yields:
        The real PyMOL cmd module with the fixture object loaded.
    """
    real_pymol.load(str(FIXTURE_PATH), "fx")
    real_pymol.color("red", "fx and chain A")
    real_pymol.show("sticks", "fx")
    real_pymol.show("spheres", "fx and resn ZN")
    real_pymol.label("fx and name CA", "name")
    real_pymol.set_view(
        (
            1.0,
            0.0,
            0.0,
            0.0,
            1.0,
            0.0,
            0.0,
            0.0,
            1.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            -0.5,
            0.5,
            -20.0,
        )
    )
    real_pymol.set("sphere_scale", "0.35", "fx")
    real_pymol.set("cartoon_transparency", "0.25", "fx")
    real_pymol.disable("fx")
    real_pymol.sync()
    try:
        yield real_pymol
    finally:
        real_pymol.delete("fx")
