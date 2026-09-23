# Data tests

Owned by dataset-and-oracle evidence. No parser, policy, or runtime
behavior is exercised here -- those stay owned by `tests/contract`,
`tests/adversarial`, and `tests/integration`.

Two generations of evidence live side by side.

The original chain-A/red fixture (M-01, issue #8): the gold-case
schema, the independent chain-membership oracle, its sabotage check,
and the real-PyMOL suite that grades the one accepted plan.

The generalized dataset pipeline (master plan item 14): the controlled
structure builder, the selection-expression oracle, the sample record,
the plan taxonomy, the per-category report, and the committed
conformance slice.

## Where each claim is settled

The pipeline makes two different kinds of claim, and they are
deliberately not proved in the same place.

*Structural* claims -- that the expression tree is evaluated with the
right precedence, that a record round-trips, that every enumerated plan
satisfies policy -- are settled hermetically, without PyMOL. So is one
claim that is not about a record at all: `test_corpus_cli.py` settles
how a run names its output directory and how it moves a finished
corpus into place, because both ways a corpus is lost -- a name that
does not distinguish it from a different one, and a promotion that
deletes the destination before writing it -- are decided entirely
outside PyMOL, and neither shows up in any sample.

*Claims about Open-Source PyMOL's own behavior* cannot be settled by
more Python, so they are settled against real headless PyMOL:

| Module | What it settles |
| --- | --- |
| `test_structures_real_pymol.py` | Every controlled structure survives reconstruct-then-extract byte for byte. A structure that does not is excluded here rather than poisoning every sample built on it. |
| `test_oracle_real_pymol.py` | The oracle's selection membership and whole-plan predictions match what PyMOL actually does. |
| `test_generate_sample_real_pymol.py` | End-to-end generation through the production execution boundary. |
| `test_conformance_real_pymol.py` | The committed slice still verifies against today's contracts. |

The committed slice is two files, not one. `samples.jsonl` holds what
verified; `rejections.jsonl` holds the deliberately ungradable
attempts -- one naming the polymer flag, one orienting straight at an
expression -- which can never appear in the first because neither is a
sample. A slice carrying only the samples would be evidence that the
happy path still works and no evidence at all that the pipeline still
refuses to grade what it cannot.

## Findings worth knowing before changing any of this

Each cost a failing run to discover, and each is load-bearing.

- **A bare `resi N` is a literal identifier match in PyMOL, not a
  numeric one.** On a structure whose residue 1 carries insertion code
  A, `resi 1` matches no atom at all -- while `resi 1-999` does match
  it. The two forms are different comparisons.
- **Coordinates, occupancy and B-factor must be exact in single
  precision.** PyMOL stores them as C floats, so an authored 0.6
  occupancy comes back changed and fails the executor's byte-based
  fidelity gate. Altloc partners here split occupancy 0.5/0.5.
- **PyMOL does not return bonds in creation order**, and
  `pmc_core.snapshot.diff` sorts bonds before comparing -- so `diff`
  cannot see an ordering difference that byte equality can. Structures
  emit bonds in canonical sorted order.
- **`cmd.count_atoms` counts an atom once, not once per state**, which
  is why the oracle reads membership off the first state alone.

## What the corpus does not claim

Three categories are generated and reported as unsupported rather than
guessed, each because a contract already says so:

- `polymer`, which `pmc_core.snapshot.DECLARED_UNSUPPORTED` already
  places outside the snapshot format;
- `nonbonded`, `slice`, `ellipsoids` and `volume`, legal to emit but
  absent from `MOLECULE_REP_NAMES`, so nothing observable follows;
- `orient`'s effect on the camera, which would mean reimplementing
  PyMOL's principal-axis fit to float equality. An orienting plan is
  still kept and graded on its selection counts.

One further limitation is documented rather than fixed: a structure is
reconstructed from pseudoatoms and has no secondary structure, so
`show cartoon` sets a representation bit while nothing renders. The
snapshot records the bit, and the bit is what is graded.

## A kept sample that could not have failed

A plan can be legal, run cleanly, agree with the oracle, and still
establish almost nothing -- because what the two sides agreed on was
that nothing happened. Hiding a representation no atom is shown in,
showing one they all already carry, coloring atoms the colour they
already are, or grading a selection that matches no atom are all of
this kind: the fidelity gate ends up comparing the structure against
itself, which an oracle that predicted "nothing ever changes" would
also pass.

This was not caught by reading the code. It was found by measuring a
generated corpus: at one point 88% of the `hide` category and 22% of
the whole corpus were of this kind, and the 0% rejection rate for
`hide` was therefore measuring almost nothing. Two defences now stand:

- `tests/data/test_taxonomy.py` asserts that no enumerated expression
  matches nothing, and that the only plans predicting no observable
  change are the one deliberate inert `hide` per structure and the
  deliberately unobservable representations, which carry their own
  marker.
- `pmc_data.report` counts such samples per category in `no_op`,
  `empty_selection` and `vacuous`, alongside a `substantive` count.
  Deriving them from fields every sample already records means an
  older corpus can be measured for this too, without regenerating it.

Both are needed. The first keeps the corpus honest; the second keeps
it honest about itself if the first is ever weakened.
