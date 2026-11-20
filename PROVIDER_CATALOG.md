# Provider catalog

## Current coverage

The built-in catalog contains **44 real provider profiles** covering cloud,
local and OpenAI-compatible endpoints. The long-term target requested by the
brief is about 300 profiles; **that target is not claimed**.

Current status counts are visible with:

```bash
loopsieve providers
```

Profiles are metadata only. `CONFIGURED_NOT_TESTED` and `LOCAL_SERVER` are not
synonyms for verified. Only a successful real health probe may change a profile
to `VERIFIED`; no paid provider request was made during this release.

## Supported integration path

- `openai` protocol → `CompatibleProvider` with a full `/chat/completions`
  endpoint and optional key from `SecretStore`.
- `ollama` protocol → local `OllamaProvider`.
- `claude`/`codex` → optional official CLI planner adapters.
- Non-OpenAI protocols (Anthropic, Gemini, Bedrock, Cohere, Replicate,
  Cloudflare, etc.) are **not silently treated as OpenAI**. They require a
  dedicated protocol adapter and currently return `UNSUPPORTED_BACKEND`.

## Custom provider

```python
from loopsieve.provider_catalog import ProviderCatalog
catalog = ProviderCatalog()
catalog.add_custom({
  "id": "my-lab",
  "name": "My Lab",
  "base_url": "http://127.0.0.1:9999/v1",
  "protocol": "openai",
  "modalities": ["text"]
})
```

Base URLs with embedded credentials are rejected. Custom profiles are not stored
with secrets.

## Secure keys

`SecretStore` uses Windows DPAPI when available, then keyring, then a 0o600
local file with an explicit warning. Catalog JSON never contains an API key.
Keys are addressed as `provider:<provider-id>`.
