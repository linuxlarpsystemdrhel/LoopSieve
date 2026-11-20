# Tools and skills

## Counts in the delivered tree

| Kind | Count | What it means |
|---|---:|---|
| Local read-only tools | 63 | Actual Python functions registered in `toolkit.REGISTRY`. |
| Agent roles | 100 | JSON role manifests loaded on demand. |
| Skill manifests | 50 | Deterministic workflow manifests. |
| Plugin/CLI adapters | 50 | Detection/contract manifests; not 50 installed services. |
| Technology records | 50 | Source-indexed implementation notes. |
| Model catalog entries | 11 | Seed compatibility metadata, no weights. |
| Provider profiles | 44 | Metadata; no paid request was made. |
| Quantization methods | 14 | GGUF/IQ and external-method metadata. |
| Capability registry entries | 382 | Tools + agents + skills + plugins + technology + models + providers + quantization. |

## Capability registry

`CapabilityRegistry` exposes compact descriptors and a deterministic router:

```python
from loopsieve.capability import CapabilityRegistry
registry = Capabili
