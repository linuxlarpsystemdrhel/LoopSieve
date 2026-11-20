"""Lazy, packaged JSON manifest registry."""
from __future__ import annotations

import json
from pathlib import Path

DATA = Path(__file__).resolve().parent / 'data'
CATEGORIES = ('agents', 'plugins', 'skills', 'technologies')


def load(category: str, item_id: str):
    if category not in CATEGORIES: raise ValueError('unknown registry')
    if not item_id or any(c in item_id for c in '/\\.'):
        raise ValueError('invalid manifest id')
    for file in (DATA / category).glob('*.json'):
        obj = json.loads(file.read_text(encoding='utf-8'))
        if obj['id'] == item_id or file.stem == item_id:
            return obj
    raise KeyError(f'unknown {category} ID: {item_id}')


def list_entries(category: str):
    if category not in CATEGORIES: raise ValueError('unknown registry')
    return [json.loads(p.read_text(encoding='utf-8')) for p in sorted((DATA/category).glob('*.json'))]


def validate_catalog():
    from .toolkit import REGISTRY
    counts={}
    for category in CATEGORIES:
        entries=list_entries(category)
        ids=[x['id'] for x in entries]
        if len(ids)!=len(set(ids)):raise ValueError(f'duplicate {category} ids')
        for item in entries:
            if not item.get('name') or not item.get('id'):raise ValueError(f'invalid {category} manifest')
            tool_names = item.get('allowed_tools',[]) if category=='agents' else item.get('tools',[]) if category=='skills' else []
            for tool_name in tool_names:
                if tool_name not in REGISTRY: raise ValueError(f'{category}/{item["id"]} refers to unavailable tool: {tool_name}')
        counts[category]=len(entries)
    return counts
