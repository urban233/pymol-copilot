# Copyright 2026 PyMOL Copilot contributors.
"""The demo environment's lock is the runtime's PyMOL, plus Qt only.

docs/master_plan.md item 19. The pinned PyMOL wheel cannot open a window
without a Qt binding, so the demo's GUI runs from its own environment
(`requirements-demo.txt`). It must run the same PyMOL and numpy as the
runtime the evaluation measured, and add nothing but the binding.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DEMO_LOCK = ROOT / "requirements-demo.txt"
RUNTIME_LOCK = ROOT / "requirements_lock.txt"

#: What the demo environment adds to the runtime's packages.
QT_BINDING = {"pyside6-essentials", "shiboken6"}


def _pins(lock: Path) -> dict[str, str]:
    """Read every `name==version` pin out of a lock.

    Args:
        lock: The lock file.

    Returns:
        The locked version of each package, by lower-cased name.
    """
    pins: dict[str, str] = {}
    for line in lock.read_text(encoding="utf-8").splitlines():
        if "==" in line and not line.startswith((" ", "#")):
            name, version = line.split(" ", 1)[0].split("==")
            pins[name.lower()] = version
    return pins


def test_the_demo_runs_the_runtimes_pymol_and_numpy() -> None:
    """Every package both locks pin is pinned identically."""
    demo, runtime = _pins(DEMO_LOCK), _pins(RUNTIME_LOCK)

    assert demo["pymol-open-source-whl"] == "3.2.0.2"
    shared = set(demo) & set(runtime)
    assert shared >= {"pymol-open-source-whl", "numpy"}
    assert {name: demo[name] for name in shared} == {
        name: runtime[name] for name in shared
    }


def test_the_demo_adds_only_the_qt_binding() -> None:
    """Nothing else reaches the demo's PyMOL process."""
    demo, runtime = _pins(DEMO_LOCK), _pins(RUNTIME_LOCK)

    assert set(demo) - set(runtime) == QT_BINDING


def test_every_pin_is_hashed() -> None:
    """The lock installs with `--require-hashes`."""
    text = DEMO_LOCK.read_text(encoding="utf-8")

    assert text.count("--hash=sha256:") >= len(_pins(DEMO_LOCK))


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
