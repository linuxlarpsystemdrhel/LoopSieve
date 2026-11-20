# Feature evidence matrix

This matrix lists LoopSieve claims, not invented parity with the competitors.

| Capability | Product | Status | Source |
|---|---|---|---|
| Proof ledger | LoopSieve 0.4 | IMPLEMENTED_TESTED | `provenance.EvidenceLedger` |
| Content-addressed artifacts | LoopSieve 0.4 | IMPLEMENTED_TESTED | `provenance.ArtifactStore` |
| Verified release gate | LoopSieve 0.4 | IMPLEMENTED_TESTED | `provenance.acceptance_gate` |
| Source-backed memory | LoopSieve 0.4 | IMPLEMENTED_TESTED | `memory.ProjectMemory` |
| Git worktree isolation | LoopSieve 0.4 | IMPLEMENTED_TESTED | `worktrees.prepare_experiment` |
| Static source impact radar | LoopSieve 0.4 | PARTIAL | `project_intelligence.python_impact` |
| Offline context excerpts | LoopSieve 0.4 | PARTIAL | `project_intelligence.compile_context` |
| Persistent agent state | LoopSieve 0.3 | IMPLEMENTED_TESTED | `agent_runtime.Journal` |
| Live provider coding benchmark | LoopSieve | NOT_TESTED | `requires real providers and matched tasks` |
| Multi-agent parallel worktree merge | LoopSieve | PLANNED | `requires merge conflict tests` |
| Kitty terminal GLTF mascot | LoopSieve | PLANNED | `requires graphics protocol implementation` |

Competitor features are described in `COMPETITOR_RESEARCH.md`; no direct feature parity was established without benchmark evidence.
