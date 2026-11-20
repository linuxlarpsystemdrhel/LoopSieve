"""Conservative, deterministic diagnostic identification.

Line numbers alone do not identify an issue. We only elide a moved line when
we can resolve a stable source anchor and its enclosing symbol.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
from functools import cache
from pathlib import Path

from .models import CheckResult

SIGNAL_RE = re.compile(
    r"(?i)(error|failed|failure|exception|traceback|panic|fatal|assert|warning|warn\b|syntaxerror|typeerror|referenceerror|undefined|cannot|expected|mismatch)"
)
ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
DURATION_RE = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:ms|s|secs?|seconds?|mins?|minutes)\b", re.I
)
TIMESTAMP_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}[T ][0-9:.+\-Z]+\b")
LOCATION_RE = re.compile(
    r"(?P<path>(?:[A-Za-z]:)?[^\s():]+\.[\w]+):(?P<line>\d+)(?::(?P<col>\d+))?:\s*(?P<message>.*)"
)
PAREN_RE = re.compile(
    r"(?P<path>(?:[A-Za-z]:)?[^\s():]+\.[\w]+)\((?P<line>\d+),(?P<col>\d+)\):\s*(?P<message>.*)"
)


def clean_output(text: str) -> str:
    return "\n".join(
        x.rstrip()
        for x in ANSI_RE.sub(
            "", text.replace("\r\n", "\n").replace("\r", "\n")
        ).splitlines()
    ).strip()


def normalize_for_fingerprint(text: str, root: Path) -> str:
    """Remove timestamps and durations, but NEVER strip locations here."""
    value = clean_output(text).replace("\\", "/")
    r = str(root.resolve()).replace("\\", "/")
    if r:
        value = value.replace(r + "/", "")
    value = TIMESTAMP_RE.sub("<timestamp>", value)
    value = DURATION_RE.sub("<duration>", value)
    return "\n".join(
        " ".join(line.split()) for line in value.splitlines() if line.strip()
    )


def _read_source(path: Path) -> tuple[list[str], ast.Module] | None:
    if path.suffix not in {".py", ".pyi"}:
        return None
    try:
        if not path.is_file() or path.stat().st_size > 2_000_000:
            return None
        text = path.read_text(encoding="utf-8", errors="replace")
        return [line.strip() for line in text.splitlines()], ast.parse(text)
    except (OSError, SyntaxError, RecursionError):
        return None


def _scope_at(nodes: list[ast.stmt], line: int, prefix: str = "") -> str:
    for node in nodes:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and (
            node.lineno <= line <= (node.end_lineno or node.lineno)
        ):
            return _scope_at(node.body, line, prefix + node.name + ".")
    return prefix.removesuffix(".") or "<module>"


def _source_anchor(
    path: Path, line: int, load_source=_read_source
) -> tuple[str, str] | None:
    parsed = load_source(path)
    if parsed is None:
        return None
    lines, tree = parsed
    if not 1 <= line <= len(lines) or not lines[line - 1]:
        return None
    source = lines[line - 1]
    owner = _scope_at(tree.body, line)
    # A statement ordinal within its scope distinguishes repeated source text.
    ordinal = sum(
        1
        for earlier, text in enumerate(lines[: line - 1], 1)
        if text == source and _scope_at(tree.body, earlier) == owner
    )
    digest = hashlib.sha256(f"{source}|{ordinal}".encode()).hexdigest()[:20]
    return owner, digest


def diagnostic_identity(
    output: str, root: Path, tool: str, status: str, strict: bool = True
) -> tuple[str, list[dict]]:
    """Return exact-enough fingerprint plus reasons for deduplication decisions.

    Two different files, line locations, diagnostics in the same output, or
    code spans cannot collide by the old 'remove line numbers' heuristic.
    """
    records, related = [], []
    root = root.resolve()
    load_source = cache(_read_source)
    normalized = normalize_for_fingerprint(output, root)
    for line in normalized.splitlines():
        m = LOCATION_RE.search(line) or PAREN_RE.search(line)
        if not m:
            related.append(line)
            continue
        path_str = m.group("path").replace("\\", "/")
        try:
            line_no = int(m.group("line"))
        except ValueError:
            related.append(line)
            continue
        path = Path(path_str)
        if not path.is_absolute():
            path = root / path
        try:
            path = path.resolve()
        except (OSError, RuntimeError):
            related.append(line)
            continue
        msg = " ".join(m.group("message").split())
        anchor = (
            _source_anchor(path, line_no, load_source)
            if path.is_relative_to(root)
            else None
        )
        relative = (
            path.relative_to(root).as_posix()
            if path.is_relative_to(root)
            else str(path)
        )
        if anchor:
            location = {
                "scope": anchor[0],
                "source_anchor": anchor[1],
                "column": m.group("col") or "",
            }
            match_level = "stable-source-anchor"
        else:
            location = {"line": line_no, "column": m.group("col") or ""}
            match_level = "exact-location"
        records.append(
            {
                "file": relative,
                "message": msg,
                "location": location,
                "match_level": match_level,
                "prefix": line[: m.start()],
            }
        )
    if records:
        # Preserve multiplicity. No set(): two same-text issues are still two.
        # Preserve every non-location line because a changed traceback or
        # assertion context can turn a similar-looking failure into a new one.
        payload = {
            "tool": tool,
            "status": status,
            "diagnostics": records,
            "related_context": related,
        }
    else:
        # Conservative fallback: absent trusted location, no weakening of output.
        payload = {"tool": tool, "status": status, "opaque_output": normalized}
    fingerprint = hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return fingerprint, records


def result_fingerprint(result: CheckResult, root: Path) -> str:
    return diagnostic_identity(
        result.output, root, result.spec.name, return_category(result)
    )[0]


def return_category(result: CheckResult) -> str:
    return f"{result.status}:{result.returncode}"


def summarize_failure(result: CheckResult, max_lines: int) -> str:
    lines = clean_output(result.output).splitlines()
    if not lines:
        return "(command failed without output)"
    if len(lines) <= max_lines:
        return "\n".join(lines)
    # The final output often contains the cause and the failure summary.
    tail_count = max(1, max_lines // 2)
    tail_start = len(lines) - tail_count
    selected = set(range(tail_start, len(lines)))
    for index, line in enumerate(lines[:tail_start]):
        if len(selected) == max_lines:
            break
        if SIGNAL_RE.search(line):
            for nearby in (index, index - 1, index + 1):
                if 0 <= nearby < tail_start and len(selected) < max_lines:
                    selected.add(nearby)
    for index in range(tail_start):
        if len(selected) == max_lines:
            break
        selected.add(index)
    out, prev = [], -2
    for j in sorted(selected):
        if j > prev + 1:
            out.append("...")
        out.append(lines[j])
        prev = j
    return "\n".join(out)


def bounded(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    keep = max(100, (max_chars - 80) // 2)
    omitted = len(text) - keep * 2
    return text[:keep] + f"\n... {omitted} characters omitted ...\n" + text[-keep:]
