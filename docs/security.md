# Security model

The default tool API is read-only. It resolves paths against the current workspace, blocks obvious secret filenames and limits the size and number of files scanned. It does not run arbitrary shell strings or install external packages.

Claude Code hook installation is an explicit action in a trusted repository. Once installed, project-specific check commands can run test/build code. Review `.loopsieve.json` before enabling hooks in an untrusted checkout. `shell=False` prevents shell interpolation but does not make arbitrary executables safe.

`PostToolBatch` payloads are treated as untrusted input. The hook should never be used as a mechanism for bypassing subscription quotas or obtaining credentials from Claude sessions.

`loopsieve web` binds to 127.0.0.1, provides only GET endpoints, and returns aggregate local metadata. Do not reverse-proxy it to the internet. There is currently no user authentication, which is acceptable only for a local loopback read-only view.

The task queue uses atomic writes and a short-lived cross-process lock for state transitions. Running tasks are read-only, but cancellation cannot preempt a tool that is already executing. OS process isolation or container sandboxing is not implemented; do not treat this tool as a security sandbox for untrusted code.

Report vulnerabilities privately using the process in `SECURITY.md`.
