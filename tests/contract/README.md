# Contract tests

Owned by shared-core contract evidence: the plan/policy/protocol fixtures,
and the canonical snapshot format's deterministic codec, declared-
unsupported marker, structure digest, and field-by-field diff (all
PyMOL-free -- the real-PyMOL extraction/reconstruction round trip lives in
`tests/integration`).

Also owns the sidecar executor's own PyMOL-free evidence
(docs/master_plan.md item 4): `test_executor.py` covers `execute()`'s
parent-side validation -- an unsupported executor version, an oversized or
malformed snapshot, and a policy denial -- every one of which is rejected
before any process is ever spawned. The spawn, deadline, kill, reap, and
positive-path evidence needs a real process and lives in
`tests/integration` instead.
