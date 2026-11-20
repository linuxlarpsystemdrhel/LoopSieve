from __future__ import annotations

import errno
import hashlib
import json
import os
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any


def default_state_base() -> Path:
    override = os.environ.get("CLAUDE_PLUGIN_DATA") or os.environ.get(
        "LOOPSIEVE_STATE_DIR"
    )
    if override:
        return Path(override).expanduser().resolve()
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "LoopSieve"
    if sys_platform() == "darwin":
        return Path.home() / "Library" / "Caches" / "LoopSieve"
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "loopsieve"


def sys_platform() -> str:
    import sys

    return sys.platform


def project_state_path(root: Path, custom_state_dir: str | None = None) -> Path:
    base = (
        Path(custom_state_dir).expanduser().resolve()
        if custom_state_dir
        else default_state_base()
    )
    key = hashlib.sha256(str(root.resolve()).encode("utf-8")).hexdigest()[:16]
    return base / "projects" / key / "state.json"


def load_state(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, RecursionError):
        return {}


def save_state(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(
        prefix="state-", suffix=".json", dir=path.parent
    )
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(data, stream, indent=2, sort_keys=True)
            stream.write("\n")
        os.replace(temp_name, path)
    finally:
        try:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
        except OSError:
            pass


@contextmanager
def state_write_lock(path: Path):
    """Serialize state updates across processes while leaving checks concurrent."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix(".lock").open("a+b") as stream:
        if os.name == "nt":
            import msvcrt

            def acquire():
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            def acquire():
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

        deadline = time.monotonic() + 5
        while True:
            try:
                acquire()
                break
            except OSError as exc:
                if exc.errno not in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                    raise
                if time.monotonic() >= deadline:
                    raise TimeoutError("verification state is busy") from exc
                time.sleep(0.01)
        # Closing the descriptor also releases the lock after a process exit.
        yield


def state_stats(state: dict) -> dict[str, int]:
    raw = state.get("stats")
    if not isinstance(raw, dict):
        return {}
    stats = {}
    for name, value in raw.items():
        if type(value) not in (int, str):
            continue
        try:
            count = int(value)
        except ValueError:
            continue
        if count >= 0:
            stats[name] = count
    return stats
