# Generation configuration

This directory is owned by model-data generation. Issue #1 defined no
configuration schema or behavior for it; task M-01 (issue #8) introduces the
first one below, bounded by that task's containment: no teacher access, no
curation, no production execution path -- see
`docs/codev/wave/pymol-copilot.md`'s M-01 entry.

## `chain_a_red_structures.json`

Declares generation requests consumed by `pmc_data.generate`. Each entry
reapplies the one accepted canonical plan (`select copilot_selection, chain
A` / `color red, copilot_selection`) to a different controlled structure and
is verified through `pmc_data.verifier.verify_gold_case` before it may ever
be written as a gold record -- see `pmc_data/generate.py` for the schema and
`tests/data/test_generate_real_pymol.py` for the real-PyMOL conformance
evidence.
