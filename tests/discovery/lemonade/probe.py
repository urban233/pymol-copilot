# Copyright 2026 PyMOL Copilot contributors.
"""Lemonade capability spike: the four probes and their verdicts.

This is the re-runnable half of the spike defined by
`plans/02-lemonade-capability-spike.md`. It answers, against a live Lemonade
server reachable at `--base-url` (started via `compose.yaml` in this same
directory), the four questions the master plan's day-one spike asks:

1. Can Lemonade enforce a supplied grammar per request? (`grammar`)
2. Can a request be cancelled mid-generation? (`cancel`)
3. Does it report model identity? (`identity`)
4. Does it run on CPU and on this machine's integrated GPU? (`cpu-gpu`)

Each subcommand writes its raw evidence as JSON/text under `evidence/` and
prints one `Qn ...: <VERDICT>` line. `--all` runs every probe in a fixed
order -- identity, grammar, cpu-gpu, then cancel last -- because the
non-streaming half of the cancel probe deliberately abandons a request the
server keeps computing for some time after this process has moved on; running
it last avoids that leftover load skewing the other probes' timing.

Nothing here is a production adapter. `src/pmc_agent/inference/` (a later,
separate piece of work) is designed from this script's *findings*
(`FINDINGS.md`), not by importing or reusing this module.
"""

from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_BASE_URL = "http://localhost:13305"
DEFAULT_CONTAINER = "lemonade-spike"
DEFAULT_MODEL = "Llama-3.2-1B-Instruct-GGUF"
EVIDENCE_DIR = Path(__file__).resolve().parent / "evidence"

CAPITAL_PROMPT = "What is the capital of France? Answer with one word."
ESSAY_PROMPT = "Write a 2000 word essay about protein folding."


def _write_json(name: str, data: object) -> Path:
    """Write a JSON evidence file under `evidence/` and return its path.

    Args:
        name: The evidence file's name, e.g. `"03-identity.json"`.
        data: A JSON-serializable value to write, pretty-printed.

    Returns:
        The path the evidence was written to.
    """
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    path = EVIDENCE_DIR / name
    path.write_text(json.dumps(data, indent=2) + "\n")
    return path


def _write_text(name: str, text: str) -> Path:
    """Write a plain-text evidence file under `evidence/` and return its path.

    Args:
        name: The evidence file's name, e.g. `"01-startup.txt"`.
        text: The text to write verbatim.

    Returns:
        The path the evidence was written to.
    """
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    path = EVIDENCE_DIR / name
    path.write_text(text)
    return path


def _http_request(
    method: str,
    url: str,
    payload: dict[str, Any] | None,
    timeout: float,
) -> tuple[int, Any]:
    """Send one HTTP request and return its status code and parsed body.

    A non-2xx response is not raised -- `urllib`'s `HTTPError` carries a
    real response body (Lemonade's error responses are JSON), so it is
    decoded exactly like a success response instead of being turned into an
    exception the caller must unwrap.

    Args:
        method: The HTTP method, e.g. `"GET"` or `"POST"`.
        url: The full request URL.
        payload: A JSON request body, or `None` for no body.
        timeout: The socket timeout, in seconds.

    Returns:
        A `(status_code, body)` pair. `body` is the parsed JSON value, or
        the raw text if the response was not valid JSON.
    """
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = response.status
            raw = response.read()
    except urllib.error.HTTPError as error:
        status = error.code
        raw = error.read()
    text = raw.decode("utf-8", errors="replace")
    try:
        return status, json.loads(text)
    except json.JSONDecodeError:
        return status, text


def _api_get(
    base_url: str, path: str, timeout: float = 10.0
) -> tuple[int, Any]:
    """GET one Lemonade API path.

    Args:
        base_url: The server's base URL, e.g. `"http://localhost:13305"`.
        path: The API path, e.g. `"/api/v1/health"`.
        timeout: The socket timeout, in seconds.

    Returns:
        A `(status_code, body)` pair, as `_http_request` returns.
    """
    return _http_request("GET", base_url + path, None, timeout)


def _api_post(
    base_url: str,
    path: str,
    payload: dict[str, Any],
    timeout: float = 60.0,
) -> tuple[int, Any]:
    """POST one JSON request to a Lemonade API path.

    Args:
        base_url: The server's base URL, e.g. `"http://localhost:13305"`.
        path: The API path, e.g. `"/api/v1/load"`.
        payload: The JSON request body.
        timeout: The socket timeout, in seconds.

    Returns:
        A `(status_code, body)` pair, as `_http_request` returns.
    """
    return _http_request("POST", base_url + path, payload, timeout)


def _docker_exec(container: str, *cmd: str, timeout: float = 30.0) -> str:
    """Run a command inside the Lemonade container and return its stdout+stderr.

    Args:
        container: The Docker container name.
        *cmd: The command and its arguments, e.g. `("ls", "-la", "/dev/dri")`.
        timeout: The subprocess timeout, in seconds.

    Returns:
        The combined stdout and stderr text, whatever the exit code.
    """
    result = subprocess.run(
        ["docker", "exec", container, *cmd],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return result.stdout + result.stderr


def _docker_cpu_percent(container: str) -> str:
    """Read one instantaneous CPU-percent sample for a container.

    Args:
        container: The Docker container name.

    Returns:
        The `CPUPerc` field `docker stats` reports, e.g. `"812.34%"`, or
        `"?"` if the sample could not be taken (e.g. the container is not
        running).
    """
    result = subprocess.run(
        [
            "docker",
            "stats",
            "--no-stream",
            "--format",
            "{{.CPUPerc}}",
            container,
        ],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    return result.stdout.strip() or "?"


def _ensure_loaded(
    base_url: str,
    model: str,
    backend: str = "cpu",
    llamacpp_args: str | None = None,
) -> dict[str, Any]:
    """Load a model with a specific backend and (optional) llama.cpp args.

    Always issues the load call rather than checking first, so the caller
    gets a model in a known configuration regardless of what was loaded
    before -- Lemonade reloads in place when the requested options differ
    from what is already running.

    Args:
        base_url: The server's base URL.
        model: The model name to load, e.g. `"Llama-3.2-1B-Instruct-GGUF"`.
        backend: The `llamacpp_backend` value, e.g. `"cpu"`.
        llamacpp_args: Extra `llamacpp_args` to pass at load time, if any.

    Returns:
        The `/api/v1/load` response body.

    Raises:
        RuntimeError: The load call did not return HTTP 200.
    """
    payload: dict[str, Any] = {"model_name": model, "llamacpp_backend": backend}
    if llamacpp_args is not None:
        payload["llamacpp_args"] = llamacpp_args
    status, body = _api_post(base_url, "/api/v1/load", payload, timeout=300.0)
    if status != 200:
        msg = (
            f"failed to load {model!r} (backend={backend!r}): {status} {body!r}"
        )
        raise RuntimeError(msg)
    return body


def cmd_identity(args: argparse.Namespace) -> str:
    """Answer question 3: whether Lemonade reports model identity.

    Collects three identity surfaces (`/api/v1/models/{id}`,
    `/api/v1/health`, and a chat completion's own `model` field) and an
    echo test that sends a deliberately wrong model name, to tell apart a
    server that blindly echoes the request's `model` string from one that
    resolves and validates it against a real loaded checkpoint.

    Args:
        args: Parsed CLI arguments (`base_url`, `model`).

    Returns:
        The verdict line, already printed.
    """
    _ensure_loaded(args.base_url, args.model)

    _, catalog_entry = _api_get(args.base_url, f"/api/v1/models/{args.model}")
    _, health = _api_get(args.base_url, "/api/v1/health")
    _, chat = _api_post(
        args.base_url,
        "/api/v1/chat/completions",
        {
            "model": args.model,
            "messages": [{"role": "user", "content": "Say hi in one word."}],
            "max_tokens": 8,
        },
    )
    bad_status, bad_body = _api_post(
        args.base_url,
        "/api/v1/chat/completions",
        {
            "model": args.model.lower(),
            "messages": [{"role": "user", "content": "Say hi in one word."}],
            "max_tokens": 8,
        },
    )

    evidence = {
        "catalog_entry": catalog_entry,
        "health_model_block": health.get("all_models_loaded", [None])[0],
        "chat_response_model_field": chat.get("model"),
        "echo_test": {
            "requested_model": args.model.lower(),
            "status": bad_status,
            "body": bad_body,
            "rejected": bad_status != 200,
        },
    }
    _write_json("03-identity.json", evidence)

    validates_identity = bad_status != 200
    checkpoint_reported = bool(catalog_entry.get("checkpoint"))
    if validates_identity and checkpoint_reported:
        verdict = "YES"
    elif checkpoint_reported:
        verdict = "PARTIAL"
    else:
        verdict = "NO"
    line = f"Q3 MODEL IDENTITY: {verdict}"
    print(line)
    return line


def cmd_grammar(args: argparse.Namespace) -> str:
    """Answer question 1: whether Lemonade enforces a supplied grammar per request.

    Proves it with a grammar that forbids a token the model would otherwise
    emit: "What is the capital of France?" against
    `root ::= "Berlin" | "Madrid" | "Rome"`, which makes "Paris" unreachable
    rather than merely deprioritised. Runs a temperature-0 control first
    (must return "Paris" every time, or the rest of this probe proves
    nothing), then four constraint routes: the `grammar` chat field, a
    `response_format` JSON-schema enum, a load-time `llamacpp_args`
    `--grammar` flag, and the same `grammar` field sent directly to the
    llama-server backend port inside the container, bypassing Lemonade's
    HTTP layer entirely.

    Args:
        args: Parsed CLI arguments (`base_url`, `model`, `container`).

    Returns:
        The verdict line, already printed.
    """
    grammar = 'root ::= "Berlin" | "Madrid" | "Rome"'
    message = [{"role": "user", "content": CAPITAL_PROMPT}]

    _ensure_loaded(args.base_url, args.model)

    control = [
        _api_post(
            args.base_url,
            "/api/v1/chat/completions",
            {
                "model": args.model,
                "messages": message,
                "max_tokens": 10,
                "temperature": 0,
            },
        )
        for _ in range(3)
    ]
    control_outputs = [
        body["choices"][0]["message"]["content"] for _, body in control
    ]
    control_ok = all(output == "Paris" for output in control_outputs)

    # R1, repeated 3x: proves the per-request `grammar` field is enforced
    # deterministically, not just on a lucky single call.
    r1_runs = [
        _api_post(
            args.base_url,
            "/api/v1/chat/completions",
            {
                "model": args.model,
                "messages": message,
                "max_tokens": 10,
                "temperature": 0,
                "grammar": grammar,
            },
        )
        for _ in range(3)
    ]
    r1_outputs = [
        body["choices"][0]["message"]["content"] if status == 200 else None
        for status, body in r1_runs
    ]
    r1_status = r1_runs[0][0]
    r1_output = r1_outputs[0]

    # Tighten the grammar to a single legal token, still per-request (not
    # via llamacpp_args -- that is R3's load-time route below), to prove the
    # constraint is exact rather than merely narrowing the distribution.
    r1_single_status, r1_single_body = _api_post(
        args.base_url,
        "/api/v1/chat/completions",
        {
            "model": args.model,
            "messages": message,
            "max_tokens": 10,
            "temperature": 0,
            "grammar": 'root ::= "Berlin"',
        },
    )
    r1_single_output = (
        r1_single_body["choices"][0]["message"]["content"]
        if r1_single_status == 200
        else None
    )

    r2_status, r2_body = _api_post(
        args.base_url,
        "/api/v1/chat/completions",
        {
            "model": args.model,
            "messages": message,
            "max_tokens": 10,
            "temperature": 0,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "capital_answer",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "city": {
                                "type": "string",
                                "enum": ["Berlin", "Madrid", "Rome"],
                            }
                        },
                        "required": ["city"],
                    },
                },
            },
        },
    )
    r2_output = (
        r2_body["choices"][0]["message"]["content"]
        if r2_status == 200
        else None
    )

    r3_load_status: int | str | None = None
    r3_output = None
    r3_launch_command: list[str] = []
    try:
        _ensure_loaded(
            args.base_url,
            args.model,
            llamacpp_args="--grammar 'root ::= \"Berlin\"'",
        )
        r3_load_status = 200
        # Confirm the flag actually reached llama-server's argv, rather than
        # inferring that from the load call succeeding.
        _, r3_health = _api_get(args.base_url, "/api/v1/health")
        r3_launch_command = r3_health.get("all_models_loaded", [{}])[0].get(
            "launch_command", []
        )
        r3_status, r3_body = _api_post(
            args.base_url,
            "/api/v1/chat/completions",
            {
                "model": args.model,
                "messages": message,
                "max_tokens": 10,
                "temperature": 0,
            },
        )
        if r3_status == 200:
            r3_output = r3_body["choices"][0]["message"]["content"]
    except RuntimeError:
        r3_load_status = "load_failed"
    finally:
        # Restore a plain load so later probes see an unconstrained model.
        _ensure_loaded(args.base_url, args.model)

    r4_raw = _docker_exec(
        args.container,
        "curl",
        "-sS",
        "-m",
        "60",
        "-X",
        "POST",
        "http://127.0.0.1:8001/v1/chat/completions",
        "-H",
        "Content-Type: application/json",
        "-d",
        json.dumps(
            {
                "model": args.model,
                "messages": message,
                "max_tokens": 10,
                "temperature": 0,
                "grammar": 'root ::= "Madrid"',
            }
        ),
    )
    try:
        r4_body = json.loads(r4_raw)
        r4_output = r4_body["choices"][0]["message"]["content"]
    except (json.JSONDecodeError, KeyError, IndexError):
        r4_body = r4_raw
        r4_output = None

    evidence = {
        "control": {"outputs": control_outputs, "all_paris": control_ok},
        "r1_grammar_field": {
            "status": r1_status,
            "outputs": r1_outputs,
            "deterministic": len(set(r1_outputs)) == 1,
        },
        "r1_single_token_tightened": {
            "status": r1_single_status,
            "output": r1_single_output,
        },
        "r2_response_format_json_schema": {
            "status": r2_status,
            "output": r2_output,
        },
        "r3_llamacpp_args_grammar_flag": {
            "load_status": r3_load_status,
            "launch_command": r3_launch_command,
            "flag_present_in_launch_command": any(
                "--grammar" in part for part in r3_launch_command
            ),
            "output": r3_output,
        },
        "r4_direct_backend_grammar_field": {
            "output": r4_output,
            "raw": r4_body,
        },
    }
    _write_json("04-grammar.json", evidence)

    # The permitted set the "Berlin"/"Madrid"/"Rome" grammar allows -- a
    # match means the constraint held; "Paris" (the control's answer) is
    # what the grammar exists to forbid.
    constrained_options = {"Berlin", "Madrid", "Rome"}
    r1_enforced = r1_status == 200 and r1_output in constrained_options
    r1_rejected = r1_status != 200
    r4_enforced = r4_output in constrained_options

    if not control_ok:
        verdict = "INCONCLUSIVE (control did not return Paris)"
    elif r1_enforced:
        verdict = "YES"
    elif r4_enforced:
        # llama.cpp itself honors the grammar (R4, direct to the backend)
        # even though Lemonade's own HTTP layer did not -- a Lemonade
        # passthrough gap, not a llama.cpp limitation. Name which R1 failure
        # mode this was: a silently-ignored grammar is the one outcome the
        # plan calls out as needing to stay visible, not just "PARTIAL".
        r1_failure = "R1 rejected" if r1_rejected else "R1 silently ignored"
        verdict = f"PARTIAL (backend only; {r1_failure})"
    elif r1_rejected:
        verdict = "NO (rejected)"
    else:
        verdict = "NO (silently ignored)"
    line = f"Q1 GRAMMAR: {verdict}"
    print(line)
    return line


def cmd_cancel(args: argparse.Namespace) -> str:
    """Answer question 2: whether a request can be cancelled mid-generation.

    Starts a long generation, confirms it is actually generating (a CPU
    sample taken *before* disconnecting -- the positive control this probe
    needs to claim a "during generation" baseline at all), then closes the
    socket without finishing the read, and samples container CPU and
    `/api/v1/health`'s `is_busy` for `--cancel-window` seconds afterward. A
    clean drop to near-idle means the disconnect stopped the compute; CPU
    and `is_busy` staying pegged means it did not.

    The non-streaming probe additionally polls, past the fixed window, for
    up to `--drain-timeout` more seconds to see whether the abandoned
    request ever finishes on its own -- this is the same thing a human
    watching `/api/v1/health` would do, just bounded so the probe
    terminates.

    Args:
        args: Parsed CLI arguments (`base_url`, `model`, `container`,
            `cancel_window`, `drain_timeout`).

    Returns:
        The verdict line, already printed.
    """
    _ensure_loaded(args.base_url, args.model)

    stream_result = _cancel_streaming(
        args.base_url, args.model, args.container, args.cancel_window
    )
    nonstream_result = _cancel_nonstreaming(
        args.base_url,
        args.model,
        args.container,
        args.cancel_window,
        args.drain_timeout,
    )

    def idle_within(
        samples: list[tuple[float, float, bool]], threshold: float = 5.0
    ) -> float | None:
        for elapsed, cpu, busy in samples:
            if cpu < threshold and not busy:
                return elapsed
        return None

    stream_idle_at = idle_within(stream_result["samples"])
    nonstream_idle_at = idle_within(nonstream_result["samples"])

    evidence = {
        "streaming": {
            "cpu_percent_during_generation_before_disconnect": (
                stream_result["during_cpu"]
            ),
            "samples_after_disconnect": stream_result["samples"],
            "idle_within_window_at_seconds": stream_idle_at,
        },
        "non_streaming": {
            "samples_after_disconnect": nonstream_result["samples"],
            "idle_within_window_at_seconds": nonstream_idle_at,
            "drain_poll": nonstream_result["drain_poll"],
        },
    }
    _write_json("05-cancel.json", evidence)

    stream_verdict = (
        f"YES (~{stream_idle_at:.1f}s)" if stream_idle_at is not None else "NO"
    )
    if nonstream_idle_at is not None:
        nonstream_verdict = f"YES (~{nonstream_idle_at:.1f}s)"
    elif nonstream_result["drain_poll"]["finished_at_seconds"] is not None:
        finished_at = nonstream_result["drain_poll"]["finished_at_seconds"]
        nonstream_verdict = (
            f"NO (not cancelled; ran to completion at ~{finished_at:.0f}s)"
        )
    else:
        total_observed = args.cancel_window + args.drain_timeout
        nonstream_verdict = f"NO (still busy after {total_observed:.0f}s)"
    line = (
        f"Q2 CANCELLATION: streaming={stream_verdict}, "
        f"non_streaming={nonstream_verdict}"
    )
    print(line)
    return line


def _cancel_streaming(
    base_url: str, model: str, container: str, window_seconds: float
) -> dict[str, Any]:
    """Run the streaming half of the cancellation probe.

    Args:
        base_url: The server's base URL.
        model: The model name to request.
        container: The Docker container name, for CPU sampling.
        window_seconds: How long to sample CPU after disconnecting.

    Returns:
        A dict with `during_cpu` (the CPU-percent positive control, taken
        while still connected and reading) and `samples`, a list of
        `(elapsed_seconds, cpu_percent, is_busy)` triples measured from the
        moment the socket was closed.
    """
    import http.client

    host = base_url.split("://", 1)[1].split(":")[0]
    port = int(base_url.rsplit(":", 1)[1])

    conn = http.client.HTTPConnection(host, port, timeout=30)
    conn.request(
        "POST",
        "/api/v1/chat/completions",
        body=json.dumps(
            {
                "model": model,
                "messages": [{"role": "user", "content": ESSAY_PROMPT}],
                "max_tokens": 2000,
                "stream": True,
            }
        ),
        headers={"Content-Type": "application/json"},
    )
    response = conn.getresponse()
    # Read enough chunks to be sure generation is actually under way before
    # taking the positive-control sample.
    for _ in range(3):
        if not response.fp.readline():
            break
    during_cpu_raw = _docker_cpu_percent(container)
    try:
        during_cpu = float(during_cpu_raw.rstrip("%"))
    except ValueError:
        during_cpu = -1.0
    for _ in range(3):
        if not response.fp.readline():
            break
    conn.close()

    return {
        "during_cpu": during_cpu,
        "samples": _sample_cpu_and_busy(base_url, container, window_seconds),
    }


def _cancel_nonstreaming(
    base_url: str,
    model: str,
    container: str,
    window_seconds: float,
    drain_timeout: float,
) -> dict[str, Any]:
    """Run the non-streaming half of the cancellation probe.

    Args:
        base_url: The server's base URL (host/port for the raw socket).
        model: The model name to request.
        container: The Docker container name; also where the raw socket
            connects to, via the host's published port.
        window_seconds: How long to sample CPU/`is_busy` after disconnecting.
        drain_timeout: How much longer, past the window, to keep polling
            `/api/v1/health`'s `is_busy` for the abandoned request to finish
            on its own.

    Returns:
        A dict with `samples` (as `_cancel_streaming` returns) and
        `drain_poll`, recording whether/when the abandoned request was
        observed to finish.
    """
    host = base_url.split("://", 1)[1].split(":")[0]
    port = int(base_url.rsplit(":", 1)[1])
    body = json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": ESSAY_PROMPT}],
            "max_tokens": 2000,
            "stream": False,
        }
    ).encode("utf-8")
    request = (
        b"POST /api/v1/chat/completions HTTP/1.1\r\n"
        b"Host: " + host.encode() + b"\r\n"
        b"Content-Type: application/json\r\n"
        b"Content-Length: " + str(len(body)).encode() + b"\r\n"
        b"Connection: close\r\n\r\n" + body
    )
    sock = socket.create_connection((host, port), timeout=10)
    sock.sendall(request)
    # Give the server a moment to parse the request and start generating
    # before severing the connection, so this tests a mid-generation
    # disconnect rather than one before generation even began.
    time.sleep(1.0)
    sock.close()

    samples = _sample_cpu_and_busy(base_url, container, window_seconds)

    finished_at: float | None = None
    if samples and samples[-1][2]:  # still busy at the end of the window
        deadline = time.monotonic() + drain_timeout
        start = time.monotonic()
        while time.monotonic() < deadline:
            _, health = _api_get(base_url, "/api/v1/health", timeout=10.0)
            model_block = health.get("all_models_loaded", [{}])
            still_busy = (
                bool(model_block[0].get("is_busy")) if model_block else False
            )
            if not still_busy:
                finished_at = window_seconds + (time.monotonic() - start)
                break
            time.sleep(3.0)

    return {
        "samples": samples,
        "drain_poll": {
            "polled_for_seconds": drain_timeout,
            "finished_at_seconds": finished_at,
        },
    }


def _sample_cpu_and_busy(
    base_url: str, container: str, window_seconds: float
) -> list[tuple[float, float, bool]]:
    """Sample a container's CPU percent and `is_busy` for a fixed duration.

    Uses a deadline-based loop rather than counting fixed-length
    iterations, so `window_seconds` reflects real elapsed time regardless
    of how long each `docker stats`/`/api/v1/health` call itself takes.

    Args:
        base_url: The server's base URL, for the `is_busy` reading.
        container: The Docker container name, for the CPU reading.
        window_seconds: How many seconds to keep sampling.

    Returns:
        A list of `(elapsed_seconds, cpu_percent, is_busy)` triples.
    """
    samples: list[tuple[float, float, bool]] = []
    start = time.monotonic()
    while time.monotonic() - start < window_seconds:
        raw = _docker_cpu_percent(container)
        try:
            cpu = float(raw.rstrip("%"))
        except ValueError:
            cpu = -1.0
        _, health = _api_get(base_url, "/api/v1/health", timeout=5.0)
        model_block = (
            health.get("all_models_loaded", [])
            if isinstance(health, dict)
            else []
        )
        busy = bool(model_block[0].get("is_busy")) if model_block else False
        samples.append((time.monotonic() - start, cpu, busy))
        remaining = window_seconds - (time.monotonic() - start)
        if remaining > 0:
            time.sleep(min(1.0, remaining))
    return samples


def cmd_cpu_gpu(args: argparse.Namespace) -> str:
    """Answer question 4: whether Lemonade runs on CPU and the integrated GPU.

    Proves the CPU half against `/api/v1/health`'s per-model `device` and
    `launch_command` fields. Proves the GPU half's *absence* on this
    machine: a Linux container on an Apple Silicon host has no `/dev/dri`,
    no `/dev/kfd`, and only Mesa's `llvmpipe` software rasterizer visible to
    Vulkan -- this is demonstrated, not assumed.

    Args:
        args: Parsed CLI arguments (`base_url`, `model`, `container`).

    Returns:
        The verdict line, already printed.
    """
    _ensure_loaded(args.base_url, args.model)
    _, health = _api_get(args.base_url, "/api/v1/health")
    _write_json("06-cpu.json", health)

    model_block = health.get("all_models_loaded", [{}])[0]
    device = model_block.get("device")

    dri = _docker_exec(args.container, "ls", "-la", "/dev/dri")
    kfd = _docker_exec(args.container, "ls", "-la", "/dev/kfd")
    vulkan = _docker_exec(args.container, "vulkaninfo", "--summary")
    _, system_info = _api_get(args.base_url, "/api/v1/system-info")

    _write_text(
        "06-gpu-absent.txt",
        "docker exec ... ls -la /dev/dri:\n"
        f"{dri}\n"
        "docker exec ... ls -la /dev/kfd:\n"
        f"{kfd}\n"
        "docker exec ... vulkaninfo --summary:\n"
        f"{vulkan}\n"
        "GET /api/v1/system-info devices block:\n"
        f"{json.dumps(system_info.get('devices', {}), indent=2)}\n",
    )

    cpu_verdict = "YES" if device == "cpu" else f"NO (device={device!r})"
    line = (
        f"Q4 CPU: {cpu_verdict} | "
        "Q4 iGPU: NOT PROVEN ON THIS MACHINE "
        "(no GPU passthrough into a Linux container on Apple Silicon)"
    )
    print(line)
    return line


def main(argv: list[str] | None = None) -> int:
    """Parse CLI arguments and run the requested probe(s).

    Args:
        argv: Argument vector, or `None` to use `sys.argv[1:]`.

    Returns:
        The process exit code: 0 unless a probe's rig itself fails (a
        capability answering "no" is a valid result and always exits 0).
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--container", default=DEFAULT_CONTAINER)
    parser.add_argument(
        "--cancel-window",
        type=float,
        default=20.0,
        help="Seconds of CPU/is_busy sampling after each disconnect.",
    )
    parser.add_argument(
        "--drain-timeout",
        type=float,
        default=220.0,
        help=(
            "Extra seconds to keep polling is_busy, past --cancel-window, "
            "for the abandoned non-streaming request to finish on its own."
        ),
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--identity", action="store_true")
    group.add_argument("--grammar", action="store_true")
    group.add_argument("--cancel", action="store_true")
    group.add_argument("--cpu-gpu", action="store_true")
    group.add_argument("--all", action="store_true")
    args = parser.parse_args(argv)

    try:
        if args.all:
            cmd_identity(args)
            cmd_grammar(args)
            cmd_cpu_gpu(args)
            cmd_cancel(args)
        elif args.identity:
            cmd_identity(args)
        elif args.grammar:
            cmd_grammar(args)
        elif args.cancel:
            cmd_cancel(args)
        elif args.cpu_gpu:
            cmd_cpu_gpu(args)
    except (
        RuntimeError,
        urllib.error.URLError,
        OSError,
        KeyError,
        IndexError,
    ) as error:
        # A malformed response (e.g. HTTP 200 with no `choices`) is a rig
        # failure, not a capability answering "no" -- surface it loudly and
        # labelled, rather than letting it either masquerade as a verdict or
        # escape as a bare traceback.
        print(f"RIG FAILURE: {error!r}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
