# Copyright 2026 PyMOL Copilot contributors.
"""Build the deliverable notebook from its source, and optionally run it.

    PYTHONPATH=src:tools/winstage .venv-notebook/bin/python \\
        notebooks/build_notebook.py [--execute]

`source/pymol_copilot.py` holds the notebook in the percent format: a
line `# %%` starts a code cell, `# %% [markdown]` a Markdown cell whose
lines each begin with `# `; anything before the first cell (the file's
own header) is not part of the notebook. That file is what is reviewed; this script
turns it into `pymol_copilot.ipynb` deterministically (fixed cell ids,
fixed kernel spec, sorted keys), so rebuilding an unchanged source gives
the same cells. `--execute` runs every cell in a fresh kernel from
`notebooks/` and saves the outputs; the committed notebook is that
executed build. The end-user demonstration runs only when
`PMC_NOTEBOOK_DEMO=1` is set and a Lemonade server serves the model.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "source" / "pymol_copilot.py"
NOTEBOOK = HERE / "pymol_copilot.ipynb"

#: Which kernel runs the notebook.
KERNELSPEC = {
    "display_name": "Python 3 (ipykernel)",
    "language": "python",
    "name": "python3",
}


def parse_cells(text: str) -> list[tuple[str, str]]:
    """Split percent-format source into cells.

    Args:
        text: The source file's text.

    Returns:
        Each cell's type (`code` or `markdown`) and source, in order.

    Raises:
        ValueError: If a Markdown line does not begin with `#`.
    """
    cells: list[tuple[str, list[str]]] = []
    for line in text.splitlines():
        if line.startswith("# %%"):
            kind = "markdown" if "[markdown]" in line else "code"
            cells.append((kind, []))
        elif cells:
            cells[-1][1].append(line)
    built = []
    for kind, lines in cells:
        while lines and not lines[-1].strip():
            lines.pop()
        body = lines
        if kind == "markdown":
            for line in lines:
                if line != "#" and not line.startswith("# "):
                    raise ValueError(f"not a Markdown comment line: {line!r}")
            body = [line[2:] for line in lines]
        built.append((kind, "\n".join(body)))
    return built


def build(source: Path = SOURCE) -> object:
    """Build the unexecuted notebook.

    Args:
        source: The percent-format source.

    Returns:
        The `nbformat` notebook node.
    """
    import nbformat

    notebook = nbformat.v4.new_notebook()
    notebook.metadata = {
        "kernelspec": KERNELSPEC,
        "language_info": {"name": "python"},
    }
    for index, (kind, text) in enumerate(
        parse_cells(source.read_text("utf-8"))
    ):
        cell = (
            nbformat.v4.new_markdown_cell(text)
            if kind == "markdown"
            else nbformat.v4.new_code_cell(text)
        )
        cell["id"] = f"cell-{index:03d}"
        notebook.cells.append(cell)
    return notebook


def execute(notebook: object, timeout: int = 1800) -> object:
    """Run every cell in a fresh kernel from `notebooks/`.

    Args:
        notebook: The built notebook.
        timeout: Seconds any one cell may take.

    Returns:
        The executed notebook, with outputs and no timing metadata.
    """
    from nbclient import NotebookClient

    NotebookClient(
        notebook,
        timeout=timeout,
        kernel_name="python3",
        resources={"metadata": {"path": str(HERE)}},
        record_timing=False,
    ).execute()
    return notebook


def main(argv: list[str] | None = None) -> int:
    """Build, optionally execute, and write the notebook.

    Args:
        argv: The command line, without the program name.

    Returns:
        The exit code.
    """
    import nbformat

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--out", type=Path, default=NOTEBOOK)
    args = parser.parse_args(argv)
    notebook = build()
    if args.execute:
        notebook = execute(notebook)
    nbformat.write(notebook, args.out)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
