# Discovery tests

Owned by full-V1 contract discovery (H-02, M-02; part of the
[full-V1 contract wave](../../docs/codev/wave/pymol-copilot-full-v1-contracts.md)).
Retains only the probes, fixtures, and machine-readable results that are
useful acceptance evidence for work not yet promoted to production. Both
settled candidate comparisons have shipped: the snapshot format (H-02) as
`src/pmc_core/snapshot.py`, with its differential tests promoted into
`tests/contract/` and `tests/integration/` -- see `h02/README.md` -- and
the structure card (M-02) as `src/pmc_core/card.py`, with its tests
promoted into `tests/contract/test_card.py` and
`tests/integration/test_card_real_pymol.py`. Nothing still under this
directory is a production snapshot, card, or executor API: `h02/` retains
only the still-open execution-boundary prototype, and `m02/` no longer
exists.
