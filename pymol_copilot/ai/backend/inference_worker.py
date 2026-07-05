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

"""Background QThread worker for non-blocking inference."""

from __future__ import annotations

import threading

import pymol_copilot.ai.backend.config as config_module
import pymol_copilot.ai.backend.mock_engine as mock_engine_module
import pymol_copilot.ai.backend.protocol as protocol_module
import pymol_copilot.ai.inference.conversation as conversation_module
import pymol_copilot.ai.inference.prompt_builder as prompt_builder_module
from pymol_copilot.gui.qt import QtCore


class InferenceSignals(QtCore.QObject):
    """Signals emitted by the inference worker thread."""

    generation_started = QtCore.pyqtSignal()
    token_received = QtCore.pyqtSignal(str)
    generation_finished = QtCore.pyqtSignal(str)
    generation_error = QtCore.pyqtSignal(str)
    generation_cancelled = QtCore.pyqtSignal()
    model_loaded = QtCore.pyqtSignal()


class InferenceWorker(QtCore.QThread):
    """Runs inference on a dedicated thread with cooperative cancellation."""

    def __init__(
        self,
        config: config_module.InferenceConfig,
        parent: QtCore.QObject | None = None,
    ) -> None:
        """Initialise the worker thread.

        Args:
          config: Inference configuration shared across runs.
          parent: Optional Qt parent object.
        """
        super().__init__(parent)
        self._config = config
        self._backend: protocol_module.InferenceBackend | None = None
        self._conversation = conversation_module.Conversation()
        self._cancel_event = threading.Event()
        self._pending_prompt: str | None = None
        self._signals = InferenceSignals()

    @property
    def signals(self) -> InferenceSignals:
        """Return the worker signal bus.

        Returns:
          Signal object for UI connections.
        """
        return self._signals

    @property
    def conversation(self) -> conversation_module.Conversation:
        """Return the shared multi-turn conversation store.

        Returns:
          Conversation instance mutated by the controller.
        """
        return self._conversation

    def update_config(self, config: config_module.InferenceConfig) -> None:
        """Replace runtime configuration and unload any loaded backend.

        Args:
          config: New inference configuration.
        """
        self._config = config
        if self._backend is not None:
            self._backend.unload()
            self._backend = None

    def submit(self, user_prompt: str) -> None:
        """Queue a user prompt for the next worker run.

        Args:
          user_prompt: Natural-language request text.
        """
        self._pending_prompt = user_prompt
        if not self.isRunning():
            self.start()

    def request_cancel(self) -> None:
        """Request cancellation of the active generation."""
        self._cancel_event.set()

    def request_stop(self) -> None:
        """Cancel generation and wait for the thread to finish."""
        self.request_cancel()
        self.wait(3000)

    def run(self) -> None:
        """Execute queued inference on the worker thread."""
        if self._pending_prompt is None:
            return

        user_prompt = self._pending_prompt
        self._pending_prompt = None
        self._cancel_event.clear()

        try:
            if self._backend is None:
                self._backend = self._create_backend()
                self._backend.load(self._config)
                self._signals.model_loaded.emit()

            self._conversation.append_user(user_prompt)
            prompt = self._build_prompt_with_budget()
            self._signals.generation_started.emit()

            def _on_token(delta: str) -> None:
                self._signals.token_received.emit(delta)

            output = self._backend.stream_completion(
                prompt,
                self._cancel_event,
                _on_token,
            )

            if self._cancel_event.is_set():
                self._signals.generation_cancelled.emit()
                return

            self._conversation.append_assistant(output)
            self._signals.generation_finished.emit(output)
        except Exception as exc:
            self._signals.generation_error.emit(str(exc))

    def unload_backend(self) -> None:
        """Unload backend resources on application shutdown."""
        if self._backend is not None:
            self._backend.unload()
            self._backend = None

    def _create_backend(self) -> protocol_module.InferenceBackend:
        """Instantiate the configured inference backend.

        Returns:
          Mock or llama.cpp backend instance.
        """
        if self._config.mock:
            return mock_engine_module.MockEngine()

        import pymol_copilot.ai.backend.llama_engine as llama_engine_module

        return llama_engine_module.LlamaEngine()

    def _build_prompt_with_budget(self) -> str:
        """Build a prompt while trimming history to fit ``n_ctx``.

        Returns:
          ChatML prompt ending at the assistant turn.

        Raises:
          RuntimeError: If the stable prefix alone exceeds the context budget.
        """
        while True:
            prompt = prompt_builder_module.build_prompt(
                self._conversation,
                prompt_family=self._config.prompt_family,
            )
            budget = prompt_builder_module.estimate_token_budget(prompt)
            if budget <= self._config.n_ctx - self._config.max_tokens:
                return prompt
            if len(self._conversation.turns) <= 1:
                raise RuntimeError(
                    "Prompt prefix exceeds context window. "
                    "Increase --ctx-size (e.g. 4096)."
                )
            del self._conversation.turns[0:2]
