# Copyright 2026 PyMOL Copilot contributors.
"""Offline evaluation harness (docs/master_plan.md item 16).

Runs a model through the runtime's own request graph against the held-out
split and grades every sample against the assertions stored with it. No
runtime package may depend on this one: it depends on pmc_data, which
tools/bazel/check_dependency_boundaries.py forbids in every runtime
closure, so a runtime import of pmc_eval fails that check transitively.
"""
