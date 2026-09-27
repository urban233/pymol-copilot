# `pmc_server`

`pmc_server.transport.LoopbackPlanServer` is a threaded, authenticated
loopback-only HTTP server; `pmc_server.lifecycle.RequestGraphLifecycle` is
its only caller, translating decoded V1 requests into
`pmc_agent.session.RequestGraphSession` calls and its result mapping back
into typed wire responses. Every state, transition, and terminal the
request graph can reach belongs to `pmc_agent.graph`, never to this
package.

## The production entrypoint

`main.py` (docs/master_plan.md item 12) is the first thing that starts a
real server process: `build_engine()` connects to Lemonade once and falls
back to `pmc_agent.inference.unavailable.UnavailableEngine` on any
capability failure, so the server starts and stays available for
diagnostics through `copilot_health` even when no local model can be
reached (SPECIFICATION.md:609) — there is no retry and no second engine
(SPECIFICATION.md:554).

`serve()` then starts the real `LoopbackPlanServer` on an ephemeral
loopback port with a fresh `secrets.token_urlsafe(32)` credential, and
hands both to PyMOL through a private local handoff file rather than an
environment variable: a live credential in an environment variable is
visible to every child process and, on some platforms, to `ps`. The
handoff file is written the same way `pmc_client.recovery.RecoveryStore`
writes its own recovery points — staged, `chmod`ed to `0600`, verified,
then atomically replaced into place — and removed again on shutdown.
`pmc_client.bootstrap.connect_from_handoff` is the one reader, and
validates every field before building a client from it: see that
module's own docstring for what it refuses and why.

Killing the server process is always safe for the live PyMOL session:
every client command past that point reports one bounded diagnostic line
rather than raising, and no partial recovery state is created by a
request that never reached apply.
