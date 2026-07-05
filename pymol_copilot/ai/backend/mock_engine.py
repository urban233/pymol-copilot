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
# -------------------------------------------------------------------
# Additional authors of this source file include:
#
# ==============================================================================

"""Deterministic mock inference backend for UI development without GGUF."""

from __future__ import annotations

import re
import threading
import time
import typing

import pymol_copilot.ai.backend.config as config_module

_REFUSAL_KEYWORDS = re.compile(
    r"\b(rotate|zoom|spin|clip|simulation|dynamics|dock|homology)\b",
    re.IGNORECASE,
)

_POSITIVE_TEMPLATE = (
    "I will prepare the requested PyMOL visualization.\n"
    "<tool_call>\n"
    '{"name": "load_structure", "arguments": {"pdb_id": "7BZ5"}}\n'
    "</tool_call>\n"
    "<tool_call>\n"
    '{"name": "color_by_scheme", "arguments": {"target": "7BZ5", '
    '"color": "red"}}\n'
    "</tool_call>\n"
)

_REFUSAL_TEMPLATE = (
    "This operation cannot be automated here. "
    "Please use PyMOL's interface directly to perform it."
)


class MockEngine:
    """Streams canned assistant output word-by-word for M4 UI testing."""

    def __init__(self) -> None:
        """Initialise an unloaded mock engine."""
        self._config: config_module.InferenceConfig | None = None

    def load(self, config: config_module.InferenceConfig) -> None:
        """Accept configuration without loading any model file.

        Args:
          config: Runtime inference configuration.
        """
        self._config = config

    def unload(self) -> None:
        """Clear cached configuration."""
        self._config = None

    def stream_completion(
        self,
        prompt: str,
        cancel_event: threading.Event,
        on_token: typing.Callable[[str], None],
    ) -> str:
        """Emit a deterministic assistant response based on prompt keywords.

        Args:
          prompt: Formatted ChatML prompt (only the user segment is inspected).
          cancel_event: Set to abort streaming early.
          on_token: Callback for each streamed fragment.

        Returns:
          Full generated assistant text.

        Raises:
          RuntimeError: If ``load`` was not called first.
        """
        if self._config is None:
            raise RuntimeError(
                "MockEngine.load() must be called before inference."
            )

        user_match = re.search(
            r"<\|im_start\|>user\n(.*?)(?:<\|im_end\|>|<\|redacted_im_end\|>|$)",
            prompt,
            re.DOTALL,
        )
        user_text = user_match.group(1).strip() if user_match else prompt

        if self._config.dry_run or _REFUSAL_KEYWORDS.search(user_text):
            output = _REFUSAL_TEMPLATE
        else:
            output = _POSITIVE_TEMPLATE

        parts = re.split(r"(\s+)", output)
        accumulated = ""
        for part in parts:
            if cancel_event.is_set():
                break
            if not part:
                continue
            on_token(part)
            accumulated += part
            time.sleep(0.02)

        return accumulated
