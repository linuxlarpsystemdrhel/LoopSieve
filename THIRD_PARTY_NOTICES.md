# Third-party notices

LoopSieve 0.6.0 does not bundle third-party source code or model weights in the
Git repository or source ZIP.

## Runtime dependencies

The core runtime uses the Python standard library only. Optional dependencies
are installed by the user and remain under their own licenses:

| Package | Use | License | Notes |
|---|---|---|---|
| Textual | Optional TUI | MIT | Not installed by default; `pip install '.[tui]'` |
| psutil | Optional memory/process telemetry | BSD-3-Clause | Not required; falls back to standard-library detection |
| PyYAML | Optional YAML validation in one local tool | MIT | Not required; the tool reports `REQUIRES_DEPENDENCY` |

## External models and providers

The model catalog in `src/loopsieve/data/models/catalog.json` contains metadata
and links to user-selected models. Model weights are **not** distributed with
LoopSieve. Each upstream model has its own license and acceptable-use terms. The
catalog records a declared license per entry, but LoopSieve does not grant any
right to redistribute those weights.

Examples include Apache-2.0, MIT, Llama Community licenses, Gemma terms and the
DeepSeek Model License. Hugging Face metadata is fetched through the public API;
model files are not redistributed. Review the upstream license before downloading or
redistributing a model. A model's license can change; verify it at the source.

## Competitor projects

The competitor research documents mention projects such as OpenClaw, Hermes,
OpenCode, Codex, Gemini CLI, OpenHands, Cline, Goose, Aider and Kilo Code. No
source code from those projects is bundled. They are referenced for product and
architecture research only. See `docs/COMPETITOR_RESEARCH.md` and
`docs/COMPETITOR_SNAPSHOT.json` for the recorded inspection metadata.

## Assets

The pixel-art mascot in `src/loopsieve/mascot.py` is original Unicode artwork
created for this project. The optional glTF mascot under `src/loopsieve/assets/`
is original project artwork. It is not a copy of a third-party character.

## Security and license reporting

If you believe a third-party component has been included without proper
attribution, open a private security advisory or contact the maintainers. Include
the file, upstream project and license evidence.


## Research-only upstream clones

The following repositories were shallow-cloned for architecture and license
review; no source was copied into LoopSieve:

- anomalyco/opencode (MIT)
- openclaw/openclaw (MIT)
- cline/cline (Apache-2.0)
- obra/superpowers (MIT)
- NousResearch/hermes-agent (MIT)
- addyosmani/agent-skills (MIT)
- Aider-AI/aider (Apache-2.0)
- pi0/pi-mono (MIT)
- openai/codex (Apache-2.0)
- google-gemini/gemini-cli (Apache-2.0)

Exact commit SHAs and the studied components are in
`UPSTREAM_INTEGRATIONS.md`. The OpenAI Codex, Hermes and Gemini CLI checkouts hit
Windows path-length limits; this is recorded as a partial checkout, not a
completed full-source audit.

## Optional local inference runtime

Optional inference uses an independently installed llama.cpp runtime under its
MIT license. User-supplied models retain their respective licenses.
[llama.cpp license](https://github.com/ggml-org/llama.cpp/blob/master/LICENSE).
