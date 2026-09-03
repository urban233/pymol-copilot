<p align="center">
  <img src="assets/logo/logo.png" alt="PyMOL-Copilot Logo" width="100">
</p>


<p align="center">
  <strong>A local AI assistant designed for structural biologists.</strong>
</p>

<p align="center">
  <img src="assets/splash_screen.png" alt="PyMOL-Copilot Logo" width="600">
</p>

![Status: Experimental](https://img.shields.io/badge/status-experimental-orange.svg)
[![License: BSD-3 Clause](https://img.shields.io/badge/License-BSD%203%20Clause-blue.svg)](http://www.gnu.org/licenses/gpl-3.0)
[![Python: 3.13.13](https://img.shields.io/badge/python-3.13.13-blue.svg)](https://www.python.org)

PyMOL Copilot is a local AI server designed for structural biologists.
It translates natural language instructions into safe, reproducible PyMOL commands, 
turning complex visualization scripting into a simple conversation.

---

## Development

The pinned development baseline is CPython 3.13.13 with Bazel 9.2.0 and
Bazelisk 1.29.0. Windows, macOS, and Linux are candidate build environments,
not yet qualified product support. See the
[development setup guide](docs/development_setup.md) for the authoritative
commands.

## 👁️‍🗨️ The Vision

Structural biology workflows require navigating dozens of precise PyMOL commands, 
complex selection algebra, and representation modes. 
PyMOL Copilot lowers this technical barrier for laboratory researchers. 
Instead of memorizing script syntax or spending time writing `.pml` scripts, 
you simply describe your experimental intent in plain language.


```

"Load the 1DPX protein, color chain A red, and measure the distance between residues 45 and 102."

```
