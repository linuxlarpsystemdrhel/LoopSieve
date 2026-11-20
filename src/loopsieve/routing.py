"""Task-aware selection of the smallest useful read-only tool set."""
from __future__ import annotations


def route_tools(agent: dict, task: str) -> dict:
    allowed = [str(x) for x in agent.get('allowed_tools', [])]
    text = str(task).lower()
    priorities = []
    for tool in allowed:
        score = 0
        if tool in ('workspace_tree', 'file_read', 'search_text') and any(w in text for w in ('find', 'inspect', 'review', 'read')):
            score += 4
        if tool.startswith('python_') and 'python' in text:
            score += 3
        if tool.startswith('git_') and ('git' in text or 'diff' in text or 'commit' in text):
            score += 3
        if 'test' in text and tool in ('unit_discovery', 'verification_report'):
            score += 3
        if tool in ('secret_pattern_scan', 'workspace_symlinks') and any(w in text for w in ('security', 'secret', 'symlink')):
            score += 4
        if score:
            priorities.append((score, tool))
    priorities.sort(key=lambda x: (-x[0], x[1]))
    tools = [x[1] for x in priorities[:5]]
    if not tools:
        tools = [x for x in ('workspace_tree', 'file_read') if x in allowed][:2]
    return {'agent': agent.get('id'), 'task': str(task)[:300], 'tools': tools,
            'allowed': allowed, 'reason': 'deterministic keyword routing; no tool was executed'}
