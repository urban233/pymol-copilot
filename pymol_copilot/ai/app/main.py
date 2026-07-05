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

"""CLI entry point for the cBioMOL AI assistant application."""

from __future__ import annotations

import argparse
import pathlib
import sys

from pymol_copilot.gui.qt import QtWidgets

import pymol_copilot.ai.app.main_window as main_window_module
import pymol_copilot.ai.backend.config as config_module
import pymol_copilot.ai.execution.pymol_session as pymol_session_module


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments.

    Args:
      argv: Optional argument vector override.

    Returns:
      Parsed namespace.
    """
    parser = argparse.ArgumentParser(
        description="cBioMOL PyMOL AI assistant (experimental)",
    )
    parser.add_argument(
        "--model",
        type=pathlib.Path,
        default=None,
        help="Path to the quantized GGUF model.",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use the mock backend instead of llama.cpp.",
    )
    parser.add_argument(
        "--ctx-size",
        type=int,
        default=2048,
        help="Context window size in tokens.",
    )
    parser.add_argument(
        "--no-grammar",
        action="store_true",
        help="Disable GBNF grammar constraints.",
    )
    parser.add_argument(
        "--enable-execution",
        action="store_true",
        help="Start a headless PyMOL session for plan execution.",
    )
    parser.add_argument(
        "--viewport-cores",
        type=int,
        default=2,
        help="CPU cores reserved for viewport rendering.",
    )
    parser.add_argument(
        "--prompt-family",
        choices=("qwen2", "qwen3"),
        default=None,
        help=(
            "ChatML prompt family override. Defaults to filename detection "
            "('qwen3' when the GGUF name contains qwen3)."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Launch the PyQt6 AI assistant application.

    Args:
      argv: Optional argument vector override.

    Returns:
      Process exit code.
    """
    args = _parse_args(argv)
    model_path = config_module.resolve_model_path(args.model)

    if not args.mock and not model_path.exists():
        print(
            f"[ERROR] GGUF model not found: {model_path}\n"
            "Use --mock for UI development without a model.",
            file=sys.stderr,
        )
        return 1

    inference_threads, viewport_cores = config_module.compute_thread_budget(
        args.viewport_cores,
    )
    prompt_family = args.prompt_family or config_module.detect_prompt_family(
        model_path,
    )

    config = config_module.InferenceConfig(
        model_path=model_path,
        n_ctx=args.ctx_size,
        n_threads=inference_threads,
        mock=args.mock,
        use_grammar=not args.no_grammar,
        viewport_cores=viewport_cores,
        prompt_family=prompt_family,
    )

    pymol_session: pymol_session_module.PyMOLSessionProvider | None = None
    if args.enable_execution:
        headless = pymol_session_module.HeadlessPyMOLSession()
        headless.start()
        pymol_session = headless

    app = QtWidgets.QApplication(sys.argv)
    theme_path = (
        pathlib.Path(__file__).resolve().parent / "styles" / "theme.qss"
    )
    if theme_path.exists():
        app.setStyleSheet(theme_path.read_text(encoding="utf-8"))

    window = main_window_module.MainWindow(
        config,
        pymol_session=pymol_session,
        execution_enabled=args.enable_execution,
    )
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
