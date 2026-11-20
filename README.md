<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/branding/logo-dark.svg">
  <img src="assets/branding/logo-light.svg" width="320" alt="LoopSieve logo">
</picture>

# LoopSieve

Local verification and diagnostic delta filtering for coding workflows, with optional on-device LLM explanations.

LoopSieve runs project checks against changed files, records their outcomes, and controls how much diagnostic output goes back to a developer or coding agent. If a check fails twice with the same diagnostic identity, the Claude Code hook can show the unchanged failure without attaching the same log again. An optional local model can explain current failures from the command line.

## Feature status

**Established core.** The CLI selects and runs configured checks, bounds output and runtime, and records the outcome. The verification cache reuses successful results only for checks that declare deterministic behavior and complete local inputs. The Claude Code hook can attach the diagnostic delta to the conversation. The terminal workbench exposes check history, local tools, task state, and provider settings.

**Experimental.** `check --explain` provides advisory summaries with a user-configured local llama.cpp model. The existing bounded agent runtime, provider routing, orchestration, and multi-model workbench are also available for opt-in use. Provider and model catalog entries carry their own verification status.

**Planned.** Broader real-project quality evaluation, CUDA validation on additional devices, stronger Windows process containment, and structured parsing for additional check tools. See the [roadmap](docs/roadmap.md).

## Requirements and installation

- Python 3.11 or later. The core uses the standard library.
- The tools your repository checks call, such as Python, npm, Go, or Cargo.
- Textual for the optional full-screen workbench. The command-line interface and portable workbench run without it.
- For local explanations, a trusted Linux `llama-server` build and your own compatible GGUF. See [installation](docs/installation.md) and [model setup](docs/llm-integration.md).

From the checkout:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install .
loopsieve doctor
```

## Quick start

In a trusted project, initialize a check configuration, inspect it, and pass the files you changed.

```bash
loopsieve init
loopsieve check src/example.py
loopsieve report --json
```

To try the bundled failure example from this checkout:

```bash
loopsieve check --root examples/local-diagnostics example.py
```

The example exits with code 1 and displays the failed check. Other entry points include `loopsieve demo` for the offline demonstration, `loopsieve tui` for the terminal workbench, and `loopsieve claude install` for the optional project hook. See [usage](docs/usage.md) for commands and exit codes.

## How it works

1. The CLI or hook resolves the project, configuration, and changed files.
2. The planner selects checks by changed file kind. The runner executes each check as an argument array and captures bounded output.
3. The engine records results and computes diagnostic identities from the tool, outcome, source location or source anchor, and related output.
4. The CLI and hook report verification status. The hook can omit a repeated log when its identity matches. The opt-in model receives current failure evidence and returns a separate suggestion.

See the [architecture map](docs/architecture.md) for the verification, agent and model data flows.

## Local LLM example

The [local model guide](docs/llm-integration.md) shows how to supply a GGUF, start a loopback server, and select the served alias with `--llm-config`. A failed check still exits 1 when the server is unavailable. The model receives a bounded diagnostic excerpt and its reply appears as advice.

## Measured performance

The [benchmark report](docs/benchmarks.md) includes offline diagnostic fixtures, Python fingerprint profiling, and a tool for measuring inference with your own local model.

## Use cases and limits

- Validate changed files locally after an edit or before handing a change to a reviewer.
- Reduce repeated failure context in a Claude Code session while keeping the failed status visible.
- Ask a local model to suggest the next debugging step from a specific failure.
- Inspect stored check outcomes and the conditions for a verification cache hit.

Configured checks run with your account's operating-system privileges. Run them in projects you trust. Small-model advice can be generic or wrong. Diagnostic benchmarks use controlled failures. Model quality depends on the weights and settings you provide. See [known limitations](KNOWN_LIMITATIONS.md) and the [security policy](SECURITY.md).

## Credits

- **Developers** — mynex and Absolute Eclipse Media.
- **AI-assisted development** — Codex, MiniMax Code, Kimi Code, Qwen Code, OpenCode, Antigravity, and Claude Code.

## Contributing and license

See [CONTRIBUTING.md](CONTRIBUTING.md), [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md), and [CHANGELOG.md](CHANGELOG.md). LoopSieve is distributed under the [MIT license](LICENSE).
