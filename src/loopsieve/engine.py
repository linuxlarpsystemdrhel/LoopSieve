"""Core verification engine with safe caching and diagnostic identity."""

from __future__ import annotations

import time
from pathlib import Path

from .config import Config
from .diagnostics import bounded, result_fingerprint, summarize_failure
from .models import CheckResult, CheckSpec, VerificationRun
from .planner import select_checks
from .runner import run_check
from .state import (
    load_state,
    project_state_path,
    save_state,
    state_stats,
    state_write_lock,
)
from .verification_state import snapshot


def _mapping(state: dict, key: str) -> dict:
    value = state.get(key)
    return value if isinstance(value, dict) else {}


def _run_checks(root: Path, files: list[Path], checks: list[CheckSpec], cached: dict):
    results, decisions, updates = [], [], {}
    for check in checks:
        key, reason = snapshot(root, check, files)
        prior = _mapping(cached, check.name)
        if key and prior.get("key") == key and prior.get("status") == "PASS":
            result = CheckResult(
                check,
                0,
                0.0,
                "",
                [],
                skipped=True,
                skip_reason="verified content-addressed cache",
                status="SKIPPED_VALID_CACHE",
            )
            reason = "validated full input fingerprint"
        else:
            result = run_check(check, root, files)
            if not result.status:
                if result.timed_out:
                    result.status = "TIMEOUT"
                elif result.skipped:
                    result.status = "SKIPPED_UNVERIFIED"
                else:
                    result.status = "PASS" if result.returncode == 0 else "FAIL"
            updates[check.name] = None
            if key:
                reason = "changed inputs or no prior successful verification"
                if result.status == "PASS":
                    after, _ = snapshot(root, check, files)
                    if after == key:
                        updates[check.name] = {
                            "key": key,
                            "status": "PASS",
                            "timestamp": time.time(),
                        }
                    else:
                        reason = "inputs changed or became unreadable during execution; result not cached"
        results.append(result)
        decisions.append(
            {"check": check.name, "status": result.status, "reason": reason}
        )
    return results, decisions, updates


def _format_context(run: VerificationRun, config: Config) -> str:
    failures = run.failed_results
    if failures:
        parts = [
            f"LoopSieve: local verification found {len(failures)} failing check(s) "
            f"after {len(run.changed_files)} changed file(s)."
        ]
        for result in failures:
            parts.append(
                f"\n[{result.spec.name}] status={result.status} exit={result.returncode} "
                f"time={result.duration_seconds:.2f}s\ncommand: {' '.join(result.command)}\n"
                f"{summarize_failure(result, config.max_diagnostic_lines)}"
            )
        return bounded("\n".join(parts), config.max_context_chars)
    if run.passed:
        if not config.include_success_context:
            return ""
        cached = sum(result.status == "SKIPPED_VALID_CACHE" for result in run.results)
        duration = sum(result.duration_seconds for result in run.results)
        return f"LoopSieve: local verification passed {len(run.results)} check(s) ({cached} validated cache hit(s)) in {duration:.2f}s."
    run.skipped = True
    run.skip_reason = "checks were not verified"
    return "LoopSieve: verification NOT CONFIRMED. Checks were skipped or blocked."


def _update_state(
    state: dict,
    run: VerificationRun,
    fingerprints: dict,
    updates: dict,
    decisions: list,
) -> None:
    cache = _mapping(state, "verified_checks")
    for name, entry in updates.items():
        if entry is None:
            cache.pop(name, None)
        else:
            cache[name] = entry
    stats = state_stats(state)
    for key, delta in {
        "runs": 1,
        "raw_diagnostic_chars": run.diagnostic_chars,
        "emitted_context_chars": run.emitted_chars,
        "repeated_failures_suppressed": int(run.repeated),
        "passed_runs": int(run.passed),
        "failed_runs": int(not run.passed),
    }.items():
        stats[key] = stats.get(key, 0) + delta
    state.update(
        version=2,
        root=str(run.root),
        updated_at_unix=int(time.time()),
        stats=stats,
        verified_checks=cache,
        verification_decisions=decisions,
        failure_fingerprints=fingerprints,
        last_context=run.context,
        last_results=[
            {
                "name": result.spec.name,
                "status": result.status,
                "returncode": result.returncode,
                "duration_seconds": round(result.duration_seconds, 4),
                "timed_out": result.timed_out,
                "output_chars": len(result.output),
            }
            for result in run.results
        ],
        last_changed_files=[
            str(path.relative_to(run.root) if path.is_relative_to(run.root) else path)
            for path in run.changed_files
        ],
    )


def verify(root: Path, changed_files: list[Path], config: Config) -> VerificationRun:
    root = root.resolve()
    run = VerificationRun(root=root, changed_files=[])
    try:
        run.changed_files = list(
            dict.fromkeys((root / path).resolve() for path in changed_files)
        )
    except (OSError, RuntimeError, ValueError):
        run.skipped = True
        run.skip_reason = "could not resolve a changed file path"
        return run
    if not run.changed_files:
        run.skipped = True
        run.skip_reason = "no changed files"
        return run
    checks = select_checks(config.checks, run.changed_files)
    if not checks:
        run.skipped = True
        run.skip_reason = "no matching checks"
        return run

    state_path = None
    cached = {}
    try:
        state_path = project_state_path(root, config.state_dir)
        cached = _mapping(load_state(state_path), "verified_checks")
    except (OSError, RuntimeError, ValueError) as exc:
        run.state_warning = f"verification state unavailable: {exc}"
    run.results, decisions, updates = _run_checks(
        root, run.changed_files, checks, cached
    )
    run.diagnostic_chars = sum(len(result.output) for result in run.failed_results)
    fingerprints = {
        result.spec.name: result_fingerprint(result, root)
        for result in run.failed_results
    }
    full_context = _format_context(run, config)
    run.context = full_context
    run.emitted_chars = len(full_context)
    if state_path is None:
        return run
    try:
        with state_write_lock(state_path):
            latest = load_state(state_path)
            run.repeated = (
                bool(fingerprints)
                and config.deduplicate_failures
                and fingerprints == _mapping(latest, "failure_fingerprints")
            )
            if run.repeated:
                names = ", ".join(sorted(fingerprints))
                run.context = bounded(
                    f"LoopSieve: verification still fails in {names}, but the verified diagnostic "
                    "identities are unchanged. No duplicate failure log is attached.",
                    config.max_context_chars,
                )
            run.emitted_chars = len(run.context)
            _update_state(latest, run, fingerprints, updates, decisions)
            save_state(state_path, latest)
    except OSError as exc:
        run.repeated = False
        run.context = full_context
        run.emitted_chars = len(full_context)
        run.state_warning = f"could not save verification state: {exc}"
    return run


def state_report(root: Path, config: Config) -> dict:
    path = project_state_path(root.resolve(), config.state_dir)
    state = load_state(path)
    stats = state_stats(state)
    raw = stats.get("raw_diagnostic_chars", 0)
    emitted = stats.get("emitted_context_chars", 0)
    return {
        "state_path": str(path),
        "stats": stats,
        "diagnostic_context_reduction_ratio": round(
            (raw - emitted) / raw if 0 <= emitted < raw else 0.0, 4
        ),
        "last_results": state.get("last_results", []),
        "last_changed_files": state.get("last_changed_files", []),
        "verification_decisions": state.get("verification_decisions", []),
    }
