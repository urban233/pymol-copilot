# Unit tests

Owned by isolated shared-core and subsystem behavior tests: every module
here injects a fake for whatever process boundary its own subject would
otherwise cross (a spawned sidecar, a real inference engine, PyMOL itself),
so nothing in this directory launches anything.

`test_agent_runtime.py` and `test_validation_service.py` predate the request
graph: the first pins the LangGraph/httpx dependency wiring
(`pmc_agent.runtime`) that item 8's own graph superseded as the package's
real content; the second covers `pmc_server.validation.PlanValidationService`,
the `/v1/validate` sidecar-executor lifecycle (docs/master_plan.md item 4)
against a fake executor.

The rest is docs/master_plan.md item 8's own evidence, one file per node
group so each can be read (and broken) independently:

- `test_inference_fake.py` covers `pmc_agent.inference.fake.FakeEngine`
  itself -- scripted replay in order, call recording, and the loud failure
  a test that miscounts its own attempts should get instead of a plausible
  default.
- `test_request_graph_transitions.py` proves the graph's shape before any
  node does real work: every edge SPECIFICATION.md:420-425 describes is
  reachable and lands where specified, `REQUEST_STATES` is exactly the
  eleven names this item owns (a set-equality assertion, so a twelfth status
  cannot appear without the suite noticing), and the routing function fails
  closed on an unrecognized status rather than defaulting to a live one.
- `test_request_graph_generation.py` covers `preparing` and `generating`
  against a `FakeEngine`: a contract-manifest mismatch or a malformed
  snapshot fails closed before the engine is ever called; both `ask` forms
  (empty output, an explicit `ask:` line) reach `TERMINAL_ASK` with a
  bounded question and no plan; every `EngineFailure` category reaches
  `TERMINAL_FAILED` typed, with no traceback; and `target_object` always
  equals the request's own resolved object, never anything the completion
  names. `validating` is already real by this step, so every test here also
  injects a fake executor that always succeeds -- `validating`'s own
  behavior is `test_request_graph_repair.py`'s to prove.
- `test_request_graph_repair.py` covers `validating` and the bounded repair
  loop: first-pass success, a repaired failure that still reaches
  `pending_approval`, exhausting the repair budget at exactly three attempts
  and never a fourth, a hostile completion rejected with zero repairs, an
  infrastructure failure (a sidecar timeout) that fails closed without
  consuming one, an ordinary policy denial that does get repaired, a
  regression case for a whole-plan denial that names no per-operation
  decision (`pmc_core.policy.PlanDecision` allows an empty `decisions` tuple
  even when `allowed` is False, which once raised an unhandled
  `StopIteration` inside the graph), and that no two attempts ever reuse one
  `ExecutionRequest`.
- `test_request_graph_pending.py` covers `pending_approval`, expiry,
  supersession, and cancellation through
  `pmc_agent.session.RequestGraphSession`, not the bare graph: a validated
  request parks with a minted plan id and expiry; reject and cancel each
  reach their own terminal; a second submit supersedes the first, leaving
  exactly one pending plan; a reject one tick past the TTL reaches `expired`,
  not `rejected`; a reject naming the wrong plan id changes nothing; and,
  with real `threading.Thread`s repeated across many iterations, two
  concurrent submits for one session never both park -- the per-session lock
  is what stands between that and a corrupted checkpoint.
- `test_server_lifecycle.py` covers `pmc_server.lifecycle
  .RequestGraphLifecycle`'s own translation between the graph's result
  mapping and this protocol's typed wire responses: a validated plan's
  `applicable` derived from the request's own fidelity status alone, a
  contract mismatch or an exhausted repair budget reported as a typed
  failure with no partial plan, an `ask` completion's question surfacing as
  the failure message, and a reject or cancel with nothing pending refused
  as `no_pending_plan` rather than reaching the graph at all.

The no-model-authority proof that ties all of the above together --
SPECIFICATION.md:551-552, that no completion can move a protected field --
is deliberately not here: it is written adversarially, against the finished
graph, in `tests/adversarial/test_model_authority.py`.
