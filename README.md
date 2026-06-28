# PyMOL Copilot

## Environment Setup

To develop or run PyMOL Copilot locally, you must create a `.env_path` file in the project root directory. This file should contain exactly one line: the absolute path to the root directory of the conda environment you wish to use.

### `.env_path` Examples

**Windows:**
```text
C:\Users\username\miniconda3\envs\pymol_copilot_dev
```

**macOS:**
```text
/Users/username/miniconda3/envs/pymol_copilot_dev
```

**Linux:**
```text
/home/username/miniconda3/envs/pymol_copilot_dev
```

## Development & Automation

PyMOL Copilot uses a standalone Python task runner called `pymake` to automate common development tasks. It provides a make-like experience using only the Python standard library.

### Running Tasks

Use the platform-specific wrapper scripts to run tasks:

- **Windows:** `.\pymake.bat <task> [args]`
- **Linux/macOS:** `./pymake.sh <task> [args]`

To see all available tasks and their options, run:
```bash
.\pymake.bat --help
```

### Available Tasks

| Task | Description |
| :--- | :--- |
| `format` | Format the Python codebase with Ruff. |
| `lint` | Run static analysis (linting) on Python code with Ruff. |
| `check_types` | Run static type checking with `mypy`. |
| `test` | Execute the test suite with `pytest`. |
| `build_whl` | Build the wheel file directly using the Conda environment (cross-platform).|

Example: Run tests with verbose output:
```bash
.\pymake.bat test verbose=true
```
