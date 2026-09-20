# Contract tests

Owned by shared-core contract evidence: the plan/policy/protocol fixtures,
the canonical snapshot format's deterministic codec, declared-unsupported
marker, structure digest, and field-by-field diff, and the structure
card's deterministic rendering (golden bytes, ordering/signed-zero
invariance, per-field-mutation sensitivity, and the explicit markers
behind its size bounds) -- all PyMOL-free, the real-PyMOL
extraction/reconstruction and extraction-then-render paths live in
`tests/integration`.

Also owns the sidecar executor's own PyMOL-free evidence
(docs/master_plan.md item 4): `test_executor.py` covers `execute()`'s
parent-side validation -- an unsupported executor version, an oversized or
malformed snapshot, a plan/snapshot digest mismatch, and a policy denial --
every one of which is rejected before any process is ever spawned. It also
covers typed handling of scratch-directory and OS-level spawn failures. The
deadline, kill, reap, and positive-path evidence needs a real process and
lives in `tests/integration` instead.
