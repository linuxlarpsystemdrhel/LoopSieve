"""Provider catalog with explicit verification states and secure key lookup.

The catalog is metadata. A profile is not marked VERIFIED until a real health
probe succeeds. API keys are read from the environment or SecretStore; they are
never written into catalog JSON.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .providers import CLIProvider, CompatibleProvider, OllamaProvider, ProviderError
from .secure_store import SecretStore

CATALOG_PATH = Path(__file__).resolve().parent / 'data' / 'providers' / 'catalog.json'


@dataclass(frozen=True)
class ProviderProfile:
    id: str
    name: str
    base_url: str
    protocol: str = 'openai'
    auth: str = 'bearer'
    models_endpoint: str | None = '/models'
    modalities: tuple[str, ...] = ('text',)
    streaming: bool = True
    tool_calling: bool = True
    status: str = 'CONFIGURED_NOT_TESTED'
    source: str = 'public provider documentation'
    license: str = 'provider terms'
    verified_models: tuple[str, ...] = ()
    notes: str = ''
    custom: bool = False

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> 'ProviderProfile':
        if not isinstance(value, dict) or not value.get('id'):
            raise ValueError('provider profile needs an id')
        return cls(
            id=str(value['id']), name=str(value.get('name') or value['id']),
            base_url=str(value.get('base_url') or ''), protocol=str(value.get('protocol', 'openai')),
            auth=str(value.get('auth', 'bearer')), models_endpoint=value.get('models_endpoint'),
            modalities=tuple(value.get('modalities', ['text'])),
            streaming=bool(value.get('streaming', True)), tool_calling=bool(value.get('tool_calling', True)),
            status=str(value.get('status', 'CONFIGURED_NOT_TESTED')),
            source=str(value.get('source', 'public provider documentation')),
            license=str(value.get('license', 'provider terms')),
            verified_models=tuple(value.get('verified_models', []) or []),
            notes=str(value.get('notes', '')), custom=bool(value.get('custom', False)))

    def as_dict(self) -> dict:
        value = asdict(self)
        value['modalities'] = list(self.modalities)
        value['verified_models'] = list(self.verified_models)
        return value


def load_catalog(path: Path | str | None = None) -> list[ProviderProfile]:
    source = Path(path) if path else CATALOG_PATH
    raw = json.loads(source.read_text(encoding='utf-8'))
    items = raw.get('providers', raw) if isinstance(raw, dict) else raw
    if not isinstance(items, list):
        raise ValueError('provider catalog must contain a providers array')
    return [ProviderProfile.from_dict(x) for x in items if isinstance(x, dict)]


class ProviderCatalog:
    def __init__(self, catalog: list[ProviderProfile] | None = None, store: SecretStore | None = None):
        self.providers = catalog if catalog is not None else load_catalog()
        self.store = store or SecretStore()
        self._custom: dict[str, ProviderProfile] = {}

    def get(self, provider_id: str) -> ProviderProfile:
        if provider_id in self._custom:
            return self._custom[provider_id]
        for profile in self.providers:
            if profile.id == provider_id:
                return profile
        raise KeyError(f'unknown provider: {provider_id}')

    def search(self, query: str = '', *, modality: str | None = None,
               status: str | None = None, limit: int = 50) -> list[ProviderProfile]:
        terms = set(re.findall(r'[a-z0-9+]+', query.lower()))
        rows = list(self.providers) + list(self._custom.values())
        if modality:
            rows = [x for x in rows if modality in x.modalities]
        if status:
            rows = [x for x in rows if x.status == status]
        if terms:
            rows = [x for x in rows if terms & set(re.findall(r'[a-z0-9+]+', f'{x.id} {x.name} {x.protocol}'.lower()))]
        rows.sort(key=lambda x: (x.status != 'VERIFIED', x.name.lower()))
        return rows[:max(1, min(int(limit), 300))]

    def status(self) -> dict:
        counts: dict[str, int] = {}
        for x in list(self.providers) + list(self._custom.values()):
            counts[x.status] = counts.get(x.status, 0) + 1
        return {'count': len(self.providers) + len(self._custom), 'target_count': 300,
                'status_counts': counts,
                'verified': counts.get('VERIFIED', 0),
                'custom': len(self._custom),
                'policy': 'Only a real probe may change status to VERIFIED.'}

    def add_custom(self, value: dict[str, Any]) -> ProviderProfile:
        profile = ProviderProfile.from_dict({**value, 'custom': True,
                                             'status': value.get('status', 'CONFIGURED_NOT_TESTED')})
        if not re.fullmatch(r'[a-zA-Z0-9_.-]{1,80}', profile.id):
            raise ValueError('custom provider id must be a safe identifier')
        parsed = urlparse(profile.base_url)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname:
            raise ValueError('custom provider needs an http(s) base URL')
        if parsed.username or parsed.password:
            raise ValueError('base URL may not contain credentials')
        self._custom[profile.id] = profile
        return profile

    def key_name(self, provider_id: str) -> str:
        return 'provider:' + provider_id

    def resolve_key(self, provider_id: str) -> str | None:
        env_name = 'LOOPSIEVE_' + re.sub(r'[^A-Z0-9]', '_', provider_id.upper()) + '_KEY'
        return os.environ.get(env_name) or self.store.get(self.key_name(provider_id))

    def store_key(self, provider_id: str, secret: str) -> dict:
        self.get(provider_id)
        return self.store.set(self.key_name(provider_id), secret)

    def build(self, provider_id: str, model: str, *, endpoint: str | None = None,
              timeout: int = 90) -> Any:
        profile = self.get(provider_id)
        base = endpoint or profile.base_url
        if profile.protocol == 'ollama':
            return OllamaProvider(model=model, endpoint=base.rstrip('/') + '/api/chat', timeout=timeout)
        if profile.protocol in ('claude', 'codex'):
            return CLIProvider(profile.protocol, timeout=timeout)
        if profile.protocol == 'openai':
            chat = base.rstrip('/')
            if not chat.endswith('/chat/completions'):
                chat += '/chat/completions'
            return CompatibleProvider(model=model, endpoint=chat,
                                      api_key=self.resolve_key(provider_id), timeout=timeout)
        # Non-OpenAI protocols must not be silently treated as OpenAI. A dedicated
        # adapter is required before this can be called a real integration.
        raise ProviderError(f'{profile.protocol} requires a dedicated protocol adapter (NOT_IMPLEMENTED)',
                            kind='UNSUPPORTED_BACKEND', retryable=False)

    def probe(self, provider_id: str, *, timeout: int = 10) -> dict:
        profile = self.get(provider_id)
        try:
            provider = self.build(provider_id, model='probe', timeout=timeout)
            value = provider.probe() if hasattr(provider, 'probe') else {'state': 'UNVERIFIED'}
        except Exception as exc:
            value = {'state': 'BROKEN' if isinstance(exc, ProviderError) else 'UNSUPPORTED',
                     'reason': f'{type(exc).__name__}: {exc}', 'provider': provider_id}
        value['profile_status_before'] = profile.status
        return value


def import_litellm_profiles() -> list[ProviderProfile]:
    """Optional discovery of installed LiteLLM model providers; no data invented."""
    try:
        import litellm  # type: ignore
    except Exception:
        return []
    names = getattr(litellm, 'provider_list', None) or getattr(litellm, 'LITELLM_PROVIDERS', None) or []
    rows = []
    for name in names if isinstance(names, (list, tuple)) else []:
        text = str(name).strip()
        if not text:
            continue
        rows.append(ProviderProfile(id='litellm-' + re.sub(r'[^a-z0-9-]', '-', text.lower()),
                                    name=text, base_url='', protocol='openai',
                                    status='CONFIGURED_NOT_TESTED',
                                    source='installed litellm provider list',
                                    notes='Base URL and auth require user configuration.'))
    return rows
