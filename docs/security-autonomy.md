# Autonomous agent security

Default: read-only. User grants `--allow-writes` and `--allow-checks` separately. Actions are decoded from strict JSON, checked against each agent's manifest permissions, checked against session permissions, and performed by a limited local runner.

The agent cannot run an arbitrary shell command, write files outside the workspace, patch sensitive credential paths, create arbitrary executables, install plugins, or access external services through a tool. Source edits use atomic replace and a unique old-text match; the write is rejected when the target is missing, ambiguous or over 1 MiB.

Project verification is a deliberate exception: running a check means running a command defined in `.loopsieve.json`. Such checks are **not OS sandboxed**. Only approve checks in repositories and configurations you trust.

Studio binds to loopback and validates Host, Origin and a random CSRF token before mutation. The HTTP API is not intended to be publicly accessible. It has no remote account and stores no provider credentials. It does not auto-run tasks after a browser refresh.

The SQLite journal bounds message content and redacts common credential assignments. This redaction is not perfect. Do not paste secrets into agent task requests. Exported session capsules include hashes and verified summaries, but no source code or model transcripts.

`loopsieve mcp list` only inspects a local configuration. It never installs, launches or authenticates an MCP server. External adapters are listed without automatically spawning processes.

Unimplemented or incomplete: hardened per-agent OS isolation, file-level write locks across processes, nonblocking cancellation of system test subprocesses, formal proof of complete cache dependencies and model-specific prompt injection defenses.
