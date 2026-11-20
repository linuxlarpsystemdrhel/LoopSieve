# Autonomous runtime, v0.3.0

## Architecture

```text
User CLI / terminal chat / localhost Studio
               |
          Provider selection (explicit)
               |
     100 lazy agent JSON manifests
               |
     AgentRuntime (finite-state actor)
               |          SQLite Journal
     provider.complete() <------------> sessions / events
               |
      ONE validated JSON action
               |
 permission gate -> safe path -> read / tree / patch / verify
               |
    feedback returned to provider next turn
               |
 evidence gate -> finish / blocked / budget exhausted
```

Each agent is a logical actor with an identity, role description, action allowlist, and durable session record. It is not a separate model, process, or concurrent worker. The shared runtime is the same for all 100 roles. Only the user's selected provider is contacted, and only when the user launches or continues an agent task.

Actions: `inspect`, `tree`, `patch`, `verify`, `finish`, `blocked`. The model returns a single JSON object. LoopSieve never executes model-authored shell commands. Source edits require explicit permission and an exact unique match in an existing workspace file. Verification uses the project's preconfigured checks and requires separate permission. If any file was edited, `finish` requires a passing verification outcome since the last edit. An agent cannot grant itself new permissions.

SQLite stores sessions, messages with bounded size, task state, and compact event records. It does not store model weights or API keys. A time/step budget prevents unlimited model loops. Completed sessions cannot be resumed; paused sessions can be restored from disk.

The orchestration API accepts a dependency DAG and validates missing references and cycles. It intentionally executes sequentially. Parallel isolated worktrees, actual inter-agent model handoffs, checkpointed file rollback and fine-grained interruption of already executing verification commands remain outstanding.

## Providers

- Ollama: `POST /api/chat`, JSON mode, loopback only.
- OpenAI-compatible: optional explicit HTTPS endpoint and API key from an environment variable. Credential content is not included in a saved session.
- Claude CLI: opt-in `claude -p --tools ''` planner bridge, untested on a live installation here.
- Codex CLI: opt-in read-only `codex exec` planner bridge, untested on a live installation here.

These providers are not interchangeable entitlements. A paid provider subscription is not guaranteed to include API access or unrestricted automation.

## Observability

`agent inspect` and Studio show externally observable actions, short tool results, status, evidence and event times. The model's private chain of thought is neither accessible nor claimed.

## Known hazards

- The semantic quality of model decisions is not validated by an external benchmark.
- Prompt injection in source files can still influence recommendations. The action allowlist and approval gates limit execution consequences, but do not guarantee model alignment.
- User-approved project checks are subprocesses and are not an OS sandbox. Do not approve check execution from an untrusted repository.
- Cancel and pause prevent applying a model decision returned *after* cancellation. An in-progress file edit or subprocess may still complete in a narrow race window.
- Studio provider attachments are in memory. After a Studio restart, use the CLI to rebind and resume persisted sessions.
