"""Conservative local release checks and reproducible evidence attachments."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .models import CheckSpec
from .provenance import acceptance_gate
from .runner import run_argv
from .toolkit import safe_path


def run_required_checks(
    root: Path, commands: dict[str, list[str]], timeout: int = 25
) -> dict:
    """Only explicitly provided commands are executed. No shell or implicit installs."""
    root = Path(root).resolve()
    if not commands or len(commands) > 20:
        raise ValueError("1..20 checks required")
    if not 1 <= timeout <= 180:
        raise ValueError("timeout must be 1..180 seconds")
    results = {}
    for name, command in commands.items():
        if (
            not isinstance(name, str)
            or not name
            or not isinstance(command, list)
            or not command
        ):
            raise ValueError("invalid check entry")
        if len(command) > 24 or any(
            not isinstance(x, str) or len(x) > 1000 for x in command
        ):
            raise ValueError("unsafe command arguments")
        spec = CheckSpec(
            name, tuple(command), timeout_seconds=timeout, max_output_chars=8000
        )
        completed = run_argv(spec, command, root)
        if completed.timed_out:
            results[name] = {
                "status": "TIMEOUT",
                "evidence_id": None,
                "authenticity": "real",
            }
        elif completed.status == "ERROR":
            results[name] = {
                "status": "ERROR",
                "evidence_id": None,
                "authenticity": "real",
                "error": completed.output,
            }
        else:
            output = completed.output[-4000:]
            state = "PASS" if completed.returncode == 0 else "FAIL"
            proof = hashlib.sha256(
                json.dumps([command, completed.returncode, output]).encode()
            ).hexdigest()
            results[name] = {
                "status": state,
                "exit_code": completed.returncode,
                "output": output,
                "evidence_id": "sha256:" + proof,
                "authenticity": "real",
                "command": command,
            }
    gate = acceptance_gate(list(commands), results).as_dict()
    return {"gate": gate, "results": results}


def evaluate_release_evidence(
    root: Path, statuses: dict[str, dict], expected: list[str]
) -> dict:
    """Only accept independently supplied evidence, do not infer success from a process result alone."""
    summary = acceptance_gate(expected, statuses).as_dict()
    summary["workspace"] = str(Path(root).resolve())
    summary["checks_expected"] = len(expected)
    return summary
