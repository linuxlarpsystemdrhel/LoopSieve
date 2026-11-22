<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/branding/logo-dark.svg">
  <img src="assets/branding/logo-light.svg" width="320" alt="LoopSieve logo">
</picture>

# LoopSieve

**Native Rust build.** `loopsieve` covers local verification, diagnostic deltas, persistent Ollama agent sessions, scoped teams, local model management, and terminal and browser workbenches. `loopsieve-rs` remains an alias. Python remains available for compatibility workflows.

[Migration guide](MIGRATION.md) · [Rust implementation status](docs/IMPLEMENTATION_STATUS.md) · [Benchmarks](docs/benchmarks.md)

Local verification and diagnostic delta filtering for coding workflows, with optional on-device LLM explanations.

LoopSieve runs project checks against changed files, records their outcomes, and controls how much diagnostic output goes back to a developer or coding agent. If a check fails twice with the same diagnostic identity, the Claude Code hook can show the unchanged failure without attaching the same log again. An optional local model can explain current failures from the command line.

## Feature status

**Established core.** The CLI selects and runs configured checks, bounds output and runtime, and records the outcome. The verification cache reuses successful results only for checks that declare deterministic behavior and complete local inputs. The Claude Code hook can attach the diagnostic delta to the conversation. The terminal workbench exposes check history, local tools, task state, and provider settings.

**Experimental.** Native `check --explain`, the Ollama-backed agent runtime, and sequential team scheduling are opt-in. Catalog entries retain their individual verification status. External providers, advanced orchestration and the full-screen workbench remain available through Python.

**Planned.** Broader real-project quality evaluation, CUDA validation on additional devices, stronger Windows process containment, and structured parsing for additional check tools. See the [roadmap](docs/roadmap.md).

## Requirements and installation

- Rust 1.89 or later and a C compiler for native dependencies.
- The runtime tools called by your project's checks, such as Cargo, npm, Go or Python.
- Optional Ollama for local agents or a trusted llama.cpp build and GGUF for advisory explanations.

From the checkout:

```sh
cargo build --release --workspace --locked
./target/release/loopsieve doctor
./target/release/loopsieve check --json crates/loopsieve-core/src/lib.rs
./target/release/loopsieve tui
```

For an installed command, use `cargo install --path crates/loopsieve-cli --locked --bin loopsieve`. For legacy workflows, run `PYTHONPATH=src python -m loopsieve` from the checkout. See the [migration guide](MIGRATION.md) for data and command compatibility.

## Quick start

In a trusted project, initialize a check configuration, review it, and pass changed files:

```sh
loopsieve init
loopsieve check src/lib.rs
loopsieve report --json
```

Run `loopsieve claude install` to add a project-local post-edit hook. `loopsieve web` opens a read-only localhost dashboard, and `loopsieve tui` opens the native terminal workbench. See the [migration guide](MIGRATION.md) for local agents and model commands.

## How it works

1. The CLI or hook resolves the project, configuration, and changed files.
2. The planner selects checks by changed file kind. The runner executes each check as an argument array and captures bounded output.
3. The engine records results and computes diagnostic identities from the tool, outcome, source location or source anchor, and related output.
4. The CLI and hook report verification status. The hook can omit a repeated log when its identity matches. The opt-in model receives current failure evidence and returns a separate suggestion.

See the [architecture map](docs/architecture.md) for the verification, agent and model data flows.

## Local LLM example

Run `loopsieve models serve --weights .local-models/your-model.gguf` to start a compatible local llama.cpp server. Use `loopsieve check --explain --llm-config PATH FILE` with the served alias. [Local model guide](docs/llm-integration.md). A failed check still exits 1 when the server is unavailable. The model receives a bounded diagnostic excerpt and its reply appears as advice.

## Measured performance

The [benchmark report](docs/benchmarks.md) includes the native CLI comparison, offline diagnostic fixtures, Python fingerprint profiling, and a harness for measuring inference with your own local model.

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
