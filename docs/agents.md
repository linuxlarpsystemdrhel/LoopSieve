# Agent catalog

One hundred agent role definitions are included as JSON files in `src/loopsieve/data/agents`. They are intentionally separate from the runtime.

Every manifest includes a unique ID, name, specialization, task keywords, responsibilities, quality gates, safety policy, allowed tools, resource limits, input/output schemas, communication policy, retry policy and an example task. Search uses deterministic keyword matching; it does not invoke a language model.

```bash
loopsieve agents list
loopsieve agents select "debug python test failure"
loopsieve agents show 002-python-engineer
```

A selected role is not a live chatbot. Its tool allowance can be used to execute approved read-only local tasks through `TaskStore`. No API key is loaded; no GPU resources are reserved.

```bash
loopsieve tasks create "inspect Python module" --agent 002-python-engineer --tool python_ast_symbols --args '{"path":"main.py"}'
loopsieve tasks list
loopsieve tasks run TASK_ID
```

Tasks with no executable tool report `BLOCKED`. Results and errors are persisted atomically. Tasks are not concurrently dispatched, and there is no cross-process distributed lock in this preview. An external provider adapter and multi-worker scheduler will need their own documented security model before being added.
