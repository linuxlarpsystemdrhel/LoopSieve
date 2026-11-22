# Rust implementation status

Status refers to the native implementation. The Rust CLI is the primary build described in the README. It embeds the same 100 role manifests as the Python implementation. Legacy workflows remain available during parity work.

## Verified inventory and migration order

| Area | Observed in the Python alpha | Rust migration status |
|---|---|---|
| Checks, fixtures, cache and state | `runner.py`, `engine.py`, `verification_state.py` and regression tests | Core flow runs through native CLI. Three historical fixtures have matching counters. |
| Agent sessions and roles | SQLite journal, bounded JSON actions, role manifests, explicit write and check permissions | Native local model turns, scoped exact-match edits, checkpoints, recovery, and verification-gated completion. Selected SQLite sessions import into new native sessions. In-place continuation and Python checkpoint import remain pending. |
| Models | Ollama and compatible adapters, CLI bridges, optional local diagnostic endpoint | Loopback Ollama decisions and inventory, llama.cpp streaming advice and launcher, and checksum-pinned file management. External adapters and resumable downloads remain pending. |
| Teams and isolation | Declarative work items, write-conflict checks and explicit Git worktree creation | Native check and agent DAGs use three scheduling strategies. Agent teams support per-task local models and enforce declared write sets. Parallel editing and isolated worktrees remain pending. |
| Context, MCP and plugins | Project metadata, memory, catalog workflows, and MCP configuration inspection | Native tool subset, manifest metadata, and offline MCP inspection. Context compiler, memory, skill execution, plugin probes and a live MCP client remain pending. |
| Evidence | Python event ledger, artifact hashes, and session handoffs | Native verification chain and export link check runs to sessions and task IDs. Agent checkpoints record before and after digests and bounded observations. Python evidence and grants are excluded from import. Full provenance parity remains pending. |
| Interfaces | Terminal workbench, Claude Code hooks and compatibility web surfaces | Native terminal workbench and chat, read-only localhost dashboard, and Claude local hook installer. Full-screen UI and Studio remain pending. |

## Local verification

| Check | Linux result |
|---|---|
| `cargo test --workspace --locked` | 38 tests passed. They cover the three historical fixtures, a complete agent patch/verification/restore workflow, team dependency blocking, streaming advice, and SQLite migration with synthetic data. |
| `PYTHONPATH=src python -m unittest discover -s tests -q` | 161 Python tests passed with loopback test servers available. A restricted sandbox run failed when it denied socket creation and writes to the default cache path. |
| `cargo fmt --all -- --check`, `cargo clippy --workspace --all-targets --locked -- -D warnings`, `cargo build --workspace --release --locked` | All passed. |
| `cargo audit` | No advisories reported for the 147 locked workspace dependencies in the database consulted. |
| `actionlint .github/workflows/*.yml` | Workflow validation passed. Hosted CI, macOS and Windows runs remain pending. |
| Native release binary on this checkout | `check` ran the workspace's real Cargo test command. `plan` and `run` verified the example task. `evidence verify` validated both records, and the export retained the task ID. |
| Standalone installation and dashboard | Cargo installation worked into a temporary prefix. A copied binary ran with an empty `PATH`. The native HTTP dashboard returned HTML and JSON on loopback and rejected a foreign `Host` and `POST`. |
| Model integration scope | Ollama and llama.cpp protocols were exercised with local HTTP fixtures. Live model generation, real weights and cross-platform runtime execution remain unverified in this pass. |
| Intentional failing Python example | Two native runs against `examples/local-diagnostics/example.py` returned exit 1. The first exposed `ZeroDivisionError`, and the second classified it as an unchanged failure. |
| Runtime comparison | Three workloads with 20 samples per implementation on the current binary. [Method and measurements](benchmarks.md#current-native-runtime). |

## Capability backlog

The description column records the desired behavior. The evidence column gives the module and exercised behavior where this pass implemented part of the capability. For pending rows, acceptance requires a working entry point and a test covering the stated behavior; security and performance checks are still pending.

| ID | Capability and acceptance intent | Status | Rust evidence and remaining boundary |
|---|---|---|---|
| 001 | **Adaptive Swarm Scaling**. Dynamically adjust the number of active logical agents according to task complexity, available resources, and actual workload. | NOT_STARTED | — |
| 002 | **Hierarchical Mission Delegation**. Allow orchestrator agents to create bounded sub-missions with explicit ownership and budgets. | NOT_STARTED | — |
| 003 | **Agent Specialization Optimizer**. Recommend specialized agent roles based on recurring project tasks and measured performance. | NOT_STARTED | — |
| 004 | **Capability-Based Agent Discovery**. Match tasks to agents using typed capability descriptors rather than role names alone. | NOT_STARTED | — |
| 005 | **Dynamic Team Composition**. Assemble different teams for architecture, implementation, debugging, testing, and release work. | NOT_STARTED | — |
| 006 | **Multi-Agent Consensus**. Compare independently generated solutions using explicit criteria and verification evidence. | NOT_STARTED | — |
| 007 | **Agent Debate Protocol**. Allow agents to challenge proposed technical decisions before implementation. | NOT_STARTED | — |
| 008 | **Conflict-Aware Parallel Coding**. Coordinate concurrent coding agents using write-set analysis and isolated workspaces. | NOT_STARTED | — |
| 009 | **Automatic Agent Recovery**. Restore interrupted agents from persisted state without repeating already verified work. | EXPERIMENTAL | Manual interrupted-turn recovery consumes the claimed step and blocks on a pending patch. Automatic replay remains open. |
| 010 | **Agent Performance Intelligence**. Track task success, latency, cost, and failure patterns to improve future assignment decisions. | NOT_STARTED | — |
| 011 | **Goal-to-Task Compiler**. Transform natural-language objectives into structured requirements and executable task graphs. | NOT_STARTED | — |
| 012 | **Multi-Level Planning**. Maintain strategic plans, milestone plans, and immediate execution plans. | NOT_STARTED | — |
| 013 | **Automatic Plan Repair**. Update affected tasks when assumptions or requirements change. | NOT_STARTED | — |
| 014 | **Dependency Prediction**. Detect hidden dependencies between proposed code modifications. | NOT_STARTED | — |
| 015 | **Critical Path Optimization**. Prioritize tasks that constrain overall mission completion. | IMPLEMENTED_TESTED | mission.rs — critical-path order uses estimated duration and dependencies. The CLI test compares its order with FIFO and priority. |
| 016 | **Risk-Aware Planning**. Identify likely failure points before expensive implementation begins. | NOT_STARTED | — |
| 017 | **Alternative Architecture Exploration**. Compare multiple architectural proposals against explicit constraints. | NOT_STARTED | — |
| 018 | **Requirement Traceability**. Connect every requirement to implementation artifacts and tests. | NOT_STARTED | — |
| 019 | **Execution Cost Simulation**. Estimate token, time, and resource usage before launching large missions. | NOT_STARTED | — |
| 020 | **Constraint-Aware Planning**. Generate plans that respect user-defined budgets, deadlines, and security restrictions. | NOT_STARTED | — |
| 021 | **Persistent Repository Knowledge Graph**. Track relationships among files, symbols, modules, tests, and dependencies. | NOT_STARTED | — |
| 022 | **Semantic Project Memory**. Retrieve relevant historical engineering decisions and repository knowledge. | NOT_STARTED | — |
| 023 | **Context Provenance Engine**. Attach source references and freshness information to retrieved context. | NOT_STARTED | — |
| 024 | **Adaptive Context Compression**. Reduce context usage without losing essential requirements and decisions. | NOT_STARTED | — |
| 025 | **Incremental Code Indexing**. Update repository indexes only when relevant files change. | NOT_STARTED | — |
| 026 | **Cross-Session Mission Continuity**. Resume complex engineering work after application restarts. | NOT_STARTED | — |
| 027 | **Context Conflict Detection**. Identify contradictions between stored memory and current source code. | NOT_STARTED | — |
| 028 | **Model-Specific Context Packaging**. Prepare different context packages for models with different capabilities and limits. | NOT_STARTED | — |
| 029 | **Automatic Stale-Memory Invalidation**. Invalidate cached knowledge when underlying repository evidence changes. | NOT_STARTED | — |
| 030 | **User-Controlled Memory Governance**. Inspect, export, disable, expire, and delete stored project memory. | NOT_STARTED | — |
| 031 | **Diagnostic Delta Engine 3.0**. Extend diagnostic filtering with semantic identities, structured comparisons, and regression awareness. | EXPERIMENTAL | diagnostics.rs and verify.rs — structured locations and deltas. Tests cover changed columns, truncation, resolution and regression. Symbol-based fingerprints and clustering remain open. |
| 032 | **Verification Impact Predictor**. Determine which checks are likely relevant to a code change. | NOT_STARTED | — |
| 033 | **Test Selection Optimizer**. Choose a justified subset of tests while allowing full verification when necessary. | NOT_STARTED | — |
| 034 | **Evidence-Based Completion Scoring**. Measure how strongly available test evidence supports task completion. | NOT_STARTED | — |
| 035 | **Cross-Agent Verification**. Require independent verification for selected high-risk changes. | NOT_STARTED | — |
| 036 | **Regression Root-Cause Analyzer**. Correlate newly failing checks with relevant code changes. | NOT_STARTED | — |
| 037 | **Verification Freshness Tracking**. Show whether previous test results remain valid for the current repository state. | EXPERIMENTAL | snapshot.rs — pre/post fingerprints and cached verification time. Invalidation and changed-input tests pass. Dependency tracing remains open. |
| 038 | **Proof-Carrying Patch Records**. Package patches with requirements, test results, and provenance metadata. | EXPERIMENTAL | Agent checkpoints record before and after hashes. Successful runs link to session IDs. Contract-to-patch provenance remains open. |
| 039 | **Verification Failure Clustering**. Group related diagnostics without hiding distinct underlying failures. | NOT_STARTED | — |
| 040 | **Continuous Verification Supervisor**. Schedule bounded checks during long-running development missions. | NOT_STARTED | — |
| 041 | **Autonomous Feature Delivery**. Implement scoped features from requirements through verification. | NOT_STARTED | — |
| 042 | **Autonomous Bug Reproduction**. Generate and run controlled reproduction scenarios for reported defects. | NOT_STARTED | — |
| 043 | **Repository-Wide Refactoring**. Coordinate large code transformations across modules. | NOT_STARTED | — |
| 044 | **Safe Architecture Migration**. Plan and execute staged framework or language migrations. | EXPERIMENTAL | MIGRATION.md — separately compiled Rust and Python paths with isolated state. Automated migration of sessions remains open. |
| 045 | **Autonomous Documentation Synchronization**. Update documentation when verified implementation changes affect it. | NOT_STARTED | — |
| 046 | **Dependency Modernization**. Recommend and validate safe dependency upgrades. | NOT_STARTED | — |
| 047 | **API Compatibility Guardian**. Detect and report breaking interface changes. | NOT_STARTED | — |
| 048 | **Automated Code Review**. Review patches for correctness, maintainability, security, and regressions. | NOT_STARTED | — |
| 049 | **Long-Running Engineering Missions**. Execute durable workflows with checkpoints, progress tracking, and cancellation. | EXPERIMENTAL | Agent sessions persist turns and checkpoints with step limits. Team-level restart and long-run resumption remain open. |
| 050 | **Verified Release Preparation**. Prepare release artifacts and documentation only after required checks pass. | NOT_STARTED | — |
| 051 | **Universal Model Router**. Select appropriate models using capabilities and user constraints. | NOT_STARTED | — |
| 052 | **Multi-Model Collaboration**. Coordinate different models within a single mission. | EXPERIMENTAL | Sequential `team` supports a model override per task with dependency blocking. Shared dialogue and parallel analysis remain open. |
| 053 | **Local/Cloud Hybrid Execution**. Keep sensitive tasks local while routing approved tasks to cloud providers. | NOT_STARTED | — |
| 054 | **Provider Failover**. Recover gracefully when model endpoints fail. | NOT_STARTED | — |
| 055 | **Model Benchmark Arena 2.0**. Evaluate model performance using reproducible engineering tasks. | NOT_STARTED | — |
| 056 | **Adaptive Token Budgeting**. Adjust reasoning depth and context allocation to remaining budget. | NOT_STARTED | — |
| 057 | **Model Capability Profiling**. Maintain verified capability profiles instead of relying solely on model names. | NOT_STARTED | — |
| 058 | **Hardware-Aware Local Inference**. Recommend feasible model configurations based on available resources. | NOT_STARTED | — |
| 059 | **Inference Request Deduplication**. Avoid duplicate equivalent requests where caching is valid and safe. | NOT_STARTED | — |
| 060 | **Privacy-Aware Provider Selection**. Restrict external model access to approved information. | NOT_STARTED | — |
| 061 | **Mission Control TUI**. Provide a unified terminal interface for conversations, tasks, agents, tests, and artifacts. | EXPERIMENTAL | `tui` shows local verification and sessions, and `chat` runs local tasks. Full-screen views remain open. |
| 062 | **Live Agent Graph**. Visualize agent assignments, dependencies, and execution states. | NOT_STARTED | — |
| 063 | **Interactive Task DAG**. Allow users to inspect and modify mission plans. | NOT_STARTED | — |
| 064 | **Natural-Language Command Interface**. Translate user requests into inspectable operations. | EXPERIMENTAL | `agent` and `chat` turn a user task into validated local actions with observed outcomes. Other commands remain explicit. |
| 065 | **Command Palette**. Provide searchable commands, agents, sessions, and settings. | NOT_STARTED | — |
| 066 | **Session Time Machine**. Navigate historical execution events and restore supported checkpoints. | EXPERIMENTAL | `agent inspect`, `checkpoints`, and guarded `restore` expose historical turns and recover prior file content. |
| 067 | **One-Command Repository Onboarding**. Analyze a project and generate initial LoopSieve configuration. | EXPERIMENTAL | config.rs — init detects Cargo, Python and Go manifests. CLI test covers non-overwriting initialization. Broader framework detection remains open. |
| 068 | **Interactive Patch Review**. Inspect, accept, reject, or revise generated changes. | NOT_STARTED | — |
| 069 | **Explainable Agent Decisions**. Display concise reasons, evidence, and constraints behind significant actions. | NOT_STARTED | — |
| 070 | **Unified IDE Session Bridge**. Expose sessions to supported editors through stable protocols. | NOT_STARTED | — |
| 071 | **Capability-Based Security**. Grant tools only the permissions required for assigned tasks. | EXPERIMENTAL | Native agent opt-ins and role permissions gate edits and checks. Team sessions enforce declared write sets. OS isolation remains open. |
| 072 | **Sandboxed Execution**. Isolate risky commands where operating-system capabilities permit. | NOT_STARTED | — |
| 073 | **Prompt Injection Defense**. Prevent untrusted source content from redefining agent permissions. | NOT_STARTED | — |
| 074 | **Secret Protection Layer**. Detect and redact sensitive credentials. | EXPERIMENTAL | diagnostics.rs — removes recognized token patterns and terminal controls. Persisted evidence test checks a synthetic credential. General secret scanning remains open. |
| 075 | **Transactional Patch Application**. Stage modifications and support safe rollback. | NOT_STARTED | — |
| 076 | **Approval Policy Engine**. Require explicit approval for high-impact operations. | NOT_STARTED | — |
| 077 | **Resource Quota Manager**. Enforce limits on memory, CPU, processes, tokens, and execution time. | NOT_STARTED | — |
| 078 | **Crash Recovery**. Restore durable state after unexpected termination. | EXPERIMENTAL | Atomic state, interruption recovery and guarded checkpoint restoration. Team-level completion recovery remains open. |
| 079 | **Supply Chain Security**. Inspect dependencies, licenses, and artifact provenance. | EXPERIMENTAL | rust.yml — Cargo.lock and RustSec workflow. Plugin and artifact provenance remain open. |
| 080 | **Security Audit Ledger**. Record significant security decisions and execution events. | NOT_STARTED | — |
| 081 | **Rust Plugin SDK**. Allow developers to extend agents, tools, providers, and workflows. | NOT_STARTED | — |
| 082 | **WASM Plugin Isolation**. Run compatible extensions with constrained capabilities. | NOT_STARTED | — |
| 083 | **Advanced MCP Client**. Integrate external tools through permission-aware MCP connections. | NOT_STARTED | — |
| 084 | **MCP Server Mode**. Expose selected LoopSieve functionality to other compatible clients. | NOT_STARTED | — |
| 085 | **Declarative Workflow Engine**. Define reusable engineering workflows in versioned configuration files. | EXPERIMENTAL | `mission.rs` and `team.rs` schedule verification and sequential local model DAGs. General workflows remain open. |
| 086 | **Custom Agent Builder**. Create agent roles with explicit capabilities, policies, and model settings. | NOT_STARTED | — |
| 087 | **Event-Driven Automation**. Trigger approved workflows from repository events and schedules. | NOT_STARTED | — |
| 088 | **Community Extension Registry**. Discover and verify third-party extensions. | NOT_STARTED | — |
| 089 | **Cross-Tool Integration Layer**. Connect LoopSieve with compatible IDEs and coding assistants. | NOT_STARTED | — |
| 090 | **Self-Describing Tool Protocol**. Expose tool capabilities through machine-readable schemas. | NOT_STARTED | — |
| 091 | **Repository Digital Twin**. Build an interactive architectural representation of a codebase. | NOT_STARTED | — |
| 092 | **Predictive Patch Sandbox**. Test alternative changes in isolated environments before integration. | NOT_STARTED | — |
| 093 | **Engineering Causality Graph**. Connect code changes, test outcomes, dependencies, and failures to support root-cause analysis. | NOT_STARTED | — |
| 094 | **Multi-Agent Adversarial Review**. Use independent reviewers to challenge proposed changes and security assumptions. | NOT_STARTED | — |
| 095 | **Automatic Architecture Simplification**. Identify unnecessary complexity and propose evidence-backed simplifications. | NOT_STARTED | — |
| 096 | **Repository Reliability Forecasting**. Estimate maintenance risks from historical evidence while communicating uncertainty. | NOT_STARTED | — |
| 097 | **Self-Healing Mission Runtime**. Recover from transient failures using bounded retries and checkpoint restoration. | NOT_STARTED | — |
| 098 | **Adaptive Developer Preferences**. Learn user-approved conventions without silently changing permissions. | NOT_STARTED | — |
| 099 | **Human-AI Autonomy Controller**. Adjust agent independence according to task risk and user preferences. | NOT_STARTED | — |
| 100 | **Verified Engineering Mission Control**. Unify planning, implementation, orchestration, verification, review, and evidence into one coherent workflow. | NOT_STARTED | — |

## Flagships

- **DeltaMind** has a verification preview with five outcome transitions and structured diagnostic locations.
- **ProofGraph** has hash-linked verification evidence and task IDs. Requirement and patch edges remain pending.
- **Mission Replay** has evidence export and chain inspection. Per-file agent checkpoints support explicit guarded restoration. Full mission and model replay remain pending.
- **SwarmForge** has a sequential scoped-team preview. Parallel isolation remains open. **ContextFabric** remains planned.

The next compatibility boundary is the remaining Python tool catalog and skill workflows. Port each permitted deterministic tool and run its existing fixtures against both runtimes before switching its command. [Migration guide](../MIGRATION.md) · [Competitive capability matrix](COMPETITIVE_CAPABILITY_MATRIX.md).
