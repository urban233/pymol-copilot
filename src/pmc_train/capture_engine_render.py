# Copyright 2026 PyMOL Copilot contributors.
"""Capture how the evaluation engine renders and tokenizes some prompts.

A development helper, run once while the evaluation engine is up
(configs/evaluation/engine/README.md). For each named sample it asks the
engine's llama-server, inside its container, for three things:

- the chat template's rendering (`/apply-template`);
- that rendering's token ids (`/tokenize`, adding special tokens the
  way llama-server does for a chat request);
- the prompt-token count the server reports for a real one-token chat
  completion through Lemonade.

It writes one JSON fixture per sample, which `tests/test_render.py`
compares with `pmc_train.render`. Standard library only, so it runs
under any Python:

    python3 src/pmc_train/capture_engine_render.py \\
        --split data/splits/split-e4599620801af592 \\
        --sample test_gold:gold_061 --sample train:<sample_id> ...
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import argparse
import hashlib
import json
import subprocess
import urllib.request
from pathlib import Path
from typing import Any

#: Where the fixtures live.
DEFAULT_OUT = Path(__file__).parent / "tests" / "data" / "engine_render"


def _server(container: str, port: int, path: str, body: dict[str, Any]) -> Any:
    """Post JSON to the llama-server inside the engine container.

    Args:
        container: The engine container's name.
        port: llama-server's port inside the container.
        path: The endpoint.
        body: The JSON body.

    Returns:
        The decoded response.
    """
    result = subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            container,
            "curl",
            "-sf",
            "-X",
            "POST",
            f"http://127.0.0.1:{port}{path}",
            "-H",
            "Content-Type: application/json",
            "--data-binary",
            "@-",
        ],
        input=json.dumps(body).encode("utf-8"),
        capture_output=True,
        check=True,
    )
    return json.loads(result.stdout)


def _prompt_tokens(base_url: str, model_name: str, prompt_text: str) -> int:
    """Count the prompt tokens Lemonade reports for one chat request.

    Args:
        base_url: The Lemonade origin.
        model_name: The loaded model's id.
        prompt_text: The prompt.

    Returns:
        The reported prompt-token count.
    """
    body = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt_text}],
        "max_tokens": 1,
        "temperature": 0,
    }
    request = urllib.request.Request(
        f"{base_url}/api/v1/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=600) as response:
        return int(json.load(response)["usage"]["prompt_tokens"])


def _find(split: Path, set_name: str, sample_id: str) -> dict[str, Any]:
    """Read one sample's row from a split file.

    Args:
        split: The split directory.
        set_name: The split file's stem.
        sample_id: The sample.

    Returns:
        The decoded row.

    Raises:
        KeyError: If the sample is not in that file.
    """
    path = split / f"{set_name}.jsonl"
    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row["sample_id"] == sample_id:
            return row
    raise KeyError(f"{sample_id} is not in {path}")


def main() -> None:
    """Capture the named samples' renderings."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", type=Path, required=True)
    parser.add_argument("--sample", action="append", required=True)
    parser.add_argument("--container", default="pmc-eval-lemonade")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--base-url", default="http://localhost:13305")
    parser.add_argument("--model-name", default="Llama-3.2-1B-Instruct-Q4_K_M")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    health = json.loads(
        urllib.request.urlopen(
            f"{args.base_url}/api/v1/health", timeout=10
        ).read()
    )
    loaded = next(
        m
        for m in health["all_models_loaded"]
        if m["model_name"] == args.model_name
    )
    for entry in args.sample:
        set_name, sample_id = entry.split(":", 1)
        prompt_text = _find(args.split, set_name, sample_id)["prompt_text"]
        messages = [{"role": "user", "content": prompt_text}]
        rendered = _server(
            args.container, args.port, "/apply-template", {"messages": messages}
        )["prompt"]
        tokens = _server(
            args.container,
            args.port,
            "/tokenize",
            {"content": rendered, "add_special": True},
        )["tokens"]
        fixture = {
            "sample_id": sample_id,
            "set": set_name,
            "prompt_text": prompt_text,
            "prompt_sha256": hashlib.sha256(
                prompt_text.encode("utf-8")
            ).hexdigest(),
            "engine_render": rendered,
            "engine_token_ids": tokens,
            "engine_prompt_tokens": _prompt_tokens(
                args.base_url, args.model_name, prompt_text
            ),
            "engine": {
                "lemonade_version": health.get("version"),
                "checkpoint": loaded["checkpoint"],
                "llamacpp_args": loaded["recipe_options"].get("llamacpp_args"),
                "launch_command": loaded["launch_command"],
            },
        }
        path = args.out / f"{sample_id}.json"
        path.write_text(
            json.dumps(fixture, indent=1, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"{path}: {len(tokens)} tokens")


if __name__ == "__main__":
    main()
