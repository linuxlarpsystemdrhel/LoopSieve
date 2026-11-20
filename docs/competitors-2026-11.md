# Coding agents landscape, 10 November 2026

This is a focused desk review of ten relevant, widely used GitHub repositories, not a claim that LoopSieve beats them or that every issue/release has been audited. GitHub stars are rough snapshots around 9-10 November 2026 and may differ between mirrors and collection dates. The list prioritizes ecosystem relevance over strict global rank.

| Project | Approx. stars | License / language | What matters to LoopSieve |
|---|---:|---|---|
| [OpenClaw](https://github.com/openclaw/openclaw) | 394k | MIT / TypeScript | Personal agent platform, integrations, long-running gateway; very different main audience |
| [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) | 277k | MIT / TypeScript | Everything-as-plugin architecture, coordination and runtime modularity |
| [OpenCode](https://github.com/anomalyco/opencode) | 226k | MIT / TypeScript | Excellent code-focused open terminal UX and provider ecosystem |
| [Codex CLI](https://github.com/openai/codex) | 134k | Apache-2.0 / Rust | Sandboxed execution, Git workflows, noninteractive exec mode |
| [Gemini CLI](https://github.com/google-gemini/gemini-cli) | 109k | Apache-2.0 / TypeScript | Enterprise-oriented CLI, MCP, release channels |
| [OpenHands](https://github.com/All-Hands-AI/OpenHands) | 93k | Mixed MIT/enterprise / TypeScript | Coding task delegation, hosted/local execution and verification |
| [Cline](https://github.com/cline/cline) | 71k | See official LICENSE / TypeScript | IDE-native human approval, coding tools and browser assistance |
| [Goose](https://github.com/block/goose) | 56k | See official LICENSE / Rust | Local agent extensibility, CLI/desktop integration |
| [Aider](https://github.com/Aider-AI/aider) | 50k | Apache-2.0 / Python | Practical Git-native edit/test loops and repository context |
| [Kilo Code](https://github.com/Kilo-Org/kilocode) | 28k | See official LICENSE / TypeScript | Agent modes, extension UX and model routing |

Source snapshots: [GitHub OpenClaw](https://github.com/openclaw/openclaw), [OpenCode ecosystem](https://opencode.fyi/stats/), [Codex repository history](https://gitdebt.com/openai/codex), [Gemini CLI repository](https://github.com/google-gemini/gemini-cli), [OpenHands license/repo](https://repos.fru.dev/projects/openhands), [nine coding agents market comparison](https://aiusecases.dev/open-source/coding-agent/), [DeepSeek Harness repository](https://github.com/deepseek-ai/deepseek-harness). Numbers from these sources are approximations, not live GitHub API responses measured by this project.

## Feature coverage matrix

| Capability | Competing projects to inspect | LoopSieve 0.3.0 |
|---|---|---|
| Autonomous coding agent | OpenCode, Codex, OpenHands, Cline | PARTIAL. Tool-restricted action loop proven with scripted provider, no live model E2E |
| Agent orchestration | OpenClaw, DeepSeek Harness, OpenHands | PARTIAL. Sequential dependency DAG, no parallel agent write isolation |
| Terminal chat | OpenCode, Aider, Codex | IMPLEMENTED. Python terminal chat, no comparable interactive editor polish |
| Beautiful full-screen terminal UI | OpenCode, Codex, Gemini CLI | PARTIAL. Existing optional Textual catalog UI, basic chat shell |
| Desktop/web visual control | OpenHands, OpenClaw, Kilo Code | PARTIAL. Local Studio, sessions, catalogs, WebGL avatar |
| Local verification after edits | Aider, Codex, Cline | IMPLEMENTED. Trust-aware verification and diagnostic filtering |
| Real-time browser automation | Cline, OpenHands | UNSUPPORTED |
| Unified MCP protocol client | Gemini CLI, OpenCode, Goose | PARTIAL. Project MCP inspection only, no active connection management |
| Real multi-provider SDK parity | OpenCode, Goose | PARTIAL. Four opt-in planner adapters; production integrations not all tested |
| Git worktrees and merge resolution | Codex, Aider | UNSUPPORTED |
| Git-native diff tooling | Aider, Codex | IMPLEMENTED locally, through existing read-only Git tools |
| Permission approvals | Codex, Cline | PARTIAL. Startup/session flags and action gates, not per-action approval dialogs |
| Long-lived agent memory | OpenClaw, OpenHands | PARTIAL. Persistent short session messages and event journal |
| Automatic skill/plugins marketplace | Kilo Code, OpenCode | UNSUPPORTED. Manifests and probes only |
| Local model support | Goose, OpenCode | PARTIAL. Ollama protocol adapter, needs running model |
| Reproducible quality benchmarks | Aider, Codex | PARTIAL. Local repeat-failure and unit test fixtures, no cross-model benchmark |
| Original animated 3D mascot | Many modern UIs have animated characters | PARTIAL. Real glTF WebGL mesh and state renderer, terminal graphics fallback incomplete |

## Decision

LoopSieve should not compete on raw number of tools, models, agents or integrations. Its defensible core remains trust-aware, local verification with compact diagnostics and observable, bounded agent actions. The biggest unresolved advantage to prove is whether these choices improve successful tasks per model turn on real coding benchmark suites. That experiment has not been run.

No code from the listed repositories has been copied into LoopSieve. This table is a design/market reference, not dependency attribution.
