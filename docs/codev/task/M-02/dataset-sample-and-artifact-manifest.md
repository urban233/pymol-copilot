# M-02 Dataset Sample and Artifact Manifest Needs

**Status:** Draft discovery evidence
**Owner:** Martin Urban (`urban233`)
**Reviewer:** Hannah Kullik (`kullik01`)
**Authority:** [M-02](../../wave/pymol-copilot-full-v1-contracts.md#m-02-define-full-v1-card-and-dataset-needs)
**Scope:** Candidate field inventory and schema examples only. This document
does not define a production codec, package a dataset, or assign final card or
snapshot values before contract freeze.

## Sample record

Every candidate sample must retain the following fields. A required field that
is unavailable or incompatible rejects the candidate; no field is silently
defaulted.

| Field group | Required fields | Purpose |
|---|---|---|
| Identity and split | `sample_id`, `split_id`, `dataset_contract_version` | Stable sample identity and immutable split membership |
| Structure and context | `structure_artifact_id`, `structure_sha256`, `structure_source`, `snapshot_date`, `sequence_cluster_30pct`, `snapshot`, `snapshot_contract_version`, `snapshot_digest`, `card`, `card_sha256`, `card_contract_version` | Reproduce the exact structure and model context, including the dated snapshot and immutable 30% sequence-cluster reference |
| Intent and taxonomy | `intent`, `intent_source`, `category_id`, `difficulty`, `task_id`, `template_id` | Preserve natural-language lineage and coverage category |
| Plan and policy | `canonical_plan_pml`, `typed_plan_id`, `plan_contract_version`, `parser_contract_version`, `policy_contract_version`, `policy_decisions` | Identify the reviewed executable behavior and its authorization result |
| Assertions and oracle | `assertions`, `assertion_evaluator_version`, `oracle_status`, `oracle_version`, `task_success` | Preserve the grading claim and distinguish independent, PyMOL-reference, human-reviewed, and unsupported categories |
| Execution evidence | `execution_request_id`, `execution_report`, `input_fingerprint`, `result_fingerprint`, `command_outcomes`, `normalized_error`, `timing` | Retain bounded success/failure evidence without replacing it with a boolean |
| Provenance | `fixture_id`, `fixture_sha256`, `fixture_source`, `template_ref`, `author_ref`, `teacher_model_ref`, `prompt_ref`, `generation_parameters_ref`, `generation_seed`, `pymol_provenance_ref`, `shared_core_manifest_ref`, `generator_revision`, `author_or_generator`, `created_at` | Make controlled-fixture, generation, PyMOL, and shared-core lineage auditable; each reference is immutable or candidate-only |
| Decisions | `policy_decisions`, `grammar_decisions`, `parser_decisions` | Retain the per-sample authorization, grammar, and parser decisions required to interpret the plan |
| Shared contracts | `execution_contract_version`, `error_envelope_version`, `grammar_contract_version`, `manifest_version` | Prevent train/serve use across incompatible contract versions |

`snapshot` and `card` are opaque candidate bytes until H-02 and M-02 freeze
their contracts. Their checksums and version fields are mandatory even when a
sample has a non-execution category. A non-execution sample may omit
`canonical_plan_pml`, `typed_plan_id`, and execution evidence only when it
records a `non_execution_reason` of `controlled_fetch`, `clarification`,
`refusal`, `no_op`, or `repair`; repair instead requires its normalized error
and prior attempt identity.

## Artifact manifest

The immutable dataset artifact needs a companion manifest with the following
fields:

| Field group | Required fields | Purpose |
|---|---|---|
| Artifact identity | `artifact_id`, `artifact_sha256`, `manifest_version`, `created_at`, `supersedes_artifact_id` | Content-addressed immutable package and correction lineage |
| Contract matrix | Snapshot, card, plan, parser, policy, grammar, execution, error-envelope, oracle, evaluator, and dataset-contract versions | Reject incompatible runtime, generation, training, or evaluation pairings |
| Contents | `sample_count`, `sample_index_sha256`, category/difficulty counts, non-execution counts, failed-record count | Verify package completeness and coverage without deriving it from mutable files |
| Structure provenance | Structure artifact identities/checksums/sources, fixture identities/checksums, sequence-cluster version, license records | Support regeneration and split-integrity review |
| Generation provenance | Generator revision/configuration, templates, prompts when used, model identity when used, seeds, environment, and PyMOL version | Preserve reproducibility and license/audit facts |
| Split and curation | Split manifest identity, decontamination manifest identity, deduplication basis, audit protocol/result identity | Preserve the basis for all reported training/evaluation results |
| Evidence and limitations | Oracle coverage, unsupported/deferred categories, execution-report index, error corpus index, known limitations | Prevent incomplete categories from appearing verified |

## Candidate JSON shape

The shape below demonstrates containment and required relationships, not final
wire names or serialization.

```json
{
  "sample_id": "sample-controlled-001",
  "split_id": "train",
  "dataset_contract_version": "candidate",
  "structure": {
    "artifact_id": "controlled-fixture",
    "sha256": "<fixture-sha256>",
    "source": "self-authored",
    "snapshot_date": "<snapshot-date>",
    "sequence_cluster_30pct": "<immutable-cluster-entry>"
  },
  "context": {
    "snapshot_contract_version": "candidate",
    "snapshot_digest": "<candidate-digest>",
    "card_contract_version": "candidate",
    "card_sha256": "<candidate-card-sha256>"
  },
  "intent": {
    "text": "<intent>",
    "source": "reviewed-template",
    "category_id": "loaded-object-selection",
    "difficulty": "candidate"
  },
  "contracts": {
    "plan": "1",
    "policy": "1",
    "execution": "candidate",
    "oracle": "candidate",
    "grammar": "candidate",
    "parser": "candidate"
  },
  "provenance": {
    "template_ref": "<candidate-template-ref>",
    "author_ref": "<candidate-author-ref>",
    "teacher_model_ref": null,
    "prompt_ref": "<candidate-prompt-ref>",
    "generation_parameters_ref": "<candidate-generation-parameters-ref>",
    "generation_seed": "<candidate-seed>",
    "pymol_provenance_ref": "<candidate-pymol-provenance-ref>",
    "shared_core_manifest_ref": "<candidate-shared-core-manifest-ref>"
  },
  "decisions": {
    "policy_decisions": [],
    "grammar_decisions": [],
    "parser_decisions": []
  },
  "verification": {
    "oracle_status": "independent-required",
    "assertions": [],
    "execution_report": null,
    "task_success": null
  }
}
```

The placeholder values deliberately cannot enter training, evaluation, or
runtime. At contract freeze, this example must become a strict schema with
exact field order/canonical bytes where relevant, version compatibility rules,
and malformed/missing-field tests.

## Candidate-card dependency

The field inventory does not choose the live-state serialization or card
format. H-02 Candidate A now provides a controlled input for M-02 golden-byte,
mutation, parity, and truncation experiments. Card bytes, `card_sha256`, and
`card_contract_version` remain candidate-only until the joint fixture freeze
selects a production contract and its compatibility policy.
