# Discovery tests

Owned by full-V1 contract discovery (H-02, M-02; part of the
[full-V1 contract wave](../../docs/codev/wave/pymol-copilot-full-v1-contracts.md)).
Retains only the probes, fixtures, and machine-readable results that are
useful acceptance evidence for work not yet promoted to production. Both
of H-02's candidate comparisons are now settled and shipped: the snapshot
format as `src/pmc_core/snapshot.py`, with its differential tests promoted
into `tests/contract/` and `tests/integration/`, and the execution
boundary as `src/pmc_core/executor.py` plus `src/pmc_sidecar/child.py`,
with its own evidence promoted the same way. `tests/discovery/h02` no
longer exists. `m02/` remains, holding the still-open structure-card
candidate: nothing under this directory is a production snapshot, card,
or executor API.
