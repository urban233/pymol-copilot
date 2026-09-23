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

The gold set, split and label audit (master plan item 15): the gold
record and its committed items, the held-out split, decontamination,
the manifest and datasheet, and the audit. See "The gold set, split
and audit" below.

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

## The gold set, split and audit

Item 15 turns the corpus into something an evaluation can rest on. Each
claim it makes has a test that has been sabotaged -- the property
broken, the test watched failing, the break reverted.

| Module | What it settles |
| --- | --- |
| `test_gold_set.py` | A gold record round-trips; its category is derived from its own plan, never declared; a reference plan the parser or the policy refuses never becomes a candidate. The committed `gold_items.jsonl` covers every supported verb set, verb-term pair and boolean shape, sits only on held-out structures, and never selects nothing or predicts no change. A gold item the oracle and PyMOL disagree on is an error, not a drop. |
| `test_split.py` | Every structural feature is on both sides of the split, the held-out names exist in the matrix, no structure is on both sides by content, and the held-out set cannot change without a `SPLIT_VERSION` bump. |
| `test_decontam.py` | The near-duplicate rule, pinned by `testdata/near_duplicate_pairs.jsonl`: hand-labelled pairs, each with the reason for its label. |
| `test_split_cli.py` | The split build end to end: no held-out structure reaches training, every corpus sample lands exactly once, and each untrustworthy input -- unreviewed or stale gold, an incomplete corpus, broken lineage, a dirty tree -- is refused. |
| `test_manifest.py` | The validator recomputes every hash and catches a flipped byte or a forged split id; the datasheet states the split's limits. |
| `test_audit.py` | The audit draw is seeded and training-only, a half-filled sheet is refused, `unsure` is never folded into a count, and the Wilson interval matches independently computed values. |

`oracle_executor.py` and `split_fixture.py` are the shared fakes: a
child that agrees with the oracle, one that does not, and a small
synthetic repository the split suites build from. Every sample in it
is produced by the real `verify_sample` on the real structure matrix,
so lineage checks see what a real run records.

### Findings worth knowing before changing any of this

- **Decontaminating against templated held-out intents would gut
  training.** The templates repeat across structures, so counting the
  held-out corpus's intents as test intents dropped 40% of training on
  exact match alone and 72% at a character-shingle similarity of 0.7.
  The gold set is therefore the only test split decontaminated
  against, and `heldout_synthetic` is reported as structure-held-out
  only.
- **Character-shingle similarity cannot treat an entity swap
  consistently.** It scored `chain A` to `chain B` 0.56 on a short
  intent and 0.95 on a long one. The rule compares entities exactly
  and only the remaining words fuzzily.
- **Selection-kind words and negations are entities.** Treated as
  ordinary words, `het atoms` matched `polymer atoms` and `everything
  except chain A` matched `chain A` in the real enumeration.
- **The synthetic structures are backbone-only.** Gold intents avoid
  words like "backbone", "side chain" and "ligand pocket", which would
  select everything or nothing; each non-obvious mapping is recorded in
  the item's `concept` field.

