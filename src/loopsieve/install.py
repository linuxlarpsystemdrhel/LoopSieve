from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any


MARKER = "loopsieve hook"


def _settings_path(root: Path) -> Path:
    return root / ".claude" / "settings.json"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"cannot parse {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _cli_path() -> str:
    found = shutil.which("loopsieve")
    if found:
        return found
    # Useful while developing from a venv where the console script is not on PATH.
    return sys.executable


def install_hook(root: Path, timeout_seconds: int = 180) -> Path:
    path = _settings_path(root)
    data = _load_json(path)
    hooks = data.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError("settings.json hooks must be an object")
    entries = hooks.setdefault("PostToolBatch", [])
    if not isinstance(entries, list):
        raise ValueError("PostToolBatch hooks must be an array")

    command = _cli_path()
    if Path(command).resolve() == Path(sys.executable).resolve() and shutil.which("loopsieve") is None:
        args = ["-m", "loopsieve.cli", "hook"]
    else:
        args = ["hook"]
    for entry in entries:
        if isinstance(entry, dict) and entry.get("description") == MARKER:
            return path
    entries.append(
        {
            "description": MARKER,
            "hooks": [
                {
                    "type": "command",
                    "command": command,
                    "args": args,
                    "timeout": timeout_seconds,
                }
            ],
        }
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path


def uninstall_hook(root: Path) -> Path:
    path = _settings_path(root)
    data = _load_json(path)
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        return path
    entries = hooks.get("PostToolBatch")
    if isinstance(entries, list):
        hooks["PostToolBatch"] = [
            entry for entry in entries if not (isinstance(entry, dict) and entry.get("description") == MARKER)
        ]
        if not hooks["PostToolBatch"]:
            hooks.pop("PostToolBatch", None)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path
