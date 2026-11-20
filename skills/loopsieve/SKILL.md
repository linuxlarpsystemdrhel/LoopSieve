---
name: loopsieve
description: Inspect LoopSieve verification status, explain failures, or help configure project checks.
---

Use LoopSieve for deterministic verification before spending another model turn on a failure that local tools can explain.

Useful commands:

- `loopsieve init` to detect checks and create `.loopsieve.json`.
- `loopsieve check <files...>` to run relevant checks directly.
- `loopsieve report` to inspect local run statistics.
- `loopsieve install-hook` to add the project PostToolBatch hook.
- `loopsieve uninstall-hook` to remove that hook.

When LoopSieve reports an unchanged repeated failure, work on the existing failure instead of asking for the same full log again.

Do not claim a fixed token or plan-usage saving based only on LoopSieve's diagnostic-character statistics.
