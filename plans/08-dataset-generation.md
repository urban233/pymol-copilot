# Dataset generation

## Context

This is item 14 of
[docs/master_plan.md:503-519](docs/master_plan.md#L503-L519) — Martin's, sized
at ~5 days, `ready`, with prerequisites 2, 4, 5 and 13 all merged. It is the
longest single item left and items 15, 16, 17 and 18 all sit behind it.

Today `src/pmc_data/` implements exactly one task shape. Every module is
hard-wired to "select chain A, colour it red":

- [oracle.py:19-31](src/pmc_data/oracle.py#L19-L31) is one function,
  `expected_chain_atom_ids(pdb_path, chain_id)`. Chain membership is the
  entire independent surface.
- [pdb.py:18-28](src/pmc_data/pdb.py#L18-L28) carries two fields per atom,
  `serial` and `chain_id`. No resi, resn, name, element, altloc, state or
  hetatm flag, so no other predicate is computable at all.
- [gold_case.py:272-289](src/pmc_data/gold_case.py#L272-L289) asserts every
  record's `canonical_plan_pml` equals `CHAIN_A_RED_PLAN.render_pml()`.
- [verifier.py:340](src/pmc_data/verifier.py#L340) executes the module
  constant `CHAIN_A_RED_PLAN` rather than the case's own plan, and drives
  PyMOL in-process through `cmd.do()` — it never touches
  `pmc_core.executor`.
- [generate.py:40-44](src/pmc_data/generate.py#L40-L44) freezes
  `_SELECTION_NAME`, `_TARGET_COLOR` and `_TARGET_CHAIN`.

Of the three assertion kinds only one is genuinely PyMOL-independent:
`color_state` takes its expected value from `cmd.get_color_index()`
([verifier.py:250](src/pmc_data/verifier.py#L250)) and
`no_unintended_change` is a PyMOL-versus-PyMOL differential.

**Outcome:** a generalized `src/pmc_data/` that emits a few thousand
verified samples across the whole supported command surface, each graded by
an oracle that predicts the complete resulting state without PyMOL, executed
through `pmc_core.executor`, recorded with full provenance, and accompanied
by an honest per-category rejection rate in which the categories the oracle
cannot grade are marked unsupported rather than guessed.

### The machinery this item should reuse rather than rebuild

The shared core already ships every seam this item needs, and two of them
were built naming item 14 as their caller.

- **[`pmc_core.snapshot`](src/pmc_core/snapshot.py)** — `AtomRecord`
  ([snapshot.py:86-123](src/pmc_core/snapshot.py#L86-L123)) already carries
  the exact per-atom field set a generalized oracle needs: `serial, name,
  alt, resn, chain, resv, ins_code, elem, hetatm, q, b, color, reps, label,
  coord`. `ObjectSnapshot.states`
  ([snapshot.py:173](src/pmc_core/snapshot.py#L173)) models multiple states
  and `view` ([snapshot.py:175](src/pmc_core/snapshot.py#L175)) the camera.
  `reconstruct()` ([snapshot.py:268](src/pmc_core/snapshot.py#L268))
  documents empirically-won handling of altloc, insertion codes and
  multi-state coordinates.
- **[`pmc_core.executor.execute()`](src/pmc_core/executor.py#L967)** —
  `ExecutionRequest.expected_resulting_fingerprint`
  ([executor.py:225-231](src/pmc_core/executor.py#L225-L231)) is documented
  as *"an optional independently computed fingerprint … that the boundary
  must match after a fully successful run"*, enforced at
  [executor.py:1189-1196](src/pmc_core/executor.py#L1189-L1196) with
  `REASON_FIDELITY_MISMATCH`. This is precisely the oracle seam this item
  needs, already plumbed to the wire
  ([protocol.py:1244](src/pmc_core/protocol.py#L1244)). **No change to
  `pmc_core` or `pmc_sidecar` is required.**
- **[`pmc_core.prompt.build_for_data()`](src/pmc_core/prompt.py#L240)** —
  the dataset-writer seam, taking an `ObjectSnapshot` and an intent and
  stamping `prompt_version`, `card_version`, `grammar_version` and
  `policy_version`. `pmc_data` does not call it anywhere today; this item is
  its first real caller.
- **[`pmc_core.policy.evaluate_plan()`](src/pmc_core/policy.py#L427)** and
  **[`pmc_core.parser.parse_pml()`](src/pmc_core/parser.py#L126)** — the
  independent verdict and the round-trip check every emitted plan must pass.

### The three categories the contracts already declare ungradable

This item's "report honestly, mark unsupported rather than guess" clause has
a principled answer that falls out of the existing contracts rather than
being invented here:

1. **The `polymer` term.** `DECLARED_UNSUPPORTED`
   ([snapshot.py:76-79](src/pmc_core/snapshot.py#L76-L79)) already carries
   `"unsupported state=explicit-polymer-classification route=contract-freeze"`.
   The snapshot format records no polymer flag, so there is no observable
   ground truth for `PolymerTerm`
   ([plan.py:331](src/pmc_core/plan.py#L331)).
2. **Four of the fourteen representations.**
   `REPRESENTATION_ALLOWLIST` ([plan.py:713](src/pmc_core/plan.py#L713)) has
   14 entries; `MOLECULE_REP_NAMES`
   ([snapshot.py:40-51](src/pmc_core/snapshot.py#L40-L51)) records 10. The
   difference — `nonbonded`, `slice`, `ellipsoids`, `volume` — is legal to
   emit but invisible in any snapshot, so `show`/`hide` of those four cannot
   be graded. [plan.py:708-712](src/pmc_core/plan.py#L708-L712) already
   flags this divergence.
3. **`orient`'s camera effect.** `orient` changes only `view`, and `view` is
   inside the fingerprint the executor compares. Predicting PyMOL's exact
   view matrix would mean reimplementing its principal-axis fit and zoom to
   float equality. That is a guess, so it is not attempted.

### Decisions taken (from the clarifying questions)

These are settled, not open.

1. **Controlled structures are authored `ObjectSnapshot` values**, generated
   programmatically and seeded — not PDB files. `pdb.py` is *not* extended
   and keeps serving the legacy chain-A case only. Structure identity is the
   SHA-256 of the canonical snapshot JSON plus
   `snapshot.structure_digest()`.
2. **Grading is the fingerprint gate, with no changes outside
   `src/pmc_data/`.** The oracle predicts the whole resulting
   `ObjectSnapshot`; its hash goes in as `expected_resulting_fingerprint`.
   Field-level `snapshot.diff()` diagnostics live in a real-PyMOL harness
   under `tests/data/` used to develop and validate the oracle, not in the
   production run.
3. **A new `Sample` record type is added; `GoldCase` is left untouched**,
   along with its two committed records and their drift guard.
4. **The corpus is written to `data/`** (gitignored) by a `bazel run`
   developer binary, with a small committed conformance slice under
   `src/pmc_data/` replayed by a bounded CI test.

### Decisions I took, stated so you can overrule them

- **`orient` samples are generated and kept, with the camera assertion
  explicitly marked unsupported.** The brief says an ungradable category is
  *marked* unsupported, not dropped. An `orient`-containing plan cannot use
  the fingerprint gate at all (the unpredictable `view` is inside the hash),
  so those samples are graded on the assertions that do exist — every
  command reported `OUTCOME_OK`, and every `SelectionCount` matches the
  oracle's independently predicted count — and carry
  `unsupported_assertions: ["camera_view"]`. Nothing claims the camera was
  checked. The alternative is excluding `orient` entirely, which would leave
  a fifth of the verb surface unrepresented in training data.
- **Intents are program-generated from per-category templates.** "Program-
  first for each verb" rules out a teacher, and back-translation stays out
  of scope exactly as `configs/generation/README.md` already records for the
  current pipeline. Templates must fit `MIN_INTENT_CHARACTERS` /
  `MAX_INTENT_CHARACTERS` ([prompt.py:180-184](src/pmc_core/prompt.py#L180-L184)).
- **The frozen colour name→index table lands in `pmc_data`, not
  `pmc_core`.** The snapshot stores `color` as an int, so the oracle needs
  the mapping; `pmc_core.plan` deliberately freezes names only. Putting it
  in `pmc_data` honours "no `pmc_core` changes". If you would rather it sat
  beside `COLOR_ALLOWLIST`, say so — it is a one-file move.
- **Parallelism is in the generator, not the executor.** `execute()` already
  isolates every run in its own `tempfile.mkdtemp(prefix="pmc-executor-")`
  scratch directory, so concurrent calls are safe. A few thousand samples
  means a few thousand spawned PyMOL processes; serially that is hours, so
  the CLI takes a worker count.
- **Sample count is reached by combinatorics over structures × plans**,
  seeded and reproducible: roughly 24 controlled structures × ~150 enumerated
  plans. The CLI takes a target budget rather than hard-coding a number.

## Delivery: one branch, one PR

Branch `feat/dataset-generation` off `main`, on a new issue linked per
`CONTRIBUTING.md` guideline 1. Conventional Commits, one commit per step.

Per-step gate, from
[docs/development_setup.md](docs/development_setup.md):

```
bazel test //... --lockfile_mode=error
bazel run //tools/quality:ruff --lockfile_mode=error -- check .
bazel run //tools/quality:ruff --lockfile_mode=error -- format --check .
bazel run //tools/quality:pyrefly --lockfile_mode=error -- check
```

A step is not done until its named test passes **and** that test has been
sabotage-checked: break the thing it covers, confirm exactly that test goes
red and no other, restore.

Every new module starts with `# Copyright 2026 PyMOL Copilot contributors.`
and `from __future__ import annotations`, uses Google-style docstrings, one
import per line, and an 80-column limit.

---

## Step 1 — Frozen colour index table

`color red, <target>` must be predicted as an integer colour index without
PyMOL. No name→index table exists anywhere in the repository today; the old
verifier asked PyMOL itself.

Add `COLOR_INDEX_BY_NAME: Mapping[str, int]` covering every name in
`COLOR_ALLOWLIST`, generated once from `cmd.get_color_indices()` against
`pymol-open-source-whl==3.2.0.2` and frozen as a literal — the same pattern
and the same justification as `COLOR_ALLOWLIST`
([plan.py:522-527](src/pmc_core/plan.py#L522-L527)), with the generating
command recorded in the module docstring.

**Touches:** `src/pmc_data/colors.py` (new), `src/pmc_data/BUILD.bazel`,
`tests/data/test_colors.py` (new), `tests/data/BUILD.bazel`,
`tests/integration/test_real_pymol_allowlist.py`,
`tests/integration/BUILD.bazel`.

**Test:** `tests/data/test_colors.py::test_table_covers_the_whole_allowlist`
asserts `set(COLOR_INDEX_BY_NAME) == set(COLOR_ALLOWLIST)` hermetically, and
`tests/integration/test_real_pymol_allowlist.py::test_frozen_color_indices_match_real_pymol`
asserts every frozen `(name, index)` pair equals `cmd.get_color_index(name)`
in real headless PyMOL — one direction only, matching that module's existing
"widening is a reviewed decision" stance.

---

## Step 2 — Controlled structure builder

A PyMOL-free builder that produces `ObjectSnapshot` values directly, seeded
and deterministic, spanning the feature matrix the brief names: multiple
chains, hetero atoms, multiple states, alternate locations — plus insertion
codes, which `reconstruct()` already handles and which stress the same
identity machinery.

`build_structure(spec: StructureSpec) -> ObjectSnapshot` with a
`StructureSpec` carrying `seed`, `chain_count`, `residues_per_chain`,
`hetatm_groups`, `state_count`, `altloc_pairs`, `insertion_codes`. Atom
serials are the stable identity; `reps` are emitted in `MOLECULE_REP_NAMES`
order so extraction and prediction cannot disagree on ordering.

`enumerate_structures(seed) -> tuple[StructureSpec, ...]` produces the
standing matrix (~24 specs) actually used by the corpus run.

**Touches:** `src/pmc_data/structures.py` (new),
`src/pmc_data/BUILD.bazel`, `tests/data/test_structures.py` (new),
`tests/data/test_structures_real_pymol.py` (new),
`tests/data/BUILD.bazel`.

**Test:**
`tests/data/test_structures.py::test_matrix_covers_every_declared_feature`
asserts the enumerated matrix contains structures with >1 chain, with
hetero atoms, with >1 state, with altloc pairs and with insertion codes, and
that `build_structure` is byte-identical for a repeated seed.
`tests/data/test_structures_real_pymol.py::test_every_structure_is_a_reconstruction_fixed_point`
is the **admission gate**: for each spec it runs
`executor.probe_fidelity()` and asserts `snapshot.diff(built,
reconstructed)` is empty. A structure that is not a fixed point of
reconstruct→extract can never be graded by prediction, so it is excluded
here rather than producing mysterious mismatches later.

---

## Step 3 — Oracle: selection-expression evaluator

Extend `oracle.py` from one chain function to a total evaluator over the
`SelectionExpression` → `AndClause` → `Factor` → term tree
([plan.py:367-483](src/pmc_core/plan.py#L367-L483)). The tree is already
disjunctive normal form, so this is a direct structural recursion: `or`
across clauses, `and` across factors, `not` inside a factor.

- `atom_matches_term(term, atom) -> bool` for `ChainTerm`, `ResiTerm`
  (single and inclusive range, against `resv`), `ResnTerm`, `NameTerm`,
  `HetatmTerm`.
- `PolymerTerm` raises `UnsupportedAssertionError` — the snapshot carries no
  polymer flag and `DECLARED_UNSUPPORTED` already says so. It is never
  guessed.
- `selected_serials(snapshot, expression) -> frozenset[int]`.

`expected_chain_atom_ids` stays, so the legacy chain-A path and its tests
keep working unchanged.

`tests/data/test_oracle_sabotage.py:52` string-matches `oracle.py`'s exact
two-line body and will fail by design the moment the module changes; it is
re-pointed at the new independent-derivation body in the same commit.

**Touches:** `src/pmc_data/oracle.py`, `tests/data/test_oracle.py`,
`tests/data/test_oracle_sabotage.py`,
`tests/data/test_oracle_real_pymol.py` (new), `tests/data/BUILD.bazel`.

**Test:**
`tests/data/test_oracle.py::test_precedence_matches_the_typed_tree` covers
`not`/`and`/`or` nesting hermetically against a built structure, including
an empty result and a full-object result.
`tests/data/test_oracle_real_pymol.py::test_membership_agrees_with_real_pymol`
is the real proof: for a seeded sample of expressions over the structure
matrix, it reconstructs the object and asserts the oracle's serial set
equals `cmd.iterate(expr, "ids.append(ID)")`. This is the differential that
would catch a wrong reading of PyMOL's own semantics.

---

## Step 4 — Oracle: plan application

`apply_plan(snapshot, plan) -> ExpectedOutcome`, the function whose output
becomes `expected_resulting_fingerprint`. `ExpectedOutcome` carries
`snapshot: ObjectSnapshot`, `selection_counts: tuple[SelectionCount, ...]`
and `unsupported: tuple[str, ...]`.

Per verb, applied in plan order against a named-selection environment:

| Verb | Predicted effect |
| --- | --- |
| `select` | No change to the object. Binds the name to a serial set and appends the predicted `SelectionCount`. |
| `color` | Sets `AtomRecord.color` to `COLOR_INDEX_BY_NAME[color]` for every matching atom, in every state. |
| `show` | Adds the representation to `AtomRecord.reps` for matching atoms, re-sorted into `MOLECULE_REP_NAMES` order. A representation outside those ten is recorded in `unsupported` and changes nothing. |
| `hide` | Removes it, same ordering rule, same unsupported handling. |
| `orient` | Records `"camera_view"` in `unsupported` and leaves the snapshot alone. A plan whose `unsupported` is non-empty must not be fingerprint-graded. |

**Touches:** `src/pmc_data/oracle.py`, `tests/data/test_oracle.py`,
`tests/data/test_oracle_real_pymol.py`.

**Test:** `tests/data/test_oracle.py::test_each_verb_predicts_its_own_effect`
covers all five verbs hermetically, including that `select` leaves the
snapshot byte-identical, that the four non-observable representations are
reported unsupported rather than applied, and that `orient` reports
`camera_view`.
`tests/data/test_oracle_real_pymol.py::test_predicted_snapshot_matches_extraction`
reconstructs, runs the plan, extracts, and asserts
`snapshot.diff(predicted, extracted) == []` — the field-level harness that
makes a mismatch diagnosable during development.

---

## Step 5 — Sample record schema

A new `Sample` type recording everything the brief lists, alongside the
untouched `GoldCase`. Frozen dataclasses with `to_dict`/`from_dict`,
rejecting any incomplete record exactly as `gold_case.py` already does
(reuse `required_string`, [gold_case.py:76-94](src/pmc_data/gold_case.py#L76-L94)).

```
Sample
  sample_id           stable identity
  intent              the templated natural-language intent
  category            taxonomy category (Step 6)
  difficulty          taxonomy difficulty
  structure           StructureIdentity(sha256, structure_digest, spec, seed)
  versions            SampleVersions(plan, card, prompt, grammar, policy,
                                     snapshot, executor, pymol)
  plan_pml            canonical .pml, cross-checked against render_pml()
  plan_json           protocol.encode_plan() form
  prompt_text         PromptV1.text() as the model will see it
  assertions          the assertions actually evaluated
  unsupported_assertions  named, never silently absent
  verification        VerificationRecord(status, reason, command_outcomes,
                                         selection_counts, fingerprints)
```

`card_version` comes from the `PromptV1` that `build_for_data()` returns,
not from a constant re-read in `pmc_data` — that is what makes the stamp
meaningful. Records serialize as JSONL, one sample per line, for a corpus of
this size.

**Touches:** `src/pmc_data/sample.py` (new), `src/pmc_data/BUILD.bazel`,
`tests/data/test_sample.py` (new), `tests/data/BUILD.bazel`.

**Test:** `tests/data/test_sample.py::test_round_trip_preserves_every_field`
plus a parametrized `test_missing_required_field_is_rejected` over each
top-level key, mirroring `test_gold_case.py`'s existing discipline, and
`test_unsupported_assertions_survive_round_trip` proving an unsupported
marker cannot be lost in serialization.

---

## Step 6 — Plan enumeration and the category taxonomy

`enumerate_plans(structure, seed, budget) -> Iterator[PlanCandidate]`,
where `PlanCandidate` pairs an `ActionPlan` with its `category`,
`difficulty` and templated `intent`.

Categories are derived from the plan's own shape — verb set, term kinds,
boolean composition — not hand-labelled, so the rejection report cannot
drift from what was actually generated. Terms are instantiated from the
structure's real content (its actual chains, residue numbers, residue names,
atom names), so a plan is never vacuous.

Every emitted plan must satisfy the policy's structural rules by
construction: a selection is defined before it is referenced, no name is
defined twice, and the plan stays within `MAX_COMMANDS`.

**Touches:** `src/pmc_data/taxonomy.py` (new), `src/pmc_data/BUILD.bazel`,
`tests/data/test_taxonomy.py` (new), `tests/data/BUILD.bazel`.

**Test:**
`tests/data/test_taxonomy.py::test_every_emitted_plan_is_allowed_and_round_trips`
asserts, for every plan the enumerator yields across the whole structure
matrix, that `evaluate_plan(plan).allowed` is True and that
`parse_pml(plan.render_pml())` returns an equal `ActionPlan` — the two
independent authorities agreeing before PyMOL is ever involved. A companion
`test_taxonomy_covers_every_verb_and_term` asserts all five verbs and all
six terms appear, the `polymer` and four-representation categories included
so they can be *reported* as unsupported rather than quietly missing.

---

## Step 7 — Verified generation through `pmc_core.executor`

`verify_sample(structure, candidate) -> Sample | Rejection`, the heart of
the item:

1. `snapshot_json = to_json(structure)`; `digest = structure_digest(structure)`.
2. `prompt = build_for_data(structure, candidate.intent)` — the first real
   call to that seam.
3. `expected = oracle.apply_plan(structure, candidate.plan)`.
4. If `expected.unsupported` is empty, compute
   `"sha256:" + sha256(to_json(expected.snapshot))` and pass it as
   `expected_resulting_fingerprint`. Otherwise pass `None` and record the
   unsupported assertion names on the sample.
5. `execute(ExecutionRequest(executor_version=EXECUTOR_VERSION,
   plan=candidate.plan, snapshot_json=snapshot_json,
   expected_snapshot_digest=digest,
   expected_resulting_fingerprint=fingerprint))`.
6. Keep the sample only if `report.reason == REASON_OK` **and** every
   predicted `SelectionCount` matches the report's. Anything else is a
   `Rejection` carrying the report's own `status`/`reason` and failing
   `command_outcomes`.

`REASON_FIDELITY_MISMATCH` means real PyMOL disagreed with the oracle. That
is always a rejection and never a repair: the sample is dropped and counted.

The existing `generate.py` chain-A path and `verifier.py` are left in place
so the committed gold records and their real-PyMOL tests keep passing; the
new path is additive.

**Touches:** `src/pmc_data/generate.py`, `src/pmc_data/BUILD.bazel`,
`tests/data/test_generate.py`, `tests/data/test_generate_sample.py` (new),
`tests/data/test_generate_sample_real_pymol.py` (new),
`tests/data/BUILD.bazel`.

**Test:**
`tests/data/test_generate_sample.py::test_only_a_clean_report_is_promoted`
drives a fake executor returning each of `REASON_OK`,
`REASON_FIDELITY_MISMATCH`, `REASON_COMMAND_FAILURE` and
`REASON_POLICY_DENIED`, asserting only the first yields a `Sample` and each
rejection carries its own reason — the promotion guard, proved without
PyMOL. `test_selection_count_disagreement_is_rejected` covers a report that
is `REASON_OK` but whose counts contradict the oracle.
`tests/data/test_generate_sample_real_pymol.py::test_a_sample_per_category_verifies`
runs one plan from each gradable category end to end through the real
executor.

---

## Step 8 — Corpus CLI and the honest rejection report

Rewrite `generate_cli.py` as the corpus binary: seeded, parallel across a
`--workers` pool, writing to `data/samples/<run-id>/`:

- `samples.jsonl` — verified samples only.
- `rejections.jsonl` — every rejection with its category and reason.
- `report.json` — per category: attempted, kept, rejected by reason, and the
  count marked unsupported, plus the overall rejection rate.

The report prints the per-category table to stdout at the end of a run. A
category with zero kept samples is reported as such rather than omitted —
the failure mode the brief is guarding against is a category quietly
vanishing from the corpus.

The binary no longer imports PyMOL itself; `execute()` spawns
`pmc_sidecar.child`, which is the only thing that does.

**Touches:** `src/pmc_data/generate_cli.py`, `src/pmc_data/report.py` (new),
`src/pmc_data/BUILD.bazel`, `configs/generation/corpus.json` (new),
`configs/generation/BUILD.bazel`, `configs/generation/README.md`,
`tests/data/test_report.py` (new), `tests/data/BUILD.bazel`.

**Test:** `tests/data/test_report.py::test_rates_are_computed_per_category`
builds a synthetic mix of samples and rejections and asserts the aggregation
is exact, that a zero-kept category still appears, and that unsupported
counts are reported separately from rejections — an unsupported category is
not a failure and must not inflate the rejection rate.

---

## Step 9 — Committed conformance slice

A run of a few thousand samples cannot live in `bazel test //...`. Commit a
small fixed slice — roughly one sample per category — under
`src/pmc_data/conformance/samples.jsonl`, and add a bounded CI test that
replays each committed sample through the real executor and asserts it still
verifies.

This is what catches contract drift: a bumped `CARD_VERSION`, a changed
colour index, an altered snapshot field will fail here in minutes rather
than surfacing in a months-old corpus.

**Touches:** `src/pmc_data/conformance/samples.jsonl` (new),
`src/pmc_data/BUILD.bazel`,
`tests/data/test_conformance_real_pymol.py` (new),
`tests/data/BUILD.bazel`.

**Test:**
`tests/data/test_conformance_real_pymol.py::test_every_committed_sample_still_verifies`
re-runs each committed sample and asserts `REASON_OK` and an unchanged
`resulting_fingerprint`, and
`test_committed_slice_covers_every_category` asserts the slice has not
silently lost a category.

---

## Step 10 — Documentation and the master plan

**Touches:** `tests/data/README.md` (the ownership boundary now includes the
sample schema, structure builder, taxonomy and conformance slice),
`configs/generation/README.md` (drop the stale `docs/codev/wave/` reference,
document the corpus config), `data/README.md` (name the corpus layout),
`src/pmc_data/BUILD.bazel` visibility review, `docs/master_plan.md` (item 14
→ done, with the PR number and the measured per-category rejection rate).

**Test:** `bazel test //...` green, plus
`tests/integration/test_subsystem_imports.py` unchanged and passing —
`pmc_data` must still import without PyMOL present.

---

## Verification (end to end)

```
bazel build //... --lockfile_mode=error
bazel test //... --lockfile_mode=error
bazel run //tools/bazel:check_dependency_boundaries --lockfile_mode=error
bazel run //tools/quality:ruff --lockfile_mode=error -- check .
bazel run //tools/quality:ruff --lockfile_mode=error -- format --check .
bazel run //tools/quality:pyrefly --lockfile_mode=error -- check
```

Then the corpus run itself, which is the item's actual deliverable:

```
bazel run //src/pmc_data:generate_cli -- \
    --config configs/generation/corpus.json \
    --seed 20260921 --workers 8 --out data/samples
```

Acceptance:

1. `data/samples/<run-id>/samples.jsonl` holds a few thousand verified
   samples.
2. `report.json` gives a per-category rejection rate, with `polymer`, the
   four non-observable representations, and `orient`'s camera assertion all
   listed as unsupported rather than as passes.
3. Re-running with the same seed reproduces the same corpus byte for byte.
4. `check_dependency_boundaries` still passes — `pmc_data` must not have
   entered any runtime closure.

## Risks

- **The oracle disagrees with PyMOL on a selection edge case.** Most likely
  on `resi` ranges against insertion codes, on case sensitivity in `resn`/
  `name`, or on `hetatm` after reconstruction via `pseudoatom`. Mitigated
  structurally: Step 3's real-PyMOL differential test compares membership
  directly, and any residual disagreement shows up as
  `REASON_FIDELITY_MISMATCH` and is counted, never silently accepted.
- **A structure is not a reconstruction fixed point.** Altloc and
  multi-state are exactly where `reconstruct()` documents hard-won
  behaviour. Step 2's admission gate excludes such a structure up front
  instead of letting it poison every sample built on it.
- **`cmd.count_atoms` on a multi-state object may not equal the first
  state's matching atom count.** This is assumed, not verified, and the
  `selection_counts` check in Step 7 depends on it. Step 4's real-PyMOL test
  settles it empirically; if the assumption is wrong the prediction rule
  changes, not the architecture.
- **Runtime.** A few thousand spawned PyMOL processes is the dominant cost.
  Parallelism is in the CLI and each `execute()` is independently
  sandboxed, but a full run is still tens of minutes, and it stays out of
  CI by design — Step 9's committed slice is what CI actually runs.
- **`show cartoon` on a pseudoatom-built object.** The reconstructed object
  has no secondary structure, so a representation bit may be set while
  nothing renders. The snapshot records the bit, which is what is graded, so
  this is a documented limitation of the corpus rather than a defect — worth
  stating in `tests/data/README.md` so item 15's audit does not rediscover
  it.
- **The frozen colour table drifts from PyMOL.** Same failure mode as
  `COLOR_ALLOWLIST`, mitigated the same way: Step 1's real-PyMOL
  conformance test.
