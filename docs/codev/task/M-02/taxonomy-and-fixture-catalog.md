# M-02 V1 Taxonomy and Fixture Catalog

**Status:** Draft discovery evidence
**Owner:** Martin Urban (`urban233`)
**Reviewer:** Hannah Kullik (`kullik01`)
**Authority:** [M-02](../../wave/pymol-copilot-full-v1-contracts.md#m-02-define-full-v1-card-and-dataset-needs)
**Scope:** Full planned V1 intent coverage only. This catalog does not select
serialization, define a production card API, or promote a dataset.

## Shared fixture status

No H-02 candidate canonical snapshot or jointly reviewed full-V1 fixture
catalog exists yet. Every execution category below is therefore `deferred`,
not silently omitted. The listed snapshot facts define the requirements for
the fixture-freeze checkpoint; they are not a claim that the current
`StructureSnapshotV1` placeholder contains them.

## Execution categories

| Category | Required snapshot facts | Oracle status | Assertion type | Command-policy dependency | Fixture/status |
|---|---|---|---|---|---|
| Loaded-object selection | Object/state identity; atom identity, chain, residue, insertion code, atom name, element, altloc, polymer/hetero classification, coordinates | Independent atom-set oracle required | Exact atom-set equality; empty/non-empty result; no unintended state change | Safe selection expression forms | H-02 multi-state, altloc, hetero fixture required; deferred |
| Representation and color | Object/atom visibility, representation, color, object/state identity, atom identity | PyMOL reference plus independent scope oracle where possible | Representation, visibility, color, and unchanged-outside-scope assertions | Reviewed representation and color forms | H-02 display-bearing fixture required; deferred |
| Constrained labels | Atom identity, label text inputs, visibility, color, coordinates, object/state identity | Human-reviewed assertion until an independent text/display oracle exists | Label presence/content/scope assertion; unsupported marker when not machine-checkable | Fixed label templates and bounded formatting | H-02 label-capable fixture required; deferred |
| View and orientation | Object/state identity, coordinates, view matrix, supported setting state | PyMOL reference | Exact or tolerance-bounded view/state comparison | Reviewed view forms | H-02 view fixture required; deferred |
| Safe settings | Supported setting name/value, object/state scope, representation/visibility state | PyMOL reference plus policy validation | Exact setting state and unchanged-outside-scope assertion | Explicit safe-setting allowlist | H-02 supported-setting fixture required; deferred |
| Geometric measurements | Atom identity, coordinates, object/state identity, existing measurement objects | Independent numeric oracle where practical; PyMOL reference otherwise | Numeric value with explicit tolerance; measurement-object identity and scope | Reviewed distance, angle, area, and RMSD forms | H-02 measurement fixture required; deferred |

## Non-execution categories

| Category | Required snapshot facts | Oracle status | Assertion type | Command-policy dependency | Fixture/status |
|---|---|---|---|---|---|
| Controlled fetch | None before an approved accession; post-fetch object identity and checksum after load | Runtime-owned approval/result oracle | Fetch proposal, approval, load result, and no-plan-before-load assertion | Outside model-plan policy | Explicit non-execution category; deferred to controlled-fetch workflow |
| Clarification | Complete card fields relevant to the ambiguous reference, plus truncation/unsupported markers | Human-reviewed | Bounded clarification request; no execution assertion | No plan is authorized | Explicit non-execution category; deferred pending card candidate |
| Refusal | Policy-relevant request classification; no session facts required when hostile | Deterministic policy classification | Refusal and zero-execution assertion | Default deny | Explicit non-execution category; ready for policy fixtures only |
| No-op | None, or card facts only when response references loaded state | Deterministic response classification | No plan and zero-execution assertion | No plan is authorized | Explicit non-execution category; ready for text-only fixtures |
| Repair | Canonical plan, normalized execution error, command index, and card version | Shared error-envelope evidence required | Bounded repair trajectory; error-byte parity; no execution for hostile errors | Retry classification and default deny | Deferred until H-02 execution/report candidate exists |

## Fixture-freeze requirements

The joint H-02/M-02 catalog must map each row to a controlled synthetic
fixture or retain it as an explicit unsupported/deferred case. The execution
fixture set must cover modified coordinates, multiple states, alternate
locations, hetero atoms, object and atom display state, supported settings,
and measurement objects. Each fixture record must include its source,
checksum, snapshot candidate version, relevant-state coverage, mutation
operations, and cleanup boundaries.

## Card and dataset follow-up

Once H-02 supplies candidate canonical snapshots, this catalog will name the
input fixture for deterministic card-byte experiments. The follow-up will
record exact field order, escaping, numeric normalization, collection order,
truncation and unsupported markers, and every field-mutation result. Dataset
sample and artifact-manifest examples will then retain the snapshot/card,
plan, assertions, execution evidence, provenance, and all contract versions.
