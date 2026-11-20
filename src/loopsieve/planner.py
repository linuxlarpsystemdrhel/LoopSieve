from __future__ import annotations

from pathlib import Path

from .models import CheckSpec
from .project import classify_file


def select_checks(checks: tuple[CheckSpec, ...], changed_files: list[Path]) -> list[CheckSpec]:
    kinds = {classify_file(path) for path in changed_files}
    selected: list[CheckSpec] = []
    for check in checks:
        if not check.enabled:
            continue
        accepted = set(check.kinds)
        if "any" in accepted or accepted & kinds:
            selected.append(check)
    return selected
