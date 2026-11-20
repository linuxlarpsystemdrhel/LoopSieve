> Historical 0.5.0 report. The current 0.6.0 report is [FINAL_REPORT.md](../FINAL_REPORT.md).

# LoopSieve v0.5.0 alpha: engineering report

Date: 2026-11-10  
Status: alpha

## Outcome

This is an incremental, testable release based on LoopSieve v0.4.0. It adds a
terminal-first workbench, provider health and fallback controls, hardware-aware
local model management, and a safer dependency-aware orchestrator. It is **not**
a completed autonomous engineering platform and it does not deliver the 100
items in the original innovation list. The 0.4.0 provenance and verification
features remain in the source tree.

The release report below contains exactly 20 release items. Each row states what
was built, what was actually checked, and what remains unverified.

## 20 release items

| # | Item | Implementation | Verification evidence | Limits |
|---:|---|---|---|---|
| 1 | Terminal workbench as the primary surface | `tui.py`, `commands.py`, `mascot.py`; no-argument launch opens the workbench | `test_features_v05.py::test_tui_sections_are_safe`; `test_commands_v05.py::test_read_only_commands` | Optional Textual path was not visually QA'd; no measured FPS |
| 2 | Provider health monitor | `provider_health.ProviderHealthMonitor`; persisted health states and stable failure classification | `test_provider_fallback.py::test_classification_is_stable`; `test_health_monitor_persists_and_probes` | Classification is local and heuristic; no exhaustive provider taxonomy |
| 3 | Safe provider fallback | `FallbackProvider` and `FallbackController`; fail-closed when disabled; no in-flight model switch | `test_fallback_switches_and_records_failure`; `test_disabled_fallback_fails_closed` | Live multi-provider chains and outages were not exercised |
| 4 | Hardware detection | `hardware.py`; CPU, RAM, NVIDIA and ROCm probes; unknown values remain unknown | `test_model_manager.py::test_hardware_has_explicit_unknowns` | No GPU library dependency; vendor tools may be absent |
| 5 | Hardware-aware model catalog | `model_manager.py`, `data/models/catalog.json`; fit labels and task-based selection | `test_fit_labels_are_explicit`; `test_manager_select_auto_and_memory` | Catalog metadata only; no model weights are distributed |
| 6 | Transparent memory estimate | `quantization.py`; weights, KV cache, compute buffers, overhead and safety margin | `test_memory_estimate_is_transparent_and_positive` | An estimate is not a runtime measurement; no live VRAM benchmark |
| 7 | Verified model downloads | `ModelDownloader`; HTTPS, license acceptance, explicit approval and SHA-256 verification | `test_downloader_requires_checksum_and_approval`; `test_loopback_download_verifies_checksum` | The test used loopback fixtures; no real model download was performed |
| 8 | Dependency-aware orchestrator | `orchestrator.py`; DAG validation, priorities, retries, replanning and bounded workers | `test_orchestrator_v05.py` (five tests) | Tests use fixture runtimes; no live multi-agent reasoning quality benchmark |
| 9 | Write-set-scoped parallelism | `_safe_parallel` and `detect_write_conflicts`; unknown write sets stay sequential | `test_parallel_read_only_tasks`; `test_write_conflict_is_rejected_before_execution`; `test_unknown_write_set_runs_sequentially` | Only thread-safe providers; declared write sets are trusted |
| 10 | Retry and dynamic replanning | `Orchestrator` retry/replan callbacks; additions are validated against the DAG | `test_retry_after_transient_failure`; `test_replan_adds_a_new_item` | Replanning is callback-driven; no autonomous architectural repair |
| 11 | Pre-write checkpoints and restore | `checkpoint.CheckpointTimeMachine`; snapshots stored in the session journal | `test_runtime_v05.py::test_checkpoint_restore_and_time_machine` | Restores LoopSieve checkpoints, not arbitrary Git history |
| 12 | Cross-agent conflict resolver | `conflict.CrossAgentConflictResolver`; detect and policy-based resolution | `test_features_v05.py::test_conflict_resolver` | Policies are explicit; no semantic code merge |
| 13 | Verified task handoff | `handoff.VerifiedTaskHandoff`; completed/evidence/changed-file hash checks | `test_verified_handoff_and_tamper_detection` | Does not replay the full model conversation or environment |
| 14 | Reliability ranking | `reliability.py`; ranks roles from local completed and verified sessions | `test_reliability_and_budget` | Local outcome counts only; not a general model-quality score |
| 15 | Adaptive swarm budget | `budget.AdaptiveSwarmBudget`; hardware and call-count recommendations | `test_reliability_and_budget` | Uses estimates and configured limits; no live cost accounting |
| 16 | Failure prediction | `failure.py`; heuristic risk from changed files and local history | `test_failure_prediction_and_routing` | Heuristic only; no trained model or guarantee |
| 17 | Deterministic tool routing | `routing.py`; routes declared tools by role and task text | `test_failure_prediction_and_routing` | Deterministic rules; no online learning |
| 18 | Model arena | `arena.ModelPerformanceArena`; one real fixture against a supplied provider | No dedicated automated test in this suite; command path exists | One fixture is not a model ranking; no live provider run |
| 19 | Expanded agent actions | `agent_runtime.py`; all 100 roles can use read-only tool, search, diff and checkpoint restore actions | `test_runtime_v05.py` (tool/search/diff/permission tests); existing 100-role runtime tests | No arbitrary shell action; model quality still unverified |
| 20 | Claude Code hooks | `claude_code.py`, `hooks/hooks.json`, `.claude-plugin/plugin.json`; `PostToolBatch` and `PostToolUse` support | `test_claude_code_v05.py` install/status/uninstall and payload tests | No live Claude Code session was run in this environment |

## Test evidence

Run from the source checkout:

```bash
python -m pip install .
python -m pytest -q
python -m loopsieve demo
python -m loopsieve innovations --summary
```

Release validation in this environment (Windows 11, Python 3.14.7, source on
`PYTHONPATH=src`) produced:

```
116 passed, 129 subtests passed in 30.44s
```

The 129 subtests are not counted as additional independent test functions. The
previous 0.4.0 validation on Linux/Python 3.13 produced `82 passed, 122 subtests
passed in 46.20s`; that result is retained as historical evidence, not as a
current cross-platform guarantee. macOS and live-provider CI jobs were not run
here. Optional Textual visual QA and Studio WebGL animation FPS were not tested
in a browser.

## Quantitative measurements

The inherited synthetic `stable-repeat.json` fixture, using the unchanged
conservative deduplication algorithm:

- 8 iterations and 7 repeated failure instances.
- Raw diagnostic text: 19,144 characters.
- Emitted context: 2,911 characters.
- Diagnostic text reduction: **84.79%**.

This is **not** an input-token, output-token, billed-dollar or Claude
subscription-usage benchmark. No real-LLM paired experiment was performed.

A hardware probe on the current Windows host reported an NVIDIA RTX 5060 with
8,151 MiB total VRAM and 32,712 MiB total RAM. These are operating-system/vendor
tool readings. The model memory figures are estimates from declared metadata;
no local model was loaded or measured during this release validation.

## What is verified and what is not

Verified by the current suite:

- The 20 mechanisms above have importable implementations and dedicated tests,
  except the model arena, which has no dedicated automated test.
- The shared runtime still completes a bounded read-only session for all 100
  role manifests using a deterministic fixture provider.
- The offline demo performs a real file patch and a real Python `unittest` check.
- The orchestrator rejects declared write-set conflicts before execution, keeps
  unknown write sets sequential, retries transient failures and accepts a
  validated replanned item.
- Provider health classification and fallback state persist locally; disabled
  fallback fails closed.
- Hardware unknowns remain explicit and model fit labels are stable.
- The diagnostic benchmark still avoids known false-suppression cases.

Not verified by this release:

- Live Claude, Codex or Ollama task quality, latency or token usage.
- 100 agents reasoning independently or concurrently in production.
- Real parallel edits in separate Git worktrees with automatic merging.
- Model arena results against live providers.
- Browser visual QA, terminal graphics protocols or measured animation FPS.
- Full Windows/macOS/Linux cross-platform CI and packaging validation.
- Security against hostile repositories, prompt injection and crash-consistency
  faults beyond the existing regression tests.
- Any claim of 10,000 GitHub stars or superiority over competing agents.

## Innovation coverage

The original 100-item innovation inventory remains **5 IMPLEMENTED_TESTED, 16
PARTIAL and 79 PLANNED**. The 20 release items in this report are engineering
delivery items and are not a retroactive reclassification of those 100 ideas.
See `INNOVATION_COVERAGE.md` and `INNOVATIONS.json` for the item-by-item status.

## Security and safety

- New execution paths are opt-in. Writes require `--allow-writes`, checks require
  `--allow-checks`, and model downloads require license acceptance and explicit
  approval.
- Provider fallback never switches a model in the middle of an in-flight tool
  action. Disabled fallback fails closed.
- The evidence ledger is locally tamper-evident, not externally notarized. An
  attacker who replaces the whole database and head can forge local history.
- No model weights or competitor source code are bundled. Model downloads are
  user-initiated and checksum-gated.
- The core proof and verification tools send no telemetry. Network access remains
  optional.
- Project checks remain unsandboxed subprocesses explicitly approved by the
  operator. Do not run this alpha as a public server or against untrusted code
  without an external sandbox.

## Still missing

- Verified 100-agent live reasoning quality and safe automatic merging.
- End-to-end live provider benchmarks with identical tasks and budgets.
- A real MCP client and lifecycle-managed skill/plugin approvals.
- Stronger process isolation, fuzzing, prompt-injection testing and
  crash-consistency testing.
- Cross-platform release validation and a user study for usability.
- A credible path to 10,000 GitHub stars; this release makes no such prediction.

**Release recommendation:** publish as a transparent `v0.5.0-alpha` only. Do not
present it as 100 finished innovations or as a production replacement for
Claude Code, Codex, OpenClaw or OpenCode.
