# Launch notes

The project is an engineering preview. Introduce it as a local verification tool with an expanding developer console, not as an autonomous replacement for existing coding agents.

A practical first announcement:

> LoopSieve checks code after your coding agent edits it and returns only the useful new diagnostics. The tool runs locally, has no required model API, and integrates with Claude Code through its documented PostToolBatch hook.
>
> The 0.2 preview also includes a local toolbox, role definitions, and browser and terminal views. The focus is keeping verification trustworthy. If you have an annoying repeat-error loop, try the reproducible fixtures and share an example.

A good public demonstration should start with the original false-cache and false-duplicate regressions. Show that those tests now pass, then run the stable repeated-diagnostic benchmark with its actual output.

Do not claim a percentage reduction in Claude plan limits from synthetic text benchmarks. Include the 0.2 limitations in the announcement. Prefer real bug reports and contributors over star-count marketing.
