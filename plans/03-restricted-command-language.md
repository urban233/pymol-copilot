# Restricted command language

## Context

This is item 2 of [docs/master_plan.md:98-121](docs/master_plan.md#L98-L121) —
"**Biggest single item**", ~4–6 days, and the one the same document calls
**not cuttable** at [docs/master_plan.md:413](docs/master_plan.md#L413):
*"Item 2, the real command language — without it there is no product, only a
hardcoded string."*

Today `pmc_core` is exactly that hardcoded string.
[src/pmc_core/plan.py:21-27](src/pmc_core/plan.py#L21-L27) pins the entire
language to three constants, `SelectOperation.__post_init__` raises unless the
selection name is literally `copilot_selection` and the expression is literally
`chain A`, and `ActionPlan.__post_init__` accepts exactly two operations in
exactly one order. The parser is genuinely total and the policy genuinely
default-deny, but both are total and default-deny over a language with one
sentence in it.
[docs/master_plan.md:17](docs/master_plan.md#L17) states it plainly: *"There is
no general verb allowlist anywhere in the code."*

Four downstream items are blocked on this. Item 6 (error envelope) must capture
real PyMOL failures "for each supported verb". Item 13 (prompt builder) emits a
grammar. Item 14 (dataset generation) is "Program-first for each verb" and
cannot generalize past chain-A/red until the verbs exist. Item 16's untuned
baseline is measured against that dataset.

**Outcome:** a real restricted language — five verbs, an explicit allowlist
table, a total parser returning a typed plan or a typed indexed rejection, and a
policy that re-derives the same verdict from the typed values without trusting
the parser. Every `FIXTURE_*` constant and `initial_fixture_plan()` gone from
`pmc_core`. `render_pml()` still canonical and idempotent — in fact more
strongly so than today, because the grammar below gives every plan exactly one
spelling.

### Decisions taken (from the clarifying questions)

These were answered directly and are not open:

1. **Targets accept an inline expression or a name.** `color`, `show`, `hide`
   and `orient` take either a full selection expression or a bare identifier
   that an **earlier `select` in the same plan** created. Not a mix of the two
   in one target — a target is one or the other.
2. **`orient` takes a target, always.** There is no zero-argument command in the
   language.
3. **No parentheses. PyMOL precedence: `not` > `and` > `or`.** This follows the
   master plan's *"combined with and/or/not — nothing else"*.
4. **`initial_fixture_plan()` is deleted too**, not just the `FIXTURE_*`
   constants, and its four call sites are rewritten.
5. **All 178 PyMOL built-in color names** are the color allowlist.
6. **All 14 PyMOL representations** are the `show`/`hide` allowlist — the same
   tuple the snapshot extractor uses, so the two lists can never drift.
7. **Selection names require a `copilot_` prefix.**
8. **Bounds: 128 commands, 32 terms per expression, 16 KiB of input.**

### Decisions I took, stated so you can overrule them

These are token-level details nothing in the repository specifies. Each is the
conservative reading; none is expensive to widen later, because
[SPECIFICATION.md:488](SPECIFICATION.md#L488) permits *"Additive syntax only
within a major version"*.

- **Chain IDs are case-sensitive, keywords are not.** Verbs and keywords are
  lowercase-only (as today). Arguments keep their own domain's case: `chain A`
  and `chain a` are different chains in the PDB, and `resn ALA` is uppercase
  because residue names are.
- **`resi` is non-negative.** `[0-9]{1,6}`, so `resi 1-100` splits on its one
  hyphen without ambiguity. Negative residue numbers (expression tags) and
  insertion codes (`52A`) are **not** supported in V1. Recorded as a limitation,
  not forgotten.
- **Atom names are `[A-Z0-9]{1,4}`.** Primed nucleic-acid atom names (`C1'`,
  `O2'`) are therefore unsupported — the apostrophe is denied by the quoting
  rule, and relaxing that would reopen quote handling across the whole parser.
  Also recorded as a limitation.
- **`resn` is `[A-Z0-9]{1,3}`**, matching the master plan's own `resn XXX`.
  Five-character CCD ligand codes are out of V1.
- **`chain` is `[A-Za-z0-9]{1,4}`.**
- **`_deepsalmon` is excluded** from the 178, leaving 177. It is PyMOL's one
  underscore-prefixed internal alias and is not a name a user would type.
- **The allowlist table lives in `plan.py`**, alongside the typed values it
  governs, rather than in a fourth module — you named three files and the table
  is ~60 lines.

### The one thing that makes the grammar unambiguous

The `copilot_` prefix decision has a consequence worth stating, because it is
load-bearing rather than merely tidy. A target is either a name or an
expression, and the parser must decide which from the first token. Every
expression starts with `chain`, `resi`, `resn`, `name`, `hetatm`, `polymer` or
`not`; every name starts with `copilot_`. The two sets cannot overlap, so no
lookahead and no backtracking is needed — and `name` as a keyword can never be
confused with a name as a reference. Dropping the prefix rule later would
require replacing that with a real disambiguation rule.

---

## The language

```text
plan        := command ("\n" command)* "\n"
command     := select | color | show | hide | orient
select      := "select " sel_name ", " expression
color       := "color " color_name ", " target
show        := "show " representation ", " target
hide        := "hide " representation ", " target
orient      := "orient " target

target      := sel_name | expression
sel_name    := "copilot_" [a-z0-9_]{1,24}
color_name  := one of COLOR_ALLOWLIST        (177 names)
representation := one of REPRESENTATION_ALLOWLIST   (14 names)

expression  := and_clause (" or " and_clause)*
and_clause  := factor (" and " factor)*
factor      := ["not "] term
term        := "chain " [A-Za-z0-9]{1,4}
             | "resi " [0-9]{1,6} ["-" [0-9]{1,6}]
             | "resn " [A-Z0-9]{1,3}
             | "name " [A-Z0-9]{1,4}
             | "hetatm"
             | "polymer"
```

Everything else is rejected. No comments, no quoting, no continuations, no tabs,
no `\r`, no repeated spaces, no leading or trailing whitespace, no case
variation in keywords — all of which `parser.py` already rejects today and
which this change preserves verbatim.

Because there are no parentheses and no optional whitespace, **every plan has
exactly one spelling.** That is what makes the round-trip property below
provable in both directions rather than just one.

---

## Two hard constraints the rewrite must not break

**1. The policy sabotage test matches source text literally.**
[tests/contract/test_policy_sabotage.py:47-56](tests/contract/test_policy_sabotage.py#L47-L56)
copies `pmc_core` to a temp directory, finds this exact string in `policy.py`,
flips `allowed=False` to `allowed=True`, re-runs `test_policy.py` in a
subprocess and requires it to fail:

```python
        case _:
            return PolicyDecision(
                operation_index=operation_index,
                allowed=False,
                reason=REASON_UNSUPPORTED_OPERATION_TYPE,
            )
```

Eight spaces before `case _:`. If that block is reformatted, renamed, or moved
out of a `match` at function-body indentation, the test raises
`AssertionError("default-deny branch was not found")` — loudly, not silently.
The new `policy.py` keeps `PolicyDecision`, its three field names,
`REASON_UNSUPPORTED_OPERATION_TYPE`, and that block byte-for-byte. The new
`test_policy.py` keeps a test named
`test_non_operation_value_is_denied_by_default`, which is the name the sabotage
test greps for in the subprocess output.

**2. `pmc_core` must never import PyMOL.**
[tests/adversarial/test_parser_rejections.py:264-271](tests/adversarial/test_parser_rejections.py#L264-L271)
asserts `"pymol" not in sys.modules` before and after parsing. So the 177 color
names are a **frozen literal tuple in source**, generated once from
`cmd.get_color_indices()` and then never read from PyMOL at runtime. Step 8 adds
the conformance test that keeps the frozen copy honest.

---

## Existing tests that become wrong, not merely incomplete

Worth knowing before starting, because these will look like regressions:

| Test | Why it breaks |
|---|---|
| `test_expression_like_content_is_rejected` — `chain A and resn ALA`, `chain A or chain B` | Both become **valid**. They move to positive round-trip cases. |
| `test_unknown_verbs_are_rejected` — `hide red, copilot_selection` | `hide` becomes a known verb; this now rejects as `unsupported_representation`, not `unknown_verb`. |
| `test_truncated_input_is_rejected` — `select copilot_selection, chain A\n` | A one-command plan is now valid. |
| `test_extra_commands_are_rejected` (whole test) | Multi-command plans are the point. Replaced by a bounds test at 129 commands. |
| Every `test_*_rejects_unsupported_*` in `test_plan.py` | Rewritten against the allowlist rather than the three constants. |

---

## Step 1 — Selection expressions and the allowlist tables

**Files:** [src/pmc_core/plan.py](src/pmc_core/plan.py) (rewrite),
`tests/contract/test_plan.py` (rewrite),
[tests/contract/BUILD.bazel](tests/contract/BUILD.bazel).

Term types, one frozen dataclass each, each validating its own charset in
`__post_init__` and each with a `render()` returning its one canonical spelling:

```python
ChainTerm(chain_id)          ResiTerm(first, last)     ResnTerm(residue_name)
NameTerm(atom_name)          HetatmTerm()              PolymerTerm()
```

`ResiTerm.last` is `None` for the single-residue form and renders `resi 5`;
otherwise `resi 5-40`, with `first <= last` enforced.

Precedence is encoded **structurally** rather than re-derived at render time:

```python
Factor(term, negated)  # "not chain A" | "chain A"
AndClause(factors)  # joined with " and "
SelectionExpression(clauses)  # joined with " or "
```

`not` > `and` > `or` falls out of the nesting, and `render()` is a two-level
join. This is what makes rendering canonical by construction: there is no
expression value with two spellings, so idempotence is not a property that has
to be tested into existence.

Then the tables, as module constants:

```python
COLOR_ALLOWLIST: tuple[str, ...]  # 177 names, sorted
REPRESENTATION_ALLOWLIST: tuple[str, ...]  # the 14 from REP_NAMES, in order
SELECTION_NAME_PREFIX = "copilot_"
MAX_COMMANDS = 128
MAX_EXPRESSION_TERMS = 32
MAX_INPUT_BYTES = 16384
```

Copy `REPRESENTATION_ALLOWLIST` from
[tests/discovery/h02/harness.py:63-77](tests/discovery/h02/harness.py#L63-L77)
in that file's order (`lines, sticks, spheres, dots, surface, mesh, nonbonded,
nb_spheres, cartoon, ribbon, labels, slice, ellipsoids, volume`) so the snapshot
extractor and the command language read the same sequence. Item 3 promotes that
harness into `src/pmc_core/snapshot.py`; when it does, the two should import one
tuple, not keep two.

Generate `COLOR_ALLOWLIST` once and paste the result in — do not hand-type it:

```text
bazel run //tools/quality:ruff -- --version   # any target that materializes @pypi
python -c "
import pymol; pymol.finish_launching(['pymol','-qck'])
from pymol import cmd
names = sorted(n for n, _ in cmd.get_color_indices() if not n.startswith('_'))
print(len(names)); print(names)"
```

against the Bazel-materialized `pymol_open_source_whl` site-packages. On PyMOL
3.2.0.2 this yields **177** names, all matching `[a-z][a-z0-9_]*`, longest
`rutherfordium` at 13 characters. Record the PyMOL version in a comment above
the tuple — the list is a claim about a specific version.

**Test that proves it:**

```text
bazel test //tests/contract:plan --lockfile_mode=error
```

`test_plan.py` covers: each term type renders its canonical form; each rejects
its out-of-charset input with `ValueError`; precedence nests as
`chain A and resi 1-100 or hetatm` → `(chain A and resi 1-100) or hetatm`;
`not hetatm and polymer` → `(not hetatm) and polymer`; `render()` is idempotent;
values are frozen; `COLOR_ALLOWLIST` has 177 entries with no duplicates and none
starting with `_`; `REPRESENTATION_ALLOWLIST` equals the harness tuple.

---

## Step 2 — One operation dataclass per verb, and the allowlist table

**Files:** [src/pmc_core/plan.py](src/pmc_core/plan.py) (continued),
`tests/contract/test_plan.py` (continued).

```python
SelectOperation(selection_name, expression)  # expression only, never a name
ColorOperation(color, target)
ShowOperation(representation, target)
HideOperation(representation, target)
OrientOperation(target)

type TARGET = NamedSelection | SelectionExpression
type OPERATION = (
    SelectOperation
    | ColorOperation
    | ShowOperation
    | HideOperation
    | OrientOperation
)
```

Keep the house alias convention exactly as
[src/pmc_core/plan.py:103-105](src/pmc_core/plan.py#L103-L105) has it —
SCREAMING_SNAKE `type` statement plus the
`globals()["Operation"] = OPERATION` shim — and add the same shim for `TARGET`.

`NamedSelection(name)` is a thin frozen wrapper so a target is a typed value in
both cases rather than a bare `str` that could be mistaken for text.

The explicit allowlist table the master plan asks for, keyed by verb:

```python
@dataclass(frozen=True)
class VerbRule:
    verb: str
    argument_forms: tuple[str, ...]  # e.g. ("representation", "target")
    operation_type: type


COMMAND_ALLOWLIST: Mapping[str, VerbRule]  # MappingProxyType, 5 entries
```

`argument_forms` is the declarative part: `select` is
`("selection_name", "expression")`, `color` is `("color", "target")`, `show` and
`hide` are `("representation", "target")`, `orient` is `("target",)`. Both the
parser (step 3) and the policy (step 5) read this table. That is deliberate and
does not weaken the independence requirement: what must not be shared is the
*decision path*, and the policy re-derives its verdict from the typed operation's
own fields rather than from anything the parser computed. One declarative table
with two independent readers is the point.

`ActionPlan.__post_init__` now enforces:

- `1 <= len(operations) <= MAX_COMMANDS`;
- every `NamedSelection` appearing in a target was created by a `SelectOperation`
  **earlier in the same plan** — the generalization of today's
  select-then-color cross-reference at
  [src/pmc_core/plan.py:137-141](src/pmc_core/plan.py#L137-L141);
- a selection name is not created twice.

`render_pml()` is unchanged in shape: `"\n".join(op.render()) + "\n"`.

**Test that proves it:**

```text
bazel test //tests/contract:plan --lockfile_mode=error
```

Per verb: construction, `render()`, and rejection of a bad argument. Plan level:
a forward reference (`color red, copilot_x` before the `select`) raises; a
duplicate selection name raises; 128 operations construct and 129 raise; the
empty plan raises.

---

## Step 3 — Rewrite the parser

**Files:** [src/pmc_core/parser.py](src/pmc_core/parser.py) (rewrite),
`tests/contract/test_parser.py` (new),
[tests/contract/BUILD.bazel](tests/contract/BUILD.bazel).

`parse_pml(text) -> ActionPlan | ParseRejection` keeps its signature and its
totality contract. `ParseRejection` keeps `command_index`, `category`, `message`.
The existing input-level rejections in
[`_split_lines`](src/pmc_core/parser.py#L140-L189) and
[`_tokenize_command`](src/pmc_core/parser.py#L192-L265) carry over as-is — they
are good and they are not what this change is about.

New structure:

1. input level: size, empty, `\r`, `\t`, `#`, `\\\n`, blank lines
2. line count against `MAX_COMMANDS`
3. per line: strip-equality, quote, continuation, double-space checks
4. verb lookup in `COMMAND_ALLOWLIST` → `unknown_verb` on miss
5. argument split driven by that verb's `argument_forms`
6. `_parse_target` → name (prefix rule) or `_parse_expression`
7. `_parse_expression`: split on `" or "`, then `" and "`, then optional
   `"not "`, then `_parse_term`; count terms against `MAX_EXPRESSION_TERMS`
8. build `ActionPlan`, converting its `ValueError` into a rejection

Also expose `parse_selection_expression(text) -> SelectionExpression |
ParseRejection` as public API — step 6 needs it, and item 13's grammar work will
too.

**Totality.** Every `ValueError` a `plan.py` constructor can raise is caught at
its call site and converted. Do not add a blanket `except Exception` — the fuzz
test in step 4 is what proves totality, and a blanket catch would make it prove
nothing.

The stable rejection categories, each of which gets a negative test in step 4:

```text
empty_input              input_too_large          command_count
alternate_whitespace     comment                  quoting
continuation             unknown_verb             invalid_syntax
unsupported_color        unsupported_representation
invalid_selection_name   invalid_selection_expression
expression_too_complex   undefined_selection
```

**Test that proves it:**

```text
bazel test //tests/contract:parser --lockfile_mode=error
```

`test_parser.py` is the positive suite. Per verb, at least one round trip in
both directions:

```python
assert parse_pml(text).render_pml() == text  # text -> plan -> text
assert parse_pml(plan.render_pml()) == plan  # plan -> text -> plan
```

Cover: each verb; a name target and an expression target for each of
`color`/`show`/`hide`/`orient`; each of the six term forms; `resi N` and
`resi N-M`; `not`; `and`; `or`; a mixed-precedence expression; a multi-command
plan that defines two selections and uses both.

---

## Step 4 — Rebuild the adversarial suite

**Files:** [tests/adversarial/test_parser_rejections.py](tests/adversarial/test_parser_rejections.py)
(rewrite), `tests/adversarial/test_denied_forms.py` (new),
`tests/adversarial/test_parser_totality.py` (new),
[tests/adversarial/BUILD.bazel](tests/adversarial/BUILD.bazel).

Keep the existing house style exactly: literal adversarial strings inline, one
`@pytest.mark.parametrize` per category, explicit `ids=[...]` naming the
technique, no corpus data files, no generator.

**`test_parser_rejections.py`** — one test function per rejection category
listed in step 3, each asserting both `isinstance(result, ParseRejection)` and
the exact `category`, and — for per-command categories — the exact
`command_index`, which is the part the current suite mostly does not check.

**`test_denied_forms.py`** — the corpus the master plan names explicitly, each
case asserting a rejection **and** `"pymol" not in sys.modules` afterwards:

| Group | Examples |
|---|---|
| Python-evaluating | `select copilot_x, __import__('os')`, `color red, eval("1")`, `select copilot_x, chain A and exec(...)`, `python`, `run`, backtick forms |
| Shell metacharacters | `select copilot_x, chain A; rm -rf /`, `` ` ``, `$(...)`, `\|`, `&&`, `>`, newline-escaped forms |
| File paths | `load /etc/passwd`, `save ~/out.pse`, `cd ..`, `select copilot_x, chain A, /tmp/x`, UNC and `C:\` forms |
| Load/save/fetch | `load`, `save`, `fetch 1abc`, `png`, `set_key`, `system`, `cmd.do` |
| Plugin invocations | `plugin load x`, `import pmg_tk`, `extend`, `alias`, `@script.pml`, `spawn` |

Every one of these fails at step 4 of the parser (`unknown_verb`) or step 5
(`invalid_syntax`) — but the test asserts the *outcome*, not the path, so the
suite keeps its meaning if the parser is restructured.

**`test_parser_totality.py`** — the fuzz fixture
[SPECIFICATION.md:486](SPECIFICATION.md#L486) asks for (*"Corpus round-trip,
grammar-generation, fuzz, and adversarial fixtures"*). No new dependency: a
`random.Random(seed)` with a fixed seed, drawing a few thousand strings from an
alphabet that includes every keyword, every metacharacter, `\x00`, `\r`, `\t`,
`\\`, quotes, high Unicode and long runs. Assert only that `parse_pml` returns
an `ActionPlan | ParseRejection` and never raises. Print the seed on failure so
a red run is reproducible.

Add `denied_forms` and `parser_totality` `py_test` targets and extend the
`test_suite(name = "all", ...)` list.

**Test that proves it:**

```text
bazel test //tests/adversarial/... --lockfile_mode=error
```

---

## Step 5 — Rewrite the policy

**Files:** [src/pmc_core/policy.py](src/pmc_core/policy.py) (rewrite),
`tests/contract/test_policy.py` (rewrite).
[tests/contract/test_policy_sabotage.py](tests/contract/test_policy_sabotage.py)
is **not edited** — it must pass unchanged.

`PolicyDecision`, `PlanDecision`, `evaluate_operation`, `evaluate_plan` keep
their names and shapes. Reason codes:

```text
REASON_ALLOWED_OPERATION               (replaces REASON_ALLOWED_FIXTURE_OPERATION)
REASON_UNSUPPORTED_OPERATION_TYPE      (must not be renamed -- sabotage test)
REASON_UNSUPPORTED_SELECT_ARGUMENTS    REASON_UNSUPPORTED_COLOR_ARGUMENTS
REASON_UNSUPPORTED_SHOW_ARGUMENTS      REASON_UNSUPPORTED_HIDE_ARGUMENTS
REASON_UNSUPPORTED_ORIENT_ARGUMENTS    REASON_UNSUPPORTED_PLAN_SHAPE
REASON_UNDEFINED_SELECTION_REFERENCE
```

The point of this module is that it assumes the typed value may be a lie. Today
[src/pmc_core/policy.py:11-17](src/pmc_core/policy.py#L11-L17) admits the
current check is vacuous because construction already enforces everything; after
this change it stops being vacuous, because the surface is wide enough for a
constructor bypass to produce something meaningfully wrong.
`tests/contract/test_policy.py` already builds exactly such values with
`object.__new__` + `object.__setattr__`, and that pattern carries forward.

So `evaluate_operation` re-derives, per operation, without consulting the
parser: the verb is in `COMMAND_ALLOWLIST`; the color is in `COLOR_ALLOWLIST`;
the representation is in `REPRESENTATION_ALLOWLIST`; the selection name matches
the prefix rule; every term in every expression matches its charset; the term
count is within `MAX_EXPRESSION_TERMS`. `evaluate_plan` re-derives the plan-level
rules: `1..MAX_COMMANDS`, and every `NamedSelection` defined by an earlier
`SelectOperation`.

The `case _:` block at the end of `evaluate_operation` stays byte-identical to
the text quoted above.

**Test that proves it:**

```text
bazel test //tests/contract:policy //tests/contract:policy_sabotage \
  --lockfile_mode=error
```

`test_policy.py` keeps `test_non_operation_value_is_denied_by_default` under
that exact name, plus: one allow case per verb; one deny case per reason code,
each built via the constructor bypass; determinism
(`evaluate_plan(p) == evaluate_plan(p)`); and `"pymol" not in sys.modules`.

The sabotage target passing is the real gate here. If it reports *"default-deny
branch was not found"*, the `case _:` block was reformatted — fix the block, not
the test.

---

## Step 6 — Widen the wire protocol

**Files:** [src/pmc_core/protocol.py](src/pmc_core/protocol.py),
[tests/contract/test_protocol.py](tests/contract/test_protocol.py).

This is not optional scope creep — it is a break the earlier steps cause.
[src/pmc_core/protocol.py:362](src/pmc_core/protocol.py#L362) hard-codes
`len(command_list) == 2` and
[src/pmc_core/protocol.py:370](src/pmc_core/protocol.py#L370) hard-codes
`case (SelectOperation() as select, ColorOperation() as color)`. Any valid
one-command or three-command plan would be rejected on the wire.

- `_plan_commands` gains a `case` per verb.
- `_decode_plan` accepts `1..MAX_COMMANDS` commands.
- `_decode_command` decodes all five verbs with strict exact-field-set checks,
  as the existing two already do.
- A target encodes as `{"kind": "name", "value": "copilot_core"}` or
  `{"kind": "expression", "value": "chain A and polymer"}`, and the expression
  form decodes through `parse_selection_expression` from step 3. Routing the
  wire's expression text back through the same total parser means the wire
  cannot express an operation the parser would have refused — a decoder that
  rebuilt the term tree directly from JSON would be a second, unaudited entry
  point into the typed contract.
- Every `ValueError` from a `plan.py` constructor still surfaces as
  `ProtocolDecodeError`, as at
  [src/pmc_core/protocol.py:398-401](src/pmc_core/protocol.py#L398-L401).

**Test that proves it:**

```text
bazel test //tests/contract:protocol --lockfile_mode=error
```

Extend the existing suite: a five-command plan round-trips; a one-command plan
round-trips; a 129-command plan is rejected; an unknown verb on the wire is
rejected; an expression string that the parser would reject is rejected as
`ProtocolDecodeError` rather than crashing; unknown fields per verb are rejected.

---

## Step 7 — Delete `initial_fixture_plan()` and fix its four callers

**Files:** [src/pmc_core/plan.py](src/pmc_core/plan.py) (removal),
[src/pmc_server/lifecycle.py:102](src/pmc_server/lifecycle.py#L102),
[src/pmc_data/gold_case.py:254](src/pmc_data/gold_case.py#L254),
[src/pmc_data/generate.py:198](src/pmc_data/generate.py#L198),
[src/pmc_data/verifier.py:340](src/pmc_data/verifier.py#L340),
[tests/unit/test_server_lifecycle.py](tests/unit/test_server_lifecycle.py),
`tests/data/test_generate.py`, `tests/data/test_gold_case.py`,
`tests/data/test_gold_case_verifier.py`,
`tests/integration/test_command.py`, `tests/integration/test_loopback_transport.py`.

Three of the four callers are in `pmc_data` and all three want the *same* plan.
Define it once there, constructed from `pmc_core` types:

```python
# src/pmc_data/gold_case.py
CHAIN_A_RED_PLAN: ActionPlan = ActionPlan(
    operations=(
        SelectOperation(
            selection_name="copilot_selection",
            expression=SelectionExpression(
                clauses=(AndClause(factors=(Factor(ChainTerm("A"), False),)),)
            ),
        ),
        ColorOperation(color="red", target=NamedSelection("copilot_selection")),
    )
)
```

`generate.py` and `verifier.py` import it. This keeps the drift guard at
[src/pmc_data/verifier.py:341](src/pmc_data/verifier.py#L341) meaningful: it
compares checked-in gold-case JSON against `pmc_core`'s own `render_pml()`
output, which is exactly what it was written to catch. Moving the fixture into
the package that owns fixtures is the point — no fixture-shaped helper survives
in `pmc_core`.

`lifecycle.py` builds its own two-operation plan inline. It is a different
package, it is the only caller there, and item 8 replaces the whole module with
the LangGraph request graph — do not invent a shared helper for one call site
that is scheduled for deletion.

The rendered bytes must not change:
`"select copilot_selection, chain A\ncolor red, copilot_selection\n"`. Every
checked-in gold case, every `FIXTURE_PML` constant in the test suite, and
`src/pmc_data/gold_cases/*.json` continue to match. If they do not, the grammar
has drifted from the fixture and that is a step-1 or step-2 bug, not a data
problem — do not regenerate the gold cases to make it pass.

**Test that proves it:**

```text
bazel test //... --lockfile_mode=error
```

This is the first point at which the whole suite is green. See the note below.

---

## Step 8 — Prove the frozen allowlists against real PyMOL

**Files:** `tests/integration/test_real_pymol_allowlist.py` (new),
[tests/integration/BUILD.bazel](tests/integration/BUILD.bazel).

The 177 colors and 14 representations are a frozen snapshot of a specific PyMOL
build. Nothing currently stops them drifting, and a drifted allowlist has a
nasty failure mode: a plan that the parser accepts and the policy allows, which
then fails at execution. That is precisely the case
[SPECIFICATION.md:487](SPECIFICATION.md#L487) means by denial needing to happen
before execution.

One direction only:

- every name in `COLOR_ALLOWLIST` is in `cmd.get_color_indices()`;
- every name in `REPRESENTATION_ALLOWLIST` is accepted by `cmd.show` on a loaded
  fixture without error.

Do **not** assert the reverse. A newer PyMOL adding a colour must not turn the
build red — widening the allowlist is a deliberate act under
[SPECIFICATION.md:487](SPECIFICATION.md#L487)'s *"Expansion requires security
review"*, not something CI should demand.

Follow the real-PyMOL target pattern from
[tests/integration/BUILD.bazel:53-77](tests/integration/BUILD.bazel#L53-L77):
`size = "large"`, `timeout = "moderate"`, `tags = ["exclusive"]`, deps on
`@pypi//pymol_open_source_whl` and `//tools/winstage:winstage`, and the
`os._exit(pytest.main([__file__]))` main-block that
`test_real_pymol_command.py` uses — `raise SystemExit` there can be overridden
by PyMOL's headless cleanup and silently report 0 on a real failure.

**Test that proves it:**

```text
bazel test //tests/integration:real_pymol_allowlist --lockfile_mode=error
```

---

## A note on step ordering and a red tree

Steps 1–7 are one atomic change to the typed contract and ship as **one PR**.
There is no ordering that avoids a red window: rewriting `plan.py` breaks
`policy.py`, `protocol.py`, `lifecycle.py`, `generate.py`, `gold_case.py` and
`verifier.py` at the same moment, because all six import the types or the
constants being replaced. Plan 01 had the same shape and said so —
*"step 4 breaks two gates that only step 5 repairs"*.

So: each step above names the focused target that must pass **once that step is
finished**, and `bazel test //...` is expected to be red from the first edit in
step 1 until step 7 completes. Do not try to keep the full suite green in
between; you will end up writing shims you then delete. Commit one commit per
step so the PR reads as the sequence it is.

---

## Verification (end to end)

The full gate sequence from
[docs/development_setup.md](docs/development_setup.md), all seven commands:

```text
bazel mod graph --lockfile_mode=error
bazel build //... --lockfile_mode=error
bazel test //... --lockfile_mode=error
bazel run //tools/bazel:check_dependency_boundaries --lockfile_mode=error
bazel run //tools/quality:ruff --lockfile_mode=error -- check .
bazel run //tools/quality:ruff --lockfile_mode=error -- format --check .
bazel run //tools/quality:pyrefly --lockfile_mode=error -- check
```

Then the six assertions specific to this change:

1. **No fixture constants survive in the core.**
   `grep -rn "FIXTURE_\|initial_fixture_plan" src/pmc_core/` returns nothing.
   (`FIXTURE_INTENT`/`FIXTURE_SNAPSHOT`/`FIXTURE_MANIFEST` in
   [src/pmc_server/lifecycle.py:24-28](src/pmc_server/lifecycle.py#L24-L28) and
   [src/pmc_client/command.py:20-22](src/pmc_client/command.py#L20-L22) are the
   request-side fixture and stay — they belong to items 8 and 10.)
2. **The sabotage test still catches a disabled default-deny.**
   `bazel test //tests/contract:policy_sabotage` passes. If it reports
   *"default-deny branch was not found"*, the `case _:` block was reformatted.
3. **Round trip holds in both directions** for every verb —
   `//tests/contract:parser` green.
4. **Every rejection category has a negative case** and every named denied form
   is denied with zero execution — `//tests/adversarial/...` green.
5. **The parser is total** — `//tests/adversarial:parser_totality` green over a
   few thousand fuzzed inputs.
6. **The frozen allowlists match real PyMOL** —
   `//tests/integration:real_pymol_allowlist` green.

Finally, by hand, the thing no test asserts: read `plan.py`'s allowlist table
cold and check that the set of things a model could emit and have accepted is
the set you actually intend to ship. The table is the security boundary; if it
does not read as one, it is wrong regardless of what is green.

CI evidence comes from the PR's three-OS matrix
([.github/workflows/bazel.yml](.github/workflows/bazel.yml)) — a bare branch
push runs nothing.

---

## Risks

| Risk | Where it shows | Mitigation |
|---|---|---|
| The `case _:` block is reformatted by `ruff format` or by hand, silently disarming the sabotage test | `//tests/contract:policy_sabotage`, step 5 | The test raises `AssertionError("default-deny branch was not found")` rather than passing vacuously. Run that one target immediately after touching `policy.py`, not at the end |
| The 177-name colour tuple is hand-typed and contains a typo | Step 8, after all the interesting work is done | Generate it with `cmd.get_color_indices()` and paste; never type it. Step 8 catches a typo, but late |
| Precedence is re-derived at render time instead of encoded structurally, breaking idempotence for some expression | Step 1 | The `SelectionExpression → AndClause → Factor` nesting makes a two-spelling value unconstructible. If you find yourself writing a precedence table in `render()`, the types are wrong |
| A blanket `except Exception` is added to `parse_pml` to make the fuzz test pass | Step 3/4 | That converts a crash into a silent rejection and makes the totality test prove nothing. Catch `ValueError` at each constructor call site only |
| `filterwarnings = ["error"]` turns a PyMOL import warning into a failure in the new real-PyMOL target | Step 8 | Known territory — narrow per-module ignore, never a global loosening |
| Windows `MAX_PATH` on the new real-PyMOL target | Step 8, windows-2025 leg only | Depend on `//tools/winstage:winstage` and call `winstage.ensure_importable()` before importing PyMOL, exactly as `test_real_pymol_command.py` does (issue #12) |
| The rendered fixture bytes shift and the checked-in gold cases stop matching | Step 7 | That is a grammar bug in step 1/2. Fix the grammar; do not regenerate `src/pmc_data/gold_cases/*.json` to make it pass |
| Scope creeps into `show`/`hide` with no target, `all`, object names, or parentheses | Throughout | All four were considered and excluded. `SPECIFICATION.md:488` allows additive syntax within a major version, so they are cheap to add later and expensive to remove |
| The denied-forms corpus tests the parser's internal path rather than the outcome | Step 4 | Assert `ParseRejection` plus `"pymol" not in sys.modules`. Assert the exact `category` only where it is genuinely stable |
