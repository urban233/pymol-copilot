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

"""Protocol definition for pluggable inference backends."""

from __future__ import annotations

import threading
import typing

if typing.TYPE_CHECKING:
    import pymol_copilot.ai.backend.config as config_module


class InferenceBackend(typing.Protocol):
    """Contract implemented by mock and llama.cpp inference engines."""

    def load(self, config: "config_module.InferenceConfig") -> None:
        """Load model resources required for inference.

        Args:
          config: Runtime inference configuration.

        Raises:
          FileNotFoundError: If a real model file is missing.
          RuntimeError: If backend initialisation fails.
        """
        ...

    def unload(self) -> None:
        """Release backend resources."""
        ...

    def stream_completion(
        self,
        prompt: str,
        cancel_event: threading.Event,
        on_token: typing.Callable[[str], None],
    ) -> str:
        """Stream a completion for the given prompt.

        Args:
          prompt: Fully formatted ChatML prompt ending at assistant turn.
          cancel_event: Set by the UI thread to abort generation.
          on_token: Callback invoked for each incremental text delta.

        Returns:
          Full assistant output text accumulated during streaming.

        Raises:
          RuntimeError: If generation fails before completion.
        """
        ...
