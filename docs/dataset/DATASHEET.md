# Datasheet: PyMOL-Copilot dataset split `e4599620801af592`

Rendered from `manifest.json` by `pmc_data.manifest`; do not edit by
hand. Split version 2, built from commit
`9f44e54abd07f88bc46a8a6ed863b1866f147020`.

## Motivation

This split trains and evaluates a small local model that turns a
structural biologist's natural-language intent into a restricted,
verified PyMOL command plan (master plan items 15-17). It exists so
the offline evaluation measures generalization to structures the model
never saw, on intents a person wrote rather than a template.

## Composition

| File | Records | SHA-256 |
| --- | --- | --- |
| train.jsonl | 2389 | `db7cda83228adc05…` |
| test_gold.jsonl | 68 | `82db3e8a55331f5f…` |
| heldout_synthetic.jsonl | 842 | `b648c24c3ed48a7f…` |
| decontam_dropped.jsonl | 68 | `017219df6ee565a1…` |
| excluded.jsonl | 89 | `ae1b9d6a33d54dca…` |

- **`train.jsonl`** -- corpus samples on training structures, after
  decontamination. 120 categories.
- **`test_gold.jsonl`** -- the test split: 68
  hand-reviewed gold items, all on held-out structures, covering every
  supported verb set, verb-term pair and boolean shape.
- **`heldout_synthetic.jsonl`** -- corpus samples on held-out
  structures, with templated intents. A secondary evaluation set:
  structure-held-out, but not intent-held-out.
- **`decontam_dropped.jsonl`** -- training samples removed because their
  intent near-duplicated a gold intent, each with the gold item it
  matched.
- **`excluded.jsonl`** -- corpus samples removed from both sides
  because their plan uses an excluded representation.

Each sample carries its structure identity and checksum, every
contract version, the canonical plan, the prompt as the model sees it,
the assertions evaluated, the assertions that could not be, and the
executor's verification record.

## Collection process

- **Structures** are 24 controlled
  structures authored in code by `pmc_data.structures` at seed
  20260921. No PDB or wwPDB-derived data is included.
- **Training labels** are program-first: `pmc_data.taxonomy` enumerates
  a plan, the oracle in `pmc_data.oracle` predicts its result without
  PyMOL, and the plan is executed by real headless Open-Source PyMOL
  (pymol-open-source-whl==3.2.0.2) in a fresh sidecar. A sample is kept
  only if PyMOL agrees with the oracle.
- **Training intents are templated** from the plan, not written by a
  person or a teacher model.
- **Gold intents** were drafted by `claude-opus-5-5` (68) and
  reviewed and edited by `Martin` (68). Every gold
  reference plan passed the same oracle-and-PyMOL verification.
- Contract versions: card_version=1, executor_version=1, grammar_version=1, policy_version=1, prompt_version=1, protocol_version=1, pymol_version=3.2.0a, snapshot_version=1.

## Preprocessing

- **Split by source structure.** Held out: `altloc_two_residues`, `everything_bonded`, `insertion_codes_two_chains`, `longer_two_chains`, `three_states`, `two_chains_hetatm`. Every
  structural feature appears on both sides. No held-out structure's
  spec, snapshot hash or structure digest appears in training.
- **Excluded representations: `slice`.** 89 corpus
  samples whose plan shows or hides one were removed from training and
  from `heldout_synthetic` alike. Reason: Martin judged the one slice sample in the split version 1 label audit wrong and directed that every slice sample be dropped (2026-09-25).
- **Decontamination** (`entity-gated-token-jaccard`, threshold
  0.5) dropped 68 training
  samples whose intent names the same entities as a gold intent and is
  worded almost the same. Drop counts at other thresholds: 0.30: 79, 0.50: 68, 0.70: 15.
- **Training is decontaminated against gold intents only.** The
  templated intents repeat across structures, so counting the
  held-out templated intents as test intents would drop
  618 of 2457 training
  candidates on exact normalized match alone. `heldout_synthetic` is
  therefore reported as structure-held-out only.

## Label audit

50 training labels were drawn at random (seed 20260923) and judged by claude-opus-5-5, at Martin's request, calibrated to Martin's split version 1 verdicts.

- **Observed error rate: 0/50 = 0.000** (Wilson 95% interval 0.000-0.071), over the 50 labels judged correct or wrong.
- Unsure: 0, reported separately and not counted as either. If every unsure label were wrong, the rate would be 0.000.
- Sheet SHA-256: `2f4807858593b374ad801e30f5fa02ffc8dd224dd4cda021f50568e262b1928e`.

Earlier split versions, superseded by this one and kept in `docs/dataset/history/`:

- Split version 1 (`f6c24e0f8463359c`): 1/50 wrong = 0.020 (Wilson 95% interval 0.004-0.105), judged by Martin.

## Uses

Fine-tuning (item 17) trains on `train.jsonl` only. The offline
evaluation (item 16) reports on `test_gold.jsonl`, with
`heldout_synthetic.jsonl` as a secondary structure-generalization
figure. Neither evaluation file may be used for training, prompt
selection or model selection.

## Distribution and license

- Code: BSD 3-Clause License; Copyright (c) 2026, Martin Urban (LICENSE)
- Structures: authored synthetically in this repository by pmc_data.structures; no PDB or wwPDB-derived data
- PyMOL: pymol-open-source-whl 3.2.0.2, as its wheel metadata states: License: Open-Source PyMOL Copyright Notice (full text recorded in manifest.json)
- Gold intents: written for this repository: drafted by claude-opus-5-5 and reviewed and edited by Martin
- Teacher outputs: none; training intents are templated by pmc_data.taxonomy
- Publication: none planned; SPECIFICATION.md records that no publication is planned for this deliverable

## Maintenance and regeneration

The split is immutable once inspected: changing the held-out set
requires bumping `SPLIT_VERSION`. Regenerate with:

```
bazel run //src/pmc_data:corpus_cli -- --config configs/generation/corpus.json
bazel run //src/pmc_data:gold_cli
bazel run //src/pmc_data:split_cli -- build --corpus data/samples/seed-20260921-5806db370de5
```

Configuration files, by SHA-256:

- `configs/generation/corpus.json`: `7e9648a50ff9e87f4781d712245e68ee60ab7c2581ef70f165e399d2d29c0e65`
- `configs/generation/split.json`: `55c6b1c1a49d1999528daf6454be8f789f23f62921f2b5ca18ecfc4ff0913175`

## Limits

- **Training intents are templated.** A model can learn the templates'
  phrasing; the gold set measures whether it handles anything else.
- **The structures are synthetic and backbone-only.** They share one
  residue vocabulary (ALA, SER, GLY, VAL, LEU, with ZN and HOH), carry
  no side chains, and have no ligand chemistry, so domain words like
  "side chain" or "ligand pocket" cannot be graded.
- **The split is by spec, not by sequence cluster.** It tests
  generalization across feature combinations and coordinates, not to
  new chemistry.
- **Gold intents were drafted by a model** and then reviewed by a
  person, which is weaker independence than intents written from
  scratch by a structural biologist.
