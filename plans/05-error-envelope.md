# Error envelope

## Context

This is item 6 of [docs/master_plan.md:167-180](docs/master_plan.md#L167-L180)
— ~2 days, Martin, and one of only two items the plan's dependency graph
currently marks `ready`. It gates item 8 (the LangGraph request graph, which
feeds an error envelope into each repair attempt) and item 11 (output and
diagnostics, which must produce *"a bounded, actionable message — no
tracebacks, no plan text leaking through an error"*).

Today nothing in the repository normalizes a PyMOL failure. The two places
that touch one both stringify it and move on:
[src/pmc_data/verifier.py:402-406](src/pmc_data/verifier.py#L402-L406) catches
bare `Exception` and writes `f"evaluator error: {error}"` into a free-text
`invalid_reason`; [src/pmc_data/generate.py:225-231](src/pmc_data/generate.py#L225-L231)
does the same with `str(error)`. Neither is machine-readable, neither is
bounded, and the two produce different text for the same underlying failure.
That is precisely the divergence this item exists to prevent.

**Outcome:** `src/pmc_core/errors.py` — one typed envelope, one total
normalizer, a stable category vocabulary, and a corpus of real PyMOL error
strings captured from real PyMOL and checked in, with a real-PyMOL conformance
test that fails when a PyMOL upgrade rewords one of them.

---

## Decisions taken (from the clarifying questions)

These were answered directly and are not open.

1. **`errors.py` gets its own type; `protocol.py` is not touched.**
   [src/pmc_core/protocol.py:683-729](src/pmc_core/protocol.py#L683-L729)
   already has a `FailureEnvelopeV1(category, message, retryable)` used by
   `FailedPlanResponseV1`. That type describes a **request-level** failure on
   the wire. The new type describes a **per-command execution** failure. They
   are different things and stay separate, which also keeps this item purely
   additive against a wire contract that PRs #24, #27 and #28 already depend
   on.
2. **The corpus lives in `tests/contract/testdata/pymol_errors/`.** The
   intent's *"under tests/data/"* means "as test data", not "inside the
   `src/pmc_data` test package" — `tests/data/` is already that package, and a
   `pmc_core` corpus does not belong under it. Placing it beside the contract
   test that consumes it matches `test_card.py` and `test_snapshot.py`.
3. **A committed capture script plus a real-PyMOL conformance test** keep the
   corpus honest, mirroring how snapshot and card proved themselves against
   real PyMOL rather than against their own expectations.
4. **The byte-equality requirement is satisfied today by a single-normalizer
   assertion**, because neither consumer exists yet. See
   [Step 5](#step-5--contract-tests) and
   [Deliberately deferred](#deliberately-deferred).

---

## What driving real PyMOL actually showed

I ran two throwaway probes against real headless PyMOL **3.2.0a** (the version
in this repository's Bazel closure) before writing the steps below, because
every step depends on which channel actually carries a failure. The probes
were deleted; their findings are recorded here because they change the design.

### Finding 1 — `cmd.do()` cannot detect a failure at all

`cmd.do()` returned `None` for **every** case, including a plainly invalid
color and a plainly invalid representation. It never raises. Its error text
goes to PyMOL's own output stream, written from C at the file-descriptor
level, on PyMOL's thread — so a Python-level `contextlib.redirect_stderr`
misses it entirely, and even an `os.dup2` capture races the command. Under
that capture, `cmd.sync()` additionally deadlocked with
`cmd.sync() timed out (lock_attempt)`.

This matters beyond this item: **`cmd.do()` is what
[src/pmc_data/verifier.py:363](src/pmc_data/verifier.py#L363) currently uses to
execute a plan.** Any per-command outcome reporting built on `cmd.do()` is
reporting nothing.

### Finding 2 — the typed `cmd.*` API raises synchronously and cleanly

Driving the same failures through `cmd.color`, `cmd.show`, `cmd.select` and
`cmd.orient` raised immediately, with nothing written to any stream:

| Case | Result |
| --- | --- |
| `cmd.color("notacolor", "all")` | raises `pymol.CmdException: Unknown color.` |
| `cmd.color("red", "copilot_missing")` | raises `pymol.CmdException: Error: Invalid selection name "copilot_missing".\ncopilot_missing<--` |
| `cmd.show("notarep", "all")` | raises **`pymol.parsing.QuietException`**, message embeds the full 24-entry representation list over 5 lines |
| `cmd.select("copilot_c", "chain ZZZZ")` | **returns `0`** — no exception |
| `cmd.orient("copilot_c")` on an empty selection | **returns `None`** — no exception |

So the normalizer's input is the typed API's exception, not a captured stream.

### Finding 3 — two unrelated exception types, and multi-line messages

`pymol.CmdException` and `pymol.parsing.QuietException` are different types
from different modules. A normalizer that catches only `CmdException` silently
misses every representation error. This is the concrete justification for the
intent's *"`unknown` as a catch-all that preserves bounded text rather than
dropping it"*.

Messages are also **multi-line** and **embed the offending input** — the
`show` message carries a 5-line table, and the selection-name message carries
a `copilot_missing<--` caret line. Both must be flattened and bounded.

### Finding 4 — some failures are not exceptions at all

A zero-atom `select` and an `orient` over an empty selection both **succeed**.
They are outcomes, not errors. `errors.py` therefore normalizes *raised*
failures only, per the intent's wording (*"a raw PyMOL execution failure"*).
The empty-selection outcome belongs to item 4, which already promises
*"selection counts"*, and to item 16's *"empty-selection rate"*.

> **Hand-off to item 4 (Hannah).** Findings 1 and 4 are load-bearing for the
> sidecar executor's *"report per-command outcome by index"*: it must dispatch
> through the typed `cmd.*` API rather than `cmd.do()`, and it must treat a
> zero-atom result as a reported outcome rather than expect an exception.
> Recorded here rather than acted on, because item 4 is not this item.

---

## Decisions I took, stated so you can overrule them

- **`ERROR_ENVELOPE_VERSION = 1`, an `int`**, matching
  [src/pmc_core/snapshot.py:32](src/pmc_core/snapshot.py#L32)'s
  `SNAPSHOT_VERSION = 1` rather than `protocol.py`'s string
  `PROTOCOL_VERSION = "1"`. Both are `pmc_core` schema versions; the wire
  version is a different thing.
- **Quoted spans in a message are redacted.**
  `Invalid selection name "copilot_missing".` normalizes to
  `invalid selection name "<redacted>".` `ParseRejection`'s own docstring at
  [src/pmc_core/parser.py:88-90](src/pmc_core/parser.py#L88-L90) already
  commits to *"never quotes enough of the input to leak a plan back through an
  error"*, and item 11 repeats it. Redaction also makes the message a function
  of the *category* rather than of the plan, which is what makes byte-equality
  across call sites achievable at all. **This is the decision most worth
  overruling** — it trades some diagnostic value for the leak guarantee, and
  the structured `verb` and `command_index` fields recover most of that value.
- **Category names are snake_case stable strings**, following
  [src/pmc_core/policy.py:53-81](src/pmc_core/policy.py#L53-L81) and
  `parser.py`'s rejection categories, exported as module constants rather than
  an enum, for the same reason those two are.
- **`MAX_MESSAGE_BYTES = 256`.** The longest real message observed was the
  `show` representation table at 291 bytes; 256 forces the truncation path to
  be exercised by a genuine case rather than by a synthetic one.
- **The corpus is JSON, one file per verb**, sorted keys, LF endings, one
  trailing newline — the same determinism discipline `render_pml()` and the
  snapshot serializer already hold themselves to.

---

## Step 1 — The typed envelope

**Files:** `src/pmc_core/errors.py` (new)

Add the version constant, the category vocabulary, and the frozen dataclass.
Validation happens in `__post_init__`, so an envelope that exists at all is
well-formed — the same invariant `plan.py` holds.

```python
ERROR_ENVELOPE_VERSION = 1
MAX_MESSAGE_BYTES = 256

CATEGORY_UNKNOWN_COLOR = "unknown_color"
CATEGORY_UNKNOWN_REPRESENTATION = "unknown_representation"
CATEGORY_INVALID_SELECTION_NAME = "invalid_selection_name"
CATEGORY_SELECTION_SYNTAX = "selection_syntax"
CATEGORY_UNKNOWN = "unknown"

CATEGORIES: frozenset[str] = frozenset({...})


@dataclass(frozen=True)
class ExecutionErrorV1:
    envelope_version: int
    command_index: int
    verb: str
    category: str
    message: str
```

`__post_init__` rejects: a version that is not `ERROR_ENVELOPE_VERSION`; a
`command_index` outside `0 <= i < plan.MAX_COMMANDS`; a `verb` absent from
`plan.COMMAND_ALLOWLIST`; a `category` absent from `CATEGORIES`; a `message`
that is empty, exceeds `MAX_MESSAGE_BYTES`, or contains a character outside
printable ASCII. Reusing `COMMAND_ALLOWLIST` as the verb authority means the
envelope cannot name a verb the language does not have.

**Test that proves it:** `tests/contract/test_errors.py::test_envelope_rejects_*`
— one negative case per rejected condition, plus a positive construction.

---

## Step 2 — Message normalization

**Files:** `src/pmc_core/errors.py`

A private, total `_normalize_message(raw: str) -> str`, applied in this order:

1. Redact every double-quoted span to `"<redacted>"`.
2. Drop any line ending in PyMOL's `<--` caret marker.
3. Collapse every whitespace run, including newlines, to one space; strip.
4. Lowercase the leading `Error:` / `Selector-Error:` prefix into the flat
   form, so the same failure spells the same way whichever prefix PyMOL used.
5. Replace any character outside printable ASCII with `?`.
6. Truncate to `MAX_MESSAGE_BYTES` on a character boundary, appending `...`
   inside the bound rather than overflowing it.

Every step is deterministic and input-length-bounded. No regular expressions
with backtracking on untrusted text, for the reason
[src/pmc_core/plan.py:24-27](src/pmc_core/plan.py#L24-L27) already gives.

**Test that proves it:** parametrized cases for each rule, plus
`test_normalization_is_idempotent` (normalizing a normalized message returns
it unchanged) and `test_normalization_never_exceeds_the_bound` over the whole
corpus.

---

## Step 3 — The normalizer

**Files:** `src/pmc_core/errors.py`

```python
def normalize(
    error: BaseException, *, command_index: int, verb: str
) -> ExecutionErrorV1:
```

Classification reads an **ordered table** of `(category, exception type or
None, substring)` rules and takes the first match; anything unmatched becomes
`CATEGORY_UNKNOWN` with its bounded text preserved, never dropped. The table
is a module constant so a reviewer can read the whole classification in one
screen.

`normalize` never raises: a `verb` outside the allowlist or an out-of-range
`command_index` is a programming error in the *caller*, so those still raise
from `__post_init__` — but no property of the *exception* can make it raise,
which is what makes it safe to call from an `except` block.

**Test that proves it:**
`test_every_category_is_reachable_from_a_corpus_entry`,
`test_an_unrecognised_exception_becomes_unknown_with_its_text_preserved`, and
`test_normalize_never_raises_on_an_arbitrary_exception` over a list of
unrelated exception types.

---

## Step 4 — Capture the corpus from real PyMOL

**Files:** `tests/integration/capture_pymol_errors.py` (new, `py_binary`),
`tests/contract/testdata/pymol_errors/{select,color,show,hide,orient}.json`
(new), `tests/integration/BUILD.bazel`

The script drives real headless PyMOL through the **typed `cmd.*` API** (per
Finding 2), one deliberately broken command per case per verb, and records
each raised failure:

```json
{
  "pymol_version": "3.2.0a",
  "cases": [
    {
      "case": "unknown_color",
      "verb": "color",
      "exception_type": "pymol.CmdException",
      "raw_message": "Unknown color.",
      "expected": {
        "envelope_version": 1, "command_index": 0, "verb": "color",
        "category": "unknown_color", "message": "unknown color."
      }
    }
  ]
}
```

Cases must cover, per verb: an argument outside the allowlist, a target naming
a selection that does not exist, and a malformed selector — plus at least one
case that lands in `unknown`, so the catch-all is corpus-backed rather than
hypothetical. Note in the script's docstring which cases are **unreachable
through a policy-valid plan** (an unknown color cannot get past
`parser.py`'s `unsupported_color`); they stay in the corpus as normalizer
evidence, marked, because the normalizer is a boundary and must hold for input
the boundary above it is supposed to have stopped.

The script writes deterministically: sorted keys, two-space indent, LF, one
trailing newline. Re-running it on an unchanged PyMOL must produce a
byte-identical file.

**Test that proves it:** re-running the script leaves `git status` clean.

---

## Step 5 — Contract tests

**Files:** `tests/contract/test_errors.py` (new),
`tests/contract/BUILD.bazel`, `tests/contract/README.md`

Hermetic, no PyMOL import. Loads the corpus and asserts:

1. **Byte stability** — for every corpus entry, `normalize()` produces exactly
   the recorded `expected` envelope. This is the intent's byte-equality
   requirement in the form that is meaningful today.
2. **One normalizer** — `pmc_data` and `pmc_agent` both resolve
   `pmc_core.errors.normalize` to the *same object*, so no second
   implementation can drift into existence unnoticed. This is the assertion
   that will be replaced by a genuine two-call-site test when items 8 and 14
   land.
3. **Every category is corpus-backed** and every corpus entry's category is in
   `CATEGORIES` — neither set may contain a member the other does not.
4. **No redaction escape** — no envelope message produced from the corpus
   contains any `copilot_` substring, the one token guaranteed to be
   plan-derived.

**Test that proves it:** the module itself, wired as
`//tests/contract:errors`.

---

## Step 6 — Real-PyMOL conformance test

**Files:** `tests/integration/test_errors_real_pymol.py` (new),
`tests/integration/BUILD.bazel`

Re-drives every corpus case against live PyMOL and asserts the raised
exception type and raw message still match what is checked in. Tagged
`exclusive`, matching the four existing real-PyMOL targets in that package,
and importing `winstage` first as
[tests/integration/conftest.py](tests/integration/conftest.py) does.

It also asserts the recorded `pymol_version` matches `cmd.get_version()[0]`,
so a PyMOL upgrade produces one clear failure naming the version rather than
five confusing message mismatches.

**Test that proves it:** the module itself. Sabotage check — hand-edit one
`raw_message` in the corpus and confirm this test fails.

---

## Step 7 — Wiring

**Files:** `src/pmc_core/BUILD.bazel`, `tests/contract/BUILD.bazel`,
`tests/integration/BUILD.bazel`

- Add `"errors.py"` to the `pmc_core` `py_library` `srcs`.
- Add `py_test(name = "errors")` to `tests/contract`, with the corpus as
  `data`, and `":errors"` to that package's `test_suite`.
- Add the `py_binary` and the `exclusive`-tagged `py_test` to
  `tests/integration`.
- `pyproject.toml` needs **no** change: `tests` is already in
  `project-includes`, and nothing here is a bare sibling module needing a
  `search-path` entry.

> **Merge note.** Both `src/pmc_core/BUILD.bazel` (`"card.py"` vs
> `"errors.py"` in `srcs`) and `tests/contract/BUILD.bazel` (`:card` vs
> `:errors` in the suite) are also touched by PR #29, on adjacent
> alphabetical lines. Expect a one-line conflict on whichever merges second.

---

## Verification (end to end)

```
bazel test //... \
  && bazel run //tools/quality:ruff -- check . \
  && bazel run //tools/quality:pyrefly -- check
```

plus, once:

```
bazel run //tests/integration:capture_pymol_errors   # corpus unchanged
git status --porcelain                                # must be empty
```

CI must be green on ubuntu-24.04, macos-15 and windows-2025 — Windows
specifically, because the new real-PyMOL target goes through `winstage` and
issue #12.

---

## Risks

- **The corpus is PyMOL-version-locked.** Mitigated, not removed, by the
  conformance test in step 6: an upgrade turns a silent wrong normalization
  into a loud test failure naming the version.
- **Redaction may over-redact.** `show`'s representation list is not
  quoted, so it survives and gets truncated; a future PyMOL that quotes it
  would lose it. The truncation test over the corpus will show this.
- **`QuietException` is not part of PyMOL's documented API.** The ordered
  rule table matches on substring as well as type, and the `unknown`
  catch-all covers a rename, so a PyMOL refactor degrades the category
  rather than crashing the normalizer.
- **The `unknown` catch-all can absorb a category that deserved a name.**
  Item 16's per-category reporting will surface that as an
  `unknown`-heavy breakdown. Accepted for V1.

---

## Deliberately deferred

- **The true cross-call-site byte-equality test.** It needs the dataset
  pipeline of item 14 and the runtime path of item 8. Step 5's
  one-normalizer assertion is the standing guard until then, and is recorded
  as such in the plan document and in the test's own docstring — see the
  caution now carried under item 6 in the master plan (PR #30).
- **Retry classification.** Whether a category is retryable is item 8's
  decision — it owns the repair-attempt budget — not this module's.
- **Empty-selection reporting.** Finding 4: an outcome, not an error, and
  item 4's to report.

---

## What implementation changed

Recorded after the fact, as `plans/03` records its own divergences. Nothing
here contradicts the four answered questions; each is something driving real
PyMOL settled that the plan had guessed at.

- **`orient` has no selection failure that raises.** Step 4 assumed each verb
  would yield an undefined-selection case and a malformed-selector case.
  Measured against PyMOL 3.2.0a, `cmd.orient` returns `None` for an undefined
  selection name, for a malformed selector and for `None` itself. Its only
  raising failure is an argument PyMOL cannot coerce, so `orient.json` holds
  exactly that one case — which conveniently is also the corpus's only
  `unknown` entry, satisfying step 4's requirement that the catch-all be
  corpus-backed rather than hypothetical. The finding is carried in
  `pymol_error_cases.py`'s docstring as a hand-off to item 4.
- **Redaction covers single quotes as well as double.** The plan said
  double-quoted spans. PyMOL quotes selection names with `"` but representation
  names with `'`, and both are plan-derived, so redacting only one would have
  been a leak the `copilot_`-substring test could not catch. Both styles now
  redact, and both normalize to the same double-quoted `"<redacted>"` spelling.
  An unterminated quote redacts to end of text rather than being left alone.
- **`MAX_MESSAGE_BYTES = 256` no longer claims to be exercised by a real
  case.** The 291-byte figure was the *raw* `show` message; once whitespace is
  collapsed it is 226 bytes, comfortably inside the bound. The bound stays at
  256 deliberately — item 8 feeds this message to a repair attempt, and the
  list of valid representations is the part that makes the repair succeed — and
  the truncation path is covered by an explicitly synthetic case instead.
- **A shared case table, not an import of the capture script.** Steps 4 and 6
  would have had the conformance test import the capture binary. The broken
  commands now live in their own `tests/integration/pymol_error_cases.py`,
  imported as a bare sibling module by both, so a case added to the capture is
  covered by the conformance test without a second edit. `pyproject.toml`'s
  pyrefly `search-path` comment records it alongside `snapshot_support.py`.
- **The corpus crosses packages as a filegroup.** Step 6 assumed
  `tests/integration` could `glob` the corpus by relative path. Bazel forbids
  `..` in a glob, so `tests/contract` exports it as `:pymol_error_corpus`.
- **The conformance test must exit through `os._exit`.** With the ordinary
  `raise SystemExit(pytest.main(...))` ending, a deliberately corrupted corpus
  message made pytest report `1 failed` while Bazel still reported the target
  `PASSED` — real PyMOL's shutdown overrides the process status. The other
  real-PyMOL modules in this package already end with `os._exit` for this
  reason; this one now does too. Caught by step 6's sabotage check, which is
  the only reason it was caught at all.

## What review changed

Seven findings from the review on #31, each reproduced before it was fixed and
each re-checked by sabotaging the fix and watching the new test fail.

- **The capture binary reported success after detecting failure.** `main`
  returned 1 for a case that stopped failing, but `sys.exit(1)` after
  `cmd.do("quit")` is overridden by real PyMOL's shutdown, so `bazel run`
  printed success and left a partial corpus behind. The binary now exits
  through `os._exit`, like every other real-PyMOL module in the package, and
  writes nothing at all when a case went silent — a corpus missing a case it
  claims to cover is worse than no new corpus.
- **Truncation could split the redaction token, breaking idempotence.**
  `"x" * 243 + '"secret"' + "y" * 10` normalized to 256 bytes ending in
  `"<redacted`, whose stray quote a second pass redacted again into a
  different 255-byte string. `_truncation_boundary` now moves the cut back to
  the start of a token it would have split, so the documented cross-boundary
  byte stability holds. The all-`x` truncation case could never have caught
  this; the interaction has its own cases now.
- **Unquoted plan text survived.** Redaction covered quoted spans and caret
  lines only, so `normalize(RuntimeError("command copilot_secret failed"), …)`
  kept `copilot_secret` — and the `unknown` category deliberately preserves
  text, which is exactly where such a message lands. Any space-delimited token
  carrying `SELECTION_NAME_PREFIX` now redacts whole. The prefix is the one
  token a plan is guaranteed to contribute, since `pmc_core.plan` accepts no
  selection name without it.
- **`str(error)` could raise.** `__str__` is user-defined; a `BaseException`
  whose `__str__` raised propagated out of `normalize` and lost the original
  failure — the one thing this boundary exists to prevent. `_message_text`
  now returns None instead, which `normalize_message` already handles.
  `exception_type_name` is total for the same reason, since a metaclass can
  make `__module__` raise too; it reports `UNSPECIFIED_TYPE_NAME`.
- **The envelope version was checked by equality, not by type.** `True`,
  `1.0` and `1+0j` all compare equal to 1 and constructed, and the last made
  `to_dict()` something `json` cannot encode. `envelope_version` is now
  type-checked exactly as `command_index` already was.
- **The consumer assertion was tautological.** Asserting that two imported
  modules are not None, and that `pmc_core.errors.normalize` is the
  `normalize` imported from `pmc_core.errors`, could not fail. Neither
  consumer references the normalizer yet, so no test here can prove both
  *reach* it; what is provable now is that neither has grown a second one, so
  the contract test scans both packages' sources for a competing `normalize`,
  `normalize_message` or `ExecutionErrorV1`, and requires any consumer that
  does call `normalize(` to name `pmc_core.errors`. That second assertion is
  vacuous until item 14 and item 8 land, and turns into the real
  cross-subsystem check the moment either does.
- **The captured index and verb were fed back as the normalizer's input.**
  `test_the_normalizer_reproduces_the_captured_envelope` read
  `expected["command_index"]` and `expected["verb"]` out of the very envelope
  it then compared against, so two of the five recorded fields asserted
  nothing: a corpus edited from index 1 to 0 stayed green. Both now come from
  `pymol_error_cases.cases()`, the same table the capture drove and the
  conformance test re-drives, which `tests/contract` reaches through a
  widened `visibility` on that PyMOL-free `py_library`. Both sabotages now
  fail the target.

### Second round

Hannah's re-review found two more, one on each side of the corpus.

- **The conformance run was not replaying the capture's environment.** The
  corpus is captured with `-qck`, but `test_errors_real_pymol.py` launched
  with `-qc`, this package's usual arguments. `-k` skips the user's pymolrc
  files and plugins, so without it a startup script could pre-create
  `copilot_undefined`, define `notacolor`, or monkeypatch a `cmd` method, and
  the conformance run would pass or fail for a reason unrelated to the PyMOL
  drift it exists to detect. The arguments now live in one place,
  `pymol_error_cases.LAUNCH_ARGUMENTS`, beside the case table and for the
  same reason: the capture and the conformance test must not be able to
  disagree about what the corpus describes.

  Two checks rather than the shared constant alone, because passing a flag
  and having it take effect are different claims. The capture writes its
  launch arguments into every corpus file, and the hermetic contract test
  fails when they are not `LAUNCH_ARGUMENTS`, so a recapture taken under
  other arguments cannot quietly become the new baseline. The conformance
  test then reads `pymol.invocation.options` and asserts the live process
  really did load no plugins and no pymolrc. Dropping the `-k` from the
  constant fails exactly one test on each path.

  Recapturing changed nothing but the new field: every captured message is
  byte-identical, which is independent evidence the corpus had been captured
  under `-qck` all along and only the replay was wrong. Regenerating twice
  is still byte-identical.

  The other real-PyMOL modules in `tests/integration/` still launch with
  `-qc`. They are not replaying checked-in evidence, so the same argument
  does not apply to them, and changing them belongs to whichever item cares.

- **The consumer assertion was still textual, and still vacuous.** The
  previous round replaced a tautology with a scan requiring any consumer
  that calls `normalize(` to name `pmc_core.errors` somewhere in the file.
  That is co-occurrence, not resolution: `from another_module import
  normalize` next to an unrelated `import pmc_core.errors` passes, and so
  does a bare comment naming this module, which leaves exactly the
  divergent-normalizer regression it was written for undetectable.

  The scan now parses the source and resolves each call target through the
  module's own import bindings, so what is compared is the callable the call
  reaches rather than strings that happen to share a file. It follows the
  four shapes a consumer could plausibly use -- plain `from`-import, aliased
  `from`-import, module attribute, fully qualified -- and reports anything
  resolving elsewhere, including a normalizer the module defines itself.
  Indirection through a computed target is not followed and the docstring
  says so rather than implying otherwise.

  Deferring the assertion was the alternative Hannah offered, and the reason
  against it is that item 8 and item 14 would then have to remember. What
  made deferral tempting was the vacuity, and that is addressed directly:
  `_SCAN_CASES` runs the scan over nine sources that do call a normalizer,
  five legitimate and four divergent, every one of them naming something
  called `normalize` and three also naming `pmc_core.errors`. The mechanism
  is proved now and arms itself when either call site lands. Sabotage: a
  scan that reports nothing fails exactly the four divergent cases, and one
  that skips import resolution fails five of the nine.
