"""Claude Code integration status and installation helpers.

LoopSieve uses Claude Code's official project hook mechanism. It does not read
Claude credentials, bypass limits or launch a competing chat interface.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .install import MARKER, install_hook, uninstall_hook


def _load(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def status(root: Path) -> dict:
    root = Path(root).resolve()
    settings = root / '.claude' / 'settings.json'
    hooks_file = root / 'hooks' / 'hooks.json'
    plugin = root / '.claude-plugin' / 'plugin.json'
    data = _load(settings)
    entries = data.get('hooks', {}).get('PostToolBatch', []) if isinstance(data.get('hooks'), dict) else []
    installed = any(isinstance(e, dict) and e.get('description') == MARKER for e in entries)
    hook_manifest = _load(hooks_file)
    plugin_manifest = _load(plugin)
    mcp = [p for p in (root / '.mcp.json', root / '.claude' / 'mcp.json') if p.is_file()]
    return {
        'workspace': str(root),
        'claude_code': {
            'settings_exists': settings.is_file(),
            'hook_installed': installed,
            'hook_marker': MARKER,
            'settings_path': str(settings),
            'plugin_manifest': str(plugin) if plugin.is_file() else None,
            'plugin_name': plugin_manifest.get('name'),
            'hooks_manifest': str(hooks_file) if hooks_file.is_file() else None,
            'hooks_manifest_events': sorted(hook_manifest.get('hooks', {}).keys()) if isinstance(hook_manifest.get('hooks'), dict) else [],
            'mcp_configs': [str(p) for p in mcp],
            'status': 'READY' if installed else 'NOT_INSTALLED',
        },
        'policy': 'Official project hooks only; no credential extraction and no provider-limit bypass.',
    }


def install(root: Path, timeout_seconds: int = 180) -> dict:
    path = install_hook(root, timeout_seconds=timeout_seconds)
    return {'status': 'INSTALLED', 'settings_path': str(path), 'timeout_seconds': timeout_seconds,
            'hook_event': 'PostToolBatch', 'next': 'Restart Claude Code or reload project hooks.'}


def uninstall(root: Path) -> dict:
    path = uninstall_hook(root)
    return {'status': 'REMOVED', 'settings_path': str(path)}


def hook_payload_example() -> dict[str, Any]:
    return {'cwd': '/project', 'hook_event_name': 'PostToolBatch',
            'tool_calls': [{'tool_name': 'Edit', 'tool_input': {'file_path': 'src/a.py'}}]}
