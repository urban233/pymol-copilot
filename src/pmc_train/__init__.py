# Copyright 2026 PyMOL Copilot contributors.
"""Model development: completion-only fine-tuning (master plan item 17).

Runs in the separate Python 3.12 training environment
(`requirements-train.txt`), outside the Bazel closure. Nothing here is
imported by the runtime. Unsloth is imported only inside a GPU training
run, never at package import.
"""
