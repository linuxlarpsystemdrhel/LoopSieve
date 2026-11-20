"""Local model catalog, hardware-aware fit decisions and verified downloads.

The manager never downloads a model or starts an inference server implicitly.
Every status is either measured, computed from declared metadata, or explicitly
marked as unverified.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .hardware import HardwareProfile, detect_hardware
from .quantization import QUANTIZATIONS, estimate_memory, get_quantization, recommend_quantization

CATALOG_PATH = Path(__file__).resolve().parent / 'data' / 'models' / 'catalog.json'
SUPPORTED_ARCHITECTURES = {'llama', 'phi', 'mistral', 'gemma', 'deepseek'}
STATUS_READY = 'READY'
STATUS_HYBRID = 'HYBRID'
STATUS_CPU = 'CPU ONLY'
STATUS_MEMORY = 'INSUFFICIENT MEMORY'
STATUS_ARCH = 'UNSUPPORTED ARCHITECTURE'
STATUS_DOWNLOAD = 'REQUIRES DOWNLOAD'
STATUS_UNVERIFIED = 'NOT VERIFIED'

# Public compatibility vocabulary requested by the local-model workflow.
COMPAT_READY_GPU = 'READY_GPU'
COMPAT_READY_HYBRID = 'READY_HYBRID'
COMPAT_CPU_ONLY = 'CPU_ONLY'
COMPAT_NEEDS_DOWNLOAD = 'NEEDS_DOWNLOAD'
COMPAT_UNSUPPORTED_BACKEND = 'UNSUPPORTED_BACKEND'
COMPAT_GATED = 'GATED'
COMPAT_LICENSE_RESTRICTED = 'LICENSE_RESTRICTED'
COMPAT_INSUFFICIENT_MEMORY = 'INSUFFICIENT_MEMORY'
COMPAT_UNKNOWN = 'UNKNOWN'


def compatibility_label(value: dict) -> str:
    status = value.get('status')
    if value.get('gated'):
        return COMPAT_GATED
    if value.get('license_restricted'):
        return COMPAT_LICENSE_RESTRICTED
    if status == STATUS_READY:
        return COMPAT_READY_GPU
    if status == STATUS_HYBRID:
        return COMPAT_READY_HYBRID
    if status == STATUS_CPU:
        return COMPAT_CPU_ONLY
    if status == STATUS_DOWNLOAD:
        return COMPAT_NEEDS_DOWNLOAD
    if status == STATUS_MEMORY:
        return COMPAT_INSUFFICIENT_MEMORY
    if status == STATUS_ARCH:
        return COMPAT_UNSUPPORTED_BACKEND
    return COMPAT_UNKNOWN


@dataclass(frozen=True)
class ModelSpec:
    id: str
    name: str
    provider: str = 'ollama'
    architecture: str = 'llama'
    params_b: float = 0.0
    active_params_b: float | None = None
    moe: bool = False
    layers: int = 32
    kv_heads: int = 8
    head_dim: int = 128
    context_tokens: int = 8192
    quantizations: tuple[str, ...] = ('q4_k_m', 'q5_k_m', 'q8_0')
    license: str = 'UNKNOWN'
    download: str | None = None
    download_url: str | None = None
    sha256: str | None = None
    tags: tuple[str, ...] = ()
    notes: str = ''
    installed: bool = False

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> 'ModelSpec':
        if not isinstance(value, dict) or not value.get('id'):
            raise ValueError('model entry needs an id')
        qs = value.get('quantizations') or ['q4_k_m', 'q5_k_m', 'q8_0']
        return cls(
            id=str(value['id']), name=str(value.get('name') or value['id']),
            provider=str(value.get('provider', 'ollama')),
            architecture=str(value.get('architecture', 'llama')),
            params_b=float(value.get('params_b', 0) or 0),
            active_params_b=(float(value['active_params_b']) if value.get('active_params_b') else None),
            moe=bool(value.get('moe', False)),
            layers=int(value.get('layers', 32) or 32),
            kv_heads=int(value.get('kv_heads', 8) or 8),
            head_dim=int(value.get('head_dim', 128) or 128),
            context_tokens=int(value.get('context_tokens', 8192) or 8192),
            quantizations=tuple(str(x).lower() for x in qs),
            license=str(value.get('license', 'UNKNOWN')),
            download=value.get('download'), download_url=value.get('download_url'),
            sha256=value.get('sha256'), tags=tuple(value.get('tags', []) or []),
            notes=str(value.get('notes', '')), installed=bool(value.get('installed', False)),
        )

    def as_dict(self) -> dict:
        value = asdict(self)
        value['quantizations'] = list(self.quantizations)
        value['tags'] = list(self.tags)
        return value


def load_catalog(path: Path | str | None = None) -> list[ModelSpec]:
    source = Path(path) if path else CATALOG_PATH
    raw = json.loads(source.read_text(encoding='utf-8'))
    values = raw.get('models', raw) if isinstance(raw, dict) else raw
    if not isinstance(values, list):
        raise ValueError('model catalog must contain a models array')
    return [ModelSpec.from_dict(x) for x in values if isinstance(x, dict)]


def _best_quantization(model: ModelSpec, budget_mb: int | None, context_tokens: int | None) -> str:
    qs = [q for q in model.quantizations if q in QUANTIZATIONS]
    if not qs:
        return 'q4_k_m'
    if budget_mb and budget_mb > 0:
        recommended = recommend_quantization(model.params_b, budget_mb, context_tokens=context_tokens or model.context_tokens,
                                             layers=model.layers, kv_heads=model.kv_heads, head_dim=model.head_dim)
        if recommended.get('selected') in qs:
            return recommended['selected']
    # Prefer Q4_K_M as a balanced default when no budget is supplied.
    return 'q4_k_m' if 'q4_k_m' in qs else qs[0]


def fit_status(model: ModelSpec, hardware: HardwareProfile | None = None, *,
               quantization: str | None = None, context_tokens: int | None = None,
               installed: bool | None = None, backend: str | None = None,
               strict_gpu: bool = False, gated: bool | str = False,
               license_restricted: bool = False) -> dict[str, Any]:
    """Return one of the explicit user-facing fit statuses plus an estimate."""
    hardware = hardware or detect_hardware()
    q = quantization or _best_quantization(model, None, context_tokens)
    if q not in QUANTIZATIONS:
        return {'status': STATUS_UNVERIFIED, 'model': model.id, 'reason': f'unknown quantization {q}',
                'estimate': None, 'requires_download': not bool(installed)}
    if model.architecture.lower() not in SUPPORTED_ARCHITECTURES:
        return {'status': STATUS_ARCH, 'model': model.id, 'quantization': q,
                'reason': f'{model.architecture} is not in the verified architecture list',
                'estimate': None, 'requires_download': not bool(installed)}
    if model.params_b <= 0:
        return {'status': STATUS_UNVERIFIED, 'model': model.id, 'quantization': q,
                'reason': 'model parameter count is unknown', 'estimate': None,
                'requires_download': not bool(installed)}
    estimate = estimate_memory(model.params_b, q, context_tokens=context_tokens or model.context_tokens,
                               layers=model.layers, kv_heads=model.kv_heads, head_dim=model.head_dim)
    total = estimate['total_mb']
    is_installed = bool(model.installed if installed is None else installed)
    if not is_installed:
        value = {'status': STATUS_DOWNLOAD, 'model': model.id, 'quantization': q,
                 'estimate': estimate, 'fit': _memory_fit(total, hardware),
                 'requires_download': True, 'reason': 'model is not installed in the selected backend',
                 'gated': gated, 'license_restricted': license_restricted,
                 'strict_gpu': strict_gpu, 'backend': backend or model.provider}
        value['compatibility'] = compatibility_label(value)
        return value
    fit = _memory_fit(total, hardware)
    if strict_gpu and hardware.total_vram_mb is None:
        fit = STATUS_MEMORY
    if fit == STATUS_MEMORY:
        value = {'status': STATUS_MEMORY, 'model': model.id, 'quantization': q,
                 'estimate': estimate, 'fit': fit, 'requires_download': False,
                 'reason': f'estimated {total:.0f} MiB exceeds available VRAM and RAM',
                 'gated': gated, 'license_restricted': license_restricted,
                 'strict_gpu': strict_gpu, 'backend': backend or model.provider}
        value['compatibility'] = compatibility_label(value)
        return value
    value = {'status': fit, 'model': model.id, 'quantization': q, 'estimate': estimate,
             'fit': fit, 'requires_download': False, 'gated': gated,
             'license_restricted': license_restricted, 'strict_gpu': strict_gpu,
             'backend': backend or model.provider}
    value['compatibility'] = compatibility_label(value)
    return value


def _memory_fit(total_mb: float, hardware: HardwareProfile) -> str:
    vram = hardware.total_vram_mb
    free_vram = hardware.free_vram_mb if hardware.free_vram_mb is not None else vram
    ram_free = hardware.ram_free_mb
    ram_total = hardware.ram_total_mb
    if vram is None:
        if ram_free is not None:
            return STATUS_CPU if total_mb <= ram_free else STATUS_MEMORY
        if ram_total is not None:
            return STATUS_CPU if total_mb <= ram_total else STATUS_MEMORY
        return STATUS_UNVERIFIED
    if total_mb <= (free_vram or vram):
        return STATUS_READY
    if ram_free is not None and total_mb <= vram + ram_free:
        return STATUS_HYBRID
    if ram_total is not None and total_mb <= vram + ram_total:
        return STATUS_HYBRID
    return STATUS_MEMORY


class ModelManager:
    """Hardware-aware catalog operations used by CLI and TUI."""
    def __init__(self, catalog: list[ModelSpec] | None = None, hardware: HardwareProfile | None = None):
        self.models = catalog if catalog is not None else load_catalog()
        self.hardware = hardware or detect_hardware()

    def find(self, model_id: str) -> ModelSpec:
        wanted = str(model_id or '').strip()
        for model in self.models:
            if model.id == wanted or model.id.lower() == wanted.lower():
                return model
        raise KeyError(f'unknown model: {model_id}')

    def status(self, installed: list[str] | None = None) -> dict[str, Any]:
        installed_set = {x.lower() for x in (installed or [])}
        rows = []
        for model in self.models:
            is_installed = model.installed or model.id.lower() in installed_set or model.id.split(':')[0].lower() in installed_set
            value = fit_status(model, self.hardware, installed=is_installed)
            value['name'] = model.name
            value['provider'] = model.provider
            value['license'] = model.license
            value['download'] = model.download
            value['tags'] = list(model.tags)
            rows.append(value)
        return {'hardware': self.hardware.as_dict(), 'models': rows,
                'policy': 'Estimates are not runtime measurements. No model was downloaded or started.'}

    def memory(self, model_id: str, quantization: str | None = None, context_tokens: int | None = None) -> dict:
        model = self.find(model_id)
        q = quantization or _best_quantization(model, None, context_tokens)
        estimate = estimate_memory(model.params_b, q, context_tokens=context_tokens or model.context_tokens,
                                   layers=model.layers, kv_heads=model.kv_heads, head_dim=model.head_dim)
        return {'model': model.id, 'name': model.name, 'quantization': q, 'estimate': estimate,
                'hardware': self.hardware.as_dict(), 'fit': fit_status(model, self.hardware, quantization=q, context_tokens=context_tokens)}

    def select(self, model_id: str, quantization: str | None = None, *,
               provider: str | None = None, installed: bool = False,
               context_tokens: int | None = None) -> dict:
        model = self.find(model_id)
        q = quantization or _best_quantization(model, None, context_tokens)
        fit = fit_status(model, self.hardware, quantization=q, context_tokens=context_tokens,
                         installed=installed, backend=provider or model.provider)
        return {'selected': model.id, 'name': model.name, 'quantization': q,
                'provider': provider or model.provider, 'fit': fit,
                'compatibility': fit.get('compatibility'), 'license': model.license,
                'download': model.download, 'download_url': model.download_url,
                'sha256': model.sha256, 'notes': model.notes}

    def auto(self, task: str, *, installed: list[str] | None = None,
             max_mb: int | None = None, prefer_tags: tuple[str, ...] = ('coding',)) -> dict:
        installed_set = {x.lower() for x in (installed or [])}
        candidates = []
        for model in self.models:
            is_installed = model.installed or model.id.lower() in installed_set or model.id.split(':')[0].lower() in installed_set
            fit = fit_status(model, self.hardware, installed=is_installed)
            if fit['status'] in (STATUS_MEMORY, STATUS_ARCH):
                continue
            tags = set(model.tags)
            score = len(tags & set(prefer_tags)) * 4 + (2 if is_installed else 0)
            if 'coding' in task.lower() and 'coding' in tags:
                score += 2
            candidates.append((score, model.params_b, model, fit))
        if not candidates:
            return {'selected': None, 'status': 'NO_FIT',
                    'reason': 'no catalog model fits the detected memory or architecture',
                    'hardware': self.hardware.as_dict()}
        candidates.sort(key=lambda x: (x[0], -x[1]), reverse=True)
        score, _, model, fit = candidates[0]
        return {'selected': model.id, 'name': model.name, 'fit': fit, 'score': score,
                'quantization': fit.get('quantization'), 'hardware': self.hardware.as_dict()}

    def benchmark(self, model_id: str, provider: Any = None, *, timeout: int = 60) -> dict:
        """Run a real provider call if a provider is supplied; otherwise say UNVERIFIED."""
        model = self.find(model_id)
        if provider is None:
            return {'status': 'UNVERIFIED', 'model': model.id,
                    'reason': 'no provider supplied; LoopSieve does not start a model automatically',
                    'measured': False}
        agent = {'name': 'Model Benchmark', 'instructions': 'Return one JSON object only.'}
        started = time.monotonic()
        try:
            decision = provider.complete([{'role': 'user',
                                           'content': 'Return exactly {"action":"tree"} as one JSON object.'}], agent)
            elapsed = round((time.monotonic() - started) * 1000, 2)
            return {'status': 'MEASURED', 'model': model.id, 'latency_ms': elapsed,
                    'decision': decision, 'measured': True,
                    'note': 'One local call; not a coding-quality benchmark.'}
        except Exception as exc:
            return {'status': 'FAILED', 'model': model.id, 'error': f'{type(exc).__name__}: {exc}',
                    'measured': True, 'latency_ms': round((time.monotonic() - started) * 1000, 2)}


class ModelDownloader:
    """Checksum- and license-gated download. Never starts a server."""
    def __init__(self, root: Path | str, max_bytes: int = 20 * 1024 ** 3):
        self.root = Path(root)
        self.max_bytes = max_bytes

    def verify(self, path: Path | str, sha256: str) -> dict:
        p = Path(path)
        if not p.is_file():
            return {'status': 'MISSING', 'path': str(p)}
        digest = hashlib.sha256()
        with p.open('rb') as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b''):
                digest.update(chunk)
        actual = digest.hexdigest()
        expected = str(sha256).lower()
        return {'status': 'PASS' if actual == expected else 'FAIL', 'path': str(p),
                'sha256': actual, 'expected': expected, 'size': p.stat().st_size}

    def download(self, url: str, destination: Path | str, *, sha256: str | None = None,
                 license: str | None = None, accept_license: bool = False,
                 approve: bool = False, max_bytes: int | None = None,
                 allow_http_loopback: bool = False, resume: bool = True,
                 progress: Any = None) -> dict:
        parsed = urlparse(url)
        loopback = parsed.scheme == 'http' and parsed.hostname in ('127.0.0.1', 'localhost', '::1')
        if (parsed.scheme != 'https' and not (allow_http_loopback and loopback)) or not parsed.hostname:
            raise ValueError('model downloads require an explicit HTTPS URL')
        if parsed.username or parsed.password or parsed.fragment:
            raise ValueError('download URL may not contain credentials or fragments')
        if not approve:
            raise PermissionError('explicit approval is required before downloading model weights')
        if not sha256 or len(str(sha256)) != 64:
            raise ValueError('a 64-character SHA-256 checksum is required before download')
        if not license or license == 'UNKNOWN':
            raise ValueError('a declared model license is required before download')
        if not accept_license:
            raise PermissionError('explicit license acceptance is required before download')
        limit = int(max_bytes or self.max_bytes)
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            existing = self.verify(target, sha256)
            if existing['status'] == 'PASS':
                return {**existing, 'status': 'PASS', 'resumed': False, 'license': license, 'source': url}
            raise FileExistsError(f'destination already exists: {target}')
        partial = target.with_suffix(target.suffix + '.part')
        offset = 0
        digest = hashlib.sha256()
        if resume and partial.is_file():
            offset = partial.stat().st_size
            if offset > limit:
                raise ValueError('partial download exceeds the size limit')
            with partial.open('rb') as existing:
                for chunk in iter(lambda: existing.read(1024 * 1024), b''):
                    digest.update(chunk)
        headers = {'User-Agent': 'LoopSieve-model-downloader'}
        if offset:
            headers['Range'] = f'bytes={offset}-'
        request = Request(url, headers=headers)
        size = offset
        resumed = bool(offset)
        try:
            with urlopen(request, timeout=60) as response:
                if response.status not in (200, 206):
                    raise ValueError(f'download returned HTTP {response.status}')
                # A server that ignores Range restarts the file from byte zero.
                restart = offset and response.status == 200
                mode = 'wb' if restart else ('ab' if offset else 'wb')
                if restart:
                    offset = 0
                    size = 0
                    digest = hashlib.sha256()
                    resumed = False
                with partial.open(mode) as out:
                    for chunk in iter(lambda: response.read(1024 * 1024), b''):
                        size += len(chunk)
                        if size > limit:
                            raise ValueError(f'download exceeds {limit} bytes')
                        digest.update(chunk)
                        out.write(chunk)
                        if progress:
                            try:
                                progress(size, limit)
                            except Exception:
                                pass
            actual = digest.hexdigest()
            if actual != str(sha256).lower():
                raise ValueError(f'checksum mismatch: expected {sha256}, got {actual}')
            os.replace(partial, target)
            return {'status': 'PASS', 'path': str(target), 'sha256': actual, 'size': size,
                    'license': license, 'source': url, 'resumed': resumed,
                    'partial_retained': False}
        except Exception:
            if partial.exists():
                # Keep the .part file so a later call can resume; cleanup is explicit.
                pass
            raise

    def cleanup_partial(self, destination: Path | str) -> dict:
        p = Path(destination)
        partial = p.with_suffix(p.suffix + '.part')
        if partial.exists():
            size = partial.stat().st_size
            partial.unlink()
            return {'removed': True, 'path': str(partial), 'bytes': size}
        return {'removed': False, 'path': str(partial), 'bytes': 0}

