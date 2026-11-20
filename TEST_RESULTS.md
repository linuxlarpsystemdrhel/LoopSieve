# Test results

For the latest release-preparation measurements, see the [current report](docs/release-readiness.md). The data below documents the earlier 0.6.0 baseline.

Date: 2026-11-10  
Platform: Windows 11, Python 3.14.7  
Command: `python -m pytest -q`

```text
128 passed, 129 subtests passed in 43.52s
```

Baseline before the 0.6.0 changes: **116 passed, 129 subtests passed**.

## Verified in the current suite

- 100 role manifests complete a bounded read-only session with a fixture provider.
- Real file patch + real Python `unittest` in the offline demo.
- Checkpoint restore, permission denial, tool/search/diff actions.
- Provider health classification, persisted fallback and fail-closed behavior.
- Write-set conflict rejection, safe parallel reads, retries and replanning.
- Hardware detection with explicit unknown values.
- Model memory estimates, fit/compatibility labels and resumable checksum-gated downloads.
- Hugging Face cursor pagination against a local fake API.
- Capability registry/router and 15-model/1,500-logical-agent team registration.
- Team message bus and export.
- Claude Code hook install/status/uninstall and `PostToolUse` payload.

## Not verified

- Live Claude, Codex or Ollama task quality/latency/tokens.
- 15 loaded models or 1,500 live inference calls.
- 300 live provider profiles.
- Real GPTQ/AWQ/EXL2/HQQ/AQLM/VPTQ quantization runs.
- Computer control, GUI automation or a VM sandbox.
- macOS execution and browser visual QA.
