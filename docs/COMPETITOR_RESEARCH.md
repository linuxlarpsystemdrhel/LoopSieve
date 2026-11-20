# Competitor research: 2026-11-10

This snapshot uses repository metadata from the GitHub API, README views and one inspected source or manifest path per project.
**Important limitation:** complete source archives could not be downloaded into the build container due to restricted network access. Source inspection was remote and limited. Do not use this table as proof of exhaustive code review.

| Project | Stars (snapshot) | License | Inspected file | Opportunity for LoopSieve |
|---|---:|---|---|---|
| [openclaw/openclaw](https://github.com/openclaw/openclaw) | 394,281 | MIT | [src/entry.ts](https://github.com/openclaw/openclaw/blob/3f17d921f6cc1cf03d52054a74ba3a5e885f5c35/src/entry.ts) | Multi-channel complexity, not a narrow verification tool |
| [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) | 262,233 | MIT | [agent/acp_client.py](https://github.com/NousResearch/hermes-agent/blob/7b294065935441225475f813380038ffdf43ff37/agent/acp_client.py) | Large autonomous platform; heavier operational scope |
| [anomalyco/opencode](https://github.com/anomalyco/opencode) | 225,790 | MIT | [packages/core/package.json](https://github.com/anomalyco/opencode/blob/98e4b5343e33aafded479b9ff71c12fd760d9d87/packages/core/package.json) | Mature general coding agent, a direct clone would not differentiate |
| [openai/codex](https://github.com/openai/codex) | 134,667 | Apache-2.0 | [codex-rs/core/src/agent_communication.rs](https://github.com/openai/codex/blob/b32ada5320b043bde03a10edab6b88fc126812b4/codex-rs/core/src/agent_communication.rs) | Official OpenAI product; not LoopSieve equivalent |
| [google-gemini/gemini-cli](https://github.com/google-gemini/gemini-cli) | 108,754 | Apache-2.0 | [packages/core/src/index.ts](https://github.com/google-gemini/gemini-cli/blob/1930f25394c4b6338b64ffdb43083fca41614798/packages/core/src/index.ts) | Product access and user cohort differ |
| [OpenHands/OpenHands](https://github.com/OpenHands/OpenHands) | 93,108 | MIT | [src/index.ts](https://github.com/OpenHands/OpenHands/blob/d64cb8a75ec520dd00b75d98838c80158b255344/src/index.ts) | Operational complexity; broad target |
| [cline/cline](https://github.com/cline/cline) | 71,489 | Apache-2.0 | [apps/cli/README.md](https://github.com/cline/cline/blob/92b9f722a16d2a03c1153e12f9a0e759455f509d/apps/cli/README.md) | Full IDE integration takes significant maintenance |
| [aaif-goose/goose](https://github.com/aaif-goose/goose) | 56,421 | Apache-2.0 | [crates/goose-agent/Cargo.toml](https://github.com/aaif-goose/goose/blob/3cf332836a13e6adb864f4c028309a7e0b0b6d27/crates/goose-agent/Cargo.toml) | Broad general-purpose agent |
| [Aider-AI/aider](https://github.com/Aider-AI/aider) | 50,047 | Apache-2.0 | [aider/repomap.py](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/repomap.py) | Model editing quality untested against LoopSieve |
| [Kilo-Org/kilocode](https://github.com/Kilo-Org/kilocode) | 27,927 | MIT | [packages/core/package.json](https://github.com/Kilo-Org/kilocode/blob/b69e4d64e78d2c1ad18c5273a6f9f482d86adf37/packages/core/package.json) | Broad platform, feature parity impractical in one release |

## Original implementation principle

LoopSieve did not vendor code from the competitors above. Inspirations are high-level patterns only: clear approval boundaries, source-aware context, modular provider adapters, reproducible evidence, and isolation.
No comparative benchmark of autonomous task success has been performed.
README/blob identifiers and commit SHA are stored in `COMPETITOR_SNAPSHOT.json` for reproducibility.

## Product decision

Continue shipping local verification and evidence as the primary value proposition. Avoid head-to-head claims about agent quality without identical models, task fixtures, tool permissions, and repeated trials.
Prefer functionality that can be demonstrated without connecting a paid provider.
