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

"""Multi-turn conversation store for ChatML prompt construction."""

from __future__ import annotations

import dataclasses


_SYSTEM_PROMPT = (
    "You are a PyMOL AI assistant for the cBioMOL platform. "
    "You help structural biologists automate protein visualization "
    "workflows using natural language. "
    "When the user asks you to perform a structural biology operation, "
    "respond with the appropriate tool call. "
    "For viewport operations (rotate, zoom), explain they must be done "
    "manually."
)


@dataclasses.dataclass
class Conversation:
    """Ordered user/assistant turns used to build inference prompts."""

    turns: list[dict] = dataclasses.field(default_factory=list)

    def append_user(self, content: str) -> None:
        """Append a user message turn.

        Args:
          content: Natural-language user request.
        """
        self.turns.append({"role": "user", "content": content})

    def append_assistant(self, content: str) -> None:
        """Append an assistant message turn.

        Args:
          content: Raw assistant output including tool-call blocks.
        """
        self.turns.append({"role": "assistant", "content": content})

    def clear(self) -> None:
        """Remove all stored turns."""
        self.turns.clear()

    @property
    def system_prompt(self) -> str:
        """Return the stable system prompt prefix.

        Returns:
          Base system instructions shared across every inference call.
        """
        return _SYSTEM_PROMPT
