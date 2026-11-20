from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def positive_int(name: str, value: Any) -> int:
    if type(value) not in (int, str):
        raise ValueError(f"{name} must be a positive integer")
    try:
        result = int(value)
    except ValueError:
        raise ValueError(f"{name} must be a positive integer") from None
    if result <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return result


def boolean(name: str, value: Any) -> bool:
    if type(value) is not bool:
        raise ValueError(f"{name} must be a boolean")
    return value


def _strings(name: str, value: Any) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{name} must be an array of strings")
    return tuple(value)


@dataclass(frozen=True)
class CheckSpec:
    name: str
    command: tuple[str, ...]
    kinds: tuple[str, ...] = ("any",)
    timeout_seconds: int = 120
    max_output_chars: int = 12000
    cwd: str = "."
    enabled: bool = True
    inputs: tuple[str, ...] = ()
    complete_inputs: bool = False
    deterministic: bool = False
    env_keys: tuple[str, ...] = ()

    @classmethod
    def from_dict(
        cls, value: dict[str, Any], defaults: dict[str, Any] | None = None
    ) -> "CheckSpec":
        defaults = defaults or {}
        command = _strings("command", value.get("command"))
        if not command or not command[0].strip():
            raise ValueError("command must begin with an executable")
        name = value.get("name", command[0])
        cwd = value.get("cwd", ".")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("name must be a nonempty string")
        if not isinstance(cwd, str) or not cwd.strip():
            raise ValueError("cwd must be a nonempty string")
        return cls(
            name=name,
            command=command,
            kinds=_strings("kinds", value.get("kinds", ["any"])) or ("any",),
            timeout_seconds=positive_int(
                "timeout_seconds",
                value.get("timeout_seconds", defaults.get("timeout_seconds", 120)),
            ),
            max_output_chars=positive_int(
                "max_output_chars",
                value.get("max_output_chars", defaults.get("max_output_chars", 12000)),
            ),
            cwd=cwd,
            enabled=boolean("enabled", value.get("enabled", True)),
            inputs=_strings("inputs", value.get("inputs", [])),
            complete_inputs=boolean(
                "complete_inputs", value.get("complete_inputs", False)
            ),
            deterministic=boolean("deterministic", value.get("deterministic", False)),
            env_keys=_strings("env_keys", value.get("env_keys", [])),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "command": list(self.command),
            "kinds": list(self.kinds),
            "timeout_seconds": self.timeout_seconds,
            "max_output_chars": self.max_output_chars,
            "cwd": self.cwd,
            "enabled": self.enabled,
            "inputs": list(self.inputs),
            "complete_inputs": self.complete_inputs,
            "deterministic": self.deterministic,
            "env_keys": list(self.env_keys),
        }


@dataclass
class CheckResult:
    spec: CheckSpec
    returncode: int
    duration_seconds: float
    output: str
    command: list[str]
    timed_out: bool = False
    skipped: bool = False
    skip_reason: str | None = None
    status: str = ""

    @property
    def passed(self) -> bool:
        return self.status in {"PASS", "SKIPPED_VALID_CACHE"} or (
            not self.status
            and not self.skipped
            and not self.timed_out
            and self.returncode == 0
        )


@dataclass
class VerificationRun:
    root: Path
    changed_files: list[Path]
    results: list[CheckResult] = field(default_factory=list)
    context: str = ""
    repeated: bool = False
    skipped: bool = False
    skip_reason: str | None = None
    diagnostic_chars: int = 0
    emitted_chars: int = 0
    state_warning: str | None = None

    @property
    def failed_results(self) -> list[CheckResult]:
        return [r for r in self.results if not r.passed and not r.skipped]

    @property
    def passed(self) -> bool:
        return bool(self.results) and all(result.passed for result in self.results)
