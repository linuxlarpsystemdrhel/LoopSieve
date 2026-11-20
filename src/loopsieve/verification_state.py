"""Conservative content-addressed verification caching.

Caching is OFF by default. A valid PASS may be reused only if the check's
complete_inputs assertion is explicit and every declared input can be hashed.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
from pathlib import Path

from .models import CheckSpec
from .runner import expand_command

IGNORED = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    ".loopsieve",
    ".local-models",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
}
CONFIG_INPUTS = [
    ".loopsieve.json",
    "pyproject.toml",
    "setup.cfg",
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "Cargo.toml",
    "Cargo.lock",
    "go.mod",
    "go.sum",
    "requirements.txt",
    "ruff.toml",
    "tsconfig.json",
    "pytest.ini",
    "Makefile",
]


def _check_executable(executable: str, cwd: Path) -> Path | None:
    if os.path.dirname(executable):
        if os.name == "nt" and not Path(executable).is_absolute():
            return None
        found = shutil.which(str(cwd / executable))
    elif os.name == "nt":
        # CreateProcess may search in directories outside the supplied child cwd.
        return None
    else:
        search = os.pathsep.join(
            str(cwd / directory) for directory in os.get_exec_path()
        )
        found = shutil.which(executable, path=search)
    return Path(found).resolve(strict=True) if found else None


def _collect_inputs(root: Path, patterns: tuple[str, ...]) -> set[Path]:
    pending = []
    for pattern in patterns:
        if not pattern or Path(pattern).is_absolute() or ".." in Path(pattern).parts:
            raise ValueError("unsafe dependency pattern")
        matching = list(root.glob(pattern))
        if not matching:
            raise ValueError(f"dependency pattern has no matches: {pattern}")
        pending.extend(matching)
    visited, paths = set(), set()
    while pending:
        path = pending.pop()
        if path in visited:
            continue
        visited.add(path)
        if any(
            part in IGNORED or part.startswith(".venv-")
            for part in path.relative_to(root).parts
        ):
            continue
        if path.resolve(strict=True) != path:
            raise ValueError("symlink dependency cannot be verified safely")
        mode = path.stat().st_mode
        if stat.S_ISDIR(mode):
            pending.extend(path.iterdir())
        elif stat.S_ISREG(mode):
            paths.add(path)
        else:
            raise ValueError("non-regular dependency cannot be verified safely")
    return paths


def _identity(info: os.stat_result) -> tuple[int, ...]:
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def _file_digest(path: Path) -> str:
    with path.open("rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("dependency must be a regular file")
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if _identity(before) != _identity(path.stat()):
        raise ValueError("dependency changed during hashing")
    return digest


def snapshot(
    root: Path, spec: CheckSpec, changed_files: list[Path]
) -> tuple[str | None, str]:
    if not spec.complete_inputs or not spec.inputs or not spec.deterministic:
        return (
            None,
            "deterministic complete dependency set not declared; fresh execution required",
        )
    try:
        command, cwd = expand_command(spec, root, changed_files)
        if not cwd.is_relative_to(root) or not cwd.is_dir():
            return None, "working directory is unavailable or escapes project"
        executable = _check_executable(command[0], cwd) if command else None
        if executable is None:
            return None, "executable cannot be resolved safely"
        paths = _collect_inputs(root, spec.inputs)
        for name in CONFIG_INPUTS:
            path = root / name
            if path.is_file() or path.is_symlink():
                paths.add(path)
        for path in changed_files:
            if not path.is_relative_to(root) or not path.is_file():
                return (
                    None,
                    "changed dependency is missing, outside the project or not a regular file",
                )
            paths.add(path)
        files = {}
        for path in sorted(paths):
            if path.resolve(strict=True) != path:
                return None, "symlink dependency cannot be verified safely"
            files[path.relative_to(root).as_posix()] = _file_digest(path)
        if not files:
            return None, "empty dependency set"
        meta = {
            "schema": 2,
            "command": command,
            "cwd": str(cwd),
            "spec": spec.as_dict(),
            "executable": str(executable),
            "executable_identity": _identity(executable.stat()),
            "files": files,
            "environment": {
                key: os.environ.get(key)
                for key in (
                    "PATH",
                    "PYTHONPATH",
                    "PYTHONHOME",
                    "VIRTUAL_ENV",
                    "NODE_ENV",
                    "RUSTFLAGS",
                    "CARGO_TARGET_DIR",
                    "GOFLAGS",
                    "CFLAGS",
                    "CXXFLAGS",
                    "JAVA_HOME",
                    "CI",
                    *spec.env_keys,
                )
            },
        }
        digest = hashlib.sha256(json.dumps(meta, sort_keys=True).encode()).hexdigest()
        return digest, "all explicitly declared inputs hashed"
    except ValueError as exc:
        return None, str(exc)
    except (OSError, RuntimeError):
        return None, "dependency or executable unavailable during fingerprinting"
