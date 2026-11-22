# Benchmarks

## Current native runtime

The current release `loopsieve` executable was measured with the same method and host as the initial migration baseline below. Each cell is the median of 20 new processes after two discarded warm-up runs. The results cover CLI overhead and exclude model inference.

| Workload | Python time (ms) | Rust time (ms) | Python peak RSS (KiB) | Rust peak RSS (KiB) |
|---|---:|---:|---:|---:|
| CLI `--help` | 76.45 | 1.30 | 30,098 | 5,142 |
| Offline repeated-diagnostic fixture | 79.61 | 10.68 | 30,244 | 7,174 |
| Successful one-command check with fresh state | 76.32 | 4.37 | 30,318 | 7,562 |

```sh
cargo build --workspace --release --locked
python benchmarks/compare_runtime.py --rust target/release/loopsieve --runs 20 --output /tmp/loopsieve-runtime.json
```

[Raw measurements and environment metadata](../benchmarks/rust-runtime.json).

## Rust migration baseline

This is the historical measurement of the verification-only preview.

Each value is the median of 20 measured runs per implementation and workload. The harness discards two warm-up runs and alternates Python and Rust. Every sample starts a new process. The check workload uses fresh local state and runs one `true` subprocess. A small native helper measures elapsed time and the CLI process's peak RSS via Linux `wait4`. Filesystem caches stay warm.

| Workload | Python time (ms) | Rust time (ms) | Python peak RSS (KiB) | Rust peak RSS (KiB) |
|---|---:|---:|---:|---:|
| CLI `--help` | 77.71 | 0.98 | 30,008 | 3,784 |
| Offline repeated-diagnostic fixture | 78.39 | 10.47 | 30,290 | 5,536 |
| Successful one-command check with fresh state | 76.51 | 3.77 | 30,322 | 5,554 |

Host: Arch Linux x86_64, AMD Ryzen 7 7800X3D, Python 3.14.10, Rust 1.100.0. These workloads measure the CLI and its verification overhead on one machine. Longer checks can be dominated by the subprocess, and inference performance is measured separately.

```sh
cargo build --workspace --release --locked
python benchmarks/compare_runtime.py --runs 20 --output /tmp/loopsieve-runtime-baseline.json
```

The harness requires Linux and a C compiler. [Raw measurements and environment metadata](../benchmarks/rust-baseline.json).

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
