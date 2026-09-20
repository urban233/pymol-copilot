# Structure card

## Context

This is item 5 of [docs/master_plan.md:155-165](docs/master_plan.md#L155-L165)
— Martin, ~2 days. It is the last of the four week-1 shared-core promotions,
and the only one whose prototype is already feature-complete.

[SPECIFICATION.md:485](SPECIFICATION.md#L485) defines the contract the card has
to satisfy: *"Versioned deterministic compact text/schema | Same
implementation and bytes for equivalent snapshots | Unsupported structures
produce explicit preparation failure or bounded omission marker | Version
change requires dataset/model compatibility decision | Symbol identity plus
byte-equality fixtures."* Its declared consumers in that same row are the
dataset system, the prompt builder and the grammar — none of which exist yet.

The prototype already meets that. `tests/discovery/m02/card_candidate.py` is
268 lines with a total renderer, canonical ordering, signed-zero
normalization, bounded truncation with an explicit marker, fail-closed
handling of malformed and wrong-version snapshots, and 12 PyMOL-free tests
plus one real-PyMOL test. It has no PyMOL import today and imports only
`json`, `math` and `pmc_core.snapshot` types. The two caller seams the master
plan cares about — `render_for_data` and `render_for_runtime` — exist and are
already proved byte-identical.

What is missing is not behaviour, it is status. The module is discovery
evidence by explicit policy
([tests/discovery/README.md:10-12](tests/discovery/README.md#L10-L12): *"Nothing
still under this directory is a production snapshot, card, or executor API"*),
so nothing may import it, and the other side of the contract is already
waiting for it: [tests/contract/test_snapshot.py:303-309](tests/contract/test_snapshot.py#L303-L309)
pins the two declared-unsupported markers byte-for-byte and says its purpose is
*"what keeps pmc_core.card (item 5) a pure pass-through of this module's own
declaration."*

**Outcome:** `src/pmc_core/card.py` as an importable production module with a
`CARD_VERSION` constant stamped into every card it emits, including both
failure cards; its 12 PyMOL-free tests carried into `tests/contract/test_card.py`
and its one real-PyMOL test into `tests/integration/`; and
`tests/discovery/m02/` deleted, along with every reference to it in
`pyproject.toml`, `tests/integration/BUILD.bazel` and `tests/discovery/README.md`.

### Decisions taken (from the clarifying questions)

These were answered directly and are not open:

1. **Seams only, in `pmc_core`.** The master plan's *"both the dataset writer
   and the runtime prompt builder stamp into their output"* cannot be executed
   literally today: the prompt builder is item 13 and generalized dataset
   generation is item 14, and neither exists. What ships now is
   `CARD_VERSION` plus the `render_for_data`/`render_for_runtime` seams, with a
   contract test proving the two are byte-identical. Items 13 and 14 call
   those seams; **nothing in `src/pmc_data` or `src/pmc_agent` changes in this
   item.**
2. **`CARD_VERSION = 1`, an int**, mirroring
   [SNAPSHOT_VERSION](src/pmc_core/snapshot.py#L32) in the module this card is
   derived from — not `PROTOCOL_VERSION`'s string form. The rendered first
   line becomes `card-version=1`.
3. **`tests/discovery/m02/` is deleted entirely**, not left with a README.
   Unlike `h02/`, which still holds item 4's unpromoted executor prototype,
   nothing in `m02/` survives promotion.
4. **The one real-PyMOL test gets its own target in `tests/integration/`**,
   not folded into an existing module and not dropped.

### One decision I took, stated so you can overrule it

**The card should fail closed on an undeclared unsupported set.** `render()`
currently splices `snapshot.unsupported` into its output unvalidated
([card_candidate.py:187](tests/discovery/m02/card_candidate.py#L187)), while
`_valid_snapshot` checks every other field. A snapshot carrying a fabricated
`unsupported` tuple therefore emits arbitrary attacker-chosen lines into model
context. `pmc_core.snapshot.from_json` already rejects exactly this at
[snapshot.py:481-485](src/pmc_core/snapshot.py#L481-L485), and
`test_declared_unsupported_matches_the_structure_card_markers` says the card
is meant to be *"a pure pass-through"* of that declaration. Step 3 closes it.

This is the one behavioural change in the promotion, which is why it is a
separate step landing **after** the byte-identical port is proved, not folded
into step 1. If you would rather ship the port unchanged and handle this at
the contract-freeze checkpoint, drop step 3 — nothing else depends on it.

---

## What must not change

**No PyMOL import, and no new Bazel dependency.**
[tools/bazel/check_dependency_boundaries.py:26-39](tools/bazel/check_dependency_boundaries.py#L26-L39)
bans `//src/pmc_agent`, `//src/pmc_data`, `//src/pmc_train` and
`//tools/winstage` from `pmc_core`'s closure, plus torch/transformers/peft/
trl/unsloth/langgraph/lemonade by name.
[src/pmc_core/BUILD.bazel](src/pmc_core/BUILD.bazel) has **no `deps` at all**
today and must still have none after this change. The card needs only `json`,
`math` and `pmc_core.snapshot`, so this is free — but it is the reason
`render()` takes an already-extracted `ObjectSnapshot` and never a live `cmd`.

**The rendered bytes, apart from the version line.** Every byte of every card
this module emits is a contract surface. The only intended difference between
the prototype's output and the production module's output is
`card-version=candidate-1` → `card-version=1`. If any other byte moves, that
is a porting bug, not an improvement.

---

## Step 1 — Port the renderer to `src/pmc_core/card.py`

**Files:** `src/pmc_core/card.py` (new),
[src/pmc_core/BUILD.bazel](src/pmc_core/BUILD.bazel) (add to `srcs`).

Copy [tests/discovery/m02/card_candidate.py](tests/discovery/m02/card_candidate.py)
across **unchanged below the import block**. Every function body — `_text`,
`_number`, `_atom_key`, `_atom_line`, `_is_number`, `_is_int`,
`_valid_snapshot`, `_malformed_card`, `render`, `render_for_data`,
`render_for_runtime` — is already correct and already tested. Do not
restructure, rename, or "tidy" any of it.

Four changes, and only these four:

1. **The version constant**, with the `#:` comment style every other
   `pmc_core` constant uses ([snapshot.py:29-32](src/pmc_core/snapshot.py#L29-L32)):

   ```python
   #: This module's own structure-card contract version, stamped as the
   #: first line of every card -- including both failure cards, so a
   #: rejected card is still attributable to a version. Both caller seams
   #: below emit it; the dataset writer (master plan item 14) and the
   #: prompt builder (item 13) stamp it into their own records by calling
   #: them.
   CARD_VERSION = 1
   ```

   `render()` and `_malformed_card()` already interpolate `{CARD_VERSION}`, so
   an int renders `card-version=1` with no further edit.

2. **The module docstring**, in the house form for a promoted module — compare
   [snapshot.py:2-18](src/pmc_core/snapshot.py#L2-L18), which opens *"This is
   the production promotion of H-02's differential discovery work (originally
   `tests/discovery/h02/harness.py` ...)"*. State the same three things:
   that this is the production promotion of M-02's card candidate, that it
   takes an already-extracted `ObjectSnapshot` and never imports PyMOL, and
   that `render_for_data`/`render_for_runtime` exist to be proved
   byte-identical rather than because they differ.

3. **The import block.** The prototype puts `SNAPSHOT_VERSION` after the
   CapWords names; `pmc_core` orders constants first. Also add the `__future__`
   line every `src/pmc_core` module carries verbatim, including its comment:

   ```python
   from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

   import json
   import math

   from pmc_core.snapshot import SNAPSHOT_VERSION
   from pmc_core.snapshot import AtomRecord
   from pmc_core.snapshot import BondRecord
   from pmc_core.snapshot import ObjectSnapshot
   from pmc_core.snapshot import StateSnapshot
   ```

4. **Google `Args:`/`Returns:`/`Raises:` docstrings on the private helpers**,
   which the prototype leaves bare. `snapshot.py`'s own `_atom_record_from_json`
   is the model. Note that ruff will *not* catch their absence — `D103` does not
   apply to underscore-prefixed functions — so this is house style, enforced
   only by review. `render()` gains a `Raises: ValueError` line for the
   `max_atoms_per_state < 1` guard it already has.

Then add `"card.py"` to `srcs` in
[src/pmc_core/BUILD.bazel:5-12](src/pmc_core/BUILD.bazel#L5-L12), alphabetically
between `__init__.py` and `parser.py`. There is one `py_library` for the whole
package, so no new target and no `deps` change.
[src/pmc_core/__init__.py](src/pmc_core/__init__.py) has no re-exports —
consumers write `from pmc_core.card import render`.

**Test that proves it:**

```text
bazel build //... --lockfile_mode=error
bazel run //tools/bazel:check_dependency_boundaries --lockfile_mode=error
grep -rn "import pymol\|from pymol" src/pmc_core/          # expect no output
diff tests/discovery/m02/card_candidate.py src/pmc_core/card.py
```

The `diff` is the load-bearing check, and it is a **review** check, not a
green/red one: read every hunk and confirm each is the module docstring, the
import block, the `CARD_VERSION` line, or an added helper docstring. **No hunk
may fall inside a function body.** If one does, the port changed behaviour.

**This step has no behavioural proof of its own** — the golden-byte test in
step 2 is what actually proves the port. Do not treat a green `bazel build`
here as the step passing; steps 1 and 2 are one unit of work and can land as
one commit if you prefer.

---

## Step 2 — Carry the PyMOL-free tests into `tests/contract/`

**Files:** `tests/contract/test_card.py` (new),
[tests/contract/BUILD.bazel](tests/contract/BUILD.bazel) (new target, plus the
`test_suite`), [tests/contract/README.md](tests/contract/README.md).

Move 12 of the 13 tests from
[tests/discovery/m02/test_card_candidate.py](tests/discovery/m02/test_card_candidate.py)
— everything except `test_h02_candidate_a_snapshot_renders_as_a_complete_card`,
which needs real PyMOL and goes to step 4. Keep `_IDENTITY_VIEW`, `_snapshot()`
and `_with_atom()` as they are, and keep all 20 parametrize cases of
`test_model_relevant_field_mutation_changes_card` and all 3 of
`test_invalid_view_length_returns_stable_malformed_card`. That is 12 functions,
33 collected cases.

Three edits while moving:

- `from card_candidate import render` → `from pmc_core.card import render`
  (likewise both seams), and drop the now-unused `extract` import.
- Rename `test_data_and_runtime_candidate_callers_have_byte_parity` →
  `test_data_and_runtime_callers_have_byte_parity`. These are no longer
  candidates.
- **Update the golden bytes.** Only the first line changes:

  ```python
      assert card == (
          "card-version=1\nstatus=complete\n"
          "unsupported state=measurement-objects route=plan-report\n"
          "unsupported state=explicit-polymer-classification route=contract-freeze\n"
          'object name="fx" enabled=false states=1\n'
          "state index=1 atoms=2 emitted=2 truncated=false\n"
          ...
      )
  ```

  The same substitution applies to the three malformed/unsupported assertions
  in `test_truncation_and_unsupported_schema_are_explicit`,
  `test_invalid_bond_endpoint_returns_stable_malformed_card`,
  `test_malformed_structural_value_returns_stable_malformed_card` and
  `test_invalid_view_length_returns_stable_malformed_card`. Type the new bytes
  by hand from the old ones — **do not** print the card and paste what the code
  produced, which would make the golden test assert only that the code equals
  itself.

Add one test the prototype does not have, which is the closest thing to
evidence for the master plan's "stamp into their output" until items 13 and 14
exist:

```python
def test_every_card_carries_the_version_on_its_first_line() -> None:
    """A rejected card is still attributable to a card version."""
```

covering all three outputs — complete, `malformed-snapshot`, and
`snapshot-schema-version` — asserting each starts `f"card-version={CARD_VERSION}\n"`.

Conventions this file must match, all uniform across the five existing contract
test modules: the `# Copyright 2026 PyMOL Copilot contributors.` first line
(ruff `CPY001`); a module docstring saying what is covered and naming
`tests/integration/test_card_real_pymol.py` as where the real-PyMOL evidence
lives; `import pytest  # noqa: I001, RUF100  # Keep imports split for Google
style.`; one-symbol-per-line `from` imports with constants before CapWords
before functions; no `from __future__` line (the test modules omit it); and the
footer

```python
if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
```

which is what makes `main = "test_card.py"` work under `py_test`.

The Bazel target follows `:snapshot` exactly — `size = "small"`, **no `tags`**
(the `exclusive` tag on `:policy_sabotage` is about subprocess spawning, not
PyMOL, and nothing here spawns anything), and this file's local `deps` order of
pytest first:

```text
py_test(
    name = "card",
    size = "small",
    srcs = ["test_card.py"],
    main = "test_card.py",
    deps = [
        "@pypi//pytest",
        "//src/pmc_core:pmc_core",
    ],
)
```

Insert `":card"` first in the `test_suite(name = "all")` list at
[tests/contract/BUILD.bazel:71-81](tests/contract/BUILD.bazel#L71-L81), which is
alphabetical. Extend `tests/contract/README.md`'s one sentence to name the
structure card's deterministic bytes alongside the snapshot codec.

**Test that proves it:**

```text
bazel test //tests/contract:card --lockfile_mode=error
bazel test //tests/contract:snapshot --lockfile_mode=error
```

`test_golden_card_has_stable_bytes` is the load-bearing one: it is what proves
step 1's port did not move a byte. `//tests/contract:snapshot` must stay green
too — `test_declared_unsupported_matches_the_structure_card_markers` is this
change's counterpart on the snapshot side, and the two markers it pins appear
verbatim in the card's golden bytes.

---

## Step 3 — Fail closed on an undeclared unsupported set

**Files:** `src/pmc_core/card.py`, `tests/contract/test_card.py`.

See "One decision I took" above for why. In `_valid_snapshot`, alongside the
existing field checks, require

```python
snapshot.unsupported == DECLARED_UNSUPPORTED
```

importing `DECLARED_UNSUPPORTED` from `pmc_core.snapshot` into the constants
tier of the import block. A snapshot failing it returns the existing
`_malformed_card()` — no new status string, no new reason code, because a
snapshot claiming to cover what the format declares unsupported is malformed in
exactly the sense that word already carries here.

Say so in the `#:` comment and in `render()`'s docstring: the card's
`unsupported` lines are a pass-through of `pmc_core.snapshot`'s single
declaration and are never independently authored, which is what
`test_declared_unsupported_matches_the_structure_card_markers` exists to keep
true.

**Test that proves it:**

```text
bazel test //tests/contract:card --lockfile_mode=error
```

with a new case:

```python
def test_undeclared_unsupported_set_returns_stable_malformed_card() -> None:
    """A snapshot may not author its own unsupported markers."""
    malformed = replace(
        _snapshot(),
        unsupported=("unsupported state=invented route=nowhere",),
    )

    assert render(malformed) == (
        "card-version=1\nstatus=unsupported reason=malformed-snapshot\n"
    )
```

Sabotage it once by hand before moving on: delete the new condition and confirm
this test goes red and the golden test stays green. If the golden test also
goes red, the condition was written in the wrong place.

---

## Step 4 — The real-PyMOL test into `tests/integration/`

**Files:** `tests/integration/test_card_real_pymol.py` (new),
[tests/integration/BUILD.bazel](tests/integration/BUILD.bazel) (new target).

`test_h02_candidate_a_snapshot_renders_as_a_complete_card` drives the renderer
with a genuinely extracted fixture rather than a hand-built one, which is the
only test that proves `extract()` and `render()` actually compose. It cannot
live in `tests/contract/`, which
[tests/contract/README.md:6-7](tests/contract/README.md#L6-L7) scopes as
PyMOL-free.

Carry it across under the production name
`test_extracted_snapshot_renders_as_a_complete_card`, keeping its five
assertions unchanged. Do **not** import `loaded_fixture` — take it as a
parameter and let [tests/integration/conftest.py](tests/integration/conftest.py)
supply it. That file's docstring documents at length why the import form was
tried and rejected (ruff `F811`, confirmed empirically); repeating the mistake
here would reintroduce it.

The target mirrors `:snapshot_round_trip`:

```text
py_test(
    name = "card_real_pymol",
    size = "large",
    timeout = "moderate",
    srcs = ["test_card_real_pymol.py"],
    main = "test_card_real_pymol.py",
    data = [
        "conftest.py",
        "testdata/h02_full_v1_fixture.pdb",
    ],
    # Launches real headless PyMOL, which supports one finish_launching
    # per interpreter; excluded from concurrent scheduling for the same
    # reason as :snapshot_round_trip.
    tags = ["exclusive"],
    deps = [
        ":snapshot_support",
        "@pypi//pymol_open_source_whl",
        "@pypi//pytest",
        "//src/pmc_core:pmc_core",
    ],
)
```

`:snapshot_support` is in the same package, so no visibility change is needed —
the `//tests/discovery/m02:__pkg__` entry it currently carries is removed in
step 5, not here.

Use the `os._exit` footer, not the `SystemExit` one the contract tests use:

```python
if __name__ == "__main__":
    _exit_code = pytest.main([__file__])
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(_exit_code)
```

Real PyMOL's headless shutdown can complete after pytest would otherwise exit
and overwrite a genuine failure with exit code 0. Copy the explanatory comment
from [test_snapshot_round_trip.py](tests/integration/test_snapshot_round_trip.py)'s
own footer rather than writing a new one.

**Test that proves it:**

```text
bazel test //tests/integration:card_real_pymol --lockfile_mode=error
```

**Watch:** [pyproject.toml:18](pyproject.toml#L18) sets
`filterwarnings = ["error"]`, which turns any warning PyMOL emits on import
into a failure. This is known territory for every new real-PyMOL target — if it
bites, add a narrow per-module ignore, never a global loosening.

---

## Step 5 — Delete `tests/discovery/m02/` and every reference to it

**Files:** delete `tests/discovery/m02/` (`BUILD.bazel`, `card_candidate.py`,
`conftest.py`, `test_card_candidate.py`);
[tests/discovery/README.md](tests/discovery/README.md);
[tests/integration/BUILD.bazel:3-31](tests/integration/BUILD.bazel#L3-L31);
[pyproject.toml:116-135](pyproject.toml#L116-L135).

Three references outlive the directory and each one breaks a gate if missed:

1. **`snapshot_support`'s visibility.**
   [tests/integration/BUILD.bazel:22-25](tests/integration/BUILD.bazel#L22-L25)
   grants `//tests/discovery/m02:__pkg__`; drop that entry, keeping
   `//tests/discovery/h02:__pkg__`, and drop the last clause of the comment
   above it (*"and tests/discovery/m02, whose card candidate test does the
   same to extract a real fixture's snapshot"*).
2. **pyrefly's `search-path`.**
   [pyproject.toml:131](pyproject.toml#L131) lists `"tests/discovery/m02"`, and
   the comment block above it names `card_candidate.py` twice. Remove the entry
   and edit both mentions out — a stale search-path entry pointing at a deleted
   directory is exactly what `pyrefly check` will complain about.
3. **`tests/discovery/README.md`.** Its closing sentence currently reads
   *"`h02/` retains only the still-open execution-boundary prototype, and `m02/`
   the still-open structure-card candidate."* Rewrite the paragraph the way it
   was rewritten for the snapshot: the card comparison is settled and shipped as
   `src/pmc_core/card.py` (master plan item 5), with its tests promoted into
   `tests/contract/test_card.py` and
   `tests/integration/test_card_real_pymol.py`. `h02/`'s executor prototype is
   then the only unpromoted thing left under the directory.

Note the dangling link on
[tests/discovery/README.md:4](tests/discovery/README.md#L4) to
`docs/codev/wave/pymol-copilot-full-v1-contracts.md`, a file deleted in
`fc6c9b8`. Fixing it is not part of this item, but you are editing the
paragraph next to it — mention it rather than silently leaving it.

**Test that proves it:**

```text
bazel query 'kind(rule, //tests/discovery/...)' --lockfile_mode=error  # only h02 and lemonade
grep -rn "card_candidate\|discovery/m02" . --exclude-dir=bazel-\* --exclude-dir=.git
bazel test //... --lockfile_mode=error
bazel run //tools/quality:pyrefly --lockfile_mode=error -- check
```

The `grep` returning nothing outside `plans/` is the load-bearing check: before
this step it returns the BUILD target, the pyrefly search path, the
`snapshot_support` visibility entry and two READMEs.

---

## Verification (end to end)

The full gate sequence from
[docs/development_setup.md:11-21](docs/development_setup.md#L11-L21):

```text
bazel version
bazel mod graph --lockfile_mode=error
bazel build //... --lockfile_mode=error
bazel test //... --lockfile_mode=error
bazel run //tools/bazel:check_dependency_boundaries --lockfile_mode=error
bazel run //tools/quality:ruff --lockfile_mode=error -- check .
bazel run //tools/quality:ruff --lockfile_mode=error -- format --check .
bazel run //tools/quality:pyrefly --lockfile_mode=error -- check
```

Then the five assertions specific to this change:

1. **The card is pure.** `grep -rn "import pymol\|from pymol" src/pmc_core/`
   returns nothing, and `//src/pmc_core:pmc_core` still declares **no `deps`**
   in its BUILD file. The boundary checker passing is necessary but not
   sufficient — it would also pass if a dep were added that happens to be
   allowed.
2. **The bytes did not move.** `//tests/contract:card` green, with
   `test_golden_card_has_stable_bytes` asserting a literal typed by hand, not
   generated from the implementation.
3. **Both seams still agree.** `test_data_and_runtime_callers_have_byte_parity`
   green. This is the whole mechanism by which items 13 and 14 cannot diverge,
   and it is worth keeping green even though neither caller exists yet.
4. **Real extraction still composes with rendering.**
   `//tests/integration:card_real_pymol` green.
5. **The prototype is gone.** `//tests/discovery/...` contains only `h02` and
   `lemonade` targets.

Finally, by hand, the thing no test asserts: read the rendered golden card cold
and ask whether it is what you want a model to see — whether the field set is
right, whether `max_atoms_per_state = 256` is the bound you want to ship, and
whether a truncated card makes its own truncation obvious enough that the model
would ask rather than guess. The card is the model's entire view of the
structure; if it does not read as sufficient, it is wrong regardless of what is
green. That judgement is easier now than after item 14 has generated a few
thousand samples against it.

CI evidence comes from the PR's three-OS matrix
([.github/workflows/bazel.yml](.github/workflows/bazel.yml)) — a bare branch
push runs nothing.

---

## Risks

| Risk | Where it shows | Mitigation |
|---|---|---|
| The golden bytes are regenerated from the new implementation instead of edited from the old ones, so the golden test asserts only that the code equals itself | Step 2, and it would pass | Type the new first line over the old literal by hand. The only permitted difference between prototype and production bytes is `candidate-1` → `1` |
| A "tidy-up" during the port silently changes rendering — reordering `_atom_line`'s field tuple, or touching `_number`'s `rstrip` chain | Step 1; caught by step 2, but only if step 2 is actually reached | The step-1 `diff` review: no hunk inside a function body. Land steps 1 and 2 together |
| `CARD_VERSION` as an int reads differently once items 13/14 stamp it into JSON next to `plan_version: "1"` | Item 14, long after this merges | Deliberate — it matches `SNAPSHOT_VERSION`, the module the card derives from. The seam functions are the only stamping path, so a later change to string form touches one constant and the golden literals, nothing structural |
| The pyrefly `search-path` entry for the deleted directory is missed, and `pyrefly check` fails only on the last gate command | Step 5 | It is one of three references listed explicitly in that step. Run the `grep` before the gate, not after |
| `filterwarnings = ["error"]` turns a PyMOL import warning into a failure on the new integration target | Step 4 | Known territory across every real-PyMOL target — narrow per-module ignore, never a global loosening |
| Windows `MAX_PATH` on the new real-PyMOL target | Step 4, windows-2025 leg only | `tests/integration/conftest.py` already calls `winstage.ensure_importable()` for the whole directory, and the target depends on `:snapshot_support`, which pulls `//tools/winstage:winstage`. Nothing extra needed — but confirm on the matrix, not locally |
| The fail-closed change in step 3 is written so broadly it rejects valid snapshots | Step 3 | Sabotage the condition by hand and confirm the golden test stays green while only the new test goes red |

---

## Delivery

One branch, one PR, following the item-3 and item-2 precedent. The first
commit on the branch is this plan, copied verbatim to
`plans/04-structure-card.md`; then one commit per step, so the PR reads as the
sequence it is. Steps 1 and 2 may share a commit.

Cross-review afterwards goes to Hannah, read-only, using the master plan's
review prompt at
[docs/master_plan.md:51-57](docs/master_plan.md#L51-L57).

---

## What review changed

Hannah's cross-review requested changes on five points, four of them in
`src/pmc_core/card.py` and one in the contract test. All five were real, and
all five are fixed on this branch. None of them moves a byte of the golden
card: `test_golden_card_has_stable_bytes` is unchanged and still green, which
is what keeps "the rendered bytes, apart from the version line" above true.

- **"Bounded" was only ever true per state.** `render()` emitted every state,
  and names, labels, representations and settings were unbounded too, so a
  trajectory or a fabricated snapshot could produce a card of any size no
  matter what `max_atoms_per_state` said. The bound is now real and stated in
  the module docstring: `max_states` (default 8) and `max_bonds` (default
  1024) join `max_atoms_per_state`, each omission carrying its own explicit
  marker line (`omitted-states reason=state-limit`, `omitted-bonds
  reason=bond-limit`) exactly as atom truncation already did. The
  caller-sized fields fail closed instead of being shortened: a text field
  over `_MAX_TEXT_CHARS`, more than `_MAX_REPS_PER_ATOM` representations or
  more than `_MAX_SETTINGS` settings renders the malformed card. Shortening
  was rejected as the alternative because a silently truncated name is one
  the model reads as whole.
- **The canonical atom order was not total.** Two atoms agreeing on all seven
  identity fields but differing in coordinates, color, label or
  representations kept their input order under Python's stable sort, so
  permuting the input moved their lines and could move canonical bond
  indices — the exact invariance the card claims. `_atom_key` now continues
  past the seven identity fields through every remaining rendered field.
  Atoms that agree on the *whole* key would render identical lines but still
  leave a bond's canonical endpoint decided by input position, so a state
  containing two of them is now rejected as malformed rather than rendered.
- **The schema-version gate accepted `True` and `1.0`.** `True == 1` and
  `1.0 == 1` in Python, and `_valid_snapshot` never checked the field's type,
  so a JSON snapshot with `"schema_version": true` rendered as
  `status=complete`. The gate now requires `_is_int` before equality.
- **`_is_number` could raise instead of answering.** `math.isfinite()` raises
  `OverflowError` for an int too large to convert to a float, and
  `from_json()` accepts such an int, so an occupancy of `10**400` crashed the
  renderer that exists to fail closed. The predicate is now written as a
  magnitude comparison against `_MAX_ABS_NUMBER`, which is exact and cannot
  overflow for any int, with `math.isfinite()` reached only for floats. This
  is also what bounds a number's rendered length.
- **The bond half of the ordering test was vacuous.** `_snapshot()` has one
  bond, so reversing its bond tuple was a no-op and the simultaneous settings
  reversal masked the gap — removing the renderer's bond sort left all 35
  cases green. Bonds and settings now have a test each, and the bond one uses
  a new three-atom, two-bond `_multi_bond_snapshot()` stored in the opposite
  of canonical order, asserting the canonical bond lines directly. Every fix
  above was sabotage-checked the way step 3 prescribes: each one removed in
  turn, confirming exactly the intended test goes red and no other.

### Second round

Hannah's re-review of the fixes above found one more, in the very key the
second fix had just widened.

- **Representation order still leaked into the canonical atom order.**
  `_atom_key` keyed the raw `atom.reps` tuple while `_atom_line` rendered
  `",".join(sorted(atom.reps))`, so a reordering the card deliberately hides
  could still decide which of two atoms sharing the identity prefix came
  first, and with it the canonical index of a bond endpoint. Two otherwise
  identical atoms were the sharper case: written with their representations
  in different orders they rendered `status=complete` with two identical atom
  lines, where writing them in the same order was correctly rejected as
  malformed.

  The repair is not another field added to the key but a change of kind: every
  key component is now the field's *rendered* form rather than its raw value.
  `_reps_text()` is the single place representations are canonicalized and
  both `_atom_line` and `_atom_key` go through it, so the sorted order and the
  rendered order can no longer drift; `_number_key()` keys a number by the
  value its own card text denotes, paired with that text, which keeps the atom
  order numeric and therefore readable while making two keys equal exactly
  when two atom lines are identical.

  That equivalence is what `_valid_snapshot`'s duplicate-atom check has always
  claimed and only now has: it closes the same leak in its remaining form,
  where two coordinates differing below the six decimals `_number()` renders
  were distinct to the key and identical in the card. Adding `sorted()` to the
  `reps` component alone would have fixed the reported case and left that one.

  Pinned by `test_equivalent_representation_order_produces_identical_card`
  (which asserts `status=complete` as well as byte equality, so the fix cannot
  pass by turning into a rejection),
  `test_indistinguishable_atoms_return_stable_malformed_card[representations-reordered]`
  and `test_atoms_differing_below_rendered_precision_are_malformed`.
  Sabotage-checked as before, each half separately: restoring the raw `reps`
  component fails exactly the first two, restoring the raw numeric components
  fails exactly the third, and no other case moves. The golden card is
  untouched.
