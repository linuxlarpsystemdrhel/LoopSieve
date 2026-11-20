"""Provider health monitoring and safe, resumable fallback.

The monitor never hides a failure and never switches model in the middle of a
tool call. A fallback is attempted only before a decision is executed; the
agent runtime keeps the session journal, checkpoints and verified evidence.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .providers import ProviderError

# Stable states used by the terminal UI and health API.
HEALTH_STATES = {
    'READY', 'UNVERIFIED', 'SERVER_UNAVAILABLE', 'AUTH_REQUIRED', 'RATE_LIMIT',
    'TIMEOUT', 'OVERLOADED', 'MISCONFIGURED', 'MODEL_ERROR', 'REQUIRES_DEPENDENCY',
    'REQUIRES_DOWNLOAD', 'DEGRADED',
}


def classify_error(exc: BaseException) -> dict[str, Any]:
    """Classify provider failures without relying on brittle provider-specific text."""
    if isinstance(exc, ProviderError):
        kind = exc.kind
        retryable = exc.retryable
    else:
        text = str(exc).lower()
        kind = ('TIMEOUT' if 'timed out' in text or 'timeout' in text else
                'AUTH_REQUIRED' if 'unauthorized' in text or '401' in text or 'auth' in text else
                'RATE_LIMIT' if 'rate limit' in text or '429' in text or 'quota' in text else
                'OVERLOADED' if 'overload' in text or '503' in text else
                'CONNECTION' if 'connection' in text or 'refused' in text or 'unreachable' in text else
                'PROVIDER_ERROR')
        retryable = kind in {'TIMEOUT', 'RATE_LIMIT', 'OVERLOADED', 'CONNECTION', 'PROVIDER_ERROR'}
    state = {
        'AUTH': 'AUTH_REQUIRED', 'AUTH_REQUIRED': 'AUTH_REQUIRED',
        'RATE_LIMIT': 'RATE_LIMIT', 'TIMEOUT': 'TIMEOUT', 'OVERLOADED': 'OVERLOADED',
        'MISSING_EXECUTABLE': 'REQUIRES_DEPENDENCY', 'MODEL': 'REQUIRES_DOWNLOAD',
        'MODEL_ERROR': 'MODEL_ERROR', 'MISCONFIGURED': 'MISCONFIGURED',
        'HTTP': 'SERVER_UNAVAILABLE', 'CONNECTION': 'SERVER_UNAVAILABLE',
        'PROVIDER_ERROR': 'DEGRADED',
    }.get(kind, 'DEGRADED')
    return {'state': state, 'kind': kind, 'retryable': retryable,
            'reason': f'{type(exc).__name__}: {str(exc)[:500]}'}


class ProviderHealthMonitor:
    """Persist health observations locally; no network call happens on construction."""
    def __init__(self, state_path: Path | None = None):
        self.path = Path(state_path) if state_path else None
        self._lock = threading.RLock()
        self._data: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if not self.path or not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding='utf-8'))
            if isinstance(raw, dict):
                self._data = {str(k): v for k, v in raw.items() if isinstance(v, dict)}
        except (OSError, ValueError):
            self._data = {}

    def _save(self) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix='.health-', suffix='.json', dir=self.path.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as handle:
                json.dump(self._data, handle, indent=2, sort_keys=True)
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def record(self, provider_id: str, state: str, *, kind: str = 'UNKNOWN',
               reason: str = '', latency_ms: float | None = None,
               model: str | None = None) -> dict:
        if state not in HEALTH_STATES:
            state = 'DEGRADED'
        item = {'provider_id': str(provider_id)[:120], 'state': state, 'kind': kind,
                'reason': str(reason)[:700], 'latency_ms': latency_ms,
                'model': model, 'checked_at': time.time()}
        with self._lock:
            self._data[item['provider_id']] = item
            self._save()
        return item

    def record_failure(self, provider_id: str, exc: BaseException) -> dict:
        info = classify_error(exc)
        return self.record(provider_id, info['state'], kind=info['kind'],
                           reason=info['reason'], model=getattr(exc, 'model', None))

    def probe(self, provider: Any) -> dict:
        started = time.monotonic()
        pid = getattr(provider, 'provider_id', type(provider).__name__)
        try:
            if hasattr(provider, 'probe'):
                value = provider.probe()
                if not isinstance(value, dict):
                    value = {'state': 'UNVERIFIED', 'reason': 'probe returned non-object'}
            else:
                value = {'state': 'UNVERIFIED', 'kind': 'NO_PROBE',
                         'reason': 'provider does not expose a non-invasive probe'}
        except Exception as exc:  # health checks must not crash the UI
            value = classify_error(exc)
        value.setdefault('provider_id', pid)
        value.setdefault('state', 'UNVERIFIED')
        value['latency_ms'] = round((time.monotonic() - started) * 1000, 2)
        value['checked_at'] = time.time()
        with self._lock:
            self._data[str(value['provider_id'])] = value
            self._save()
        return value

    def health(self, provider_id: str) -> dict:
        with self._lock:
            return dict(self._data.get(provider_id, {'state': 'UNVERIFIED', 'reason': 'no observation'}))

    def status(self) -> dict:
        with self._lock:
            return {'providers': {k: dict(v) for k, v in self._data.items()},
                    'states': {k: v.get('state') for k, v in self._data.items()}}

    def clear(self) -> None:
        with self._lock:
            self._data = {}
            self._save()


@dataclass
class ProviderSlot:
    provider: Any
    label: str = ''
    model: str | None = None
    enabled: bool = True

    @property
    def provider_id(self) -> str:
        return getattr(self.provider, 'provider_id', self.label or type(self.provider).__name__)


class FallbackProvider:
    """Try a configured provider chain in order and record every failed attempt.

    The active provider is persisted so a later run starts from the last known
    working backend. Disabling fallback makes the primary provider fail closed.
    """
    thread_safe = True

    def __init__(self, slots: list[ProviderSlot], monitor: ProviderHealthMonitor | None = None,
                 state_path: Path | None = None, enabled: bool = True):
        if not slots:
            raise ValueError('fallback chain needs at least one provider')
        self.slots = slots
        self.state_path = Path(state_path) if state_path else None
        # Keep health observations separate from the fallback index; sharing one
        # JSON file would make each writer erase the other's state.
        health_path = (self.state_path.with_suffix('.health.json') if self.state_path else None)
        self.monitor = monitor or ProviderHealthMonitor(health_path)
        self.enabled = bool(enabled)
        self._lock = threading.RLock()
        self.active_index = 0
        self.switches = 0
        self.last_error: str | None = None
        self._load_state()

    def _load_state(self) -> None:
        if not self.state_path or not self.state_path.exists():
            return
        try:
            raw = json.loads(self.state_path.read_text(encoding='utf-8'))
            if isinstance(raw, dict):
                self.active_index = min(max(int(raw.get('active_index', 0)), 0), len(self.slots) - 1)
                self.switches = int(raw.get('switches', 0))
                self.last_error = raw.get('last_error')
        except (OSError, ValueError, TypeError):
            pass

    def _save_state(self) -> None:
        if not self.state_path:
            return
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix='.fallback-', suffix='.json', dir=self.state_path.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as handle:
                json.dump({'active_index': self.active_index, 'switches': self.switches,
                           'enabled': self.enabled, 'last_error': self.last_error,
                           'saved_at': time.time()}, handle, indent=2, sort_keys=True)
            os.replace(tmp, self.state_path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    @property
    def provider_id(self) -> str:
        return 'fallback:' + ','.join(slot.provider_id for slot in self.slots)

    @property
    def active(self) -> ProviderSlot:
        return self.slots[self.active_index]

    def status(self) -> dict:
        with self._lock:
            return {'enabled': self.enabled, 'active_index': self.active_index,
                    'active': self.active.provider_id, 'switches': self.switches,
                    'last_error': self.last_error,
                    'providers': [{'index': i, 'label': slot.label or slot.provider_id,
                                   'model': slot.model, 'enabled': slot.enabled,
                                   'health': self.monitor.health(slot.provider_id)}
                                  for i, slot in enumerate(self.slots)]}

    def probe(self) -> dict:
        """Probe only the active provider; never cascade a health check."""
        slot = self.active
        if hasattr(slot.provider, 'probe'):
            value = slot.provider.probe()
        else:
            value = {'state': 'UNVERIFIED', 'kind': 'NO_PROBE',
                     'reason': 'active provider has no non-invasive probe'}
        value = dict(value)
        value.setdefault('provider_id', slot.provider_id)
        value['fallback_active'] = slot.provider_id
        return value

    def enable(self) -> dict:
        self.enabled = True; self._save_state(); return self.status()

    def disable(self) -> dict:
        self.enabled = False; self._save_state(); return self.status()

    def reset(self) -> dict:
        with self._lock:
            self.active_index = 0; self.switches = 0; self.last_error = None; self._save_state()
        return self.status()

    def complete(self, messages: list[dict], agent: dict) -> dict:
        errors: list[dict] = []
        start = self.active_index if self.enabled else 0
        stop = len(self.slots) if self.enabled else 1
        for index in range(start, stop):
            slot = self.slots[index]
            if not slot.enabled:
                continue
            try:
                value = slot.provider.complete(messages, agent)
                with self._lock:
                    if index != self.active_index:
                        self.switches += 1
                    self.active_index = index
                    self.last_error = None
                    self._save_state()
                self.monitor.record(slot.provider_id, 'READY', kind='OK', model=slot.model)
                return value
            except Exception as exc:
                info = classify_error(exc)
                self.monitor.record(slot.provider_id, info['state'], kind=info['kind'],
                                    reason=info['reason'], model=slot.model)
                errors.append({'provider': slot.provider_id, 'index': index, **info})
                if not self.enabled:
                    break
        with self._lock:
            self.last_error = errors[-1]['reason'] if errors else 'no enabled provider'
            self._save_state()
        detail = '; '.join(f"{e['provider']}={e['state']}" for e in errors) or 'no enabled provider'
        raise ProviderError(f'all fallback providers failed: {detail}',
                            kind='FALLBACK_EXHAUSTED', retryable=False)


class FallbackController:
    """Thin stateful controller used by CLI/TUI commands."""
    def __init__(self, provider: FallbackProvider):
        self.provider = provider

    def enable(self) -> dict: return self.provider.enable()
    def disable(self) -> dict: return self.provider.disable()
    def reset(self) -> dict: return self.provider.reset()
    def status(self) -> dict: return self.provider.status()

    def switch(self, index: int) -> dict:
        if not 0 <= index < len(self.provider.slots):
            raise ValueError('fallback index out of range')
        if not self.provider.slots[index].enabled:
            raise ValueError('selected provider is disabled')
        with self.provider._lock:
            self.provider.active_index = index
            self.provider._save_state()
        return self.provider.status()
