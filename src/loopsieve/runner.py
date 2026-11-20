"""Cross-platform bounded subprocess runner. Never uses shell=True."""

from __future__ import annotations

import os
import selectors
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from .models import CheckResult, CheckSpec


def expand_command(
    spec: CheckSpec, root: Path, changed_files: list[Path]
) -> tuple[list[str], Path]:
    cwd = (root / spec.cwd).resolve()
    command = []
    for token in spec.command:
        if token == "{python}":
            command.append(sys.executable)
        elif token == "{files}":
            for path in changed_files:
                relative = os.path.relpath(path, cwd)
                if relative.startswith("-"):
                    relative = "." + os.sep + relative
                command.append(relative)
        elif token == "{root}":
            command.append(str(root))
        else:
            command.append(token.replace("{root}", str(root)))
    return command, cwd


class BoundedStream:
    """Retains beginning and end in bounded RAM while draining all bytes."""

    def __init__(self, limit: int):
        self.limit = max(200, limit)
        self.head = bytearray()
        self.tail = bytearray()
        self.total = 0

    def feed(self, data: bytes) -> None:
        self.total += len(data)
        half = self.limit // 2
        if len(self.head) < half:
            take = min(len(data), half - len(self.head))
            self.head.extend(data[:take])
        self.tail.extend(data)
        tail_limit = self.limit - half
        if len(self.tail) > tail_limit:
            del self.tail[:-tail_limit]

    def render(self) -> str:
        if self.total <= self.limit:
            # Tail may overlap head for small outputs, so the end contains
            # the entire output when shorter than half, otherwise head+tail.
            if self.total <= self.limit // 2:
                return self.head.decode("utf-8", errors="replace")
            overlap = len(self.head) + len(self.tail) - self.total
            value = bytes(self.head) + bytes(self.tail[max(0, overlap) :])
            return value.decode("utf-8", errors="replace")
        omitted = self.total - len(self.head) - len(self.tail)
        return (
            self.head.decode("utf-8", errors="replace")
            + f"\n... {omitted} bytes omitted ...\n"
            + self.tail.decode("utf-8", errors="replace")
        )


def _stop(proc: subprocess.Popen) -> None:
    if os.name != "nt":
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    elif proc.poll() is None:
        try:
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
    if proc.poll() is None:
        proc.kill()
    proc.wait(timeout=5)


def _capture_posix(proc: subprocess.Popen, capture: BoundedStream, timeout: int) -> int:
    deadline = time.monotonic() + timeout
    leader_exited_at = None
    with selectors.DefaultSelector() as selector:
        selector.register(proc.stdout, selectors.EVENT_READ)
        while True:
            now = time.monotonic()
            if now >= deadline:
                raise subprocess.TimeoutExpired(proc.args, timeout)
            code = proc.poll()
            if code is not None:
                if leader_exited_at is None:
                    leader_exited_at = now
                elif now - leader_exited_at >= 0.25:
                    # A descendant can leave stdout open after the check has exited.
                    _stop(proc)
                    return code
            if selector.select(min(deadline - now, 0.05)):
                part = os.read(proc.stdout.fileno(), 8192)
                if not part:
                    break
                capture.feed(part)
    return proc.wait(timeout=max(0, deadline - time.monotonic()))


def _capture_windows(
    proc: subprocess.Popen, capture: BoundedStream, timeout: int
) -> int:
    lock = threading.Lock()
    finished = False

    def drain():
        try:
            for part in iter(lambda: proc.stdout.read1(8192), b""):
                with lock:
                    if finished:
                        return
                    capture.feed(part)
        except OSError:
            pass
        finally:
            proc.stdout.close()

    reader = threading.Thread(target=drain, daemon=True)
    reader.start()
    try:
        return proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        _stop(proc)
        raise
    finally:
        reader.join(timeout=2)
        with lock:
            finished = True


def run_check(spec: CheckSpec, root: Path, changed_files: list[Path]) -> CheckResult:
    started = time.monotonic()
    try:
        command, cwd = expand_command(spec, root, changed_files)
    except (OSError, RuntimeError, ValueError) as exc:
        return CheckResult(
            spec, 2, 0.0, f"unable to resolve check paths: {exc}", [], status="BLOCKED"
        )
    if not command:
        return CheckResult(
            spec, 2, 0.0, "empty command", [], skipped=True, status="SKIPPED_UNVERIFIED"
        )
    if not cwd.is_dir() or not cwd.is_relative_to(root.resolve()):
        return CheckResult(
            spec,
            2,
            0.0,
            "invalid or outside-workspace working directory",
            command,
            status="BLOCKED",
        )
    return run_argv(spec, command, cwd, started=started)


def run_argv(
    spec: CheckSpec, command: list[str], cwd: Path, *, started: float | None = None
) -> CheckResult:
    """Capture an already constructed argument list without expanding its tokens."""
    if started is None:
        started = time.monotonic()
    capture = BoundedStream(spec.max_output_chars)
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    try:
        proc = subprocess.Popen(
            command,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            shell=False,
            creationflags=flags,
            start_new_session=(os.name != "nt"),
            env=os.environ.copy(),
        )
        timed_out = False
        try:
            if os.name == "nt":
                code = _capture_windows(proc, capture, spec.timeout_seconds)
            else:
                code = _capture_posix(proc, capture, spec.timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            code = 124
        finally:
            if os.name != "nt":
                try:
                    if timed_out or proc.poll() is None:
                        _stop(proc)
                finally:
                    proc.stdout.close()
            elif proc.poll() is None:
                _stop(proc)
        output = capture.render()
        if timed_out:
            output = f"Timed out after {spec.timeout_seconds}s.\n" + output
        return CheckResult(
            spec, code, time.monotonic() - started, output, command, timed_out=timed_out
        )
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        status = f"Unable to execute command: {type(exc).__name__}: {exc}"
        return CheckResult(
            spec, 127, time.monotonic() - started, status, command, status="ERROR"
        )
