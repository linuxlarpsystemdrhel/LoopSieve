# Benchmarks

For the latest release-preparation measurements, see the [current report](docs/benchmarks.md). The data below documents the earlier 0.6.0 baseline.

## Diagnostic-context benchmark

`benchmarks/fixtures/stable-repeat.json`:

- 8 iterations, 7 repeated failures.
- Raw diagnostic characters: 19,144.
- Emitted characters: 2,911.
- Diagnostic reduction: 84.79%.

This is diagnostic text volume, **not** token, dollar or subscription savings.

## What is not measured

- Live model tokens/sec, first-token latency or VRAM peak.
- 15 simultaneously loaded models.
- 1,500 live agent inference calls.
- Coding accuracy across models.
- Computer-control performance.

## How to run the real arena

```bash
loopsieve arena --provider ollama --model llama3.2:3b
loopsieve modelteam parallel "Review the repository" --provider ollama --model llama3.2:3b --model llama3.1:8b
```

The arena and team paths use real runtime/checks when a real provider is supplied;
they do not invent a model result when no provider is available.
