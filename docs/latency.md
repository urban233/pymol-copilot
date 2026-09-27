# Latency

docs/master_plan.md item 12. [SPECIFICATION.md:157](../SPECIFICATION.md#L157)
sets no fixed pass/fail budget for runtime latency; this is the informal
per-stage p50/p95 note it asks for instead, measured on each developer's own
machine with `bazel run //tests/e2e:record_latency -- --repetitions 11`
(see [docs/development_setup.md](development_setup.md#recording-latency)).

Every table below is one machine's own recorded run: the engine used
(scripted, or a real Lemonade server), the repetition count, and the date.
`preview_client_local` and `approval_reverify` are each a whole console
invocation's own elapsed time minus its instrumented sub-stages, not
measured directly -- this item's own decision not to thread a timer through
`pmc_client.command` to isolate them further. `generate` reads "not
measured" unless the run named a real Lemonade server.

<!-- Paste each machine's own table below, oldest first. -->

### Linux 7.2.6-1-default · x86_64 · Python 3.13.13

Engine: scripted (FakeEngine) · Repetitions: 10 · Date: 2026-09-27

| Stage | p50 (ms) | p95 (ms) |
|---|---|---|
| fidelity_probe | 6160.246 | 7192.704 |
| submit | 9157.760 | 10169.099 |
| preview_client_local | 2.085 | 2.779 |
| approval_reverify | 3.371 | 4.127 |
| apply_round_trip | 4.334 | 5.571 |
| recovery_save | 0.618 | 0.809 |
| live_dispatch | 4023.539 | 4025.665 |
| restore_and_compare | 3.204 | 3.204 |
| outcome_report | 5.121 | 5.651 |
| generate | not measured | not measured |

`fidelity_probe` and `submit` are each dominated by a real headless PyMOL
launch (the client's own fidelity check, and the server's own sidecar
validation inside `submit`'s round trip); `live_dispatch` is the closed
dispatcher running the approved plan's four commands against the
already-live session. All three are consistent with real PyMOL process
spawns being the dominant cost on this machine -- not with a fixed budget,
which this measure does not set.
