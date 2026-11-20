# Product concepts considered

The goal of the research phase was not to find twenty names for another coding agent. Each concept below attacks a different job.

| # | Concept | Main job | Strength | Main risk |
| ---: | --- | --- | --- | --- |
| 1 | Delta verification layer | Return only new local evidence after edits | Measurable, narrow, no extra model | False suppression if fingerprinting is weak |
| 2 | Symbol context packer | Build minimal context bundles for a task | Direct context reduction | Hard to prove quality is preserved |
| 3 | Agent budget scheduler | Decide when another agent call is justified | High value for multi-agent users | Needs deep integration with runtimes |
| 4 | MCP cold-start manager | Load MCP tools only when needed | Faster startup and smaller tool context | Claude Code already improves dynamic tooling |
| 5 | Session resume ledger | Persist decisions and unfinished work | Frequent pain point | Beads and similar tools are strong here |
| 6 | Local UI quality gate | Screenshot and accessibility checks before model review | Strong visual demo | Frontend-only audience |
| 7 | Permission policy engine | Explain and enforce agent tool permissions | Security value | Enterprise products already cover parts of this |
| 8 | Test impact predictor | Run only tests affected by edits | Saves local time | Language-specific dependency analysis |
| 9 | Tool-output compressor | Reduce large command output before it reaches the model | Easy integration | Can hide important details |
| 10 | Agent failure circuit breaker | Stop repeated unproductive loops | Clear benefit | Difficult to distinguish persistence from looping |
| 11 | Multi-repo dependency navigator | Give agents cross-repo impact maps | Valuable in monorepo-adjacent teams | Complex setup |
| 12 | MCP integration health checker | Continuously validate MCP servers | Useful operations layer | Lower daily frequency |
| 13 | Agent audit ledger | Record tools, edits, tests, and handoffs | Compliance and debugging | Observability market is crowded |
| 14 | Patch proof bundle | Produce machine-readable evidence for every patch | Good for PR review | PatchProof-like projects already exist |
| 15 | Local build-error index | Search past local failures and fixes | Useful memory | Risk of stale advice |
| 16 | Dependency-change sentinel | Detect risky package updates before agents continue | Security plus reliability | Narrow trigger frequency |
| 17 | Task-to-check compiler | Convert acceptance criteria into deterministic checks | Strong quality story | Hard to automate safely without a model |
| 18 | Worktree coordinator | Allocate safe worktrees to parallel agents | Practical for teams | Gas Town and others already strong |
| 19 | Agent-ready project bootstrap | Generate clean agent policies and checks for a repo | Fast onboarding | Easy to copy, weak moat |
| 20 | Local benchmark harness | Compare coding agents on your own repository | Honest measurement | Slow time to first value |

## Five finalists

### 1. Delta verification layer

Best combination of daily frequency, measurable benefit, legal safety, low install friction, and independence from a specific model API.

### 2. Symbol context packer

Potentially larger savings, but the hardest failure mode is silent omission of a file the model needed. Evaluation is much more expensive.

### 3. Agent budget scheduler

Compelling for power users, but useful scheduling requires owning more of the agent loop than an extension should in the first release.

### 4. Test impact predictor

Excellent deterministic value, but a credible cross-language version is a large research project. It fits better as LoopSieve P1.

### 5. Session resume ledger

Very useful, but Beads and newer workspace managers already have strong adoption and a clearer lead.

## Adversarial review

The selected idea can still fail for several reasons:

- Developers may already have fast test hooks and see no benefit.
- Full test suites may be too expensive to run after each edit.
- A bad fingerprint can suppress evidence that was actually new.
- Claude Code may evolve its native verification behavior.
- A plugin that needs Python may still be more setup than users want.
- Diagnostic characters are not the same metric as model plan usage.

These risks pushed the design toward a small verification engine instead of a broad orchestration framework. It can remain useful as a direct CLI or CI helper even if the Claude Code adapter changes.
