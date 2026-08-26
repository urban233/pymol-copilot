# Design readiness delivery plan

**Status:** Draft
**Owner:** Martin Urban (`urban233`)
**Brief:** [`SPECIFICATION.md`](../../../SPECIFICATION.md)
**Design:** [shared core](../design/shared-core/design.md), [runtime application](../design/runtime-application/design.md), and [model development](../design/model-development/design.md) (all Draft)
**Project tracker:** Not used
**Supersedes:** Not applicable
**Last reviewed:** 2026-08-24

## Changes since last review

- New plan. It defines only the evidence needed to make the first design
  decisions ready for acceptance.

## Current milestone

**Outcome:** The team has reproducible reference-environment and
restricted-plan evidence to decide the first shared contracts without blocking
either developer on the other’s implementation.

**Evidence:** Two bounded discovery reports, their versioned fixtures, and an
integration decision that records which contract questions are resolved or
remain open.

**Target:** Not committed.

## Current work

Hannah and Martin each have one discovery-work slot and independently review
the other developer's work. The lanes below are ready for assignment, but they
remain discovery work rather than product implementation tasks.

| ID | Capability lane | Risk | Status | Blocked by |
|---|---|---|---|---|
| D-01 | Runtime reference-environment evidence | High | Ready | None |
| D-02 | Restricted-plan evidence | High | Ready | None |

### D-01: Runtime reference-environment evidence

- **Owner and reviewer:** Hannah Kullik (`kullik01`); Martin Urban
  (`urban233`) reviews independently.
- **Outcome and acceptance:** Pin one Open-Source PyMOL reference environment
  and report loopback companion startup, `cmd.extend()` responsiveness,
  relevant-state reconstruction in a fresh sidecar, and `.pse` recovery after
  deliberate partial application. Include modified, multi-state, and
  alternate-location fixtures. Every probe records its environment identity,
  procedure, result, and unsupported behavior. The work does not claim
  platform qualification or enable live apply.
- **Integrates with:** The snapshot, sidecar, process, and recovery contracts
  in the runtime and shared-core designs.
- **Validation:** Reproducible probe run, fixture comparison, and deliberate
  failure-and-recovery evidence.

### D-02: Restricted-plan evidence

- **Owner and reviewer:** Martin Urban (`urban233`); Hannah Kullik
  (`kullik01`) reviews independently.
- **Outcome and acceptance:** Build the smallest positive and adversarial
  native-plan corpus needed to decide tokenizer reuse, safe constrained-label
  forms, and default-deny policy boundaries. Each corpus case has an expected
  parse or rejection result from the pinned reference environment. The work
  does not freeze a parser API, policy version, dataset generation, or model
  training.
- **Integrates with:** The plan-language design and later structure-card,
  grammar, dataset, and oracle work through fixtures only.
- **Validation:** Corpus replay, rejection coverage with grammar disabled, and
  recorded PyMOL behavior probes.

## Integration checkpoints

The team uses one checkpoint to turn the two independent discovery results
into a shared fixture decision.

### I-01: Decide the first shared fixture set

- **Participating work and owner:** D-01 and D-02; Martin Urban (`urban233`)
  coordinates the checkpoint.
- **Entry evidence:** Both lanes provide versioned inputs, exact
  reference-environment identities, and unresolved findings.
- **Completion evidence:** The team records the initial fixture set and decides
  whether the snapshot, plan-language, process, and recovery questions have
  enough evidence for design acceptance. No implementation task starts from an
  unresolved contract.

## Risks and discovery

| Risk or unknown | Impact | Evidence-producing action | Owner | Decision point |
|---|---|---|---|---|
| The current design documents are Draft and have unresolved contract questions. | Product implementation could encode incompatible or unsafe assumptions. | Complete D-01 and D-02, then use I-01 to update and accept only the designs supported by evidence. | Unassigned | I-01 |
| The working tree contains uncommitted specification and design changes. | A discovery result could be evaluated against a moving planning baseline. | Confirm the intended planning baseline before either lane begins. | Human | Before D-01 or D-02 starts |
| The two discovery lanes exchange fixture inputs at I-01. | An undocumented fixture change could invalidate the other lane's evidence. | Record the fixture identities and reference environment at the checkpoint. | Martin | I-01 |

## Later milestones

- **Accepted first-contract design:** Use I-01 evidence to accept the smallest
  shared-core and runtime decisions, then plan one thin vertical slice that
  renders a validated plan without enabling apply.

## Team agreements

- Default implementation WIP: one item per developer.
- Owners do not approve their own changes.
- Hannah owns D-01 and independently reviews D-02. Martin owns D-02 and
  independently reviews D-01.
- The two discovery lanes may proceed concurrently because they share no
  implementation interface. They exchange only the reference-environment
  identity and fixture inputs at I-01.
- Status and availability live in this plan or a linked tracker, not in
  architecture documents.
