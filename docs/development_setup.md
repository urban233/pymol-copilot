# Development Setup

Please follow the setup instructions carefully.

---

## Prerequisites

* [**Miniforge3**](https://conda-forge.org/download/) (or another Conda distribution)

---

## ⚠️ Important Note on JetBrains IDEs on Windows (and maybe other platforms)

Due to current issues with **PyCharm**, configuring a project interpreter is unreliable when reusing existing Conda environments.

❗ **Workaround (Required):**
You must create a **new Conda environment through the IDE GUI** (PyCharm).
Using an already existing environment is currently **not supported** and may lead to misconfiguration.

After creating the environment, install dependencies using the provided `environment.yml`.

---

## Development

### 1. Clone the Repository

First of all, clone the repository:
```bash
git clone https://github.com/urban233/pymol-copilot.git
```

### 2. Set up the Conda Environment
PyMOL Copilot uses **Conda** for dependency management for both Python and C++.

#### Steps:

1. Open the repository in **PyCharm** or **preferred** in **CLion**.
2. Create a new Conda environment:

    * Go to **Settings → Build, Execution, Deployment → Python Interpreter**
    * Add a new interpreter → **Conda Environment**
    * Select **New environment** and choose **3.13**
    * Choose a name like `pymol_copilot_dev`
3. Once created, install dependencies:

    * Activate the environment
    ```bash
   conda activate pymol_copilot_dev
    ```
   
    * For **Linux** (especially OpenSUSE) users:
   ```bash
   conda install -c conda-forge binutils_linux-64
   ```

    * Install all development dependencies using the environment.yml file
    ```bash
   conda env update --file environment.yml
    ```

📌 For detailed instructions, see the official guide:
[https://www.jetbrains.com/help/pycharm/conda-support-creating-conda-virtual-environment.html#conda-requirements](https://www.jetbrains.com/help/pycharm/conda-support-creating-conda-virtual-environment.html#conda-requirements)

---

## Common Pitfalls

* ❌ Do **not** reuse existing Conda environments

* ❌ Do **not** skip environment creation via IDE GUI

* ✅ Always create a **new environment via the IDE**

* ✅ Always install dependencies using `environment.yml`

---

If you run into setup issues, please open an issue in the repository with details about your environment and IDE configuration.
