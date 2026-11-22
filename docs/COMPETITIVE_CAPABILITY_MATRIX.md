# Competitive capability matrix

This is a documentation review dated 2026-11-22. The cited sources describe each tool's public capabilities. Capabilities outside these sources remain unverified. No head-to-head execution or quality comparison was performed.

| Product | Documented capability | LoopSieve evidence and an acceptance boundary |
|---|---|---|
| Claude Code | Lifecycle hooks can deliver tool events and return additional context. [Hooks reference](https://code.claude.com/docs/en/hooks) | Rust accepts post-edit events and runs verification for the caller's workspace. Tested with hook fixtures. Live Claude Code integration and an installer for the Rust binary remain open. |
| OpenAI Codex | Terminal coding agent with workspace editing and command execution. [Codex CLI](https://developers.openai.com/codex/cli) | Python has an adapter and bounded editing actions. Rust accepts trusted, user-authored check definitions. Native editing requires permission and patch-review tests before parity. |
| Google Antigravity | Agent workflows across an app, CLI and IDE. [Antigravity overview](https://antigravity.google/docs/overview) | Rust provides a terminal CLI and serial DAG. Editor and browser integration need their own protocols, permissions and recorded UI tests. |
| OpenClaw | Tool policy, skills, plugins, subagents, and multiple sandbox backends. [Capabilities overview](https://docs.openclaw.ai/tools) | Python has bounded local tools and catalog-based skills. Rust limits check paths, subprocess duration and output. OS isolation and plugin enforcement require separate acceptance tests. |
| Cline | Editor and terminal agents with tool approvals. [Cline overview](https://docs.cline.bot/cline-overview) | Python tests explicit write and check permissions. Native approval policy and editor UI are pending. |
| OpenCode | Configurable agent modes, tools and permissions. [Agents](https://opencode.ai/docs/agents/) | Python holds role manifests. Native Rust task definitions pick declared checks. Role activation needs typed capability checks and persisted agent transitions. |
| Aider | Coding workflows with lint and test commands. [Linting and testing](https://aider.chat/docs/usage/lint-test.html) | Native checks and evidence work with configured tools. A generated edit would need to pass the same independent verification path before automated linkage. |
| Continue | Configurable AI agents in its editor extensions. [Continue documentation](https://docs.continue.dev/) | LoopSieve's native entry point is the CLI. Editor integration and hosted events remain unverified. |
| Roo Code | Orchestrator delegates to isolated subtask conversations. [Boomerang tasks](https://docs.roocode.com/features/boomerang-tasks) | Native declarative scheduling supports dependencies and bounded task count. Delegated model subtask contexts and replay are pending. |

Measured behavior is reported in [Benchmarks](benchmarks.md). The [implementation status](IMPLEMENTATION_STATUS.md) keeps the migration backlog and acceptance boundaries.
