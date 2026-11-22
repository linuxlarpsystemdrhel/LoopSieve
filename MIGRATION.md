# Migrate to the native Rust CLI

The Rust workspace builds `loopsieve` and the compatibility alias `loopsieve-rs`. Both run the same native code. The Python package remains available for workflows that still need parity and for existing sessions. Both runtimes understand version 1 of `.loopsieve.json`.

## Build and run

Use Rust 1.89 or newer and a C toolchain for the bundled SQLite and cryptography dependencies. Build from the checkout so Cargo can embed the shared JSON manifests.

```sh
cargo build --release --workspace --locked
./target/release/loopsieve doctor
./target/release/loopsieve check --json crates/loopsieve-core/src/lib.rs
./target/release/loopsieve report
./target/release/loopsieve evidence verify
```

Install just the native binary with `cargo install --path crates/loopsieve-cli --locked --bin loopsieve`. On Windows, the checkout binary is `target/release/loopsieve.exe`. Use the full path if the Python entry point with the same name appears first in `PATH`. The native runtime does not require Python. A configured Python check still needs the chosen interpreter. Set `LOOPSIEVE_PYTHON` to override `{python}`.

| Workflow | Native command |
|---|---|
| Create verification config | `loopsieve init` detects Rust, Python, Node.js and Go declarations while preserving an existing config. |
| Check and inspect evidence | `loopsieve check`, `report`, `doctor`, `cache`, `evidence export`, `evidence verify` |
| Order and run checks | `loopsieve plan examples/rust-mission.json --strategy critical-path` and `loopsieve run ...` |
| Local explanations | `loopsieve check --explain --llm-config PATH FILE`, with an existing llama.cpp server |
| Start a local model | `loopsieve models serve --weights PATH --device cpu` with a trusted `llama-server` |
| Model files and estimates | `loopsieve models list`, `models show`, `models memory`, `models verify`, and explicit `models download` |
| Local agents and teams | `loopsieve agent`, `agents`, `team`, and `chat` |
| Editor and local interfaces | `loopsieve claude install`, `claude status`, `claude uninstall`, `mcp list`, `tui`, `web` |
| Historical Python data | `loopsieve legacy report PATH`, `legacy sessions PATH`, `legacy import PATH SESSION_ID` |

## Local agents

Start Ollama separately and choose a locally installed model. Start read-only while inspecting the workflow.

```sh
./target/release/loopsieve models list --endpoint http://127.0.0.1:11434
./target/release/loopsieve agent run 'Inspect crates/loopsieve-core/src/lib.rs and summarize its modules' --model llama3.2:3b
./target/release/loopsieve agent sessions
./target/release/loopsieve agent inspect SESSION_ID
./target/release/loopsieve team examples/rust-team.json --strategy critical-path
```

Agent edits to existing UTF-8 files need `--allow-writes`. A separately granted `--allow-checks` lets an agent request configured verification. A patched file needs passing checks against its recorded digest before the session completes. The terminal can run agents one turn at a time with `agent new` and `agent step`. `agent checkpoints` lists recorded pre-write snapshots. `agent restore SESSION_ID --checkpoint 1 --approve-restore` checks that the current content still matches the patch before replacing it.

The team manifest supports up to 20 tasks, per-task local model and role, dependencies, step budgets, and declared write sets. `--allow-writes` grants edits only inside the corresponding task's declared files. The scheduler runs tasks sequentially and blocks dependents of incomplete tasks.

## State and compatibility

The Rust state base is `.loopsieve/rust-v1/<workspace-key>/` by default. It holds `state.json` for verification and `sessions-v1/` for new agents. `LOOPSIEVE_RUST_STATE_DIR` overrides the base, then the configured `state_dir` is considered. Each runtime continues to use its own cache and session state.

The `legacy` commands read a historical Python JSON state or `sessions.db` path explicitly. `legacy import PATH SESSION_ID` copies the selected task, role, recent tool observations and currently existing edited paths into a new native session. It starts with an empty verification record and uses current command-line grants. Run it against the original workspace. If edited files need fresh checks, grant `--allow-checks` during import and resume the new ID with `agent resume`. Exact continuation in the original session and Python checkpoints remain available through `python -m loopsieve`.

JSON report consumers should migrate to the native schema. Native diagnostics preserve exact locations, columns, and meaningful numeric values. A moved diagnostic can appear as a different failure. The original replay fixtures retain their historical normalization for benchmark comparability.

The current Rust workbench is a line-oriented terminal interface and a read-only loopback dashboard. The Python full-screen workbench, Studio, external provider adapters, legacy task and skill execution, and advanced provenance and model-team features continue to serve those workflows. [Implementation status](docs/IMPLEMENTATION_STATUS.md).

## Trusted commands

Review project configuration before running checks or installing the Claude Code hook. Verification subprocesses use the invoking account's permissions. Native agent sessions and checkpoints can contain workspace content and belong in a private state directory. The local model launcher binds to loopback and respects explicit CPU or GPU-layer selection. [llama.cpp server flags](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md) · [Claude Code hooks](https://code.claude.com/docs/en/hooks).
