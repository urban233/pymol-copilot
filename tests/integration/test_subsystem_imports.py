# Copyright 2026 PyMOL Copilot contributors.
"""Smoke tests for package boundaries and the authoritative interpreter."""

import sys
from pathlib import Path

import pytest


def test_subsystems_import_from_repository() -> None:
    """All subsystem names resolve to this checkout under CPython 3.13.13."""
    assert sys.version_info[:3] == (3, 13, 13)
    for package_name in ("pmc_core", "pmc_agent", "pmc_data", "pmc_train"):
        module = __import__(package_name)
        assert module.__file__ is not None
        assert Path(module.__file__).parts[-3:] == (
            "src",
            package_name,
            "__init__.py",
        )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
