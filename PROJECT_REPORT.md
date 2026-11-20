# LoopSieve 0.6.0 engineering report

Date: 2026-11-10  
Status: alpha

## Scope

This update starts from the supplied LoopSieve 0.5.0 ZIP and adds a real vertical
slice for model/capability/agent management. It preserves local verification,
evidence, checkpoints, Claude Code hooks and the 100 role manifests.

Detailed documents: `FINAL_REPORT.md`, `BASELINE_AUDIT.md`,
`UPSTREAM_INTEGRATIONS.md`, `TEST_RESULTS.md`, `KNOWN_LIMITATIONS.md`.

## Architecture

```text
CLI / TUI / Claude Code hook
  -> CapabilityRegistry + PermissionEngine
  -> ModelTeam (<=15 model slots)
  -> logical agents (<=100 per model)
  -> AgentRuntime bounded JSON actions
  -> workspace tools / patch + checkpoint / verify / finish
  -> SQLite Journal + evidence ledger + artifacts
```

The 100 roles are configurations for one shared runtime, not 100 loaded models.
The 15-model/1,500-agent address space is logical; one provider slot serves its
agents through a queue.

## Verified test result

Windows 11, Python 3.14.7, `python -m pytest -q`:

```text
128 passed, 129 subtests passed in 43.52s
```

Baseline: 116 passed, 129 subtests passed.

## 0.6.0 delivered

- Capability Registry (382 descriptors) and deterministic router.
- Deny-by-default PermissionEngine with grants and audit.
- DPAPI/keyring secret store.
- Official Hugging Face metadata explorer with cursor pagination.
- 44-profile provider catalog and custom OpenAI-compatible providers.
- GGUF/IQ, GPTQ, AWQ, EXL2, HQQ, AQLM and VPTQ metadata; quality/balanced/
  maximum/experimental profiles.
- Resumable checksum/license-gated downloads.
- ModelTeam with 15 model slots, 100 logical agents per slot, typed dialogue and
  read-only parallel solutions.
- TUI/CLI panels and commands for the new subsystems.
- Baseline/upstream audits, test results and honest limitations.

## Not delivered

- 300 verified providers.
- 15 simultaneously loaded local models or 1,500 live inference calls.
- Real GPTQ/AWQ/EXL2/HQQ/AQLM/VPTQ conversion and quality measurement.
- Computer twin/GUI automation/VM sandbox.
- Full live Claude/Codex/Ollama quality benchmark.
- Automatic semantic merge of parallel edits.
- The 100 original innovation items as completed features.

## Recommendation

Publish as transparent `0.6.0-alpha`. Do not present fixture-based agent runs as
live model performance or the 100-item roadmap as complete.
