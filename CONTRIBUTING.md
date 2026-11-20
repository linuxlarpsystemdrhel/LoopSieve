# Contributing

LoopSieve is intentionally small. A contribution should make verification more correct, more measurable, or easier to install.

## Development setup

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python -m unittest discover -s tests -v
```

On Windows PowerShell:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e .
python -m unittest discover -s tests -v
```

## What makes a good pull request

A good PR normally has all of these:

- one clear behavior change;
- tests for the behavior;
- no network dependency in the core runtime;
- no unsupported Claude authentication or session-token handling;
- bounded failure output;
- documentation for any new configuration;
- benchmark evidence for performance or context-reduction claims.

## Fingerprinting changes

Fingerprint changes need adversarial tests. A fingerprint that suppresses a materially new error is worse than one that emits a small amount of duplicate text.

Include at least one case that should deduplicate and one similar case that must remain distinct.

## New language support

Keep auto-detection conservative. Prefer a fast check that is already standard in the project. Do not silently install dependencies or package managers.

## New agent integrations

Use documented public extension points. Do not intercept credentials, patch proprietary binaries, or depend on leaked code.

## Claims in documentation

If a PR changes a number in the README, include the benchmark command and fixture that produced it.

## Local model and release checks

The regular suite uses local HTTP fixtures and does not download weights. Run
`python tools/check_textual.py` after installing `.[tui]` to mount the terminal
workbench without an interactive terminal. Reproduce the optional live-model
experiments using the [benchmark report](docs/benchmarks.md).

Run `actionlint .github/workflows/*.yml` before changing GitHub Actions. Run
`python -m build` and `python -m twine check dist/*` to validate distribution
metadata and contents. Keep model weights in `.local-models/` and use synthetic
diagnostics in any benchmark artifacts intended for sharing.
