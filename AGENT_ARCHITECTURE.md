# Agent architecture

The native runtime provides persistent role-bound Ollama sessions and sequential teams with per-task models. The architecture below describes the Python model-slot and dialogue implementation. [Rust architecture](ARCHITECTURE.md#native-agent-runtime) · [Implementation status](docs/IMPLEMENTATION_STATUS.md).

## Layers

1. **Role manifest** — 100 JSON definitions with instructions, permissions,
   allowed tools, budgets, success/failure criteria and escalation rules.
2. **Logical agent** — a role bound to one model slot. It has its own ID, state,
   queue history, context limit, counters and dialogue identity.
3. **Model slot** — one provider/model binding. Up to 15 slots per team.
4. **Shared runtime** — `AgentRuntime` executes bounded JSON decisions and stores
   sessions/evidence/checkpoints in SQLite.
5. **Team dialogue** — typed messages (`TASK`, `PROPOSAL`, `REVIEW`, `QUESTION`,
   `ANSWER`, `ARTIFACT`, `TOOL_RESULT`, `BLOCKED`, `VERIFIED`) stored in SQLite.
6. **Permission engine** — deny-by-default grants at the execution boundary.

## Capacity

- Up to **15 models** per `ModelTeam`.
- Up to **100 logical agents per model**.
- Maximum address space: **1,500 logical agents**.
- These are not 1,500 model processes or 1,500 copies of weights.

`ModelTeam.status()` reports `registered_agents`, per-state counts,
`model_loaded`, `inference_calls`, queued/executing/completed/failed tasks and an
explicit note that registered agents are logical roles.

## States

`READY`, `QUEUED`, `EXECUTING`, `COMPLETED`, `FAILED`, `BLOCKED`, `DISABLED`.

A task is `QUEUED` before execution, then `EXECUTING`, then terminal. The agent
returns to `READY` after a completed task and records `completed`/`inference_calls`.

## Execution

The team uses the existing bounded runtime. It does not give a model an
unrestricted shell. A model returns one JSON action; the runtime validates the
action, role permission, path boundary, write/check opt-ins and verification
evidence before applying it.

## Experiments

`run_parallel_solutions()` runs the same read-only task on multiple model slots.
It returns per-model results and a winner only when a task actually completed.
It does not merge edits or claim that an untested architecture is better.
