# The portable Windows bundle

Master plan item 20 ([plans/16-portable-bundle.md](../plans/16-portable-bundle.md)).
One ZIP that runs the notebook on Windows without any setup, including the
live demo on the CPU. This page is a draft: it records the spike (step 1);
how to build and share the bundle follows with steps 5 to 9.

## Spike: embeddable Lemonade on native Windows

Run on 2026-10-05 on the build host: Windows 11 Pro 10.0.26200, AMD Ryzen 5
3400G (8 threads), 16 GB RAM, driven from WSL2 through Windows interop.

**The artifact.** `lemonade-embeddable-11.9.0-windows-x64.zip` from the
v11.9.0 release, 5,382,390 bytes, SHA-256
`8311d9089c3f3747eb3ff5cee35c325a20686f7f5911c455763e7edf0619d1c7` (the
digest GitHub publishes). It holds `lemond.exe`, `lemonade.exe`, `LICENSE`
and `resources\` (`backend_versions.json`, `defaults.json`,
`server_models.json` and three others). No backend is included.

| Question | Finding |
| --- | --- |
| How is it started? | `lemond.exe [cache_dir] [config_dir] --host H --port P [--no-broadcast] [--log-file MODE\|PATH]`. Both directories are positional, so nothing has to live under the user's profile (the defaults are `%USERPROFILE%\.cache\lemonade` and `%USERPROFILE%\.config\lemonade`). |
| Which llama.cpp does the CPU backend install? | `lemonade backends install llamacpp:cpu` downloads `llama-b10723-bin-win-cpu-x64.zip` into `<cache_dir>\bin\llamacpp\cpu\` (44 MB). `resources\backend_versions.json` pins `cpu: b10723`, the build `configs/evaluation/finetuned_cpu.json` records. |
| Does it bind to loopback only? | With `--host 127.0.0.1`, both its HTTP port and its WebSocket port (9000, `websocket_port: auto`) listen on 127.0.0.1 only, so no firewall prompt. It resolves no IPv6 address for 127.0.0.1: clients must use `127.0.0.1`, not `localhost`. |
| How is it configured? | `<config_dir>\config.json` holds only overrides on top of `resources\defaults.json`; writing it before start works. Keys used: `extra_models_dir`, `llamacpp.backend`, `llamacpp.args`, `llamacpp.prefer_system` (default `true`: prefer a llama-server on PATH), `offline`, `no_fetch_executables`, `auto_check_model_updates`, `broadcast`, `log_file`. Each starts cleanly. |
| What does the catalog report for a local GGUF? | A GGUF in `extra_models_dir` is found at start ("Discovered 1 models from extra directory"). Its id is the file name without `.gguf`. Its `checkpoint` is `extra_models_dir` joined with the file name, with backslashes, spelled exactly as the config spells the directory, and `source` is `extra_models_dir`. |
| Does the client accept that checkpoint? | Not before item 20: `_served_model_path` split `C:\...` at the drive colon as if it were `<repo>:<file>`. Fixed in step 3 (`PureWindowsPath` comparison); the symptom would have been the grammar canary refused as "unexpected model". |
| Does it need anything a clean Windows lacks? | Yes. The llama.cpp binaries import `MSVCP140.dll` and `VCRUNTIME140.dll` (the Visual C++ 2015-2022 runtime) and do not ship them; `lemond.exe` needs only system DLLs. The bundle must carry the runtime DLLs next to `llama-server.exe`. |
| Paths with spaces? | Work. |
| Paths with non-ASCII characters? | **Fail.** `lemond` exits with code 1 and no error message when its own folder, the cache or config directory, or `extra_models_dir` contains a character such as `ü`. Launched from a non-ASCII folder it exits before writing any log. The same paths in their 8.3 short form (`C:\PMC-SP~1\CCHE~1`) work, including for `lemond.exe` itself. |

### With the model loaded

Run with Martin's consent on the same host: the fine-tuned
`Llama-3.2-1B-Instruct-pmc-train-e6c6c4dd8f6caaf9-Q4_K_M.gguf` (SHA-256
`6c5c76a0…bdbd`), llama.cpp b10723 on the CPU, `ctx_size` 16384. The server
and headless PyMOL ran from a plain Windows venv (CPython 3.13.13,
`requirements_lock.txt`) with the step 3 fix, as the notebook's section 9
does, with `--backend cpu --lemonade-base-url http://127.0.0.1:13399`.

| Question | Finding |
| --- | --- |
| Does `llamacpp.args` reach llama-server intact? | Yes. The loaded model's `launch_command` holds `--chat-template-kwargs` followed by exactly `{"date_string":"26 Jul 2024"}` as one argument, then `--parallel 1`. The single quotes in `config.json` are consumed by Lemonade's own argument splitting, as on Linux. |
| What does health report? | `device: cpu` (what the probe expects for `--backend cpu`), `recipe_options.ctx_size: 16384`, and a `checkpoint` and `-m` path identical to the catalog's. Loading took 4.6 s. |
| Where does llama-server listen? | 127.0.0.1 on a port Lemonade picks (8001 here). It warns that CORS allows all origins with no API key, as it does in the Docker engine. |
| Does the server start against it? | Yes, in 9.5 s, through the full probe (catalog, load, grammar canary). Before the step 3 fix it could not. |
| `gold_056` on the Windows CPU | The same plan as the committed CUDA run: `select copilot_sel…, name ZN` (2 atoms), `color silver`, `show dots`, fidelity exact. Applied: the zinc colour index went from 6 to 5322 (silver). |
| The notebook's unseen intent | `color marine, chain B`, `show sticks, chain B`, fidelity exact. |
| How long does a request take? | 69.4 s for `gold_056`, 45.3 s for the unseen intent. Almost all of it is reading the prompt: 2,485 tokens at about 48 tokens per second on 4 threads (52 s), then 30 tokens generated at about 8 per second. The second request reused the cached prefix (1,317 new tokens, 28 s). A newer CPU with more cores is faster; this 2019 4-core APU is a floor, not a typical laptop. |
| Does `lemond` reach the network? | With `offline: true` it logs "offline mode; using installed llamacpp:cpu backend" and no outbound request. Step 8 confirms it with the network off. |
| What is written outside the given folders? | The recovery point goes to `%TEMP%` (the notebook's own temporary folder), as planned. |

### Consequences for the bundle

- Everything `lemond` reads or writes is passed to it inside the bundle
  (`lemonade\`, a cache and config folder beside it), so it writes nothing
  under the user's profile.
- The notebook writes `config.json` fresh on every start, for the folder
  the bundle was extracted to.
- **Non-ASCII extract paths** (a user name such as `Jürgen` puts
  `Downloads` under `C:\Users\Jürgen\`): the notebook hands `lemond` the
  8.3 short form of every path. Where the volume does not create short
  names, it falls back to a staging folder with an ASCII path, as
  `tools/winstage` already does for PyMOL. The model is hard-linked there,
  not copied, when the volume allows it.
- The Visual C++ runtime DLLs are copied app-locally into the llama.cpp
  folder at build time.
- The notebook's section 9 must say how long a request takes on a CPU
  (tens of seconds to about a minute), so that a colleague does not
  mistake a busy cell for a hung one. Its prose describes the plan the
  model returns without depending on it, and checks the preview before
  applying it.
