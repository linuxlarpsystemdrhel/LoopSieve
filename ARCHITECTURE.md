# Architecture

```text
CLI / TUI / Claude Code hook
          |
          v
Capability registry + router + permission engine
          |
          v
ModelTeam (<=15 model slots) ---- TeamStore / dialogue
          |
          v
Logical agents (<=100 per model) -- role manifests
          |
          v
AgentRuntime (bounded JSON actions)
          |
          +--> workspace inspect / tool / search / diff
          +--> exact-match patch + checkpoint
          +--> configured verification
          +--> finish / blocked / restore
          |
          v
SQLite Journal + evidence ledger + artifact store
          |
          v
Generated artifacts, handoff manifest, release gate
```

The terminal is the primary product surface. Studio/WebUI modules remain in the
tree for compatibility but are not the recommended interface. The Claude Code
integration uses official project hooks and does not impersonate or copy Claude
Code internals.

The runtime does not use 1,500 model processes. One provider slot serves its
logical agents through a queue; inactive agents consume no model weights.
