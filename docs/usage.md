# Usage

## Verification

`loopsieve init` detects typical checks and writes `.loopsieve.json`. Inspect that file before running checks or installing a hook. Each check has an argv array, working directory, accepted file kinds, a timeout, and an output budget. See [configuration](../CONFIGURATION.md) for the full schema.

```bash
loopsieve check --root . path/to/changed.py
loopsieve report --root . --json
loopsieve demo
```

| `check` exit | Meaning |
|---:|---|
| 0 | All selected results passed or reused a validated successful check |
| 1 | A selected check failed, timed out, could not run, or was blocked |
| 2 | Verification could not be confirmed, no files were supplied, or optional model configuration is invalid |

`check --explain` calls a local model only for failures. Follow the [local model guide](llm-integration.md) and run the example from the checkout. If the state directory is unavailable, the command prints a warning and preserves the check's outcome.

## Terminal workbench and hook

Run `loopsieve tui` to open the workbench. Use `/help` to list commands. The same check engine backs `/verify` and the CLI. Use `loopsieve claude install` to activate the project integration and `loopsieve claude status` to inspect it. Installation may modify project-local Claude settings. Use `loopsieve claude uninstall` to remove the integration.

`loopsieve tools`, `loopsieve providers`, and `loopsieve models` expose local tooling and configuration. Remote provider adapters and credential-dependent commands are optional. See [provider setup](../PROVIDER_CATALOG.md) and [agent runtime](agent-runtime.md).
