# Prompt builder

## Context

This is item 13 of
[docs/master_plan.md:465-475](docs/master_plan.md#L465-L475) — Martin's, sized
at ~2 days. It is the last shared-core contract the model pipeline waits on:
items 14, 15, 16, 17 and 18 all sit behind it, and at ~2 days it is the
cheapest item left on either developer's board.

It is also the first item since the shared core completed, so everything it
needs already exists as shipped, reviewed machinery:

- [`pmc_core.card`](src/pmc_core/card.py) — a pure, deterministic,
  bounded renderer with `CARD_VERSION = 1`
  ([card.py:51](src/pmc_core/card.py#L51)) and two caller seams,
  `render_for_data()` ([card.py:552](src/pmc_core/card.py#L552)) and
  `render_for_runtime()` ([card.py:565](src/pmc_core/card.py#L565)). The
  second one's docstring already names its caller: *"the seam the runtime
  prompt builder (master plan item 13) calls."* This item is what makes that
  promise real.
- [`pmc_core.plan`](src/pmc_core/plan.py) — the declarative tables the
  grammar must be derived from rather than transcribed:
  `COMMAND_ALLOWLIST` ([plan.py:951](src/pmc_core/plan.py#L951), five verbs),
  `COLOR_ALLOWLIST` ([plan.py:491](src/pmc_core/plan.py#L491), 177 names),
  `REPRESENTATION_ALLOWLIST` ([plan.py:676](src/pmc_core/plan.py#L676), 14
  names), plus `SELECTION_NAME_PREFIX`, `MAX_COMMANDS`,
  `MAX_EXPRESSION_TERMS` and `MAX_SELECTION_NAME_BODY`
  ([plan.py:39-51](src/pmc_core/plan.py#L39-L51)).
- [`pmc_core.parser`](src/pmc_core/parser.py) — `parse_pml()`
  ([parser.py:126](src/pmc_core/parser.py#L126)), the total default-deny
  parser that is the *only* authority on what text is legal. The grammar this
  item emits must be a strict under-approximation of it, never a second
  opinion.
- [`pmc_core.policy`](src/pmc_core/policy.py) — `evaluate_plan()`
  ([policy.py:415](src/pmc_core/policy.py#L415)), which re-derives its verdict
  independently of the parser.

### The language the grammar has to describe

Established by reading the parser and exercising it, not by assumption:

| Verb | Canonical form |
| --- | --- |
| `select` | `select copilot_<body>, <expression>` |
| `color` | `color <color>, <target>` |
| `show` | `show <representation>, <target>` |
| `hide` | `hide <representation>, <target>` |
| `orient` | `orient <target>` |

A `<target>` is either a selection name or an expression; the `copilot_`
prefix decides which, because no expression may begin with it
([plan.py:35-39](src/pmc_core/plan.py#L35-L39)).

Six terms — `chain <id>`, `resi <n>`, `resi <n>-<m>`, `resn <name>`,
`name <atom>`, `hetatm`, `polymer` — combine through
`SelectionExpression` → `AndClause` → `Factor`, which encodes `not`, then
`and`, then `or` structurally. There are **no parentheses and no `all`**: I
confirmed `parse_selection_expression("all")` is rejected. Every plan value
has exactly one rendering and every accepted text has exactly one parse
([plan.py:16-21](src/pmc_core/plan.py#L16-L21)), so a round trip through
`render_pml()` is byte-stable — verified by hand on a four-command plan.

### What the specification requires

[SPECIFICATION.md:488](SPECIFICATION.md#L488) defines the grammar contract:
*"Syntax grammar plus measured structure-conditioned terminals | **Never
substitutes for parser/policy**; current structure entities only where sound |
Capability probe at engine startup; ignored grammar is a hard engine failure |
Grammar version recorded with model/evaluation artifact | Accept/reject corpus
and with/without ablation."*

Two clauses bind this item directly. The grammar **never substitutes for
parser or policy** — it is a generation-time narrowing, and every byte it
helps produce is still parsed and policy-checked afterwards. And the grammar
**carries a version** that is recorded with the model artifact;
[SPECIFICATION.md:491](SPECIFICATION.md#L491) lists
*"prompt/card/grammar/error versions"* among the fields a model artifact
pins, which is where `PROMPT_VERSION` below comes from.

[SPECIFICATION.md:485](SPECIFICATION.md#L485) names the prompt builder as a
declared consumer of the structure card, and
[SPECIFICATION.md:382](SPECIFICATION.md#L382) puts the grammar in the shared
core alongside the card, plan, parser, policy, error and executor contracts.

**Outcome:** `src/pmc_core/grammar.py` and `src/pmc_core/prompt.py` as
importable production modules; `POLICY_VERSION`, `GRAMMAR_VERSION` and
`PROMPT_VERSION` alongside the existing `CARD_VERSION`; a `PromptV1` value
stamped with all four versions and rendered to canonical bytes; two caller
seams proved byte-identical; and an accept/reject corpus proving the emitted
grammar agrees with the parser.

### Decisions taken (from the clarifying questions)

These were answered directly and are not open.

1. **A typed value with a canonical text rendering.** `build_prompt()`
   returns a frozen `PromptV1` carrying its parts and its four versions, with
   a deterministic `text()` rendering. Golden-byte and parity tests pin
   `text()`; item 9 derives chat messages from it for Lemonade's
   `/api/v1/chat/completions`; item 14 stores `text()` in its records. One
   source, three consumers, one set of bytes to test.
2. **Four int version constants in `pmc_core`.** `POLICY_VERSION` in
   `policy.py`, `GRAMMAR_VERSION` in `grammar.py`, `PROMPT_VERSION` in
   `prompt.py`, joining `CARD_VERSION`. Ints, matching `SNAPSHOT_VERSION`,
   `CARD_VERSION`, `ERROR_ENVELOPE_VERSION` and `EXECUTOR_VERSION`; only
   `PROTOCOL_VERSION` is a string, and it versions the wire rather than a
   `pmc_core` contract. A `PROMPT_VERSION` exists so that a pure
   prompt-wording change is versioned — without it, rewording the instructions
   would silently produce a different prompt at the same stamped version.
3. **Syntax-only grammar, derived from the tables.** Structure-conditioned
   terminals are on the master plan's own cut list, and the specification
   qualifies them as *measured* — the measurement is item 16, which does not
   exist. The grammar is generated from `COMMAND_ALLOWLIST`,
   `COLOR_ALLOWLIST` and `REPRESENTATION_ALLOWLIST` so it cannot drift from
   the parser by transcription.
4. **Seams only, in `pmc_core`.** `build_for_data()` and
   `build_for_runtime()` mirror the card's own two seams, proved
   byte-identical. **Nothing in `src/pmc_data` or `src/pmc_agent` changes in
   this item**, exactly as item 5 decided for the card.

### Decisions I took, stated so you can overrule them

- **GBNF, not JSON schema.** The Lemonade spike proved both routes
  ([FINDINGS.md](../tests/discovery/lemonade/FINDINGS.md) Q1: the per-request
  `grammar` field enforced `root ::= "Berlin"` down to an exact forced token,
  and `response_format: json_schema` enforced an enum independently). GBNF is
  the right one here because the target language *is* text — a `.pml` plan —
  and a JSON schema would force the model to emit JSON that something then has
  to unwrap into `.pml`, adding a lossy layer between the grammar and the
  parser that actually adjudicates. If you would rather item 9 use
  `response_format`, say so now: it changes step 2 and nothing else.
- **The grammar bounds repetition, but loosely.** `MAX_COMMANDS` is 128 and
  `MAX_EXPRESSION_TERMS` is 32. GBNF can express a bounded repeat only by
  writing it out, so I will emit `command+` and `term`-level recursion rather
  than 128 unrolled alternatives, and let the parser enforce the real bound.
  This is the one place the grammar is deliberately *wider* than the parser;
  the accept/reject corpus in step 3 pins that direction, so the grammar can
  never become *narrower* than the parser without a test failing.
- **`POLICY_VERSION` starts at 1 and is not wired into `plan_version`.**
  `gold_case.ContractVersions.plan_version` is the literal string `"1"` in
  both checked-in gold cases and is described as *"the pmc_core plan/policy
  contract version"*. Deriving it from the new constant is a `pmc_data`
  change, and item 14 rewrites that module wholesale. I will note the
  connection in `POLICY_VERSION`'s own comment and leave the wiring to item 14.
- **The intent is bounded at the protocol's limit.** `PlanRequestV1.intent`
  is already constrained to 1–4096 characters
  ([protocol.py:458](src/pmc_core/protocol.py#L458),
  [protocol.py:510](src/pmc_core/protocol.py#L510)). The prompt builder
  re-checks that bound itself rather than trusting its caller, and fails
  closed on an intent outside it, because the dataset path never goes through
  the protocol at all.

---

## Delivery: one branch, one PR

Branch `feat/prompt-builder` off `main`, one pull request, linked to a new
issue per [CONTRIBUTING.md](CONTRIBUTING.md)'s first pull-request guideline.
Steps 1 and 2 may share a commit; every other step is its own.

After each step:

```
bazel test //... --lockfile_mode=error \
  && bazel run //tools/quality:ruff --lockfile_mode=error -- check . \
  && bazel run //tools/quality:ruff --lockfile_mode=error -- format --check . \
  && bazel run //tools/quality:pyrefly --lockfile_mode=error -- check
```

A step is not done until its named test passes **and** that test has been
sabotage-checked: break the thing it covers, confirm exactly that test goes
red and no other, restore. This is the convention items 5, 6 and 7 each
followed after review, and both of Hannah's rounds on #29 and #31 turned on
tests that could not actually fail.

---

## Step 1 — The three version constants

**Touches:** `src/pmc_core/policy.py`, `src/pmc_core/grammar.py` (new),
`src/pmc_core/prompt.py` (new), `src/pmc_core/BUILD.bazel`.

Add `POLICY_VERSION = 1` to `policy.py` with a comment explaining what a bump
means (any change to the allowlist tables or to `evaluate_plan`'s verdict for
an input it previously accepted). Create `grammar.py` and `prompt.py` as
module skeletons carrying `GRAMMAR_VERSION = 1` and `PROMPT_VERSION = 1`, each
with the same style of comment. Add both files to the `pmc_core` `srcs`,
keeping the list alphabetical — `card.py`, `errors.py`, `executor.py`,
`grammar.py`, `parser.py`, `plan.py`, `policy.py`, `prompt.py`,
`protocol.py`, `snapshot.py`.

**Test:** `tests/contract/test_prompt.py::test_every_stamped_version_is_a_non_bool_int`
asserts all four of `CARD_VERSION`, `GRAMMAR_VERSION`, `POLICY_VERSION` and
`PROMPT_VERSION` are `int` and not `bool`. This is the exact gap Hannah found
in the error envelope, where `True == 1` passed an equality-only version gate
([plans/05-error-envelope.md](plans/05-error-envelope.md), "What review
changed"); the constants are typed correctly from the first commit rather than
after a review round.

**Also proves the boundary holds:**
`bazel run //tools/bazel:check_dependency_boundaries` must stay green — the
new modules must not pull `langgraph` or the training stack into `pmc_core`,
which the checker forbids for that root.

---

## Step 2 — `src/pmc_core/grammar.py`: derive GBNF from the tables

**Touches:** `src/pmc_core/grammar.py`.

`build_grammar() -> str` emits one GBNF document generated from
`COMMAND_ALLOWLIST`, `COLOR_ALLOWLIST` and `REPRESENTATION_ALLOWLIST`. Nothing
in this module may restate a verb, a color, a representation or a term
spelling as a literal — every terminal is read from `pmc_core.plan` at build
time, which is what makes drift impossible rather than merely unlikely.

Shape:

```
root        ::= command+
command     ::= select-cmd | color-cmd | show-cmd | hide-cmd | orient-cmd
select-cmd  ::= "select " sel-name ", " expression "\n"
color-cmd   ::= "color " color ", " target "\n"
...
expression  ::= and-clause (" or " and-clause)*
and-clause  ::= factor (" and " factor)*
factor      ::= ("not " )? term
term        ::= chain-term | resi-term | resn-term | name-term
              | "hetatm" | "polymer"
color       ::= "actinium" | "aluminum" | ...      (177, generated)
```

Two properties the module must carry in its docstring, because they are what
makes the grammar safe: it is a **generation-time narrowing, never an
authority** — `pmc_core.parser` and `pmc_core.policy` still adjudicate every
byte afterwards — and it is deliberately **no narrower than the parser**, so
that a grammar bug can only ever let through text the parser then rejects,
never block text the parser would have accepted.

**Test:** `tests/contract/test_grammar.py::test_the_grammar_is_generated_from_the_allowlists`
asserts every name in `COLOR_ALLOWLIST` and `REPRESENTATION_ALLOWLIST` and
every verb in `COMMAND_ALLOWLIST` appears as a terminal, and — the half that
actually catches drift — that the grammar contains **no** color or
representation terminal absent from those tables. Adding a color to
`plan.py` must not require editing `grammar.py`; removing one must not leave
it behind.

**Sabotage:** replace the generated color alternation with a hand-written
list of three colors. The test must go red on the missing 174.

---

## Step 3 — The accept/reject corpus: the grammar agrees with the parser

**Touches:** `tests/contract/test_grammar.py`.

This is the step that makes the grammar trustworthy, and it is what
[SPECIFICATION.md:488](SPECIFICATION.md#L488) means by *"accept/reject corpus"*.

Write a small GBNF matcher in the test — not in production code — and drive
both it and `parse_pml()` over a corpus of plans:

- **Accepted by both:** one canonical plan per verb, a multi-term expression
  using every one of the six terms, `not`/`and`/`or` at each precedence
  level, a `resi` range, and a target given as an expression rather than a
  name.
- **Rejected by both:** a verb outside the allowlist, a color outside
  `COLOR_ALLOWLIST`, a representation outside `REPRESENTATION_ALLOWLIST`, a
  selection name without the `copilot_` prefix, parentheses, and `all`.

The assertion is directional, matching the decision above: **anything the
parser accepts, the grammar must accept.** The converse is allowed to fail —
the grammar may be wider — and the test states that asymmetry explicitly
rather than leaving a reader to infer it.

**Test:** `test_the_grammar_accepts_everything_the_parser_accepts` and
`test_the_grammar_rejects_what_the_language_has_no_spelling_for`.

**Sabotage:** drop `polymer` from the generated term alternation. The first
test must go red, proving the corpus exercises every term rather than only the
ones the golden plan happens to use.

---

## Step 4 — `src/pmc_core/prompt.py`: `PromptV1` and its canonical bytes

**Touches:** `src/pmc_core/prompt.py`.

```python
@dataclass(frozen=True)
class PromptV1:
    prompt_version: int
    card_version: int
    grammar_version: int
    policy_version: int
    card: str
    intent: str

    def text(self) -> str: ...
```

`build_prompt(card: str, intent: str) -> PromptV1` stamps all four versions
and validates in `__post_init__`, the way
[`ExecutionErrorV1`](src/pmc_core/errors.py) does: each version must be a
non-bool `int` equal to its module's constant, the intent must be a `str` of
1–4096 characters, and the card must be a `str` that starts with
`card-version=`. A prompt that exists at all is one that can be rendered.

`text()` emits the four version lines first, then the card, then the intent,
each on its own line, ending in exactly one newline — the same discipline the
card itself follows, so the result is diffable and a stamped version is
readable off the first lines without parsing.

**Test:** `test_the_prompt_carries_every_version_on_its_first_lines` and
`test_the_golden_prompt_has_stable_bytes`, a byte-for-byte literal over a
fixed card and intent. The golden test is what turns any future wording change
into a deliberate `PROMPT_VERSION` bump rather than an accident.

**Test:** `test_a_prompt_outside_its_bounds_is_refused`, parametrized over an
empty intent, a 4097-character intent, a non-`str` intent, a card not starting
with `card-version=`, and `True` passed as a version. Each must raise rather
than construct.

---

## Step 5 — The two seams and the parity test

**Touches:** `src/pmc_core/prompt.py`, `tests/contract/test_prompt.py`.

```python
def build_for_data(snapshot: ObjectSnapshot, intent: str) -> PromptV1:
    return build_prompt(render_for_data(snapshot), intent)


def build_for_runtime(snapshot: ObjectSnapshot, intent: str) -> PromptV1:
    return build_prompt(render_for_runtime(snapshot), intent)
```

These are the seams item 14 and items 8/9 will call, and they are what item
13's *"the dataset generator and the runtime must call this same code"*
reduces to while neither caller exists. They also finally consume
`render_for_runtime()`, whose docstring has been promising this item since
#29.

**This is the step to be careful about.** Hannah's review of item 6 rejected
exactly this kind of assertion twice: first as a tautology, then as a textual
co-occurrence check that *"is vacuous in the current tree"* and left the
regression it was written for undetectable
([plans/05-error-envelope.md](plans/05-error-envelope.md), "Second round").
The lesson carried forward is that a parity test with no real caller must
still be able to fail today.

The seam pattern satisfies that where a textual scan did not, because both
seams are real code executed by the test:

**Test:** `test_data_and_runtime_seams_have_byte_parity` builds the same
snapshot and intent through both seams and asserts
`build_for_data(...).text() == build_for_runtime(...).text()`, over a
parametrized set of snapshots — the golden fixture, a multi-state one, and one
that renders the malformed card — so parity is proved across all three card
outcomes rather than only the happy path.

**Sabotage:** make `build_for_runtime` append a single space to the intent.
The parity test must go red on every parametrized case. If it does not, the
test is not testing what it claims and the step is not done.

**Also carry forward item 6's scan**, now that it is no longer vacuous:
`tests/contract/test_errors.py` already resolves consumer call sites through
their import bindings. Extend that same scan to `build_prompt`, so a future
consumer that grows its own prompt assembly is caught by machinery that is
already proved to work rather than by a new textual check.

---

## Step 6 — READMEs and the master plan

**Touches:** `tests/contract/README.md`, `docs/master_plan.md`.

Record what `tests/contract` now owns, and move item 13 to `done` in the
blockers table, the Mermaid graph and its own `**State:**` line — which also
moves item 14 to `ready`. Re-run the consistency check from
[PR #39](https://github.com/urban233/pymol-copilot/pull/39): every tick mark
must match the state of the item it points at, each `ready`/`blocked` must
follow from its own prerequisites, and the graph classes must agree with the
table.

---

## Verification (end to end)

All seven gates from [docs/development_setup.md](docs/development_setup.md),
on all three operating systems via CI:

```
bazel build //... --lockfile_mode=error
bazel test //... --lockfile_mode=error
bazel run //tools/bazel:check_dependency_boundaries --lockfile_mode=error
bazel run //tools/quality:ruff --lockfile_mode=error -- check .
bazel run //tools/quality:ruff --lockfile_mode=error -- format --check .
bazel run //tools/quality:pyrefly --lockfile_mode=error -- check
```

Plus, specific to this item:

1. **Every new test sabotage-checked**, each fix removed in turn, confirming
   exactly the intended test goes red and no other.
2. **No PyMOL import anywhere in the two new modules** — like `card.py`, they
   are pure and add no Bazel dependency.
3. **`check_dependency_boundaries` green**, proving neither new module pulled
   `langgraph` or the training stack into `pmc_core`.

---

## Risks

- **The grammar drifts from the parser.** Mitigated structurally: the grammar
  is generated from the same tables the parser reads, and step 3 pins the
  direction of any divergence. The residual risk is a term whose *spelling*
  the generator gets wrong while the table is right — which is what the
  accept/reject corpus covers, and why step 3's sabotage removes a term rather
  than a color.
- **The parity test passes for the wrong reason.** This is the live risk, not
  a theoretical one: it is the exact failure Hannah found twice on item 6.
  Step 5's sabotage is the specific control, and the step is not done until
  the sabotage has been run.
- **`PROMPT_VERSION` ossifies a bad prompt.** The golden-byte test makes any
  wording change loud, which is the point, but it also means iterating on
  prompt wording during item 16's evaluation will mean deliberate version
  bumps. That is the correct trade — a silently changed prompt at a stamped
  version is what would corrupt a dataset — but it should be expected rather
  than discovered.
- **GBNF may not be the shape item 9 wants.** Flagged above as an overrulable
  decision. Changing it touches step 2 only; the prompt, the seams and the
  parity test are unaffected.
