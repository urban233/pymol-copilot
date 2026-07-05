# cBioMOL - open C++ and Python platform for BioMOLecular visualization and analysis
# -------------------------------------------------------------------
# This file contains source code for the cBioMOL computer program
# Copyright (C) 2026 Hannah Kullik, Martin Urban (hannah.kullik@studmail.w-hs.de, martin.urban@studmail.w-hs.de)
# Source code is available at <https://github.com/urban233/cBioMOL>
# -------------------------------------------------------------------
# It is unlawful to modify or remove this copyright notice.
# -------------------------------------------------------------------
# Please see the accompanying LICENSE file for further information.
# -------------------------------------------------------------------
# Primary author of this source file:
#
# ==============================================================================
#
"""Automated dataset generation via the Google Gemini API.

This script reads the prompt batch files produced by::

    python generate_dataset.py --mode generate_prompts ...

and submits each file to the Gemini API, saving the model's response
as a matching ``.response.txt`` file.  Those response files are then
consumed by::

    python generate_dataset.py --mode collect_responses ...

Two tier profiles are supported:

``free``
    Uses ``gemini-2.0-flash``.  Enforces 15 RPM (4 s between requests)
    and tracks requests-per-day against the 1,500 RPD ceiling.  The
    inter-request delay is conservative — it uses the *minimum* required
    delay plus a 0.5 s buffer to absorb clock skew.

``paid``
    Uses ``gemini-2.0-flash`` at a higher throughput ceiling (2,000 RPM
    → 30 ms minimum gap).  A 100 ms floor is applied anyway to avoid
    thundering-herd behaviour on your account.

Both tiers apply exponential back-off on HTTP 429 / 503 responses with
up to ``MAX_RETRIES`` attempts.

Authentication
--------------
The API key is read from the ``GOOGLE_API_KEY`` environment variable or
from ``--api_key``.  Get a key at https://aistudio.google.com/apikey.

Usage
-----
.. code-block:: bash

    # Free tier (respects 15 RPM / 1,500 RPD limits)
    python generate_dataset_gemini.py \\
        --prompts_dir data/prompts/ \\
        --tier free

    # Paid tier (higher throughput)
    python generate_dataset_gemini.py \\
        --prompts_dir data/prompts/ \\
        --tier paid

    # Override model
    python generate_dataset_gemini.py \\
        --prompts_dir data/prompts/ \\
        --tier free \\
        --model gemini-2.0-flash-lite

    # Dry run — print prompts without calling the API
    python generate_dataset_gemini.py \\
        --prompts_dir data/prompts/ \\
        --tier free \\
        --dry_run
"""

from __future__ import annotations

import argparse
import os
import pathlib
import sys
import time

import google.generativeai as genai


# ---------------------------------------------------------------------------
# Tier configuration
# ---------------------------------------------------------------------------

# Rate limits sourced from https://ai.google.dev/gemini-api/docs/rate-limits
# All values are for the Gemini API (Google AI Studio keys).

#: Default model for both tiers.  The same model is used deliberately so
#: prompt content (not model differences) is the controlled variable.
_DEFAULT_MODEL = "gemini-2.0-flash"

#: Maximum number of retry attempts on transient API errors (429, 503).
_MAX_RETRIES = 5

#: Base back-off duration in seconds (doubles on each retry).
_BACKOFF_BASE_SECONDS = 4.0


class _TierConfig:
    """Immutable rate-limit configuration for a billing tier.

    Attributes:
      name: Human-readable tier name.
      rpm: Maximum requests per minute allowed by the API.
      rpd: Maximum requests per day (0 = unlimited / not tracked).
      min_delay_seconds: Minimum wait between consecutive API calls.
      rpd_warn_threshold: Warn when the day counter reaches this value.
    """

    def __init__(
        self,
        name: str,
        rpm: int,
        rpd: int,
        min_delay_seconds: float,
        rpd_warn_threshold: int,
    ) -> None:
        """Initialise a tier configuration.

        Args:
          name: Human-readable tier name.
          rpm: API requests-per-minute ceiling.
          rpd: API requests-per-day ceiling (0 = not tracked).
          min_delay_seconds: Minimum sleep between consecutive requests.
          rpd_warn_threshold: Issue a warning at this daily request count.
        """
        self.name = name
        self.rpm = rpm
        self.rpd = rpd
        self.min_delay_seconds = min_delay_seconds
        self.rpd_warn_threshold = rpd_warn_threshold


# Free tier: gemini-2.0-flash — 15 RPM, 1,500 RPD
# Minimum gap = 60 / 15 = 4.0 s; add 0.5 s buffer for clock skew.
_TIER_FREE = _TierConfig(
    name="free",
    rpm=15,
    rpd=1_500,
    min_delay_seconds=4.5,
    rpd_warn_threshold=1_400,
)

# Paid tier: gemini-2.0-flash — 2,000 RPM (no practical RPD cap).
# Minimum gap = 60 / 2000 = 0.030 s; apply 100 ms floor to be polite.
_TIER_PAID = _TierConfig(
    name="paid",
    rpm=2_000,
    rpd=0,
    min_delay_seconds=0.1,
    rpd_warn_threshold=0,
)

_TIERS: dict[str, _TierConfig] = {
    _TIER_FREE.name: _TIER_FREE,
    _TIER_PAID.name: _TIER_PAID,
}


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------


def _configure_api(api_key: str | None) -> None:
    """Configure the google-generativeai client with the provided key.

    Falls back to the ``GOOGLE_API_KEY`` environment variable if
    ``api_key`` is ``None``.

    Args:
      api_key: Explicit API key string, or ``None`` to use the environment.

    Raises:
      SystemExit: If no key is found in either source.
    """
    key = api_key or os.environ.get("GOOGLE_API_KEY", "")
    if not key:
        print(
            "[ERROR] No Gemini API key found.\n"
            "Set GOOGLE_API_KEY in your environment or pass --api_key.\n"
            "Get a key at https://aistudio.google.com/apikey",
            file=sys.stderr,
        )
        sys.exit(1)
    genai.configure(api_key=key)


def _call_api_with_retry(
    model: genai.GenerativeModel,
    prompt: str,
    tier: _TierConfig,
) -> str:
    """Submit a prompt to the Gemini API with exponential back-off.

    Retries on HTTP 429 (rate limit) and 503 (service unavailable) up to
    ``_MAX_RETRIES`` times.  All other exceptions are re-raised immediately.

    Args:
      model: Configured ``GenerativeModel`` instance.
      prompt: Full prompt string (system instruction already embedded).
      tier: Tier config; used for logging only.

    Returns:
      The raw text of the model's first candidate response.

    Raises:
      SystemExit: After ``_MAX_RETRIES`` consecutive failures.
    """
    delay = _BACKOFF_BASE_SECONDS
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            response = model.generate_content(prompt)
            return response.text
        except Exception as exc:  # noqa: BLE001 (intentional broad catch)
            exc_str = str(exc)
            is_retryable = (
                "429" in exc_str
                or "503" in exc_str
                or "RESOURCE_EXHAUSTED" in exc_str
                or "UNAVAILABLE" in exc_str
            )
            if not is_retryable or attempt == _MAX_RETRIES:
                print(
                    f"[ERROR] API call failed (attempt {attempt}/{_MAX_RETRIES}): {exc}",
                    file=sys.stderr,
                )
                sys.exit(1)
            print(
                f"[{tier.name}] Transient error (attempt {attempt}): {exc}\n"
                f"  Backing off {delay:.1f}s before retry ..."
            )
            time.sleep(delay)
            delay = min(delay * 2, 120.0)

    # Unreachable but satisfies the type checker.
    sys.exit(1)


# ---------------------------------------------------------------------------
# Batch file discovery and processing
# ---------------------------------------------------------------------------


def _discover_batches(prompts_dir: pathlib.Path) -> list[pathlib.Path]:
    """Return all prompt batch files, sorted by name.

    Matches both the new-style categorised names (``batch_pos_NNN.txt``,
    ``batch_neg_NNN.txt``) and legacy mixed names (``batch_NNN.txt``).

    Args:
      prompts_dir: Directory containing prompt batch ``.txt`` files.

    Returns:
      Sorted list of ``.txt`` batch file paths.

    Raises:
      SystemExit: If no batch files are found.
    """
    patterns = [
        "batch_pos_*.txt",
        "batch_neg_*.txt",
        "batch_[0-9]*.txt",
    ]
    found: list[pathlib.Path] = []
    for pattern in patterns:
        found.extend(prompts_dir.glob(pattern))

    # Exclude .response.txt files that happen to match the glob
    found = [p for p in found if not p.name.endswith(".response.txt")]

    if not found:
        print(
            f"[ERROR] No prompt batch files found in {prompts_dir}.\n"
            "Run generate_dataset.py --mode generate_prompts first.",
            file=sys.stderr,
        )
        sys.exit(1)

    return sorted(set(found), key=lambda p: p.name)


def _response_path(batch_file: pathlib.Path) -> pathlib.Path:
    """Return the expected response file path for a given batch file.

    The naming convention is ``<stem>.response.txt`` alongside the
    batch file.  This is the format expected by
    ``generate_dataset.py --mode collect_responses``.

    Args:
      batch_file: Path to a batch prompt ``.txt`` file.

    Returns:
      Sibling ``.response.txt`` path.
    """
    return batch_file.with_suffix(".response.txt")


def _process_batches(
    batches: list[pathlib.Path],
    model: genai.GenerativeModel,
    tier: _TierConfig,
    resume: bool,
    dry_run: bool,
) -> None:
    """Process each batch file, calling the API and saving responses.

    Each batch file content is submitted as a single prompt.  The model's
    response is written to ``<batch_stem>.response.txt`` in the same
    directory.  Already-completed files are skipped when ``resume=True``.

    Args:
      batches: Ordered list of batch ``.txt`` file paths.
      model: Configured ``GenerativeModel`` to call.
      tier: Active tier config for rate limiting and logging.
      resume: If ``True``, skip batches that already have a response file.
      dry_run: If ``True``, print prompts but do not call the API.
    """
    total = len(batches)
    daily_count = 0
    last_request_time: float = 0.0

    for idx, batch_file in enumerate(batches, start=1):
        resp_file = _response_path(batch_file)

        # Skip completed batches if resuming
        if resume and resp_file.exists():
            print(
                f"[{idx:3d}/{total}] SKIP (response exists): {batch_file.name}"
            )
            continue

        # Daily limit guard (free tier only)
        if tier.rpd > 0:
            if daily_count >= tier.rpd:
                print(
                    f"\n[{tier.name}] Daily request limit ({tier.rpd} RPD) reached.\n"
                    "Resume tomorrow or switch to --tier paid.",
                    file=sys.stderr,
                )
                sys.exit(1)
            if (
                tier.rpd_warn_threshold > 0
                and daily_count >= tier.rpd_warn_threshold
            ):
                remaining = tier.rpd - daily_count
                print(
                    f"[WARNING] Approaching daily limit: {daily_count}/{tier.rpd} "
                    f"requests used ({remaining} remaining today)."
                )

        prompt = batch_file.read_text(encoding="utf-8")

        if dry_run:
            print(
                f"[{idx:3d}/{total}] DRY RUN — would send {batch_file.name} "
                f"({len(prompt)} chars)"
            )
            continue

        # Rate limiting: sleep so that the gap since the last call is at
        # least tier.min_delay_seconds.
        elapsed = time.monotonic() - last_request_time
        wait = tier.min_delay_seconds - elapsed
        if wait > 0:
            time.sleep(wait)

        print(
            f"[{idx:3d}/{total}] Sending {batch_file.name} ({len(prompt)} chars) ...",
            end="",
            flush=True,
        )
        t0 = time.monotonic()
        last_request_time = t0

        response_text = _call_api_with_retry(model, prompt, tier)
        elapsed_call = time.monotonic() - t0
        daily_count += 1

        resp_file.write_text(response_text, encoding="utf-8")
        print(
            f" done in {elapsed_call:.1f}s  "
            f"[day total: {daily_count}"
            + (f"/{tier.rpd}]" if tier.rpd else "]")
        )

    if not dry_run:
        print(
            f"\n[generate_dataset_gemini] All batches processed.\n"
            f"  Requests this session : {daily_count}\n"
            f"  Response files in     : {batches[0].parent}\n"
            f"\nNext step:\n"
            f"  python generate_dataset.py \\\n"
            f"      --mode collect_responses \\\n"
            f"      --input_dir {batches[0].parent} \\\n"
            f"      --output_dir <your_data_dir>/"
        )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
      Parsed argument namespace.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Generate cBioMOL training data via the Google Gemini API. "
            "Reads batch_*.txt files and writes batch_*.response.txt."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--prompts_dir",
        type=pathlib.Path,
        default=pathlib.Path("data/prompts"),
        help="Directory containing batch_*.txt prompt files.",
    )
    parser.add_argument(
        "--tier",
        choices=list(_TIERS.keys()),
        default="free",
        help=(
            "Billing tier.  'free': 15 RPM / 1,500 RPD (Google AI Studio "
            "free tier).  'paid': 2,000 RPM (Pay-as-you-go / Vertex AI)."
        ),
    )
    parser.add_argument(
        "--model",
        default=_DEFAULT_MODEL,
        help=(
            "Gemini model name.  Defaults to gemini-2.0-flash.  "
            "Other options: gemini-2.0-flash-lite, gemini-1.5-flash, "
            "gemini-1.5-pro.  "
            "NOTE: changing the model may require adjusting --tier limits."
        ),
    )
    parser.add_argument(
        "--api_key",
        default=None,
        help=(
            "Google AI Studio API key.  Falls back to the GOOGLE_API_KEY "
            "environment variable if omitted."
        ),
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        default=True,
        help=(
            "Skip batch files that already have a matching .response.txt.  "
            "Enabled by default — use --no_resume to force re-processing."
        ),
    )
    parser.add_argument(
        "--no_resume",
        dest="resume",
        action="store_false",
        help="Re-process all batches even if a response file already exists.",
    )
    parser.add_argument(
        "--dry_run",
        action="store_true",
        help=(
            "Print what would be sent to the API without making any actual "
            "calls.  Useful for inspecting prompts before burning quota."
        ),
    )
    parser.add_argument(
        "--max_batches",
        type=int,
        default=0,
        help=(
            "Process at most this many batches (0 = no limit).  "
            "Useful for small test runs."
        ),
    )
    return parser.parse_args()


def main() -> None:
    """Entry point for the Gemini dataset generation script."""
    args = _parse_args()
    tier = _TIERS[args.tier]

    print(
        f"[generate_dataset_gemini] Starting\n"
        f"  Tier           : {tier.name} "
        f"({tier.rpm} RPM" + (f" / {tier.rpd} RPD" if tier.rpd else "") + f")\n"
        f"  Model          : {args.model}\n"
        f"  Prompts dir    : {args.prompts_dir}\n"
        f"  Resume         : {args.resume}\n"
        f"  Dry run        : {args.dry_run}\n"
        f"  Min delay      : {tier.min_delay_seconds}s between requests"
    )

    if not args.prompts_dir.is_dir():
        print(
            f"[ERROR] prompts_dir does not exist: {args.prompts_dir}",
            file=sys.stderr,
        )
        sys.exit(1)

    _configure_api(args.api_key)

    generation_config = genai.types.GenerationConfig(
        temperature=0.9,
        top_p=0.95,
        max_output_tokens=8192,
    )
    model = genai.GenerativeModel(
        model_name=args.model,
        generation_config=generation_config,
    )

    batches = _discover_batches(args.prompts_dir)

    if args.max_batches > 0:
        batches = batches[: args.max_batches]

    print(
        f"  Batches found  : {len(batches)}"
        + (f" (capped at {args.max_batches})" if args.max_batches else "")
    )

    if tier.rpd > 0 and len(batches) > tier.rpd:
        print(
            f"[WARNING] {len(batches)} batches exceed the daily limit "
            f"({tier.rpd} RPD).  The script will stop when the limit is "
            "reached.  Run again tomorrow to continue."
        )

    _process_batches(
        batches=batches,
        model=model,
        tier=tier,
        resume=args.resume,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
