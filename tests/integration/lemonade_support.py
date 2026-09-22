# Copyright 2026 PyMOL Copilot contributors.
"""Shared environment validation for opt-in Lemonade integration evidence."""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import os

import pytest

from pmc_agent.inference.lemonade import _local_origin

_BASE_URL_ENVIRONMENT_VARIABLE = "PMC_LEMONADE_BASE_URL"


@pytest.fixture(scope="session")
def lemonade_base_url() -> str:
    """Return the explicitly enabled, production-validated Lemonade origin.

    Returns:
        The configured loopback-only Lemonade HTTP origin.

    Raises:
        pytest.fail: The supplied origin is not acceptable to production.
    """
    base_url = os.environ.get(_BASE_URL_ENVIRONMENT_VARIABLE)
    if base_url is None:
        pytest.skip(
            "PMC_LEMONADE_BASE_URL is unset; Lemonade integration evidence is opt-in"
        )
    try:
        _local_origin(base_url)
    except ValueError as error:
        pytest.fail(
            "PMC_LEMONADE_BASE_URL must be a bare loopback HTTP origin: "
            f"{error}"
        )
    return base_url
