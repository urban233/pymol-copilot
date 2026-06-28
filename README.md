# PyMOL Copilot

![Status: Experimental](https://img.shields.io/badge/status-experimental-orange.svg)
[![License: BSD-3 Clause](https://img.shields.io/badge/License-BSD%203%20Clause-blue.svg)](http://www.gnu.org/licenses/gpl-3.0)
[![Python: 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org)

PyMOL Copilot is a local AI companion designed for structural biologists. 
It translates natural language instructions into safe, reproducible PyMOL commands, 
turning complex visualization scripting into a simple conversation.

---

## 👁️‍🗨️ The Vision

Structural biology workflows require navigating dozens of precise PyMOL commands, 
complex selection algebra, and representation modes. 
PyMOL Copilot lowers this technical barrier for laboratory researchers. 
Instead of memorizing script syntax or spending time writing `.pml` scripts, 
you simply describe your experimental intent in plain language.


```

"Load the 1DPX protein, color chain A red, and measure the distance between residues 45 and 102."

```

### Key Highlights
* **100% Local & Private:** Your proprietary molecular data and research prompts never leave your machine. Inference runs locally using a highly optimized, lightweight AI model.
* **Human-in-the-Loop Safety:** The assistant never updates your workspace blindly. It generates a clear, step-by-step checklist of planned actions for you to review and approve before any execution happens.
* **Automates Workflows, Not Your Mouse:** The AI handles structural orchestration (loading, alignment, measurements, and representations) while leaving camera controls (zoom, rotation, and clipping) fully to your manual mouse movements.

---

## ✨ Features

| Feature | Description |
|:---|:---|
| **Structure Loading** | Fetch from the PDB or open local files seamlessly. |
| **Smart Representations** | Cleanly toggle cartoons, sticks, and custom color schemes without graphic artifacts. |
| **Automated Measurements** | Instantly find distances, angles, and contact points using plain English. |
| **Sequence Alignment** | Align structural variations reliably, even without perfect sequence identity. |
| **Session Export** | Save your generated scenes to standard `.pse` files to review or share later in your standalone PyMOL GUI. |

---

## 🛡️ Privacy and Constraints

* **Hardware Friendly:** Engineered specifically to run on modest hardware (like everyday laptops). It performs fast language processing directly on your CPU without requiring expensive graphics cards.
* **Offline Capability:** Designed for secure laboratory environments—no internet connection is required or used during execution.
* **Domain Focus:** The companion is optimized strictly for PyMOL visualization and scene building. It will explicitly decline out-of-scope requests such as molecular dynamics, docking simulations, or homology modeling.

---

## Development Setup

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

| Task | Description                                                                 |
| :--- |:----------------------------------------------------------------------------|
| `format` | Format the Python codebase with Ruff.                                       |
| `lint` | Run static analysis (linting) on Python code with Ruff.                     |
| `check_types` | Run static type checking with `pyrefly`.                                    |
| `test` | Execute the test suite with `pytest`.                                       |
| `build_whl` | Build the wheel file directly using the Conda environment (cross-platform). |

Example: Run tests with verbose output:
```bash
.\pymake.bat test verbose=true
```
