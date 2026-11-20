# Configuration

## `.loopsieve.json`

Defines local checks, context limits, deduplication and cache policy. Treat it
like a Makefile or CI config. Checks are local argv and run with your account's privileges.

Each check must be an object. If supplied, its name must be a nonempty string and unique in the configuration. `command` must be a nonempty array of strings. `inputs`, `kinds` and `env_keys` must be arrays of strings. Boolean options use JSON `true` or `false`. Timeouts and output limits use positive integers, with decimal integer strings accepted for existing configurations. Invalid configurations cause `check` and `report` to exit with code 2 and print the affected field.

Cache reuse is opt-in via `complete_inputs` and `deterministic`. Successful executions are cached only after matching pre- and post-check input fingerprints. Prefer absolute executables or `{python}` for cacheable Windows checks. Checks may still run when the local state directory is unavailable, in which case the CLI reports a state warning beside the observed result.

## Environment

- `LOOPSIEVE_STATE_DIR` or `CLAUDE_PLUGIN_DATA` — state directory override.
- `HF_TOKEN` / `HUGGING_FACE_HUB_TOKEN` — optional Hugging Face metadata token.
- `LOOPSIEVE_<PROVIDER>_KEY` — optional provider key; prefer `loopsieve secrets`.
- `LOOPSIEVE_API_KEY` — compatible-provider key environment variable.

## Secrets

```bash
loopsieve secrets set --name provider:openai
loopsieve secrets list
loopsieve secrets delete --name provider:openai
```

Windows uses DPAPI. Non-Windows prefers keyring, then a 0o600 local file with a
warning. Catalog JSON never stores plaintext keys.

## Permissions

Dangerous actions are deny-by-default. Writes, checks, package installs, network
access and computer control require explicit grants at the execution boundary.
