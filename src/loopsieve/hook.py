from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from .config import load_config
from .engine import verify
from .project import find_project_root


EDIT_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")
PATH_KEYS = ("file_path", "path", "notebook_path")


def extract_changed_files(payload: dict[str, Any], root: Path) -> list[Path]:
    files: list[Path] = []
    calls = payload.get("tool_calls", [])
    if not isinstance(calls, list):
        calls = []
    # Claude Code's PostToolUse payload carries a single tool call instead of a batch.
    if not calls and payload.get("tool_name") in EDIT_TOOLS:
        calls = [payload]
    for call in calls:
        if not isinstance(call, dict) or call.get("tool_name") not in EDIT_TOOLS:
            continue
        tool_input = call.get("tool_input", {})
        if not isinstance(tool_input, dict):
            continue
        for key in PATH_KEYS:
            value = tool_input.get(key)
            if isinstance(value, str) and value.strip():
                path = Path(value)
                if not path.is_absolute():
                    path = root / path
                files.append(path)
                break
    return files


def build_hook_response(context: str, event_name: str = 'PostToolBatch') -> dict[str, Any]:
    if not context:
        return {}
    event_name = event_name if event_name in ('PostToolBatch', 'PostToolUse') else 'PostToolBatch'
    return {
        "hookSpecificOutput": {
            "hookEventName": event_name,
            "additionalContext": context,
        }
    }


def run_hook(payload: dict[str, Any]) -> dict[str, Any]:
    event = str(payload.get("hook_event_name", "PostToolBatch"))
    try:
        cwd_value = payload.get("cwd")
        cwd = Path(cwd_value) if isinstance(cwd_value, str) and cwd_value else Path.cwd()
        root = find_project_root(cwd)
        changed = extract_changed_files(payload, root)
        if not changed:
            return {}
        result = verify(root, changed, load_config(root))
        context = result.context
        if result.state_warning:
            context = (context + f"\nLoopSieve: {result.state_warning}").lstrip()
        return build_hook_response(context, event)
    except Exception as exc:
        # A verification helper should never break the coding session itself.
        return build_hook_response(f"LoopSieve could not run local verification: {type(exc).__name__}: {exc}", event)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (ValueError, RecursionError) as exc:
        print(json.dumps(build_hook_response(f"LoopSieve received invalid hook JSON: {exc}")))
        return 0
    if not isinstance(payload, dict):
        print("{}")
        return 0
    print(json.dumps(run_hook(payload), ensure_ascii=False))
    return 0
