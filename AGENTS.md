# AGENTS.md

## Project Context
- **Primary Language:** Python (Python-only repository)
- **Goal:** Maintain production-ready, highly defensive, statically typesafe Python code without scaffolding, drafts, or deferred implementations.

---

## Development Rules

### 1. Import Discipline (Module Namespace Isolation)
- **Wildcard imports** (`from module import *`) are strictly forbidden across all files without exception.
- **Import the module, not the object.** You must bring the module itself into the namespace, not its underlying classes, functions, or constants. 
- **Permitted Exceptions:** `typing`, `collections.abc`, `__future__`, and test parametrization decorators (e.g., `pytest.mark.parametrize`). Every other import must bring in the module itself.
- **Example Usage:**
  ```python
  # ✅ CORRECT
  import package.module
  instance = package.module.ClassName()

  from package import module
  instance = module.ClassName()

  # ❌ FORBIDDEN
  from package.module import ClassName
  from package.module import helper_function
  from package.module import SOME_CONSTANT
  ```

* This rule applies identically inside `if TYPE_CHECKING:` blocks. `from __future__ import annotations` must be present at the top of every file containing a `TYPE_CHECKING` block.
* **Grouping and Ordering:** Group imports in the following order: `__future__` → Standard Library → Third-Party → Local Modules. Separate groups by exactly one blank line, sorting alphabetically within each group. Use one import per line.

### 2. Formatting, Typography, & Signatures

* Indentation must be exactly **4 spaces**. No tabs are allowed.
* All names must follow the correct convention: CapWords classes, snake_case functions/variables, SCREAMING_SNAKE_CASE constants, _prefix privates.
* All variables that are scoped to a function or method must use a tmp_ prefix to avoid shadowing global variables.
* No line may exceed **80 characters** (including inline documentation, comments, and docstrings).
* Use double quotes `"` for regular strings, and triple-double quotes `"""` for documentation blocks.
* Omit redundant parentheses around statements (`return`, `if`, `while`, `for`). No trailing whitespace or semicolons.

### 3. Comprehensive Documentation & Type Annotations

* Every function, method, and module requires explicit type annotations for parameters and return types (do not annotate `self` or `cls`).
* Every function (both public and private) must contain a complete docstring block using triple-double quotes `"""` detailing:
* `Args:` For every parameter (excluding `self`/`cls`).
* `Returns:` If the execution returns a value other than `None`.
* `Raises:` For any explicit or propagated exceptions exposed to the caller.

---

## Repository Conventions

* **Module Initialization (`__init__.py`):** `__init__.py` files must remain strictly empty. No imports, no `__all__`, and no operational code of any kind are permitted.
* **Context Management:** Wrap all context-managed resources in explicit `with` blocks; avoid manual `.close()` calls to guarantee clean environment boundaries.

---

## Common Tasks

You should run these exact automation tools (using pymake.bat or pymake.sh) in the local integrated terminal to format, lint, and verify type safety before finishing a task.

| Task | Command | Environment / Prerequisites |
| --- | --- | --- |
| **Code Formatting** | Run the `format` task/script | Local workspace formatter |
| **Linting Fixes** | Run `lint fix=true` | Code quality suite runner |
| **Type Checking** | Run `check_types` | Static type analyzer (e.g., mypy) |
| **Run Unit Tests** | Run `pytest` | Testing framework runner |

### Testing Standards

* Follow the **AAA Pattern (Arrange – Act – Assert)** for all unit tests.
* Tests must be deterministic (no random seeds, timing dependencies, or global state leaks).
* Use `pytest` fixtures for setup and teardown tasks. Parametrize input test spaces via `@pytest.mark.parametrize` instead of writing duplicate test functions.
* For asynchronous code paths, confirm the async test runner plugin (`pytest-asyncio` or `anyio`) is explicitly declared in the development dependencies before using the `@pytest.mark.asyncio` decorator.

---

## Restrictions

* **No Placeholders:** `TODO`, `FIXME`, `XXX`, stub methods, `pass` bodies, and pseudocode are strictly forbidden. Every block of code must be fully realized, production-ready, and functionally sound.
* **No Invented APIs:** Never use an external class, function, or package wrapper unless you have directly verified its existence in the repository or active environment configuration (`pyproject.toml` or `requirements*.txt`).
* **No Hardcoded Secrets:** Credentials, API keys, and tokens must always come from environment variables or a configuration manager—never from source files or committed configuration files.
* **No Bare Excepts:** No bare `except:` blocks are allowed. Always handle explicit exceptions and chain them with `from` when re-raising.
* **No Mutable Default Arguments:** Never use mutable default arguments (e.g., `def func(x=[])`). Use `None` and instantiate inside the scope instead.

---

## Definition of Done

Junie must walk through this precise checklist and verify all items evaluate to **TRUE** before signaling task completion:

* [ ] A clean planning structure (`<plan>`) was thought through or explicitly evaluated.
* [ ] Code formatting, linting fixes, and strict type verification routines run and exit with a code of `0`.
* [ ] Code changes align perfectly with existing workspace architecture, file naming schema, and line formatting layouts.
* [ ] Automated testing blocks cover new logic paths using the AAA pattern without creating transient timing dependencies or flaky assertions.
* [ ] No `TODO`, `FIXME`, placeholder, or scaffold structures remain in the codebase.
