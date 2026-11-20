from __future__ import annotations

import json
import shutil
from pathlib import Path

from .models import CheckSpec


MARKERS = (".git", ".loopsieve.json", "pyproject.toml", "package.json", "go.mod", "Cargo.toml")


def find_project_root(start: Path) -> Path:
    start = start.resolve()
    if start.is_file():
        start = start.parent
    candidates = [start, *start.parents]
    for candidate in candidates:
        if (candidate / ".loopsieve.json").exists() or (candidate / ".git").exists():
            return candidate
    for candidate in candidates:
        if any((candidate / marker).exists() for marker in MARKERS[2:]):
            return candidate
    return start


def classify_file(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".py", ".pyi"}:
        return "python"
    if suffix in {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".vue", ".svelte"}:
        return "javascript"
    if suffix == ".go":
        return "go"
    if suffix == ".rs":
        return "rust"
    if suffix in {".c", ".cc", ".cpp", ".cxx", ".h", ".hpp", ".hh"}:
        return "cpp"
    if suffix in {".json", ".yaml", ".yml", ".toml", ".ini"}:
        return "config"
    if suffix in {".md", ".mdx", ".rst"}:
        return "docs"
    return "other"


def _node_checks(root: Path) -> list[CheckSpec]:
    package = root / "package.json"
    if not package.exists() or shutil.which("npm") is None:
        return []
    try:
        data = json.loads(package.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    scripts = data.get("scripts", {}) if isinstance(data, dict) else {}
    if not isinstance(scripts, dict):
        return []
    checks: list[CheckSpec] = []
    for script, name, timeout in (
        ("typecheck", "npm typecheck", 120),
        ("lint", "npm lint", 120),
        ("check", "npm check", 120),
    ):
        if script in scripts:
            checks.append(CheckSpec(name=name, command=("npm", "run", script, "--if-present"), kinds=("javascript", "config"), timeout_seconds=timeout))
    if not checks and "test" in scripts:
        checks.append(CheckSpec(name="npm test", command=("npm", "test", "--", "--run"), kinds=("javascript",), timeout_seconds=180))
    return checks


def _python_checks(root: Path) -> list[CheckSpec]:
    pyproject = root / "pyproject.toml"
    setup_cfg = root / "setup.cfg"
    requirements = root / "requirements.txt"
    has_python = pyproject.exists() or setup_cfg.exists() or requirements.exists() or any(root.glob("*.py"))
    if not has_python:
        return []
    checks = [
        CheckSpec(
            name="python syntax",
            command=("{python}", "-m", "compileall", "-q", "{files}"),
            kinds=("python",),
            timeout_seconds=45,
            max_output_chars=6000,
        )
    ]
    text = ""
    for file in (pyproject, setup_cfg, requirements):
        if file.exists():
            try:
                text += file.read_text(encoding="utf-8", errors="ignore") + "\n"
            except OSError:
                pass
    lowered = text.lower()
    if "pytest" in lowered or (root / "pytest.ini").exists():
        checks.append(CheckSpec(name="pytest", command=("{python}", "-m", "pytest", "-q"), kinds=("python", "config"), timeout_seconds=180))
    if "ruff" in lowered:
        checks.append(CheckSpec(name="ruff", command=("{python}", "-m", "ruff", "check", "{files}"), kinds=("python",), timeout_seconds=90))
    if "mypy" in lowered:
        checks.append(CheckSpec(name="mypy", command=("{python}", "-m", "mypy", "{files}"), kinds=("python",), timeout_seconds=120))
    return checks


def detect_checks(root: Path) -> list[CheckSpec]:
    checks: list[CheckSpec] = []
    checks.extend(_python_checks(root))
    checks.extend(_node_checks(root))
    if (root / "go.mod").exists() and shutil.which("go"):
        checks.append(CheckSpec(name="go test", command=("go", "test", "./..."), kinds=("go", "config"), timeout_seconds=180))
    if (root / "Cargo.toml").exists() and shutil.which("cargo"):
        checks.append(CheckSpec(name="cargo check", command=("cargo", "check", "--quiet"), kinds=("rust", "config"), timeout_seconds=180))
    return checks
