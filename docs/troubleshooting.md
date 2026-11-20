# Troubleshooting

**`loopsieve` command missing:** Use `python -m loopsieve`, or check that your Python scripts directory is on PATH.

**No checks selected:** Verify that changed files match the configured `kinds` in `.loopsieve.json`. Use `loopsieve init` to inspect detected checks and edit the config for your repository.

**Checks run again after a PASS:** This is expected. Caching requires explicit `complete_inputs`, `deterministic` and `inputs` fields for each check. Without them, LoopSieve never assumes an old PASS is safe to reuse.

**The same error is not suppressed:** If the error moved without an AST anchor or its context changed, LoopSieve conservatively returns it. This prevents hidden new errors.

**Textual interface unavailable:** Install `loopsieve[tui]` when package access is available. Otherwise the portable TUI remains functional.

**Plugin reports REQUIRES_DEPENDENCY:** Install the external CLI yourself if you intend to use it. LoopSieve does not auto-install third-party software.

**Skill reports PARTIAL:** Review the failed step and provide the required input file or optional local dependency.

**Browser view unavailable:** Run `loopsieve web --port 8765`, then open `http://127.0.0.1:8765`. Check whether another process uses the port. Keep the server local.

**Hook interferes with a repository:** Run `loopsieve uninstall-hook` from the project root. The installer is project-local and reversible.
