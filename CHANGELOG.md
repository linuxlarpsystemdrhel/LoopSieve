# Changelog

## Unreleased

- Added the native `loopsieve` command with persistent local Ollama agents, verified exact-match patches, checkpoint recovery and scoped sequential teams.
- Ported loopback llama.cpp explanations and model launch, checksum-pinned model files, hardware metadata, local hook installation, read-only MCP inspection, terminal chat and the local dashboard.
- Added read-only inspection of historical Python verification state and SQLite session metadata.
- Added a native Rust verification preview with bounded execution, structured diagnostic deltas, declared-input caching, and local evidence export.
- Added a native post-edit hook and declarative verification tasks with dependency ordering and failure propagation.
- Added the Rust migration guide, three-workload baseline, cross-platform build workflow, and capability coverage matrix.
- Excluded private state, credentials, model weights and local benchmark output from publication paths.
- Serialized verification-state updates across processes with an OS file lock. State failures now preserve verification outcomes.
- Validated project configuration before running checks and compared declared inputs before and after cacheable executions.
- Preserved diagnostic columns, unparsed location prefixes and failure details at the end of long logs.
- Added opt-in local diagnostic explanations with a user-supplied model and a reproducible llama.cpp CPU and CUDA benchmark harness.
- Reused the parsed Python source during diagnostic fingerprinting and confined source anchors to the project.
- Bounded POSIX output draining when a descendant keeps the verification pipe open. Release checks now share bounded capture.
- Made the Ollama loopback adapter bypass proxies and reject redirects.
- Fixed the Capabilities panel and the Textual tab identifiers.
- Prepared CI, release validation, documentation, and LoopSieve branding.

## 0.6.0 - 2026-11-10

- Added a 338-entry Capability Registry and deterministic capability router.
- Added a deny-by-default PermissionEngine with eight levels, session grants and audit.
- Added a Windows DPAPI secret store with keyring/file fallbacks; provider catalog has no plaintext keys.
- Added the official Hugging Face metadata client with server-side cursor pagination.
- Added a 44-profile provider catalog with explicit verification states and custom providers.
- Added GGUF/IQ, GPTQ, AWQ, EXL2, HQQ, AQLM and VPTQ method metadata and quality/balanced/maximum/experimental profiles.
- Added resumable `.part` downloads with Range support, checksum and license gates.
- Added a multi-model ModelTeam: up to 15 models, up to 100 logical agents per model (1,500 address space), typed dialogue bus and read-only parallel solutions.
- Added TUI/CLI surfaces for Model Team, Team Dialogue, Providers, HF, Quantization, Capabilities, Security and Activity.
- Added BASELINE_AUDIT.md, UPSTREAM_INTEGRATIONS.md and the 0.6.0 reports/tests.


## 0.5.0 - 2026-11-10

- Added the terminal workbench as the primary interface: command router, Textual view and zero-dependency fallback, pixel-art Pip mascot.
- Added provider health classification and persisted safe fallback; fallback never switches during an in-flight tool action.
- Added hardware detection (CPU/RAM/VRAM), a local model catalog, Q8/Q6/Q5/Q4/Q3/Q2 metadata, transparent memory estimates and explicit fit labels.
- Added checksum/license/approval-gated model downloads and verification; no model weights are bundled.
- Added write-set-scoped parallel orchestration, retries, dynamic replanning, conflict detection and a cross-agent conflict resolver.
- Added pre-write checkpoints and restore, verified task handoff, reliability ranking, adaptive swarm budget, failure prediction and deterministic tool routing.
- Added read-only `tool`, `search`, `diff` and checkpoint `restore` actions to all 100 role manifests.
- Added official Claude Code `PostToolBatch`/`PostToolUse` hook support and integration status commands.
- Fixed Windows SQLite handle leaks and Windows task-queue lock races found during the forensic audit.
- Updated README, architecture/security documentation, tests, SBOM and release report. Browser UI is no longer the primary product surface.

## 0.4.0 - 2026-11-10

- Added a hash-chained SQLite evidence ledger integrated into the agent journal, with integrity auditing and bounded/redacted stored events.
- Added a content-addressed artifact store, provenance-aware local memory with expiration, a release evidence gate, checked subprocess suites, and sanitized metadata capsules.
- Added source-hashed context excerpts, static Python reverse-import impact analysis, requirements-pin conflict detection, and validated acceptance criteria.
- Added opt-in detached Git worktree experiments with clean-checkout requirements and no automatic merge or deletion.
- Added evidence and impact screens to Studio, proof/innovations CLI commands and an explicitly scripted offline demo.
- Added a dated GitHub API competitor snapshot, 100-item innovation coverage manifest, dependency provenance, SBOM and an evidence-oriented release report.
- Preserved the verification/deduplication fixes and 100 agent definitions from 0.2/0.3.
- Did not implement 100 new production features, parallel multi-agent editing, or validate live LLM token savings.

## 0.3.0 - 2026-11-10

- Added a SQLite-backed autonomous agent execution loop, 100 opt-in role-specific action policies, and prompt-limited model adapters for Ollama, optional Claude/Codex CLI and OpenAI-compatible HTTPS APIs.
- Added atomic session step claiming, budget limits, cancellation guards, scoped exact-match file patching and evidence-gated completion.
- Added a sequential dependency DAG, console chat, provider/session CLI commands, local context compiler, Python symbol/import index, MCP config discovery, permission previews and reproducibility capsules.
- Added a local Studio control plane with explicit task actions, CSRF/Origin/Host checks, original glTF Pip 3D model and 15 WebGL animation modes.
- Expanded regression and integration tests. Production provider use, TUI mascot graphics and parallel autonomous editing remain unverified or incomplete.


## 0.2.0 - 2026-11-09

- Replaced unsafe file-list skip logic with explicit, conservative, content-addressed positive cache verification.
- Replaced line-stripping fingerprints with source-location-aware diagnostic identities and AST anchors where reliable.
- Added bounded streaming subprocess output and timeout recovery.
- Added 100 separate specialist role manifests with on-demand registry loading.
- Added 63 read-only developer tools, 50 skill workflows and 50 optional CLI adapter manifests.
- Added a deterministic role selector, persistent explicit task queue, and permission checks.
- Added a terminal workspace view and a read-only localhost dashboard.
- Added adversarial regression tests, a catalog test suite, and revised benchmark fixtures.
- Replaced misleading older benchmark claims with conservative measurements.

## 0.1.0 - 2026-11-09

- Initial local verification and Claude Code PostToolBatch hook integration.
