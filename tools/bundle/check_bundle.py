# Copyright 2026 PyMOL Copilot contributors.
"""Check a portable bundle from inside it, with its own Python.

    pymol-copilot\\python\\python.exe pymol-copilot\\repo\\tools\\bundle\\check_bundle.py

Master plan item 20 (plans/16-portable-bundle.md, step 6). It runs what a
colleague's double-click runs, in the launcher's environment, and fails
loudly where the bundle would fail them:

1. PyMOL launches inside a Jupyter kernel of the bundle's Python;
2. a fresh PyMOL sidecar, spawned from the bundle's relocated Python,
   runs gold item `gold_056` and reproduces the resulting fingerprint
   recorded on Linux;
3. a copy of the notebook executes top to bottom (section 9 too when the
   bundle holds the model), and the notebook's record test recomputes
   every number it reports from the committed evidence.

Nothing outside the bundle is written but temporary files; the executed
copy is kept in `state\\check\\`.
"""

from __future__ import annotations  # noqa: I001, RUF100  # Keep imports split for Google style.

import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bundle_spec  # noqa: E402

#: The bundle's folder: this file is `repo\tools\bundle\check_bundle.py`.
BUNDLE = HERE.parents[2]
REPOSITORY = BUNDLE / "repo"
NOTEBOOKS = REPOSITORY / "notebooks"


def _use_launcher_environment(*, demo: bool) -> None:
    """Give this process, and every kernel it starts, the launcher's setup.

    Args:
        demo: Whether the live demo runs.
    """
    for name, value in bundle_spec.environment(str(BUNDLE), demo=demo).items():
        if value:
            os.environ[name] = value
        else:
            os.environ.pop(name, None)
    for name in bundle_spec.STATE_VARIABLES:
        Path(os.environ[name]).mkdir(parents=True, exist_ok=True)
    for path in (REPOSITORY / "tools" / "winstage", REPOSITORY / "src"):
        sys.path.insert(0, str(path))


def _execute(cells: list[str] | Path, *, timeout: int) -> object:
    """Run a notebook in a fresh kernel from `notebooks\\`.

    Args:
        cells: Code cells to run, or a notebook file.
        timeout: Seconds each cell may take.

    Returns:
        The executed notebook.
    """
    import nbformat  # pyrefly: ignore.
    from nbclient import NotebookClient  # pyrefly: ignore.

    if isinstance(cells, Path):
        notebook = nbformat.read(cells, as_version=4)
    else:
        notebook = nbformat.v4.new_notebook(
            cells=[nbformat.v4.new_code_cell(source) for source in cells]
        )
    NotebookClient(
        notebook,
        timeout=timeout,
        kernel_name="python3",
        resources={"metadata": {"path": str(NOTEBOOKS)}},
    ).execute()
    return notebook


def check_pymol_in_a_kernel() -> str:
    """Launch PyMOL in a Jupyter kernel, as section 9 does.

    Returns:
        What PyMOL reported.
    """
    notebook = _execute(
        [
            "import notebook_support as support\n"
            "support.setup_paths()\n"
            "cmd = support.launch_pymol()",
            "cmd.fragment('ala')\nprint(cmd.count_atoms('all'))",
        ],
        timeout=600,
    )
    output = notebook.cells[1].outputs[0]["text"].strip()  # pyrefly: ignore.
    if int(output) <= 0:
        raise AssertionError(f"PyMOL built no atoms: {output}")
    return f"{output} atoms in a fragment"


def check_the_sidecar() -> str:
    """Run gold item `gold_056` in a fresh PyMOL sidecar.

    Returns:
        The fingerprint it reproduced.

    Raises:
        AssertionError: If the sidecar fails or its result differs from
            the one recorded on Linux.
    """
    from pmc_core.executor import EXECUTOR_VERSION
    from pmc_core.executor import REASON_OK
    from pmc_core.executor import ExecutionRequest
    from pmc_core.executor import execute
    from pmc_core.parser import parse_pml
    from pmc_core.parser import ParseRejection
    from pmc_core.snapshot import structure_digest
    from pmc_core.snapshot import to_json
    from pmc_data.structures import StructureSpec
    from pmc_data.structures import build_structure

    gold = REPOSITORY / "src" / "pmc_data" / "gold" / "gold_samples.jsonl"
    sample = next(
        row
        for row in map(
            json.loads, gold.read_text(encoding="utf-8").splitlines()
        )
        if row["sample_id"] == "gold_056"
    )
    snapshot = build_structure(
        StructureSpec.from_dict(sample["structure"]["spec"])
    )
    plan = parse_pml(sample["plan_pml"])
    if isinstance(plan, ParseRejection):
        raise AssertionError(f"gold_056's plan does not parse: {plan}")
    expected = sample["verification"]["expected_fingerprint"]
    report = execute(
        ExecutionRequest(
            executor_version=EXECUTOR_VERSION,
            plan=plan,
            snapshot_json=to_json(snapshot),
            expected_snapshot_digest=structure_digest(snapshot),
            expected_resulting_fingerprint=expected,
            deadline_seconds=120.0,
        )
    )
    if report.reason != REASON_OK:
        raise AssertionError(f"the sidecar failed: {report}")
    return expected


def check_the_notebook(*, demo: bool) -> str:
    """Execute a copy of the notebook and recompute what it reports.

    Args:
        demo: Whether section 9 runs (the bundle holds the model).

    Returns:
        How long it took.

    Raises:
        AssertionError: If the record test fails.
    """
    import nbformat  # pyrefly: ignore.

    started = time.monotonic()
    notebook = _execute(NOTEBOOKS / "pymol_copilot.ipynb", timeout=1800)
    copy = BUNDLE / "state" / "check" / "pymol_copilot.ipynb"
    copy.parent.mkdir(parents=True, exist_ok=True)
    nbformat.write(notebook, copy)
    elapsed = time.monotonic() - started
    test = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-p",
        "no:cacheprovider",
        str(REPOSITORY / "tests" / "notebook" / "test_notebook_record.py"),
    ]
    if not demo:
        test += ["-k", "not demonstration"]
    result = subprocess.run(
        test,
        env={
            **os.environ,
            "PMC_NOTEBOOK_PATH": str(copy),
            "PYTHONPATH": str(REPOSITORY / "src"),
        },
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(f"the record test failed on {copy}")
    return f"executed in {elapsed:.0f} s; every reported number recomputes"


def main() -> int:
    """Run every check and report.

    Returns:
        0 when every check passes, 1 otherwise.
    """
    manifest = json.loads((BUNDLE / "bundle.json").read_text(encoding="utf-8"))
    demo = manifest["model"] is not None
    _use_launcher_environment(demo=demo)
    print(f"bundle {manifest['commit']}, live demo {'on' if demo else 'off'}")
    checks = [
        ("PyMOL in a Jupyter kernel", check_pymol_in_a_kernel),
        ("PyMOL sidecar reproduces gold_056", check_the_sidecar),
        ("the notebook", lambda: check_the_notebook(demo=demo)),
    ]
    failed = 0
    # Every check is reported, not only the first that fails.
    for name, check in checks:
        try:
            print(f"ok    {name}: {check()}", flush=True)
        except Exception as error:
            failed += 1
            print(f"FAIL  {name}: {error}", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
