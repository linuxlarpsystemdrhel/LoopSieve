# Baseline audit — LoopSieve 0.5.0

Date: 2026-11-10  
Scope: the ZIP supplied at the start of this iteration, before the 0.6.0 changes.

## Measured baseline

| Metric | Value |
|---|---:|
| Project files (excluding caches) | 395 |
| Python source files | 50 |
| Python source lines | 6,400 |
| Test files | 28 |
| Test lines | 1,707 |
| Agent manifests | 100 |
| Registered local tools | 63 |
| Skill manifests | 50 |
| Plugin/CLI adapter manifests | 50 |
| Technology manifests | 50 |
| Model catalog entries | 11 |
| Original innovation entries | 100 |
| Baseline test run | 116 tests + 129 subtests, all passing |

The baseline suite passed on Windows 11 with Python 3.14.7. The 0.4.0 Linux
result (82 tests + 122 subtests) remains historical evidence, not a current
cross-platform guarantee.

## What actually worked

- Local verification, diagnostic deduplication and the release evidence gate.
- SQLite session journal, hash-chained evidence ledger and artifact store.
- 100 role manifests routed through one shared `AgentRuntime`.
- Allowlisted inspect/tree/patch/verify/finish/blocked actions with explicit
  write and check opt-ins.
- Ollama, HTTPS-compatible, Claude CLI and Codex CLI provider adapters. Only the
  Ollama HTTP contract was tested against a local fixture; no live provider was
  measured.
- Sequential DAG orchestration, retries and write-set-scoped parallel scheduling.
- Terminal workbench, provider health/fallback, model catalog, memory estimates,
  checkpoints, handoff, reliability ranking and Claude Code hooks.

## What was incomplete or misleading if read uncritically

- The 100-idea inventory was **5 implemented/tested, 16 partial, 79 planned**.
  The 20 release items from 0.5.0 were a separate engineering list.
- The 100 roles were configurations, not 100 independently evaluated live
  agents. No live multi-agent benchmark existed.
- The catalogue had 11 seed models, not a live Hugging Face explorer.
- There was no multi-model team, no team dialogue bus and no 100-logical-agent
  count per model.
- The provider layer had four adapters, not a scalable provider catalog.
- Quantization was limited to GGUF-family profiles; GPTQ/AWQ/EXL2/HQQ/AQLM/VPTQ
  were not represented.
- API keys had no dedicated encrypted store.
- The web/Studio modules remained in the tree for compatibility even though the
  terminal is the recommended surface.
- No 15-model session, 1,500 logical-agent address space, HF pagination, provider
  catalog, permission engine, secret store or resumable download existed.

## Duplication and refactoring risks

- `studio.py`, `webui.py`, `terminal_chat.py` and `commands.py` overlap in their
  presentation concerns. 0.6.0 makes `commands.py`/`tui.py` the main surface.
- `providers.py` and `provider_health.py` both model provider state; 0.6.0 adds
  `provider_catalog.py` for metadata and keeps key handling in `secure_store.py`.
- `model_manager.py` and `quantization.py` both discuss model fit; 0.6.0 keeps
  the estimator in `quantization.py` and compatibility labels in `model_manager.py`.
- `agents.py` had a small task queue and `agent_runtime.py` had a session journal;
  the new `model_team.py` composes them instead of creating a third executor.

## Security findings

- The baseline already required explicit writes and checks and blocked path
  escapes, but permissions were action checks, not a unified engine with levels,
  grants, expiry and audit.
- Secrets were environment-only. There was no DPAPI/keyring-backed store.
- Provider keys were not stored in a catalog; the new catalog never stores keys
  in JSON.
- Downloads already required SHA-256, license acceptance and approval, but did
  not retain a `.part` file for safe resume.

## Baseline conclusion

The baseline was a credible local verification and bounded-runtime alpha, not a
15-model autonomous engineering platform. 0.6.0 adds the missing vertical slice:
capability registry/router, permission engine, encrypted secret store, HF
explorer, provider catalog, quantization methods, resumable downloads and a
multi-model logical-agent team. It still does not claim live model quality,
computer control, 300 verified providers or a completed 100-innovation platform.
