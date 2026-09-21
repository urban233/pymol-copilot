# Copyright 2026 PyMOL Copilot contributors.
"""Controlled structures, authored directly as canonical snapshots.

The dataset needs structures covering multiple chains, hetero atoms,
multiple states and alternate locations (master plan item 14). They are
authored here as `pmc_core.snapshot.ObjectSnapshot` values rather than as
PDB files, for three reasons: the executor consumes a snapshot anyway, so
a file would only be converted into one through PyMOL; authoring the
value directly gives exact control over every field the oracle predicts;
and it keeps the oracle's input pure data that PyMOL never produced.

Every field value here is chosen so a structure survives
reconstruct-then-extract unchanged, because the oracle predicts against
the snapshot it was handed while PyMOL runs against the object
`pmc_core.snapshot.reconstruct` builds from it. Two constraints follow,
both discovered from existing round-trip evidence rather than assumed:

- **Coordinates, occupancies and B-factors are multiples of 0.5.** PyMOL
  stores them as C floats, so a value that is not exactly representable
  in single precision comes back changed and every sample built on that
  structure would fail the executor's fidelity gate. The existing
  fixture `tests/integration/testdata/h02_full_v1_fixture.pdb` uses
  occupancies 0.6/0.4 and its own round-trip test compares them with
  `pytest.approx`; a byte-exact pipeline cannot do that, so altloc
  partners here split occupancy 0.5/0.5 instead.
- **`view` and `settings` use values proven to round-trip.** The view
  below is the one
  `tests/integration/test_snapshot_round_trip.py` already asserts
  survives a fresh process, and settings are written in the five-decimal
  form `cmd.get` returns.

`tests/data/test_structures_real_pymol.py` is the admission gate: a spec
whose built snapshot is not a fixed point of reconstruct-then-extract is
excluded there rather than silently poisoning every sample built on it.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import itertools
import random
from dataclasses import dataclass

from pmc_core.snapshot import SNAPSHOT_VERSION
from pmc_core.snapshot import AtomRecord
from pmc_core.snapshot import BondRecord
from pmc_core.snapshot import DECLARED_UNSUPPORTED
from pmc_core.snapshot import ObjectSnapshot
from pmc_core.snapshot import StateSnapshot
from pmc_data.colors import COLOR_INDEX_BY_NAME

#: The object name every controlled structure carries.
OBJECT_NAME = "pmc_structure"

#: The camera `tests/integration/test_snapshot_round_trip.py` already
#: proves survives a reconstruct-extract cycle through a fresh process.
#: Every value is exactly representable in single precision.
DEFAULT_VIEW: tuple[float, ...] = (
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

#: Object-scope settings, in the five-decimal form `cmd.get` returns.
DEFAULT_SETTINGS: tuple[tuple[str, str], ...] = (
    ("sphere_scale", "0.35000"),
    ("cartoon_transparency", "0.25000"),
)

#: Chain identifiers drawn on in order. Upper case, matching real PDB
#: practice and `pmc_core.plan.ChainTerm`'s case-sensitive accepted form.
CHAIN_IDS = ("A", "B", "C", "D")

#: Residue names cycled through for polymer residues. All three-letter
#: standard amino acids, so `resn` terms have something real to match.
RESIDUE_NAMES = ("ALA", "SER", "GLY", "VAL", "LEU")

#: The backbone atoms every polymer residue carries. No primed names --
#: `pmc_core.plan.NameTerm` accepts `[A-Z0-9]` only, and the parser's
#: quoting rule denies the apostrophe in nucleic-acid style names.
BACKBONE_ATOM_NAMES = ("N", "CA", "C", "O")

#: The element each backbone atom reports.
_ELEMENT_BY_ATOM_NAME = {"N": "N", "CA": "C", "C": "C", "O": "O"}

#: The hetero residues appended after a chain's polymer residues.
_HETERO_RESIDUES = (("ZN", "ZN", "ZN"), ("HOH", "O", "O"))

#: Where hetero residue numbering starts, clear of any polymer residue.
_HETERO_FIRST_RESV = 901

#: The representation polymer atoms start in, and the one hetero atoms
#: start in. Both are in `pmc_core.snapshot.MOLECULE_REP_NAMES`, so both
#: are observable -- a structure whose atoms started in a representation
#: the snapshot cannot see would make `hide` unverifiable.
_POLYMER_REP = "lines"
_HETERO_REP = "spheres"

#: The color polymer and hetero atoms start in. Any valid index works;
#: these two differ so a `color` command has something to change.
_POLYMER_COLOR = COLOR_INDEX_BY_NAME["green"]
_HETERO_COLOR = COLOR_INDEX_BY_NAME["yellow"]


@dataclass(frozen=True)
class StructureSpec:
    """One controlled structure's declared shape.

    Attributes:
        spec_id: The stable identity of this spec.
        seed: The seed every coordinate in the structure derives from.
        chain_count: How many polymer chains to build, at most four.
        residues_per_chain: Polymer residues per chain.
        hetero_residues: How many hetero residues to append, at most two.
        state_count: How many coordinate states to build.
        altloc_residues: How many residues carry an alternate-location
            pair, added to the first chain.
        insertion_residues: How many residues per chain carry an
            insertion code.
        with_bonds: Whether to declare backbone bonds.
    """

    spec_id: str
    seed: int
    chain_count: int
    residues_per_chain: int
    hetero_residues: int
    state_count: int
    altloc_residues: int
    insertion_residues: int
    with_bonds: bool


def _half(value: float) -> float:
    """Quantize a coordinate to the nearest half unit.

    PyMOL stores coordinates as C floats. Quantizing to halves keeps
    every authored value exactly representable in single precision, so
    a coordinate survives reconstruct-then-extract byte for byte.

    Args:
        value: The unquantized value.

    Returns:
        The nearest multiple of 0.5.
    """
    return round(value * 2.0) / 2.0


@dataclass(frozen=True)
class _AtomPlan:
    """One atom's identity, before coordinates are drawn per state.

    Attributes:
        chain: The chain identifier.
        resv: The integer residue number.
        ins_code: The insertion code, or "" when absent.
        resn: The residue name.
        name: The atom name.
        alt: The alternate location indicator, or "".
        elem: The element symbol.
        hetatm: Whether this atom is a hetero atom.
        q: The occupancy.
    """

    chain: str
    resv: int
    ins_code: str
    resn: str
    name: str
    alt: str
    elem: str
    hetatm: bool
    q: float


def _atom_plans(spec: StructureSpec) -> tuple[_AtomPlan, ...]:
    """Lay out every atom's identity in PyMOL's own sort order.

    Atoms are emitted chain-major, then by residue number, then by
    insertion code, then in backbone order, then by alternate location.
    That is the order PyMOL itself keeps atoms in, so a reconstruction
    that sorts cannot reorder them away from the authored snapshot.

    Args:
        spec: The structure spec being laid out.

    Returns:
        The ordered atom identities.
    """
    plans: list[_AtomPlan] = []
    for chain_index in range(spec.chain_count):
        chain = CHAIN_IDS[chain_index]
        for residue_index in range(spec.residues_per_chain):
            resv = residue_index + 1
            resn = RESIDUE_NAMES[residue_index % len(RESIDUE_NAMES)]
            ins_code = "A" if residue_index < spec.insertion_residues else ""
            for atom_name in BACKBONE_ATOM_NAMES:
                plans.append(
                    _AtomPlan(
                        chain=chain,
                        resv=resv,
                        ins_code=ins_code,
                        resn=resn,
                        name=atom_name,
                        alt="",
                        elem=_ELEMENT_BY_ATOM_NAME[atom_name],
                        hetatm=False,
                        q=1.0,
                    )
                )
            carries_altloc = (
                chain_index == 0 and residue_index < spec.altloc_residues
            )
            if carries_altloc:
                for alt in ("A", "B"):
                    plans.append(
                        _AtomPlan(
                            chain=chain,
                            resv=resv,
                            ins_code=ins_code,
                            resn=resn,
                            name="CB",
                            alt=alt,
                            # Half each, not the 0.6/0.4 a real PDB
                            # would carry: see the module docstring on
                            # single-precision round-tripping.
                            elem="C",
                            hetatm=False,
                            q=0.5,
                        )
                    )
        for hetero_index in range(spec.hetero_residues):
            resn, atom_name, element = _HETERO_RESIDUES[hetero_index]
            plans.append(
                _AtomPlan(
                    chain=chain,
                    resv=_HETERO_FIRST_RESV + hetero_index,
                    ins_code="",
                    resn=resn,
                    name=atom_name,
                    alt="",
                    elem=element,
                    hetatm=True,
                    q=1.0,
                )
            )
    return tuple(plans)


def _backbone_bonds(plans: tuple[_AtomPlan, ...]) -> tuple[BondRecord, ...]:
    """Bond each polymer residue's backbone, and consecutive residues.

    Args:
        plans: The ordered atom identities.

    Returns:
        The declared bonds, addressed by position in the first state.
    """
    position_by_key: dict[tuple[str, int, str, str, str], int] = {
        (plan.chain, plan.resv, plan.ins_code, plan.name, plan.alt): index
        for index, plan in enumerate(plans)
    }
    bonds: list[BondRecord] = []

    def link(
        first: tuple[str, int, str, str, str],
        second: tuple[str, int, str, str, str],
    ) -> None:
        """Declare one single bond when both atoms exist.

        Args:
            first: The first atom's lookup key.
            second: The second atom's lookup key.
        """
        a = position_by_key.get(first)
        b = position_by_key.get(second)
        if a is not None and b is not None:
            bonds.append(BondRecord(atom_index_a=a, atom_index_b=b, order=1))

    residues = []
    seen: set[tuple[str, int, str]] = set()
    for plan in plans:
        if plan.hetatm:
            continue
        key = (plan.chain, plan.resv, plan.ins_code)
        if key not in seen:
            seen.add(key)
            residues.append(key)

    for chain, resv, ins_code in residues:
        link(
            (chain, resv, ins_code, "N", ""),
            (chain, resv, ins_code, "CA", ""),
        )
        link(
            (chain, resv, ins_code, "CA", ""),
            (chain, resv, ins_code, "C", ""),
        )
        link(
            (chain, resv, ins_code, "C", ""),
            (chain, resv, ins_code, "O", ""),
        )

    for previous, following in itertools.pairwise(residues):
        if previous[0] != following[0]:
            continue
        link(
            (previous[0], previous[1], previous[2], "C", ""),
            (following[0], following[1], following[2], "N", ""),
        )
    # Sorted by atom position, not left in creation order. The executor's
    # fidelity gate compares to_json bytes, and PyMOL does not hand bonds
    # back in the order cmd.bond created them -- pmc_core.snapshot.diff
    # sorts before comparing, so it cannot see the difference, but byte
    # equality can. Emitting a canonical order is what makes a bonded
    # structure a fixed point at all.
    return tuple(
        sorted(
            bonds,
            key=lambda bond: (
                bond.atom_index_a,
                bond.atom_index_b,
                bond.order,
            ),
        )
    )


def build_structure(spec: StructureSpec) -> ObjectSnapshot:
    """Build one controlled structure as a canonical snapshot.

    Never imports PyMOL and never reads a structure file: the returned
    value is the oracle's input, authored outright.

    Args:
        spec: The structure spec to build.

    Returns:
        The built snapshot, ready to serialize for the executor.

    Raises:
        ValueError: If the spec asks for more chains or hetero residues
            than this module defines, or for no atoms at all.
    """
    if not 1 <= spec.chain_count <= len(CHAIN_IDS):
        raise ValueError(f"unsupported chain count: {spec.chain_count}")
    if not 0 <= spec.hetero_residues <= len(_HETERO_RESIDUES):
        raise ValueError(
            f"unsupported hetero residue count: {spec.hetero_residues}"
        )
    if spec.state_count < 1:
        raise ValueError(f"unsupported state count: {spec.state_count}")

    plans = _atom_plans(spec)
    if not plans:
        raise ValueError(f"{spec.spec_id!r}: spec builds no atoms")

    rng = random.Random(spec.seed)
    states: list[StateSnapshot] = []
    for state_number in range(spec.state_count):
        atoms: list[AtomRecord] = []
        for serial, plan in enumerate(plans, start=1):
            atoms.append(
                AtomRecord(
                    serial=serial,
                    name=plan.name,
                    alt=plan.alt,
                    resn=plan.resn,
                    chain=plan.chain,
                    resv=plan.resv,
                    ins_code=plan.ins_code,
                    elem=plan.elem,
                    hetatm=plan.hetatm,
                    q=plan.q,
                    b=20.0,
                    color=_HETERO_COLOR if plan.hetatm else _POLYMER_COLOR,
                    reps=(_HETERO_REP,) if plan.hetatm else (_POLYMER_REP,),
                    label=None,
                    coord=(
                        _half(rng.uniform(-30.0, 30.0)),
                        _half(rng.uniform(-30.0, 30.0)),
                        _half(rng.uniform(-30.0, 30.0) + state_number),
                    ),
                )
            )
        states.append(StateSnapshot(atoms=tuple(atoms)))

    return ObjectSnapshot(
        schema_version=SNAPSHOT_VERSION,
        name=OBJECT_NAME,
        enabled=True,
        states=tuple(states),
        bonds=_backbone_bonds(plans) if spec.with_bonds else (),
        view=DEFAULT_VIEW,
        settings=DEFAULT_SETTINGS,
        unsupported=DECLARED_UNSUPPORTED,
    )


def enumerate_structures(seed: int) -> tuple[StructureSpec, ...]:
    """Return the standing structure matrix the corpus is built from.

    The matrix is deliberately small and explicit rather than a full
    cross product: every declared feature -- several chains, hetero
    atoms, several states, alternate locations, insertion codes and
    bonds -- appears both on its own and combined with the others, which
    is what makes a per-feature rejection rate readable.

    Args:
        seed: The base seed; each spec derives its own from it.

    Returns:
        The ordered structure specs.
    """
    specs: list[StructureSpec] = []
    index = 0

    def add(
        label: str,
        *,
        chain_count: int = 1,
        residues_per_chain: int = 4,
        hetero_residues: int = 0,
        state_count: int = 1,
        altloc_residues: int = 0,
        insertion_residues: int = 0,
        with_bonds: bool = False,
    ) -> None:
        """Append one spec to the matrix with a derived seed.

        Args:
            label: The spec's descriptive identity.
            chain_count: Polymer chains to build.
            residues_per_chain: Polymer residues per chain.
            hetero_residues: Hetero residues appended per chain.
            state_count: Coordinate states to build.
            altloc_residues: Residues carrying an altloc pair.
            insertion_residues: Residues carrying an insertion code.
            with_bonds: Whether to declare backbone bonds.
        """
        nonlocal index
        specs.append(
            StructureSpec(
                spec_id=label,
                seed=seed + index,
                chain_count=chain_count,
                residues_per_chain=residues_per_chain,
                hetero_residues=hetero_residues,
                state_count=state_count,
                altloc_residues=altloc_residues,
                insertion_residues=insertion_residues,
                with_bonds=with_bonds,
            )
        )
        index += 1

    add("minimal_single_chain")
    add("two_chains", chain_count=2)
    add("three_chains", chain_count=3)
    add("four_chains", chain_count=4)
    add("single_chain_hetatm", hetero_residues=1)
    add("two_chains_hetatm", chain_count=2, hetero_residues=2)
    add("two_states", state_count=2)
    add("three_states", state_count=3)
    add("altloc_pair", altloc_residues=1)
    add("altloc_two_residues", altloc_residues=2)
    add("insertion_codes", insertion_residues=1)
    add("insertion_codes_two_chains", chain_count=2, insertion_residues=2)
    add("bonded_backbone", with_bonds=True)
    add("bonded_two_chains", chain_count=2, with_bonds=True)
    add("longer_chain", residues_per_chain=8)
    add("longer_two_chains", chain_count=2, residues_per_chain=6)
    add(
        "hetatm_and_states",
        chain_count=2,
        hetero_residues=2,
        state_count=2,
    )
    add("altloc_and_hetatm", hetero_residues=1, altloc_residues=1)
    add(
        "altloc_and_states",
        state_count=2,
        altloc_residues=1,
    )
    add(
        "insertion_and_hetatm",
        hetero_residues=1,
        insertion_residues=1,
    )
    add(
        "everything_small",
        chain_count=2,
        residues_per_chain=4,
        hetero_residues=2,
        state_count=2,
        altloc_residues=1,
        insertion_residues=1,
    )
    add(
        "everything_bonded",
        chain_count=2,
        residues_per_chain=4,
        hetero_residues=2,
        state_count=2,
        altloc_residues=1,
        insertion_residues=1,
        with_bonds=True,
    )
    add(
        "everything_three_chains",
        chain_count=3,
        residues_per_chain=5,
        hetero_residues=2,
        state_count=3,
        altloc_residues=2,
        insertion_residues=1,
    )
    add(
        "everything_four_chains",
        chain_count=4,
        residues_per_chain=6,
        hetero_residues=2,
        state_count=2,
        altloc_residues=1,
        insertion_residues=2,
    )
    return tuple(specs)
