# Gold set, split, audit

## Context

This is item 15 of [docs/master_plan.md](docs/master_plan.md): Martin's item,
sized at about 3 days, and it blocks items 16, 17 and 18. The master plan on
local `main` still lists item 15 as blocked, but that copy is **64 commits
behind `origin/main`**. Item 14 (dataset generation) has already merged as
PR #45. This plan is written against `origin/main` at `4f3d91a`. **Run
`git pull` before implementing.**

Item 14 left the following in place (read from `origin/main`):

- `pmc_data.structures.enumerate_structures(seed)` returns **24 synthetic
  specs**. They are `ObjectSnapshot`s authored in code, with no PDB data. They
  share one small vocabulary: chains A to D, residues ALA/SER/GLY/VAL/LEU,
  backbone atoms N/CA/C/O only, and hetero residues ZN and HOH.
- `pmc_data.taxonomy.enumerate_plans` produces 11,274 attempts. `categorize()`
  derives **149 categories** from each plan's shape, in the form
  `<verbs>/<terms>/<shape>`. Of these, 108 are fully fingerprint-graded,
  about 15 `orient+select` categories are graded on selection counts only,
  and the polymer and direct-`orient` categories are unsupported. Intents
  come from templates (`"Color chain A red."`), and only 6,326 of them are
  unique.
- `pmc_data.generate.verify_sample(snapshot, spec, candidate, sample_id=…,
  executor=…)` returns `Sample | Rejection`. It grades a plan with the oracle
  and the real executor. This is the machinery the gold set reuses.
- `pmc_data.sample`: `Sample`, `read_samples`, `write_samples`,
  `current_versions`, `StructureIdentity` (which carries `spec_id`,
  `snapshot_sha256` and `structure_digest`).
- `pmc_data.corpus_cli` writes `data/samples/seed-<seed>-<id>/{samples.jsonl,
  rejections.jsonl, report.json}`. `configs/generation/corpus.json` sets seed
  `20260921` and a target of 4000.

**Outcome:** a hand-reviewed gold set that covers the whole supported surface,
on held-out structures. A training set with no held-out structure in it and no
near-duplicate of a gold intent. A content-addressed manifest and datasheet.
A 50-label audit with a measured error rate.

### Decisions (settled from the clarifying questions)

1. **Coverage is verb set × verb-term pair × shape.** Every supported verb set
   (8: `color`, `color+select`, `show`, `hide`, `hide+select`, `hide+show`,
   `color+select+show`, `orient+select`) is covered. So is every pair of
   {select, color, show, hide} × {chain, resi, resn, name, hetatm}, 20 pairs
   in all, and every boolean shape (single, and, or, and_or, single+not,
   and+not). That comes to about 70 items. Polymer terms, the four
   unobservable representations and a bare `orient` are excluded, because the
   corpus already reports them as unsupported.
2. **Claude drafts and Martin edits.** Each gold record stores who drafted it
   (the model ID) and who reviewed it. A split cannot be frozen while any
   item is unreviewed.
3. **Audit: Martin judges 50 samples drawn at random, with a recorded seed,
   from the decontaminated training split.**
4. **The split holds out 6 specs, chosen so every feature appears on both
   sides.**
5. **The gold set is the test split.** Corpus samples on held-out structures
   are removed from training and kept as a separate `heldout_synthetic` eval
   set. Training is decontaminated **against gold intents only**. The reason
   is a measurement: the templated intents repeat across structures, so
   decontaminating against templated held-out intents would drop 40% of
   training on exact match alone, and 72% at a similarity threshold of 0.7.
   The datasheet states this in so many words.

### Decisions I took, so you can overrule them

- **Held-out specs:** `longer_two_chains`, `two_chains_hetatm`,
  `three_states`, `altloc_two_residues`, `insertion_codes_two_chains` and
  `everything_bonded`. That is 2,820 of 11,274 attempts, or 25%. Each feature
  (multi-chain, hetatm, multi-state, altloc, insertion, bonds, long chain) has
  at least one training spec and at least one test spec. `three_chains` was
  swapped out for `longer_two_chains`, because otherwise no test structure
  had a long chain.
- **Near-duplicate rule: gated on entities, then fuzzy on wording.** Two
  intents count as near-duplicates only when their *entity signatures* are
  identical, and the Jaccard similarity of their remaining word tokens, after
  removing stopwords, is at least 0.5. The entity signature is the multiset of
  chain IDs, numbers, colour names, representation names, and residue and atom
  names. A plain character-shingle Jaccard was measured and rejected, because
  it scores an entity swap inconsistently: `chain A`→`chain B` scored 0.56 on
  a short intent and 0.95 on a long one. The threshold is frozen in config,
  and the report shows how many training samples each threshold drops
  (0.3/0.5/0.7).
- **No change to the `Sample` schema.** Gold provenance lives in the gold
  record, keyed by `sample_id == gold_id`. So `run_identity`, the conformance
  slice and item 14's tests are left alone.
- **The full split lives in `data/splits/`, which is gitignored.** The
  manifest, datasheet and filled audit sheet are committed under
  `docs/dataset/`, so a test can enforce that the split stays fixed.

## Delivery

Branch `feat/gold-set-split-audit` off an up-to-date `main`. Use Conventional
Commits, one per step. Run this gate after every step (from
`plans/08-dataset-generation.md`):

```
bazel test //... --lockfile_mode=error
bazel run //tools/quality:ruff --lockfile_mode=error -- check .
bazel run //tools/quality:ruff --lockfile_mode=error -- format --check .
bazel run //tools/quality:pyrefly --lockfile_mode=error -- check
```

Each step's test must also pass a sabotage check: break what the test covers,
confirm that exactly that test fails, then restore. New modules follow the
existing header, `from __future__ import annotations`, Google-style
docstrings, one import per line and 80 columns. **The implementer may edit:**
`src/pmc_data/**`, `configs/generation/**`, `tests/data/**`, `docs/dataset/**`,
`data/README.md`, `docs/master_plan.md`. **Steps 4 and 10 are for Martin.**
The implementing session stops at each of them.

---

## Step 1 — Gold record schema and loader

Add a `GoldItem` frozen dataclass with these fields: `gold_id`, `spec_id`,
`intent`, `reference_pml`, `concept` (an optional note on the domain mapping,
such as "waters = resn HOH"), `drafted_by`, `reviewed_by` (`str | None`) and
`reviewed` (`bool`). It gets `to_dict`/`from_dict`, and incomplete input is
rejected in the same way `sample.py` does it. Add `load_gold_items(path)`,
which rejects duplicate `gold_id`s and intents that are duplicates after
normalization. Add `to_candidate(item) -> PlanCandidate`. It requires
`parse_pml(reference_pml)` to return an `ActionPlan` and
`evaluate_plan(plan).allowed` to be true. It derives `category` and
`difficulty` with `taxonomy.categorize` and `difficulty_of`. **There is no
category field**, so a gold item cannot claim a category its plan does not
have. Intents must fall within `MIN_INTENT_CHARACTERS`..`MAX_INTENT_CHARACTERS`
(`pmc_core/prompt.py:68-69`). The module docstring should say how this differs
from the legacy `gold_case.py`.

**Touches:** `src/pmc_data/gold_set.py` (new), `src/pmc_data/BUILD.bazel`,
`tests/data/test_gold_set.py` (new), `tests/data/BUILD.bazel`.

**Test:** `test_gold_set.py`: `test_round_trip_preserves_every_field`, a
parametrized `test_missing_required_field_is_rejected`,
`test_unparseable_reference_is_rejected`, `test_denied_reference_is_rejected`
(for example `load x.pdb`) and `test_category_is_derived_from_the_plan`.

## Step 2 — Split definition

Add `SPLIT_VERSION = 1` and `HELD_OUT_SPEC_IDS` (the six specs above). Add
`features_of(spec) -> frozenset[str]` and `side_of(spec_id) -> "train" |
"test"`.

**Touches:** `src/pmc_data/split.py` (new), `src/pmc_data/BUILD.bazel`,
`tests/data/test_split.py` (new), `tests/data/BUILD.bazel`.

**Test:** `test_split.py`:
- `test_every_feature_is_on_both_sides`
- `test_held_out_ids_exist_in_the_matrix`, which catches a spec rename that
  would silently empty the test split
- `test_structures_are_disjoint_by_content`: no training spec's
  `snapshot_sha256` or `structure_digest` equals a test spec's, checked over
  `build_structure(enumerate_structures(20260921))`
- `test_split_is_frozen`: a golden literal of (`SPLIT_VERSION`, sorted IDs),
  so any change forces a deliberate version bump

## Step 3 — Draft the gold items (Claude)

Write about 70 records in `src/pmc_data/gold/gold_items.jsonl`, all on
held-out specs, with `drafted_by="claude-opus-5-5"` (or whichever model
actually drafts them) and `reviewed=false`. Phrase them the way a structural
biologist types: "make the zinc a sphere", "hide the waters", "colour chain B
salmon", "everything but chain A in grey", "residues 3 through 5 as sticks",
"select the CA atoms of chain B". **Only use concepts the synthetic structures
can support.** Every polymer atom is a backbone atom and there are no side
chains, so words like "backbone", "ligand" or "side chain" would either select
everything or select nothing. Record each non-obvious mapping in `concept`.
Each verb set gets at least 2 intents, worded differently from each other.
The reference `.pml` is one correct plan. Item 16 grades on the resulting
state, not on the plan's text.

**Touches:** `src/pmc_data/gold/gold_items.jsonl` (new),
`src/pmc_data/BUILD.bazel` (data), `tests/data/test_gold_set.py`.

**Test:** `test_gold_set.py::test_gold_covers_the_supported_surface` checks,
using derived categories, that every verb set, verb-term pair and shape listed
in Decision 1 is present. `test_gold_is_on_held_out_structures_only` checks
that every `spec_id` is in `HELD_OUT_SPEC_IDS`. `test_every_reference_resolves`
runs `to_candidate` on every item and checks that the oracle's
`selected_serials` is non-empty for every expression against the built
structure, so no gold plan selects nothing. **Stop here and hand over to
Martin.**

## Step 4 — Martin reviews every gold item (human gate)

Martin edits `gold_items.jsonl`: he rewrites intents that read as templated,
fixes reference plans, and sets `reviewed=true, reviewed_by="martin"`. After
that, the implementer adds the test below and re-runs Step 3's tests.

**Touches:** `src/pmc_data/gold/gold_items.jsonl`,
`tests/data/test_gold_set.py`.

**Test:** `test_every_gold_item_is_reviewed`. It is added only after the
review, so `bazel test //...` stays green while the review is in progress.

## Step 5 — Verify the gold set through the real pipeline

Add `verify_gold(items, *, seed, executor=execute) -> tuple[Sample, ...]`. It
builds each item's structure from `enumerate_structures(seed)`, calls
`to_candidate`, then calls `verify_sample(..., sample_id=item.gold_id)`. **A
`Rejection` is a hard error**, listed by `gold_id`. A gold label that the
oracle or PyMOL disagrees with has to be fixed by hand. It is never dropped.
Add a `bazel run //src/pmc_data:gold_cli` binary that writes the committed
`src/pmc_data/gold/gold_samples.jsonl` and refuses to run while any item is
unreviewed.

**Touches:** `src/pmc_data/gold_set.py`, `src/pmc_data/gold_cli.py` (new),
`src/pmc_data/gold/gold_samples.jsonl` (new, generated),
`src/pmc_data/BUILD.bazel`, `tests/data/test_gold_set.py`,
`tests/data/test_gold_set_real_pymol.py` (new), `tests/data/BUILD.bazel`.

**Test:** `test_gold_set.py::test_a_rejected_gold_item_is_an_error` drives a
fake executor that returns `REASON_FIDELITY_MISMATCH`.
`test_gold_set_real_pymol.py::test_every_gold_item_still_verifies` replays
every committed gold sample through the real executor and checks for
`REASON_OK` and an unchanged `resulting_fingerprint`. It carries the
`tags = ["exclusive"]` pattern of `conformance_real_pymol`.

## Step 6 — Decontamination

Add `normalize_intent`, which casefolds, turns punctuation into spaces and
collapses whitespace. (NFKC was dropped during implementation: its only call,
`unicodedata.normalize`, trips `tests/contract/test_errors.py`'s guard against
any data-pipeline call named `normalize` other than the error envelope's.) Add `entity_signature(intent)`, a multiset
drawn from `COLOR_ALLOWLIST`, `REPRESENTATION_ALLOWLIST`, digits,
single-letter chain IDs, and the residue and atom vocabulary of
`structures.py`. Add `frame_tokens(intent)`, which is the remaining tokens
minus a fixed stopword set. Add `find_near_duplicates(train, gold, threshold)
-> dict[sample_id, (gold_id, score)]`. `configs/generation/split.json` (new)
freezes `{"seed": 20260921, "decontam": {"method": "entity-gated-token-jaccard",
"threshold": 0.5}}`.

**Touches:** `src/pmc_data/decontam.py` (new), `configs/generation/split.json`
(new), `configs/generation/BUILD.bazel`, `src/pmc_data/BUILD.bazel`,
`tests/data/test_decontam.py` (new),
`tests/data/testdata/near_duplicate_pairs.jsonl` (new),
`tests/data/BUILD.bazel`.

**Test:** `test_decontam.py::test_labelled_pairs` runs over a committed fixture
of labelled pairs, which Martin reviews along with Step 4. The fixture must
include: pairs that differ only in case, punctuation or whitespace (duplicate);
`colour`/`color` (duplicate, which means the normalizer maps UK spelling to US
spelling); `please` or filler added (duplicate); `chain A`→`chain B`, `red`→
`blue` and `resi 4`→`resi 5` (**not** a duplicate); and `"color the waters
blue"` vs `"Color HOH residues blue."` (not a duplicate, because the entities
differ). `test_threshold_is_read_from_config` covers the config read.

## Step 7 — Build the split

Add a `bazel run //src/pmc_data:split_cli -- --corpus
data/samples/seed-…/ --out data/splits`. Its inputs are the corpus
`samples.jsonl` and `report.json`, `gold_samples.jsonl`, `gold_items.jsonl`
and `split.json`. It writes `data/splits/split-<id>/` containing
`train.jsonl`, `test_gold.jsonl`, `heldout_synthetic.jsonl` and
`decontam_dropped.jsonl`. The last of these records each dropped training
sample with the gold ID it matched and the score.

It refuses to run on any of the following:
- a corpus whose `report.json` says `complete: false`
- an unreviewed gold item
- a gold sample on a training spec
- a corpus sample whose `structure.snapshot_sha256` does not match its
  rebuilt spec (broken lineage)

Output is deterministic, and the same identity-and-promotion discipline as
`corpus_cli` applies (write into a staging directory, never destroy an
existing split).

**Touches:** `src/pmc_data/split_cli.py` (new), `src/pmc_data/split.py`,
`src/pmc_data/BUILD.bazel`, `tests/data/test_split_cli.py` (new),
`tests/data/BUILD.bazel`.

**Test:** `test_split_cli.py`, run hermetically on synthetic samples:
- `test_no_test_structure_reaches_train`: checked by spec_id,
  `snapshot_sha256` and `structure_digest`. The sabotage check is to move one
  held-out ID to train.
- `test_every_corpus_sample_lands_exactly_once` (conservation across
  train/heldout/dropped)
- `test_refuses_unreviewed_gold`
- `test_refuses_incomplete_corpus`
- `test_rerun_is_byte_identical`

## Step 8 — Manifest and datasheet

`manifest.json` contains:
- **Content hash:** SHA-256, byte count and record count for each file, plus
  the `split_id`, which is the SHA-256 over the sorted file hashes.
- **Provenance:** the git commit, and whether the tree was dirty (dirty trees
  are refused); the corpus directory name and the SHA-256 of its
  `report.json`; the SHA-256 of `gold_items.jsonl`; `current_versions()`;
  `PINNED_PYMOL_WHEEL`; the seed; `SPLIT_VERSION`; the held-out IDs; and the
  decontamination method and threshold.
- **Counts:** per split, per category and per difficulty, plus the
  decontamination sensitivity at 0.3/0.5/0.7.
- **License record:**
  - Code: BSD-3-Clause, from `LICENSE`.
  - Structures: authored synthetically in this repository, with no PDB or
    wwPDB-derived data.
  - PyMOL: the license text read from the installed wheel's metadata. It is
    copied from that metadata, never written from memory.
  - Gold intents: drafted by a named Claude model and reviewed by Martin.
  - No teacher outputs are in the training data.
  - No publication is planned (per the SPECIFICATION).
- **Regeneration config:** the exact `corpus_cli`, `gold_cli` and `split_cli`
  command lines, with the SHA-256 of each config file.

`validate_manifest(dir)` recomputes every hash. `DATASHEET.md` is rendered
from the manifest into the Datasheets-for-Datasets sections, and it must state
three limits: templated training intents, a synthetic backbone-only
vocabulary, and a split made by spec rather than by sequence cluster. Both the
manifest and the datasheet are copied to `docs/dataset/`.

**Touches:** `src/pmc_data/manifest.py` (new), `src/pmc_data/split_cli.py`,
`src/pmc_data/BUILD.bazel`, `tests/data/test_manifest.py` (new),
`tests/data/BUILD.bazel`, `docs/dataset/manifest.json` and
`docs/dataset/DATASHEET.md` (new, generated).

**Test:** `test_manifest.py`:
- `test_validator_catches_a_flipped_byte`
- `test_every_required_field_is_present`
- `test_committed_manifest_matches_the_repo`: the committed manifest's
  `gold_items` SHA-256 and held-out IDs must equal what is in the tree now.
  Editing gold after the freeze then fails CI until the split is regenerated
  and `SPLIT_VERSION` is bumped. This is how "test splits are immutable after
  inspection begins" is enforced.

## Step 9 — Audit tooling

`split_cli audit draw` samples 50 records from `train.jsonl` **only**,
without replacement, using a seed recorded in the manifest. It writes
`audit/sheet.jsonl` and `audit/sheet.md`. For each sample the sheet shows the
intent, a structure summary (chains, residue names, hetero residues, states,
altlocs, insertion codes), `plan_pml`, the selection counts, and blank
`verdict` (`correct|wrong|unsure`) and `note` fields.

The sheet header defines what counts as wrong: the plan does not do what the
intent asks on this structure (wrong target, colour, representation, or an
extra or missing effect), or the intent's wording would lead a biologist to
expect something else, such as `resi 1-4` spanning an insertion code or
"hetero atoms" including water.

`split_cli audit score` refuses a sheet with any blank verdict. It reports
k/50, the Wilson 95% interval, and the number of `unsure` verdicts
separately; they are never folded into k. It writes the result into the
manifest and the datasheet.

**Touches:** `src/pmc_data/audit.py` (new), `src/pmc_data/split_cli.py`,
`src/pmc_data/BUILD.bazel`, `tests/data/test_audit.py` (new),
`tests/data/BUILD.bazel`.

**Test:** `test_audit.py`:
- `test_draw_is_seeded_and_train_only`: the same seed gives the same IDs, and
  no gold or heldout ID is ever drawn
- `test_score_refuses_an_incomplete_sheet`
- `test_wilson_interval_known_values`: 0/50 → [0, 0.0713], and 3/50 checked
  against a hand-computed value
- `test_unsure_is_reported_not_counted`

**Stop here and hand over to Martin.**

## Step 10 — Martin audits the 50 labels (human gate)

Martin fills in `sheet.jsonl`, then runs `audit score`. The filled sheet and
the result are committed to `docs/dataset/audit/`.

**Touches:** `docs/dataset/audit/sheet.jsonl`, `docs/dataset/audit/result.json`,
`docs/dataset/manifest.json`, `docs/dataset/DATASHEET.md`.

**Test:** `test_manifest.py::test_committed_manifest_matches_the_repo` (now
also covering the audit sheet's hash), and `validate_manifest` passes on
`docs/dataset/`.

## Step 11 — Documentation and the master plan

**Touches:** `tests/data/README.md` (gold set, split, decontamination and
audit evidence), `configs/generation/README.md` (`split.json`),
`data/README.md` (the `data/splits/` layout), `docs/master_plan.md` (item 15
marked done with the PR number, **the observed error rate as a number with its
interval**, and the decontamination drop count; add a note that item 16
consumes `test_gold` and `heldout_synthetic`).

**Test:** `bazel test //...` is green, and
`tests/integration/test_subsystem_imports.py` and
`bazel run //tools/bazel:check_dependency_boundaries` pass unchanged.

---

## Verification (end to end)

```
git pull                                   # local main is 64 commits behind
bazel test //... --lockfile_mode=error      # plus ruff/pyrefly gate above
bazel run //src/pmc_data:corpus_cli -- --config configs/generation/corpus.json --workers 8
bazel run //src/pmc_data:gold_cli
bazel run //src/pmc_data:split_cli -- --corpus data/samples/seed-20260921-<id> --out data/splits
bazel run //src/pmc_data:split_cli -- audit draw --split data/splits/split-<id>
#   Martin fills audit/sheet.jsonl
bazel run //src/pmc_data:split_cli -- audit score --split data/splits/split-<id>
```

Acceptance:
1. `test_gold` has about 70 reviewed items covering Decision 1's surface, and
   all of them verify.
2. No held-out spec, snapshot hash or structure digest appears in `train`.
3. `decontam_dropped.jsonl` lists every dropped sample with the gold ID it
   matched, and the drop count is in the datasheet.
4. `validate_manifest` passes, and re-running `split_cli` reproduces the same
   `split_id`.
5. The datasheet and the master plan state the audit's error rate as k/50,
   with its Wilson interval.

## Risks

- **Gold intents drafted by the same model family that will be evaluated.**
  Martin's review in Step 4 is the mitigation. The datasheet names the
  drafting model so that the bias is disclosed rather than hidden.
- **Synthetic structures limit what "biologist intents" can mean.** With no
  side chains and no ligand chemistry, some natural phrasing cannot be
  graded. The mitigation is Step 3's `concept` field and its "selects
  something" test. The limit is stated in the datasheet.
- **The split is by spec, not by sequence cluster.** All specs share one
  residue vocabulary, so the split tests generalisation across feature
  combinations and coordinates, not to new chemistry. The datasheet says so;
  it does not claim more.
- **A gold item fails verification** because the oracle and PyMOL disagree,
  for example on `resi` with insertion codes. Step 5 makes that a hard error
  to be fixed by hand, never a silent drop.
- **The corpus is 4000 attempts drawn by `stratified_subset` across
  categories.** After the held-out specs are removed, some training categories
  may be thin. The manifest's per-category counts make that visible, and a
  larger `--target` is the lever.
