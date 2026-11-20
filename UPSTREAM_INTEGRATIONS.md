# Upstream integration audit

Date: 2026-11-10  
Policy: **no upstream source was copied into LoopSieve**. The repositories were
cloned for architecture study and license review. The delivered components are
independent Python implementations or adapters.

## Cloned research trees

All ten repositories were shallow-cloned with `GIT_LFS_SKIP_SMUDGE=1` into a
temporary research directory outside the final application. The commit SHA below
is the actual `HEAD` used for the inspection.

| Project | URL | Commit SHA | License |
|---|---|---|---|
| OpenCode | https://github.com/anomalyco/opencode | `bb87284a94f04db1dd4e7693f8339ae57b7613ea` | MIT |
| OpenClaw | https://github.com/openclaw/openclaw | `d957d05ebfc040f71c5c51736f9e688bba4581b9` | MIT |
| Cline | https://github.com/cline/cline | `c5df41f937c496ce8c8e689ba58776593c703dfa` | Apache-2.0 |
| Superpowers | https://github.com/obra/superpowers | `22f0b463e7a5e579904dd6211a520321035526f7` | MIT |
| Hermes Agent | https://github.com/NousResearch/hermes-agent | `33cbf1e813d4ff35c7709b21c809f55eb3af9288` | MIT |
| Agent Skills | https://github.com/addyosmani/agent-skills | `301b02b12bff98e4688e6984af6556802322bbde` | MIT |
| Aider | https://github.com/Aider-AI/aider | `5dc9490bb35f9729ef2c95d00a19ccd30c26339c` | Apache-2.0 |
| Pi | https://github.com/pi0/pi-mono | `88619669e2fc3efaf2697742608d0fe500ddba9d` | MIT |
| Codex | https://github.com/openai/codex | `fe8e540a80f17716bf2a3007f06e8a602192c704` | Apache-2.0 |
| Gemini CLI | https://github.com/google-gemini/gemini-cli | `e5d88fb2c036ce7e0c27131469cd963221b9d9e7` | Apache-2.0 |

The OpenAI Codex, Hermes Agent and Gemini CLI checkouts contained paths longer
than the Windows checkout limit. Their Git objects and commit trees were
available, but a complete working-tree checkout was not obtained on this host.
This is recorded as `PARTIAL_CHECKOUT_WINDOWS_PATH_LIMIT`, not as a completed
full-source audit. No source from those trees was copied.

## Studied components and LoopSieve equivalents

| Upstream | Studied area | LoopSieve implementation | Integration type | Status |
|---|---|---|---|---|
| OpenCode | provider abstraction, sessions, permissions | `providers.py`, `provider_catalog.py`, `agent_runtime.py`, `permissions.py` | independent reimplementation | VERIFIED by unit tests; live providers not tested |
| OpenClaw | gateway/events, plugins, extensions | `model_team.py` `TeamStore`/message bus, `plugins.py` | independent reimplementation | VERIFIED by message-bus and catalog tests |
| Cline | checkpoints, approval flow, context | `checkpoint.py`, `permissions.py`, `intelligence.py` | independent reimplementation | VERIFIED by checkpoint/permission tests |
| Superpowers | engineering skills, TDD, debugging workflows | `skills.py`, `planner.py`, `data/skills` | independent reimplementation | Manifest tests only; no upstream skill files copied |
| Hermes Agent | persistent sessions, orchestration, skills | `agent_runtime.py`, `orchestrator.py`, `model_team.py` | independent reimplementation | Partial upstream checkout; LoopSieve tests pass |
| Agent Skills | reusable skills, implementation/verification procedures | `capability.py`, `skills.py`, `data/skills` | reimplementation / manifest contract | Manifest contract tests |
| Aider | repository map, edit loop, Git feedback | `intelligence.py`, `project_intelligence.py`, `worktrees.py`, `agent_runtime.py` | independent reimplementation | Unit tests; no upstream code copied |
| Pi | lightweight agent loop, provider abstraction, terminal UX | `agent_runtime.py`, `tui.py`, `commands.py` | independent reimplementation | Terminal/workbench tests |
| Codex | sandbox/approval architecture, agent graph, TUI | `permissions.py`, `sandbox`-adjacent checks, `model_team.py` | architecture study; no copy | Partial checkout; computer control not implemented |
| Gemini CLI | MCP, project context, extension architecture | `mcp_manager.py`, `capability.py`, `provider_catalog.py` | independent reimplementation | MCP discovery tests; live MCP tools not tested |

## What was actually integrated

- A provider catalog with explicit `CONFIGURED_NOT_TESTED`/`LOCAL_SERVER`
  statuses and a custom-provider path.
- An encrypted secret store using Windows DPAPI (keyring/file fallbacks).
- A capability registry and deterministic router over tools, agents, skills,
  plugins, technologies, models, providers and quantization methods.
- A multi-model logical-agent team with a typed message bus and real dialogue.
- Hugging Face metadata search with server-side cursor pagination.
- Quantization method metadata for GGUF/IQ/GPTQ/AWQ/EXL2/HQQ/AQLM/VPTQ and
  profile recommendations.
- Resumable, checksum- and license-gated downloads.
- A deny-by-default permission engine with session grants and audit records.

## What was not integrated

- No upstream code was copied. No upstream license notice is required for copied
  source because no source was copied.
- No live model-quality comparison against the upstream projects was performed.
- No MCP server was started, no paid API was called, and no computer-control
  session was executed.
- The 300-provider target was not claimed: the built-in catalog contains 44
  profiles, with optional LiteLLM discovery when LiteLLM is installed.
- The 15-model/1,500-logical-agent path is implemented and tested with fixture
  providers, not with 15 loaded models or 1,500 live inference calls.

## License handling

Apache-2.0 and MIT repositories were reviewed. Their source was not copied, so
their copyright notices are not reproduced as bundled code. The LoopSieve
`THIRD_PARTY_NOTICES.md` records optional runtime dependencies and model-license
requirements. The `data/providers/catalog.json` file contains metadata only; it
does not grant rights to third-party APIs or model weights.
