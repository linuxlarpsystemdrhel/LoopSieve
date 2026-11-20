# Local tool registry

The built-in tool module contains 63 callable operations for safe file inspection, SHA-256, content search, regular expression matching, Python AST parsing, packaging metadata, Git inspection, release readiness, and security checks.

```bash
loopsieve tools list
loopsieve tools run python_functions --args '{"path":"main.py"}'
loopsieve tools run git_status
```

Tool arguments are JSON objects. Every tool is declared with a `workspace:read` permission scope and a bounded operation. Paths cannot escape the workspace, and known sensitive filenames are blocked. No arbitrary command string, shell operator or plugin-supplied Python code is executed by this registry.

The complete list is available from `loopsieve tools list`. Unit tests smoke-test every registered implementation. Some tools are optional because they depend on software such as Git, PyYAML or psutil. Missing dependencies produce an explicit structured status.

The tool API does not offer filesystem writes. Code editing and full agent execution require additional authorization and implementation.
