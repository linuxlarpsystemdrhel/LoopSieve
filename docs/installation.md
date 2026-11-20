# Installation

Requires Python 3.11 or newer. The CI matrix includes Python 3.11–3.13 on three OSes and Python 3.14 on Linux. Core features use only the Python standard library.

From a checkout:

```bash
python -m pip install .
python -m loopsieve
```

From a virtual environment or using pipx, the `loopsieve` executable is also installed. `python -m loopsieve` is available when the package is installed into that interpreter.

Advanced Textual interface, optional:

```bash
python -m pip install '.[tui]'
loopsieve tui
```

If Textual cannot be installed, `loopsieve tui` uses the portable terminal interface. A subset of the styling is enhanced when Rich is installed, but Rich is not required.

For a repository with Git and an existing test suite:

```bash
loopsieve init
loopsieve doctor
loopsieve check path/to/edited/file.py
```

Inspect `.loopsieve.json` to ensure every check is appropriate for your repository. Running tests can invoke repository code. Hook installation is opt-in:

```bash
loopsieve install-hook
loopsieve uninstall-hook
```

To open the dashboard:

```bash
loopsieve web
```

The default URL is `http://127.0.0.1:8765`. Do not forward the port to a public network.

## Platform notes

The core is designed around Python's cross-platform standard library. CI declares Windows, Linux and macOS jobs. Actual local testing for this archive was performed on Linux only. On Windows, enter commands in PowerShell; the fallback TUI supports basic console navigation. Some external Git and compiler adapters may not exist on every platform.

To uninstall, run `loopsieve uninstall-hook` from each affected project before removing the package with your normal Python package manager. Local state can remain under the OS-specific cache directory, which is shown by `loopsieve report`.

For the experimental local model, see [model integrity checks and CPU/CUDA startup](llm-integration.md).
