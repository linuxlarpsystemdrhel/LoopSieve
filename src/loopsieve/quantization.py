"""Honest quantization metadata and memory estimation.

LoopSieve does not promise that every model can be re-quantized to every size.
The estimator is deliberately explicit about its assumptions and returns an
``estimate`` (not a guarantee) so the UI can label it as such.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class QuantizationProfile:
    id: str
    bits: float
    label: str
    quality: str
    supported: bool = True
    notes: str = ''

    def as_dict(self) -> dict:
        return asdict(self)


# These are common llama.cpp/Ollama quantization families. Availability depends
# on the backend and on a real GGUF build for the specific architecture.
QUANTIZATIONS: dict[str, QuantizationProfile] = {
    'q8_0': QuantizationProfile('q8_0', 8.5, 'Q8', 'highest', True,
                                'Near-lossless in many coding evaluations; largest file.'),
    'q6_k': QuantizationProfile('q6_k', 6.56, 'Q6', 'very high', True,
                                'Good quality/size compromise when Q8 does not fit.'),
    'q5_k_m': QuantizationProfile('q5_k_m', 5.5, 'Q5', 'high', True,
                                  'Recommended default when memory is tight.'),
    'q4_k_m': QuantizationProfile('q4_k_m', 4.5, 'Q4', 'good', True,
                                  'Common local default; verify coding-task quality.'),
    'q3_k_m': QuantizationProfile('q3_k_m', 3.5, 'Q3', 'degraded', True,
                                  'Use only when Q4 does not fit; benchmark before relying on it.'),
    'q2_k': QuantizationProfile('q2_k', 2.6, 'Q2', 'experimental', True,
                                'Substantial quality risk. Not recommended for autonomous coding.'),
    'q4_k_s': QuantizationProfile('q4_k_s', 4.3, 'Q4_S', 'good', True,
                                  'Smaller Q4 variant; verify quality on the target model.'),
    'q3_k_s': QuantizationProfile('q3_k_s', 3.3, 'Q3_S', 'degraded', True,
                                  'Smaller Q3 variant; benchmark before autonomous use.'),
    'iq4_xs': QuantizationProfile('iq4_xs', 4.25, 'IQ4_XS', 'good', True,
                                  'Importance-matrix 4-bit variant; backend support varies.'),
    'iq3_xs': QuantizationProfile('iq3_xs', 3.3, 'IQ3_XS', 'degraded', True,
                                  'Importance-matrix 3-bit; quality must be measured.'),
    'iq2_m': QuantizationProfile('iq2_m', 2.7, 'IQ2_M', 'experimental', True,
                                 'Low-bit experimental method; not a safe automatic default.'),
    'iq1_m': QuantizationProfile('iq1_m', 1.75, 'IQ1_M', 'experimental', True,
                                 'Very low bit-rate; expect substantial quality loss.'),
}

# Method-level catalog. A method is only marked available when the backend and
# loader are real; this table does not imply that conversion has been run.
METHODS: dict[str, dict[str, Any]] = {
    'q4_k_m': {'family': 'gguf', 'backend': 'llama.cpp/ollama', 'bits': 4.5,
               'quality': 'good', 'status': 'AVAILABLE', 'conversion': 'backend tool required'},
    'q4_k_s': {'family': 'gguf', 'backend': 'llama.cpp/ollama', 'bits': 4.3,
               'quality': 'good', 'status': 'AVAILABLE', 'conversion': 'backend tool required'},
    'q3_k': {'family': 'gguf', 'backend': 'llama.cpp/ollama', 'bits': 3.4,
             'quality': 'degraded', 'status': 'AVAILABLE', 'conversion': 'backend tool required'},
    'q2_k': {'family': 'gguf', 'backend': 'llama.cpp/ollama', 'bits': 2.6,
             'quality': 'experimental', 'status': 'AVAILABLE', 'conversion': 'backend tool required'},
    'iq4_xs': {'family': 'gguf-iq', 'backend': 'llama.cpp', 'bits': 4.25,
               'quality': 'good', 'status': 'AVAILABLE', 'conversion': 'llama.cpp required'},
    'iq3_xs': {'family': 'gguf-iq', 'backend': 'llama.cpp', 'bits': 3.3,
               'quality': 'degraded', 'status': 'AVAILABLE', 'conversion': 'llama.cpp required'},
    'iq2_m': {'family': 'gguf-iq', 'backend': 'llama.cpp', 'bits': 2.7,
              'quality': 'experimental', 'status': 'AVAILABLE', 'conversion': 'llama.cpp required'},
    'iq1_m': {'family': 'gguf-iq', 'backend': 'llama.cpp', 'bits': 1.75,
              'quality': 'experimental', 'status': 'AVAILABLE', 'conversion': 'llama.cpp required'},
    'gptq': {'family': 'gptq', 'backend': 'auto-gptq/vllm', 'bits': 4.0,
             'quality': 'good', 'status': 'CONFIGURED_NOT_TESTED', 'conversion': 'not bundled'},
    'awq': {'family': 'awq', 'backend': 'autoawq/vllm', 'bits': 4.0,
            'quality': 'good', 'status': 'CONFIGURED_NOT_TESTED', 'conversion': 'not bundled'},
    'exl2': {'family': 'exl2', 'backend': 'exllamav2', 'bits': 4.0,
             'quality': 'good', 'status': 'CONFIGURED_NOT_TESTED', 'conversion': 'not bundled'},
    'hqq': {'family': 'hqq', 'backend': 'hqq', 'bits': 4.0,
            'quality': 'good', 'status': 'CONFIGURED_NOT_TESTED', 'conversion': 'not bundled'},
    'aqlm': {'family': 'aqlm', 'backend': 'aqlm', 'bits': 2.0,
             'quality': 'experimental', 'status': 'CONFIGURED_NOT_TESTED', 'conversion': 'not bundled'},
    'vptq': {'family': 'vptq', 'backend': 'vptq', 'bits': 2.0,
             'quality': 'experimental', 'status': 'CONFIGURED_NOT_TESTED', 'conversion': 'not bundled'},
}


def get_quantization(name: str) -> QuantizationProfile:
    key = str(name or '').lower().replace('-', '_')
    if key in QUANTIZATIONS:
        return QUANTIZATIONS[key]
    if key in METHODS:
        method = METHODS[key]
        return QuantizationProfile(key, float(method['bits']), key.upper(),
                                   str(method['quality']), True,
                                   f"{method['family']} via {method['backend']}; {method['conversion']}")
    raise ValueError(f'unsupported quantization: {name}')


def method_catalog() -> dict:
    return {'methods': [dict(id=k, **v) for k, v in sorted(METHODS.items())],
            'note': 'Metadata only. CONFIGURED_NOT_TESTED means no loader was exercised.'}


def estimate_memory(params_b: float, quantization: str = 'q4_k_m', *,
                    context_tokens: int = 8192, layers: int = 32,
                    kv_heads: int = 8, head_dim: int = 128, batch: int = 1,
                    runtime_overhead_mb: int = 512, safety_ratio: float = 0.12) -> dict[str, Any]:
    """Estimate weights, KV cache and buffers in MiB.

    The formula is intentionally conservative and transparent. It does not
    replace measuring RSS/VRAM for a specific runtime build.
    """
    q = get_quantization(quantization)
    if params_b <= 0 or context_tokens <= 0 or layers <= 0 or kv_heads <= 0 or head_dim <= 0:
        raise ValueError('model memory inputs must be positive')
    weights_mb = params_b * 1000.0 * (q.bits / 8.0)
    kv_cache_mb = (2.0 * layers * kv_heads * head_dim * context_tokens * batch * 2.0) / (1024.0 * 1024.0)
    compute_mb = max(256.0, weights_mb * 0.04)
    subtotal = weights_mb + kv_cache_mb + compute_mb + runtime_overhead_mb
    safety_mb = subtotal * max(0.0, min(safety_ratio, 0.5))
    total = subtotal + safety_mb
    return {
        'quantization': q.id, 'label': q.label, 'bits_per_weight': q.bits,
        'weights_mb': round(weights_mb, 1), 'kv_cache_mb': round(kv_cache_mb, 1),
        'compute_buffers_mb': round(compute_mb, 1),
        'runtime_overhead_mb': round(float(runtime_overhead_mb), 1),
        'safety_margin_mb': round(safety_mb, 1), 'total_mb': round(total, 1),
        'assumptions': {'context_tokens': context_tokens, 'layers': layers,
                        'kv_heads': kv_heads, 'head_dim': head_dim,
                        'batch': batch, 'safety_ratio': safety_ratio},
        'quality': q.quality, 'kind': 'ESTIMATE_NOT_MEASUREMENT',
    }


def recommend_quantization(params_b: float, budget_mb: int, **kwargs: Any) -> dict[str, Any]:
    """Pick the highest-quality quantization whose estimate fits the budget."""
    if budget_mb <= 0:
        raise ValueError('budget_mb must be positive')
    candidates = []
    for q in QUANTIZATIONS.values():
        if not q.supported:
            continue
        try:
            estimate = estimate_memory(params_b, q.id, **kwargs)
        except ValueError:
            continue
        candidates.append((estimate['total_mb'], q, estimate))
    candidates.sort(key=lambda x: x[0], reverse=True)
    for total, q, estimate in candidates:
        if total <= budget_mb:
            return {'selected': q.id, 'label': q.label, 'total_mb': total,
                    'quality': q.quality, 'estimate': estimate,
                    'reason': f'{q.label} is the highest-quality supported quantization within {budget_mb} MiB'}
    smallest = min(candidates, key=lambda x: x[0]) if candidates else None
    return {'selected': None, 'reason': f'no supported quantization fits {budget_mb} MiB',
            'smallest': smallest[0] if smallest else None,
            'estimate': smallest[2] if smallest else None}


def recommend_profiles(params_b: float, budget_mb: int, *, backend: str = 'llama.cpp/ollama',
                       context_tokens: int = 8192, layers: int = 32,
                       kv_heads: int = 8, head_dim: int = 128) -> dict:
    """Return Quality First, Balanced, Maximum Compression and Experimental profiles."""
    available = []
    for key in METHODS:
        try:
            estimate = estimate_memory(params_b, key, context_tokens=context_tokens,
                                       layers=layers, kv_heads=kv_heads, head_dim=head_dim)
        except ValueError:
            continue
        if estimate['total_mb'] <= budget_mb:
            available.append((estimate['total_mb'], key, estimate))
    available.sort(key=lambda x: x[0], reverse=True)

    def make(item):
        if not item:
            return None
        total, key, estimate = item
        return {'method': key, 'family': METHODS[key]['family'], 'total_mb': total,
                'quality': METHODS[key]['quality'], 'estimate': estimate,
                'conversion': METHODS[key]['conversion']}

    quality = next((x for x in available if METHODS[x[1]]['quality'] in ('highest', 'very high', 'high', 'good')), None)
    balanced = next((x for x in available if x[1] in ('q5_k_m', 'q4_k_m', 'q4_k_s')), None)
    maximum = available[-1] if available else None
    experimental = next((x for x in available if METHODS[x[1]]['quality'] == 'experimental'), None)
    return {'budget_mb': budget_mb, 'backend': backend,
            'quality_first': make(quality), 'balanced': make(balanced),
            'maximum_compression': make(maximum), 'experimental': make(experimental),
            'policy': 'Profiles are estimates. Low-bit methods require measured quality checks.'}

def validate_quantization_request(params_b: float, quantization: str, *,
                                  backend: str = 'ollama') -> dict[str, Any]:
    """Validate metadata only. Actual conversion requires a real backend command."""
    q = get_quantization(quantization)
    backend = str(backend or '').lower()
    supported_backends = {'ollama', 'llama.cpp', 'llamacpp', 'gguf', 'vllm', 'auto-gptq', 'autoawq', 'exllamav2', 'hqq', 'aqlm', 'vptq'}
    if backend not in supported_backends:
        return {'status': 'UNSUPPORTED_BACKEND', 'quantization': q.id,
                'reason': f'{backend or "unknown"} does not expose a documented quantization path'}
    if not q.supported:
        return {'status': 'UNSUPPORTED_QUANTIZATION', 'quantization': q.id, 'reason': q.notes}
    if params_b <= 0:
        return {'status': 'INVALID_MODEL', 'reason': 'params_b must be positive'}
    return {'status': 'VALIDATED_METADATA', 'quantization': q.id, 'bits': q.bits,
            'quality': q.quality, 'backend': backend,
            'conversion': 'NOT_PERFORMED',
            'note': 'Use the backend official tool and verify checksums/quality after conversion.'}
