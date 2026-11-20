from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import CheckSpec, boolean, positive_int
from .project import detect_checks


@dataclass(frozen=True)
class Config:
    checks: tuple[CheckSpec, ...]
    max_context_chars: int = 9000
    max_diagnostic_lines: int = 36
    include_success_context: bool = True
    deduplicate_failures: bool = True
    state_dir: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": 1,
            "max_context_chars": self.max_context_chars,
            "max_diagnostic_lines": self.max_diagnostic_lines,
            "include_success_context": self.include_success_context,
            "deduplicate_failures": self.deduplicate_failures,
            "checks": [check.as_dict() for check in self.checks],
        }


def default_config(root: Path) -> Config:
    return Config(checks=tuple(detect_checks(root)))


def load_config(root: Path) -> Config:
    path = root / ".loopsieve.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        if not path.is_symlink():
            return default_config(root)
        raise ValueError(
            f"configuration symlink does not point to a file: {path}"
        ) from None
    except (OSError, ValueError, RecursionError) as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError(".loopsieve.json must contain a JSON object")
    defaults = {
        "timeout_seconds": positive_int(
            "timeout_seconds", raw.get("timeout_seconds", 120)
        ),
        "max_output_chars": positive_int(
            "max_output_chars", raw.get("max_output_chars", 12000)
        ),
    }
    checks_raw = raw.get("checks", [])
    if not isinstance(checks_raw, list):
        raise ValueError("checks must be an array")
    checks = []
    names = set()
    for index, item in enumerate(checks_raw):
        if not isinstance(item, dict):
            raise ValueError(f"checks[{index}] must be an object")
        try:
            check = CheckSpec.from_dict(item, defaults)
        except ValueError as exc:
            raise ValueError(f"checks[{index}]: {exc}") from exc
        if check.name in names:
            raise ValueError(
                f"checks[{index}] duplicates the check name {check.name!r}"
            )
        checks.append(check)
        names.add(check.name)
    state_dir = raw.get("state_dir")
    if state_dir is not None and (
        not isinstance(state_dir, str) or not state_dir.strip()
    ):
        raise ValueError("state_dir must be a nonempty string")
    return Config(
        checks=tuple(checks),
        max_context_chars=max(
            500, positive_int("max_context_chars", raw.get("max_context_chars", 9000))
        ),
        max_diagnostic_lines=max(
            4, positive_int("max_diagnostic_lines", raw.get("max_diagnostic_lines", 36))
        ),
        include_success_context=boolean(
            "include_success_context", raw.get("include_success_context", True)
        ),
        deduplicate_failures=boolean(
            "deduplicate_failures", raw.get("deduplicate_failures", True)
        ),
        state_dir=state_dir,
    )


def write_default_config(root: Path, overwrite: bool = False) -> Path:
    path = root / ".loopsieve.json"
    if path.exists() and not overwrite:
        raise FileExistsError(f"{path} already exists")
    config = default_config(root)
    path.write_text(json.dumps(config.as_dict(), indent=2) + "\n", encoding="utf-8")
    return path
