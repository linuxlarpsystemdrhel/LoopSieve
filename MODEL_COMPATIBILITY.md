# Model compatibility

## Status vocabulary

| Label | Meaning |
|---|---|
| `READY_GPU` | Estimate fits currently free VRAM. |
| `READY_HYBRID` | Estimate fits VRAM plus host RAM; expect slower tokens/sec. |
| `CPU_ONLY` | No usable GPU detected; estimate fits RAM. |
| `NEEDS_DOWNLOAD` | Metadata exists but the model is not reported as installed. |
| `UNSUPPORTED_BACKEND` | Architecture/protocol is not in the verified list. |
| `GATED` | Hugging Face or provider reports gated access. |
| `LICENSE_RESTRICTED` | License requires explicit review/acceptance. |
| `INSUFFICIENT_MEMORY` | Estimate exceeds available memory. |
| `UNKNOWN` | Required metadata or hardware is missing. |

`ModelManager.select()` exposes both the legacy `status` (`READY`, `HYBRID`,
`CPU ONLY`, etc.) and the public `compatibility` label.

## Estimate formula

```text
weights = params_b * 1000 * bits_per_weight / 8
kv_cache = 2 * layers * kv_heads * head_dim * context * batch * 2 bytes
compute = max(256 MiB, weights * 0.04)
total = weights + kv_cache + compute + runtime_overhead + safety_margin
```

This is an **estimate**, not a measured peak. The estimator does not use only
the GGUF file size. MoE fields (`moe`, `active_params_b`) are accepted in model
metadata; the current estimate uses total weights and declared layer/KV values.

## Example hardware

The current Windows host reported:

- NVIDIA GeForce RTX 5060, 8,151 MiB total VRAM, 6,116 MiB free at probe time.
- 32,712 MiB total RAM, 18,071 MiB free at probe time.
- Python 3.14.7, Windows 11.

Example: a 7.6B model at Q4_K_M with 32K context estimates about 7,655 MiB,
including KV cache, compute buffers, 512 MiB runtime overhead and a safety
margin. That is close to the 8 GB boundary; real runtime measurements must be
taken before claiming it fits.
