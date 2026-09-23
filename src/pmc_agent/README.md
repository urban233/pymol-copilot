# `pmc_agent`

The LangGraph request graph: `received` through `pending_approval`, then
`applying`, and every terminal SPECIFICATION.md:417-426 assigns to that
span -- `rejected`, `expired`, `superseded`, `failed`, `cancelled`, `ask`,
`applied`, `apply_failed_restored`, and `rolled_back`. `restoring` remains a
client-side transient: recovery must finish even if the local server is down.

## What owns what

- `graph.py` is the graph itself: the state shape (`RequestState`), the
  node bodies (`preparing`, `generating`, `validating`, `pending_approval`),
  and the transition table between them. Every clock, id source, engine,
  executor, and policy validator a node needs is an injected seam with a
  real default, never read from a global -- a test replaces exactly the
  seam it is exercising and nothing else.
- `session.py` owns `RequestGraphSession`: one compiled graph, one
  `InMemorySaver` checkpointer, and a per-session `threading.Lock` table,
  for one server process's whole lifetime. `session_id` is the graph's own
  `thread_id`, which is what makes "at most one active request and one
  pending plan per session" (SPECIFICATION.md:409-411) structural rather
  than a separately enforced rule -- and why the lock exists at all:
  `pmc_server.transport.LoopbackPlanServer` is threaded, so two requests
  for the same session can genuinely race to touch one thread at once.
  `submit`, `reject`, `cancel`, `approve`, and `report_apply_outcome` are its
  public entry points; `pmc_server.lifecycle.RequestGraphLifecycle` is the
  one caller.
- `inference/` is the local-model boundary: `base.py`'s `InferenceEngine`
  Protocol accepts only a prompt, optional grammar, token and time bounds,
  cancellation, and a model identity; it returns a completion or typed
  failure, never an engine exception. `fake.py`'s scripted `FakeEngine`
  drives hermetic graph tests. `lemonade.py` is the production adapter: it
  streams only to one caller-selected loopback Lemonade origin, applies every
  bound, and has no remote or alternate-origin fallback. Its
  `connect_lemonade()` startup constructor proves the exact catalog and
  loaded checkpoint, then requires a grammar canary to produce its forced
  sentinel. A refused or silently ignored grammar is a hard failure, never
  an unconstrained or syntax-only mode.
- `prompt.py` is a placeholder seam, not a real prompt: `PROMPT_BUILDER`
  and a minimal default that stamps the card version, the contract
  manifest, and prior failures into bounded text. docs/master_plan.md item
  13 supplies the real prompt and grammar against this exact signature.
- `runtime.py` predates the request graph: a one-node pass-through kept to
  prove the LangGraph/httpx dependency wiring alone (`tests/unit
  /test_agent_runtime.py`). It is not part of the request path.

## The one invariant every node is designed around

SPECIFICATION.md:551-552: *"No model output determines authority, retries,
target object, network destination, policy, approval, or rollback
behavior."* The engine's own return value writes exactly one field,
`completion`; `attempt`, `target_object`, `plan_id`, `expires_at`, the
policy verdict, and every terminal transition are written by this
package's own deterministic code from inputs the engine never touches.
`tests/adversarial/test_model_authority.py` proves this adversarially,
against the finished graph, engineering a completion to influence each
protected field in turn.

## Evidence

Every state, transition, and terminal is proved in `tests/unit
/test_request_graph_*.py` and `tests/unit/test_server_lifecycle.py`,
described further in `tests/unit/README.md`. The no-model-authority suite
lives in `tests/adversarial/test_model_authority.py` instead, deliberately
separate: it is written against the graph already finished, not alongside
the code it exercises.
