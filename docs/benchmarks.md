# Benchmarks

## Offline verification

The included fixtures measure diagnostic volume and suppression without running a model.

| Fixture | Raw characters | Emitted characters | Suppressed logs |
|---|---:|---:|---:|
| Stable repeated diagnostic | 19,144 | 2,911 | 7 |
| Adversarial identity | 9,574 | 9,574 | 0 |
| Repeated failure at different locations | 31,312 | 31,312 | 0 |

```bash
loopsieve benchmark benchmarks/fixtures/stable-repeat.json --json
loopsieve benchmark benchmarks/fixtures/adversarial-identity.json --json
loopsieve benchmark benchmarks/fixtures/repeated-failure.json --json
```

The Python fingerprint profile measures 100 diagnostic locations in one source file. On the original test host, median time went from 264.64 to 4.70 ms with a matching digest. This is a targeted microbenchmark. [Before](../experiments/diagnostics-before.json), [after](../experiments/diagnostics-after.json).

## Local inference

Supply a GGUF and a JSON config as described in the [local model guide](llm-integration.md). The Linux harness compares raw logs, prepared diagnostic excerpts, and excerpts with warm prompt reuse. It measures TTFT, full latency and throughput with CPU or CUDA. Use a private output directory for any benchmark file containing generated advice or machine-specific data.

```bash
python -m experiments.benchmark_local_llm \
  --weights .local-models/your-model.gguf --llm-config .private/llm.local.json \
  --device cpu --output .private/model-benchmark.json
```

Use `--device cuda` for a CUDA-enabled runtime. Figures depend on the selected model, device and runtime configuration.
