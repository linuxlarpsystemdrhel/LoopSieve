# Hugging Face integration

## What is real

`HuggingFaceClient` uses the official public API:

- `GET /api/models` with `search`, `author`, `pipeline_tag`, `filter`, `sort`,
  `direction`, `limit` and `cursor`.
- `GET /api/models/{id}` for metadata.
- `GET /api/models/{id}/tree/{revision}` for file inventory.
- Cursor pagination is read from the response `Link: ... rel="next"` header.

The normalizer extracts model id, author, pipeline category, tags, downloads,
likes, last-modified time, license, safetensors parameter count, formats,
gating and library. No remote model code is executed and no weights are
downloaded by the explorer.

## Categories

Text Generation, Code, Vision-Language, Embeddings, Text-to-Image,
Image-to-Image, Text-to-Video, Image-to-Video, Text-to-3D, Image-to-3D,
Speech-to-Text, Text-to-Speech, Audio, Segmentation, Detection, Other.

## Token handling

A token is optional and read from `HF_TOKEN`/`HUGGING_FACE_HUB_TOKEN` or passed
explicitly. Tokens are never written to the metadata result or the team journal.
For provider keys, use `loopsieve secrets set --name provider:<id>`.

## Commands

```bash
loopsieve hf search "SmolLM2" --limit 10
loopsieve hf info HuggingFaceTB/SmolLM2-1.7B-Instruct
loopsieve hf files HuggingFaceTB/SmolLM2-1.7B-Instruct
```

## Verified test

The suite uses a local fake API to verify cursor pagination and normalization.
A separate live metadata request returned real models during development, but
the live result is not part of the automated test suite.
