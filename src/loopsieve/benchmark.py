from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from .diagnostics import bounded, diagnostic_identity


@dataclass
class BenchmarkResult:
    iterations: int
    raw_chars: int
    loopsieve_chars: int
    repeated_failures: int

    @property
    def reduction_ratio(self) -> float:
        if self.raw_chars == 0:
            return 0.0
        return 1.0 - (self.loopsieve_chars / self.raw_chars)

    def as_dict(self) -> dict:
        return {
            "iterations": self.iterations,
            "raw_chars": self.raw_chars,
            "loopsieve_chars": self.loopsieve_chars,
            "repeated_failures_suppressed": self.repeated_failures,
            "diagnostic_context_reduction_ratio": round(self.reduction_ratio, 4),
        }


def run_fixture(path: Path, root: Path | None = None, max_context_chars: int = 9000) -> BenchmarkResult:
    data = json.loads(path.read_text(encoding="utf-8"))
    outputs = data.get("outputs", [])
    if not isinstance(outputs, list) or not all(isinstance(x, str) for x in outputs):
        raise ValueError("benchmark fixture requires an outputs array of strings")
    root = (root or path.parent).resolve()
    raw_chars = sum(len(output) for output in outputs)
    emitted = 0
    previous: str | None = None
    repeats = 0
    for output in outputs:
        fingerprint, _ = diagnostic_identity(output, root, "fixture", "1")
        if previous == fingerprint:
            message = "LoopSieve: normalized diagnostics are unchanged. Duplicate log suppressed."
            repeats += 1
        else:
            message = bounded(output, max_context_chars)
        emitted += len(message)
        previous = fingerprint
    return BenchmarkResult(len(outputs), raw_chars, emitted, repeats)
