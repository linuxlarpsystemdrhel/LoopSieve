# Security policy

## Supported versions

Security fixes are applied to the latest released minor version during the pre-1.0 period.

## Threat model

LoopSieve runs local verification commands. A repository configuration can therefore request execution of programs available on the user's machine.

Treat `.loopsieve.json` with the same level of trust as `package.json` scripts, a Makefile, CI configuration, or a test runner configuration.

## Runtime protections

The current runtime:

- executes argument arrays with `shell=False`;
- applies per-command timeouts and bounded output;
- keeps the model in a bounded JSON action space;
- requires explicit `--allow-writes` and `--allow-checks` opt-ins;
- blocks path traversal, sensitive files, `.git`, dependency and cache directories;
- creates a pre-write checkpoint before every patch;
- records a hash-chained local evidence ledger;
- does not read or store Claude OAuth credentials;
- does not read or store Claude session tokens;
- does not run commands received from hook JSON;
- stores fingerprints and summaries outside the repository by default.

## Permission and secret safety

- `PermissionEngine` is deny-by-default across `READ_ONLY`, `WORKSPACE_WRITE`,
  `TEST_EXECUTION`, `LOCAL_PROCESS`, `PACKAGE_INSTALL`, `NETWORK_ACCESS`,
  `COMPUTER_CONTROL` and `SENSITIVE_OPERATION`.
- Grants are session-scoped with optional TTL and an audit trail. The runtime
  checks the execution boundary, not only the prompt.
- API keys are stored with Windows DPAPI when available, then keyring, then a
  0o600 local file with an explicit warning. Catalog JSON never contains keys.
- Hugging Face and provider catalog operations are metadata-only. Tokens are not
  written into results or team journals.
- Resumable downloads retain `.part` files; checksum, license acceptance and
  explicit approval are still required. `cleanup_partial()` removes only the
  managed partial file.

## Model and provider safety

- Provider health probes are non-invasive where the provider supports one; a probe is not a model-quality test.
- Fallback is attempted only before a decision is executed. The active provider index and every failed attempt are persisted.
- Disabling fallback makes the primary provider fail closed. There is no hidden retry that silently changes the model.
- Model downloads require HTTPS (loopback HTTP is allowed only for explicit local tests), a declared license, explicit license acceptance, explicit approval and a matching SHA-256 checksum.
- The source distribution excludes model weights. The launcher can verify a user-supplied GGUF against a provided SHA-256 before use.
- Memory estimates are computed from declared model metadata. They are not measurements and may be wrong for a specific runtime build.
- Quantization metadata does not imply that a model can be re-quantized without quality loss. Conversion must use the backend's official tool and be benchmarked afterwards.

These controls do not make an untrusted check command safe. A configured executable can still read files, access the network, or modify the machine according to the user's operating-system permissions.

### Experimental local diagnostics

The diagnostic client accepts numeric loopback HTTP, bypasses proxy settings, rejects redirects,
caps input and response sizes, and prints advisory text. The launcher accepts an explicit GGUF and can verify a supplied SHA-256. Trust the local server process and keep it
bound to loopback. Check output may contain secrets, filesystem paths or traceback
lines. The local server can retain the active prompt in memory. The original
verification context and agent journals also remain local and may contain sensitive
information.

The [local audit and release evaluation](docs/release-readiness.md) records examined
boundaries and remaining limitations.

## Reporting a vulnerability

Please use GitHub's private security advisory flow when the repository is public. Do not publish a working exploit in a normal issue before a fix is available.

A useful report includes:

- affected version;
- operating system;
- minimal reproduction;
- expected boundary;
- actual behavior;
- impact.
