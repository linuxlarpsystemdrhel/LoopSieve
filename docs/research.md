# Market research snapshot

Date: 2026-11-09

This document records the landscape used to choose LoopSieve. Star counts are point-in-time snapshots from public GitHub pages or recent GitHub-indexed pages and will change.

## What the market says

The largest projects are full coding agents and broad orchestration systems. They already have enormous feature surfaces. Competing with them on agent count is a weak entry strategy.

A second cluster focuses on usage visibility. Those tools are useful, but a dashboard mostly explains consumption after it happens.

A third cluster manages persistent work, multi-agent coordination, or context memory. This is also becoming crowded.

The gap selected for LoopSieve is narrower: deterministic local verification after an edit, with repeated diagnostic evidence removed before the next model turn.

## Projects reviewed

| Project | Snapshot | Main job | Relevance to LoopSieve |
| --- | ---: | --- | --- |
| Claude Code | about 155k stars | First-party coding agent | Target integration surface |
| OpenCode | about 225k | Multi-provider coding agent | Shows demand for open coding runtimes |
| Cline | about 71k | IDE/CLI autonomous coding agent | Broad agent alternative |
| Roo Code | about 24k, archived in 2026 | IDE coding agent | Warning against competing on another shell |
| Kilo Code | about 28k | Coding agent platform | Broad feature competitor |
| Aider | about 50k | Terminal pair programming | Mature focused CLI |
| Continue | about 36k | IDE agent platform | Large extension ecosystem |
| Goose | about 56k | Local extensible agent | Local-first precedent |
| Gemini CLI | about 109k | Google coding CLI | Major alternative harness |
| Codex CLI | about 133k | OpenAI coding CLI | Major alternative harness |
| OpenHands | about 93k | Autonomous software engineering | Broad benchmarked agent system |
| Open Interpreter | about 69k | Local computer/code agent | Local execution precedent |
| OpenClaw | about 394k | Local personal agent platform | Strong local, extensible product benchmark |
| Ruflo | about 81k | Multi-agent orchestration | Shows orchestration is already crowded |
| Gas Town | about 18.7k | Multi-agent workspace manager | Persistent coordination competitor |
| Beads | about 28.6k | Git-backed memory/work graph | Strong session continuity solution |
| HumanLayer | about 11k in recent ecosystem snapshots | Steering coding agents from one place | Human review and session control |
| CCPM | about 8.4k | GitHub Issues and worktree project management | Parallel agent workflow |
| Claude Squad variants | mixed | Curated role-based agent teams | Agent count is not a unique moat |
| VoltAgent Claude subagents | about 25k | 100+ specialized subagents | Very strong catalog precedent |
| VoltAgent agent skills | about 35k | 1000+ reusable skills | Tool/skill catalog already crowded |
| wshobson/agents | major community collection | Agent definitions and plugins | Further reduces value of a new agent catalog |
| ccusage | about 18.9k | Local token/cost reporting | Usage visibility, not prevention |
| Usage Pulse | 471 | Live Claude Code limit/context status | Polished quota visibility |
| Splitrail | 227 | Cross-agent usage tracker | Multi-tool local analytics |
| ClaudeCodeUsage | niche VS Code extension | Usage dashboard and optimization advice | Direct evidence that usage pain exists |
| claude-usage-dashboard | niche | Local usage dashboard | Another monitoring entrant |
| ai-usage-cost | niche | Local cost dashboard | Crowded monitoring category |
| Sift projects | multiple | Session search, memory, output pruning | Name and context-pruning collision |
| Proofloop projects | multiple | Verification loops | Generic verification-loop positioning collision |
| PatchProof projects | multiple | Patch evidence and regression proof | Evidence bundle collision |
| ContextRail projects | multiple | Context optimization | Context-layer naming collision |
| Tightloop projects | multiple | Agent-loop control/runtime | Loop-control naming collision |
| diffrail | niche | Deterministic file-boundary enforcement | Example of focused deterministic guardrails |

## Important first-party constraints

Claude Code officially supports lifecycle hooks, plugins, skills, subagents, MCP integrations, and `PostToolBatch`. `PostToolBatch` runs once after a batch of tool calls and can add context before the next model request.

Subagents use separate context windows, but their requests count against the same usage limits as the main conversation. That makes indiscriminate agent spawning a poor default for a tool whose goal is efficiency.

Anthropic's current legal guidance allows products to state accurately that they run Claude Code, but product names and logos must not imply that Anthropic built or endorsed them. Third-party products must not intermediate Claude subscription credentials.

LoopSieve therefore uses its own name, calls only documented local extension points, and never handles Claude credentials.

## Why not a dashboard

Usage dashboards already exist in several forms. A new dashboard would need a major new data source or a much better operator workflow to matter.

LoopSieve instead acts before the next reasoning turn. The working hypothesis is that a smaller amount of fresh, verified evidence is more useful than another visualization of usage after the session.

## Why not 30 agents

The ecosystem already contains projects with dozens or hundreds of specialized agents. More roles do not solve a unique problem by themselves, and official documentation notes that subagent requests count against the same usage limits.

A future LoopSieve agent should exist only if a deterministic local check cannot answer the question.

## Sources

Primary and current sources used in the 2026-11-09 review:

- https://code.claude.com/docs/en/hooks
- https://code.claude.com/docs/en/hooks-guide
- https://code.claude.com/docs/en/sub-agents
- https://code.claude.com/docs/en/plugins
- https://code.claude.com/docs/en/mcp
- https://code.claude.com/docs/en/legal-and-compliance
- https://github.com/anomalyco/opencode
- https://github.com/cline/cline
- https://github.com/RooCodeInc/Roo-Code
- https://github.com/Kilo-Org/kilocode
- https://github.com/Aider-AI/aider
- https://github.com/continuedev/continue
- https://github.com/block/goose
- https://github.com/openai/codex
- https://github.com/google-gemini/gemini-cli
- https://github.com/All-Hands-AI/OpenHands
- https://github.com/OpenInterpreter/open-interpreter
- https://github.com/openclaw/openclaw
- https://github.com/ruvnet/ruflo
- https://github.com/gastownhall/gastown
- https://github.com/gastownhall/beads
- https://github.com/humanlayer/humanlayer
- https://github.com/automazeio/ccpm
- https://github.com/VoltAgent/awesome-claude-code-subagents
- https://github.com/ccusage/ccusage
- https://github.com/NoobyGains/usage-pulse
- https://github.com/Piebald-AI/splitrail

The scan also included recent GitHub projects around Claude Code usage dashboards, verification loops, context pruning, MCP management, and multi-agent coordination. Those smaller projects are tracked as product-shape evidence rather than reliable popularity benchmarks.
