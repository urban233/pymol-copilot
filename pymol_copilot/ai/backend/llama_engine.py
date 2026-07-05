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

"""llama.cpp GGUF inference backend with streaming and GBNF support."""

from __future__ import annotations

import threading
import typing

import pymol_copilot.ai.backend.config as config_module
import pymol_copilot.ai.grammar.gbnf_generator as gbnf_generator_module

_IM_END = "<|" + "im_end" + "|>"

_GRAMMAR_INFERENCE_ERROR = (
    "GBNF grammar failed during inference. "
    "Try --no-grammar or update llama-cpp-python."
)


class LlamaEngine:
    """Wraps llama-cpp-python for local CPU inference."""

    def __init__(self) -> None:
        """Initialise an unloaded llama engine."""
        self._config: config_module.InferenceConfig | None = None
        self._llm: typing.Any = None
        self._grammar: typing.Any = None
        self._grammar_text: str = ""

    def load(self, config: config_module.InferenceConfig) -> None:
        """Load the GGUF model and optional GBNF grammar.

        Args:
          config: Runtime inference configuration.

        Raises:
          FileNotFoundError: If the model path does not exist.
          RuntimeError: If llama-cpp-python is unavailable or grammar probe fails.
        """
        if not config.model_path.exists():
            raise FileNotFoundError(
                f"GGUF model not found: {config.model_path}"
            )

        try:
            import llama_cpp
        except ImportError as exc:
            raise RuntimeError(
                "llama-cpp-python is not installed. Install via ai/requirements.txt."
            ) from exc

        self._config = config
        self._llm = llama_cpp.Llama(
            model_path=str(config.model_path),
            n_ctx=config.n_ctx,
            n_threads=config.n_threads,
            n_gpu_layers=config.n_gpu_layers,
            verbose=False,
        )

        if config.use_grammar:
            self._grammar_text = gbnf_generator_module.generate_grammar()
            self._grammar = llama_cpp.LlamaGrammar.from_string(
                self._grammar_text
            )
            self._probe_grammar()
        else:
            self._grammar = None
            self._grammar_text = ""

    def unload(self) -> None:
        """Release the llama.cpp model handle."""
        self._llm = None
        self._grammar = None
        self._config = None

    def _probe_grammar(self) -> None:
        """Run a one-token completion to validate grammar at sample time.

        Raises:
          RuntimeError: If grammar sampling triggers a native failure.
        """
        if self._llm is None or self._grammar is None:
            return

        try:
            stream = self._llm(
                "x",
                max_tokens=1,
                stream=True,
                grammar=self._grammar,
                temperature=0.0,
            )
            for _chunk in stream:
                break
        except OSError as exc:
            raise RuntimeError(_GRAMMAR_INFERENCE_ERROR) from exc

    def stream_completion(
        self,
        prompt: str,
        cancel_event: threading.Event,
        on_token: typing.Callable[[str], None],
    ) -> str:
        """Stream an assistant completion from llama.cpp.

        Args:
          prompt: Fully formatted ChatML prompt.
          cancel_event: Set to abort generation.
          on_token: Callback for incremental text deltas.

        Returns:
          Full assistant output text.

        Raises:
          RuntimeError: If the engine is not loaded or grammar sampling fails.
        """
        if self._llm is None or self._config is None:
            raise RuntimeError("LlamaEngine.load() must be called first.")

        try:
            stream = self._llm(
                prompt,
                max_tokens=self._config.max_tokens,
                stop=[_IM_END],
                stream=True,
                grammar=self._grammar,
                temperature=self._config.temperature,
            )
        except OSError as exc:
            if self._grammar is not None:
                raise RuntimeError(_GRAMMAR_INFERENCE_ERROR) from exc
            raise

        accumulated = ""
        try:
            for chunk in stream:
                if cancel_event.is_set():
                    break
                delta = chunk["choices"][0]["text"]
                if not delta:
                    continue
                on_token(delta)
                accumulated += delta
        except OSError as exc:
            if self._grammar is not None:
                raise RuntimeError(_GRAMMAR_INFERENCE_ERROR) from exc
            raise

        return accumulated
