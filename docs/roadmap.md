# Roadmap

## Established core

- Local verification CLI, bounded diagnostics and JSON state.
- Successful check reuse from explicit complete, deterministic inputs.
- Source-aware failure identity for Python and location-based fallback.
- Project-local Claude Code hook and a portable terminal workbench.

## Experimental

- Local explanations on Linux with a user-supplied GGUF and explicit client configuration.
- Provider adapters, model teams and agent orchestration. Consult the provider catalog for individual verification status.
- Confidence in the diagnostic model is limited to controlled failure cases.

## Planned

1. Evaluate new, repeated and changing failures on larger public projects with independent quality review.
2. Repeat CPU and CUDA measurements on additional machines and add per-process VRAM sampling during inference.
3. Extend structured diagnostic parsing to more compiler and linter output formats.
4. Validate concurrent verification and improve process containment on Windows.
5. Validate GitHub-hosted CI and artifact preparation after the owner authorizes publication.
