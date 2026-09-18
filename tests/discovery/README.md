# Discovery tests

Owned by full-V1 contract discovery (H-02, M-02; part of the
[full-V1 contract wave](../../docs/codev/wave/pymol-copilot-full-v1-contracts.md)).
Retains only the probes, fixtures, and machine-readable results that are
useful acceptance evidence for work not yet promoted to production. The
snapshot candidate comparison (H-02) is settled and shipped as
`src/pmc_core/snapshot.py`, with its differential tests promoted into
`tests/contract/` and `tests/integration/` -- see `h02/README.md`. Nothing
still under this directory is a production snapshot, card, or executor
API: `h02/` retains only the still-open execution-boundary prototype, and
`m02/` the still-open structure-card candidate.
