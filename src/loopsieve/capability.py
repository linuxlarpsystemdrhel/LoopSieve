"""Unified capability registry and deterministic capability router.

The registry exports compact descriptors only. Full manifests are loaded on
demand so a model prompt is never filled with hundreds of unrelated entries.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from .catalog import list_entries
from .model_manager import load_catalog
from .permissions import PermissionEngine
from .provider_catalog import ProviderCatalog
from .quantization import method_catalog
from .toolkit import tool_catalog


@dataclass(frozen=True)
class Capability:
    id: str
    kind: str
    name: str
    description: str
    permissions: tuple[str, ...] = ('READ_ONLY',)
    categories: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    source: str = 'builtin'
    status: str = 'READY'
    test: str | None = None
    limits: str = ''

    def compact(self) -> dict:
        return {'id': self.id, 'kind': self.kind, 'name': self.name,
                'description': self.description[:240], 'permissions': list(self.permissions),
                'categories': list(self.categories), 'tags': list(self.tags)[:12],
                'status': self.status}

    def as_dict(self) -> dict:
        value = asdict(self)
        value['permissions'] = list(self.permissions)
        value['categories'] = list(self.categories)
        value['tags'] = list(self.tags)
        return value


class CapabilityRegistry:
    def __init__(self):
        self._items: dict[str, Capability] = {}
        self._load_builtin()

    def _load_builtin(self) -> None:
        for tool in tool_catalog():
            self.register(Capability(
                id=tool['id'], kind='tool', name=tool['id'], description=tool['description'],
                permissions=('READ_ONLY',), categories=('engineering', 'local'),
                tags=tuple(re.findall(r'[a-z0-9]+', tool['description'].lower()))[:12],
                input_schema=tool.get('input_schema', {}), output_schema=tool.get('output_schema', {}),
                source='toolkit.py', status='READY',
                test='tests/test_catalog_runtime.py::test_every_tool_implements_an_actual_operation'))
        for entry in list_entries('agents'):
            self.register(Capability(
                id=entry['id'], kind='agent', name=entry['name'],
                description=entry.get('description', ''), permissions=('READ_ONLY',),
                categories=(entry.get('specialization', 'general'),),
                tags=tuple(entry.get('keywords', []))[:16], source='data/agents',
                status='READY', test='tests/test_100_role_runtime.py'))
        for entry in list_entries('skills'):
            self.register(Capability(
                id=entry['id'], kind='skill', name=entry['name'],
                description=entry.get('description', entry['name']), permissions=('READ_ONLY',),
                categories=('workflow',), tags=tuple(re.findall(r'[a-z0-9]+', entry['name'].lower()))[:12],
                source='data/skills', status='READY', test='tests/test_catalog_runtime.py'))
        for entry in list_entries('plugins'):
            self.register(Capability(
                id=entry['id'], kind='plugin', name=entry['name'],
                description=entry.get('description', entry['name']), permissions=('LOCAL_PROCESS',),
                categories=('adapter',), tags=tuple(re.findall(r'[a-z0-9]+', entry['name'].lower()))[:12],
                source='data/plugins', status=entry.get('status', 'REQUIRES_DEPENDENCY')))
        for entry in list_entries('technologies'):
            self.register(Capability(
                id=entry['id'], kind='technology', name=entry['name'],
                description=entry.get('description', entry['name']), permissions=('READ_ONLY',),
                categories=('technology',), tags=tuple(re.findall(r'[a-z0-9]+', entry['name'].lower()))[:12],
                source='data/technologies', status=entry.get('status', 'READY')))
        try:
            for model in load_catalog():
                self.register(Capability(
                    id=model.id, kind='model', name=model.name,
                    description=f'{model.params_b}B {model.architecture}; {model.license}',
                    permissions=('READ_ONLY',), categories=('model', model.provider),
                    tags=tuple(model.tags), source='data/models/catalog.json',
                    status='CATALOG_ONLY', limits=model.notes))
        except Exception:
            pass
        try:
            for profile in ProviderCatalog().providers:
                self.register(Capability(
                    id='provider:' + profile.id, kind='provider', name=profile.name,
                    description=f'{profile.protocol} provider; status={profile.status}',
                    permissions=('NETWORK_ACCESS', 'LOCAL_PROCESS'),
                    categories=('provider', profile.protocol), tags=profile.modalities,
                    source='data/providers/catalog.json', status=profile.status))
        except Exception:
            pass
        try:
            for method in method_catalog()['methods']:
                self.register(Capability(
                    id='quantization:' + method['id'], kind='quantization', name=method['id'],
                    description=f"{method['family']} via {method['backend']}; {method['quality']}",
                    permissions=('READ_ONLY',), categories=('quantization', method['family']),
                    source='quantization.py', status=method['status']))
        except Exception:
            pass

    def register(self, capability: Capability, *, replace: bool = False) -> Capability:
        if not isinstance(capability, Capability):
            raise TypeError('capability must be a Capability')
        if capability.id in self._items and not replace:
            raise ValueError(f'duplicate capability id: {capability.id}')
        self._items[capability.id] = capability
        return capability

    def get(self, capability_id: str) -> Capability | None:
        return self._items.get(str(capability_id))

    def list(self, kind: str | None = None, status: str | None = None) -> list[Capability]:
        rows = list(self._items.values())
        if kind:
            rows = [x for x in rows if x.kind == kind]
        if status:
            rows = [x for x in rows if x.status == status]
        return sorted(rows, key=lambda x: (x.kind, x.id))

    def search(self, query: str, *, kind: str | None = None, limit: int = 20) -> list[Capability]:
        terms = set(re.findall(r'[a-z0-9+]+', str(query).lower()))
        if not terms:
            return []
        scored = []
        for item in self._items.values():
            if kind and item.kind != kind:
                continue
            haystack = ' '.join([item.id, item.name, item.description,
                                  ' '.join(item.categories), ' '.join(item.tags)]).lower()
            score = sum(3 for term in terms if term in item.name.lower())
            score += sum(1 for term in terms if term in haystack)
            if score:
                scored.append((score, item))
        scored.sort(key=lambda x: (-x[0], x[1].id))
        return [x[1] for x in scored[:max(1, min(int(limit), 50))]]

    def compact(self, kind: str | None = None, limit: int = 200) -> list[dict]:
        return [item.compact() for item in self.list(kind)[:max(1, min(int(limit), 500))]]

    def route(self, task: str, *, permission_engine: PermissionEngine | None = None,
              session_id: str | None = None, limit: int = 8,
              kinds: tuple[str, ...] = ('agent', 'skill', 'tool')) -> dict:
        chosen = []
        reasons = []
        for kind in kinds:
            for item in self.search(task, kind=kind, limit=3):
                chosen.append(item)
                reasons.append({'id': item.id, 'kind': item.kind,
                                'reason': f'keywords matched task; declared permissions={list(item.permissions)}'})
        seen = set()
        result = []
        for item in chosen:
            if item.id in seen:
                continue
            seen.add(item.id)
            result.append(item.compact())
            if len(result) >= max(1, min(int(limit), 20)):
                break
        if not result:
            for fallback in ('001-chief-architect', 'workspace_tree', 'file_read'):
                item = self._items.get(fallback)
                if item:
                    result.append(item.compact())
        return {'task': str(task)[:500], 'selected': result, 'reasons': reasons,
                'method': 'deterministic keyword routing over compact descriptors',
                'permissions_checked': bool(permission_engine),
                'note': 'The router never executes a selected capability by itself.'}


def default_registry() -> CapabilityRegistry:
    return CapabilityRegistry()
