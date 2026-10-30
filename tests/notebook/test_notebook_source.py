# Copyright 2026 PyMOL Copilot contributors.
"""The committed notebook is exactly its reviewed source's build.

The notebook is reviewed as `notebooks/source/pymol_copilot.py`; the
`.ipynb` is built from it (`notebooks/build_notebook.py`) and executed.
If the two drift, a reviewer approves one text and the instructor reads
another. This compares every cell's type and source, without Jupyter:
the builder's parser is plain Python, and the notebook is JSON.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
NOTEBOOKS = ROOT / "notebooks"


def _builder() -> Any:
    """Import `notebooks/build_notebook.py` as a module.

    Returns:
        The module.
    """
    spec = importlib.util.spec_from_file_location(
        "build_notebook", NOTEBOOKS / "build_notebook.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


#: Each committed notebook's name; its source is `source/<name>.py`. The
#: second is the German short version.
NAMES = ("pymol_copilot", "pymol_copilot_kurz")


def _committed(name: str) -> dict[str, Any]:
    """Read one committed notebook.

    Args:
        name: The notebook's name, without `.ipynb`.

    Returns:
        Its JSON document.
    """
    return json.loads((NOTEBOOKS / f"{name}.ipynb").read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", NAMES)
def test_every_cell_is_the_sources_cell(name: str) -> None:
    """Same cells, same order, same types, same text."""
    source = (NOTEBOOKS / "source" / f"{name}.py").read_text("utf-8")
    expected = _builder().parse_cells(source)
    cells = _committed(name)["cells"]
    assert [(cell["cell_type"], "".join(cell["source"])) for cell in cells] == [
        (kind, text) for kind, text in expected
    ]


@pytest.mark.parametrize("name", NAMES)
def test_cell_ids_are_the_builders_own(name: str) -> None:
    """Cell ids are fixed, so a rebuild changes nothing it need not."""
    ids = [cell["id"] for cell in _committed(name)["cells"]]
    assert ids == [f"cell-{index:03d}" for index in range(len(ids))]


def test_a_markdown_cell_needs_comment_lines() -> None:
    """The parser refuses a Markdown line that is not a comment."""
    with pytest.raises(ValueError, match="not a Markdown comment line"):
        _builder().parse_cells("# %% [markdown]\n# fine\nnot a comment\n")


def test_the_files_own_header_is_not_a_cell() -> None:
    """Lines before the first cell marker stay out of the notebook."""
    cells = _builder().parse_cells("# header\n# ruff: noqa\n\n# %%\nx = 1\n")
    assert cells == [("code", "x = 1")]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
