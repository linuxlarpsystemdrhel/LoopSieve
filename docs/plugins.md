# Plugin adapters

The 50 built-in adapter records target known developer CLIs, including Python, Git, Node, Go, Rust, C/C++, Docker, Kubernetes, language formatters and several build tools.

Each adapter discovers a binary and may run a fixed version/health command. Adapters do not install software, connect to private provider APIs, or start background servers.

```bash
loopsieve plugins list
loopsieve plugins probe plugin-git
```

`REQUIRES_DEPENDENCY` means the binary is not installed. `AVAILABLE_NOT_PROBED` means it was found but has not been invoked. `AVAILABLE` means the fixed probe completed successfully. `PROBE_FAILED` is a real error.

These are **50 discovery/health adapters**, not 50 complete third-party software integrations. MCP lifecycle management, remote authentication, rollback and provider-wide actions are not implemented. Do not trust third-party manifests or execute arbitrary external commands without review.
