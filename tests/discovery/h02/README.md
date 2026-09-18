# H-02: execution-boundary discovery

The full-V1 snapshot comparison that used to live here is settled:
candidate A (canonical structured data via PyMOL's own object-construction
API) won, and shipped as production code in `src/pmc_core/snapshot.py`
(master plan item 3). Its differential evidence -- the shared harness, the
three-way candidate comparison, and the fresh-process round-trip tests --
moved to `tests/contract/test_snapshot.py` and
`tests/integration/test_snapshot_round_trip.py`, keeping their real-PyMOL/
exclusive Bazel tags.

What remains here is item 4's still-open prototype: `execution_boundary.py`
and its sabotage/positive-path probes, for the fresh-process hermetic
execution boundary that has not yet been promoted to
`src/pmc_core/executor.py`. Disposable prototype evidence only; no
production contract lives here.
