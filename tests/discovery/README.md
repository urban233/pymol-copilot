# Discovery tests

Owned by full-V1 contract discovery. Retains only the probes, fixtures,
and machine-readable results that are useful acceptance evidence for
work not yet promoted to production. The snapshot, execution-boundary
and structure-card comparisons have all shipped: the
snapshot format as `src/pmc_core/snapshot.py`, the execution boundary
as `src/pmc_core/executor.py` plus `src/pmc_sidecar/child.py`, and the
structure card as `src/pmc_core/card.py`, each with its differential
tests promoted into `tests/contract/` and `tests/integration/`.
`tests/discovery/h02` and `tests/discovery/m02` no longer exist, and
what remains here is the Lemonade capability spike alone -- nothing
under this directory is a production snapshot, card, or executor API.
