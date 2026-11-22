//! Conservative diagnostic identity and terminal-safe evidence.

use crate::digest;
use anyhow::Result;
use regex::Regex;
use serde::{Deserialize, Serialize};
use std::collections::BTreeSet;
use std::io::Read;
use std::path::Path;
use std::sync::LazyLock;

static ANSI: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"\x1b\[[0-9:;?]*[ -/]*[@-~]").unwrap());
static LOCATION: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"^(?P<path>.+?\.[\w-]+):(?P<line>\d+)(?::(?P<col>\d+))?:\s*(?P<msg>.*)$").unwrap()
});
static PAREN: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"^(?P<path>.+?\.[\w-]+)\((?P<line>\d+),(?P<col>\d+)\):\s*(?P<msg>.*)$").unwrap()
});
static LEVEL: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"(?i)^(fatal error|error|warning|note|info)(?:\[([^\]]+)\])?(?::|\s)").unwrap()
});
static HINT: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"(?i)error|fail|panic|exception|warning|mismatch|^\s*-->").unwrap()
});
static PRIVATE_KEY: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(
        r"(?s)-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?(?:-----END [A-Z0-9 ]*PRIVATE KEY-----|\z)",
    )
    .unwrap()
});
static CREDENTIALS: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"(?i)(?:github_pat_|gh[pousr]_|sk-(?:proj-)?|hf_|xox[baprs]-|AKIA)[a-z0-9_\-]{16,}|\bBearer\s+[^\s,;]+").unwrap()
});
static SECRET_FIELDS: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r#"(?i)(\b(?:api[_-]?key|(?:(?:access|refresh)[_-])?token|password|secret)\b["']?\s*[:=]\s*)(?:"[^"\r\n]*"|'[^'\r\n]*'|[^\s,;"'}]+)"#).unwrap()
});
static LEGACY_TIMING: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"(?i)\b\d+(?:\.\d+)?\s*(?:ms|s|secs?|seconds?|mins?|minutes)\b").unwrap()
});
static LEGACY_TIMESTAMP: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"\b\d{4}-\d{2}-\d{2}[T ][0-9:.+\-Z]+\b").unwrap());

fn clean(text: &str) -> String {
    let text = text.replace("\r\n", "\n").replace('\r', "\n");
    ANSI.replace_all(&text, "")
        .chars()
        .filter(|&c| {
            matches!(c, '\n' | '\t')
                || (!c.is_control()
                    && !matches!(c, '\u{202a}'..='\u{202e}' | '\u{2066}'..='\u{2069}'))
        })
        .collect()
}

pub fn redact(text: &str) -> String {
    let normalized = clean(text);
    let without_keys = PRIVATE_KEY.replace_all(&normalized, "[REDACTED PRIVATE KEY]");
    let without_credentials = CREDENTIALS.replace_all(&without_keys, "[REDACTED]");
    SECRET_FIELDS
        .replace_all(&without_credentials, "${1}[REDACTED]")
        .into_owned()
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Diagnostic {
    pub file: String,
    pub line: u32,
    pub column: Option<u32>,
    pub severity: String,
    pub code: Option<String>,
    pub message: String,
}

fn path_label(root: &Path, file: &str) -> String {
    let normalized = file.replace('\\', "/");
    let root = root.to_string_lossy().replace('\\', "/");
    let root = root.trim_end_matches('/');
    if root.is_empty() {
        return normalized;
    }
    normalized
        .strip_prefix(root)
        .and_then(|rest| rest.strip_prefix('/'))
        .unwrap_or(&normalized)
        .to_owned()
}

fn json_diagnostic(line: &str, root: &Path) -> Option<Diagnostic> {
    if !line.starts_with('{') {
        return None;
    }
    let json: serde_json::Value = serde_json::from_str(line).ok()?;
    let message = if json["reason"] == "compiler-message" {
        &json["message"]
    } else if json["$message_type"] == "diagnostic" {
        &json
    } else {
        return None;
    };
    let span = message["spans"]
        .as_array()?
        .iter()
        .find(|span| span["is_primary"] == true)?;
    Some(Diagnostic {
        file: path_label(root, span["file_name"].as_str()?),
        line: span["line_start"].as_u64()?.try_into().ok()?,
        column: span["column_start"]
            .as_u64()
            .and_then(|n| n.try_into().ok()),
        severity: message["level"].as_str()?.to_owned(),
        code: message["code"]["code"].as_str().map(str::to_owned),
        message: message["message"].as_str()?.to_owned(),
    })
}

pub(crate) fn records(text: &str, root: &Path) -> Vec<Diagnostic> {
    clean(text)
        .lines()
        .filter_map(|line| {
            let line = line.trim();
            if let Some(record) = json_diagnostic(line, root) {
                return Some(record);
            }
            let captures = LOCATION.captures(line).or_else(|| PAREN.captures(line))?;
            let message = captures.name("msg")?.as_str();
            let level = LEVEL.captures(message);
            Some(Diagnostic {
                file: path_label(root, captures.name("path")?.as_str()),
                line: captures.name("line")?.as_str().parse().ok()?,
                column: captures
                    .name("col")
                    .and_then(|part| part.as_str().parse().ok()),
                severity: level
                    .as_ref()
                    .map(|m| m[1].to_ascii_lowercase())
                    .unwrap_or_else(|| "unknown".into()),
                code: level
                    .as_ref()
                    .and_then(|m| m.get(2))
                    .map(|m| m.as_str().into()),
                message: message.to_owned(),
            })
        })
        .take(128)
        .collect()
}

pub(crate) fn identity(text: &str, omitted: usize, raw_digest: &str) -> String {
    if omitted != 0 {
        return format!("raw:{raw_digest}");
    }
    // Preserve location, case, timing values and whitespace in checks.
    // The benchmark has its own legacy normalization for fixture comparison.
    digest(clean(text).as_bytes())
}

pub(crate) fn excerpt(text: &str, max_lines: usize) -> String {
    let text = redact(text);
    let lines: Vec<_> = text.lines().collect();
    if lines.len() <= max_lines {
        return text.trim().to_owned();
    }
    let tail = lines.len() - max_lines / 2;
    let mut selected: BTreeSet<_> = (tail..lines.len()).collect();
    for (index, line) in lines[..tail].iter().enumerate() {
        if selected.len() >= max_lines {
            break;
        }
        if HINT.is_match(line) {
            selected.insert(index);
        }
    }
    for index in 0..tail {
        if selected.len() >= max_lines {
            break;
        }
        selected.insert(index);
    }
    let mut previous = None;
    let mut output = Vec::new();
    for index in selected {
        if previous.is_some_and(|last| last + 1 != index) {
            output.push("...");
        }
        output.push(lines[index]);
        previous = Some(index);
    }
    output.join("\n")
}

pub(crate) fn bounded(text: &str, limit: usize) -> String {
    let count = text.chars().count();
    if count <= limit {
        return text.to_owned();
    }
    let keep = limit.saturating_sub(80) / 2;
    let head: String = text.chars().take(keep).collect();
    let tail: String = text.chars().skip(count - keep).collect();
    format!(
        "{head}\n... {} characters omitted ...\n{tail}",
        count - keep * 2
    )
}

#[derive(Debug, Serialize)]
pub struct Benchmark {
    pub iterations: usize,
    pub raw_chars: usize,
    pub loopsieve_chars: usize,
    pub repeated_failures_suppressed: usize,
    pub diagnostic_context_reduction_ratio: f64,
}

pub fn benchmark(reader: impl Read) -> Result<Benchmark> {
    #[derive(Deserialize)]
    struct Fixture {
        outputs: Vec<String>,
    }
    let fixture: Fixture = serde_json::from_reader(reader.take(32 * 1024 * 1024))?;
    let mut result = Benchmark {
        iterations: fixture.outputs.len(),
        raw_chars: 0,
        loopsieve_chars: 0,
        repeated_failures_suppressed: 0,
        diagnostic_context_reduction_ratio: 0.0,
    };
    let mut previous = None;
    for output in fixture.outputs {
        result.raw_chars += output.chars().count();
        let compact = clean(&output).replace('\\', "/");
        let timestamp = LEGACY_TIMESTAMP.replace_all(&compact, "<timestamp>");
        let timing = LEGACY_TIMING.replace_all(&timestamp, "<duration>");
        let key = digest(
            timing
                .split_whitespace()
                .collect::<Vec<_>>()
                .join(" ")
                .as_bytes(),
        );
        if previous.as_ref() == Some(&key) {
            result.repeated_failures_suppressed += 1;
            result.loopsieve_chars +=
                "LoopSieve: normalized diagnostics are unchanged. Duplicate log suppressed.".len();
        } else {
            result.loopsieve_chars += bounded(&output, 9000).chars().count();
        }
        previous = Some(key);
    }
    if result.raw_chars != 0 {
        result.diagnostic_context_reduction_ratio =
            ((1.0 - result.loopsieve_chars as f64 / result.raw_chars as f64) * 10000.0).round()
                / 10000.0;
    }
    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rust_compiler_json_extracts_primary_span() {
        let source = r#"{"reason":"compiler-message","message":{"message":"types differ","level":"error","code":{"code":"E0308"},"spans":[{"file_name":"macros.rs","line_start":2,"column_start":4,"is_primary":false},{"file_name":"src/lib.rs","line_start":9,"column_start":12,"is_primary":true}]}}"#;
        let parsed = records(source, Path::new("/workspace"));
        assert_eq!(parsed.len(), 1);
        assert_eq!(parsed[0].file, "src/lib.rs");
        assert_eq!(parsed[0].line, 9);
        assert_eq!(parsed[0].column, Some(12));
        assert_eq!(parsed[0].code.as_deref(), Some("E0308"));
    }

    #[test]
    fn truncated_identity_uses_bytes_that_were_not_retained() {
        assert_ne!(
            identity("same preview", 30, "one"),
            identity("same preview", 30, "two")
        );
        assert_ne!(
            identity("error: expected 2 ms", 0, ""),
            identity("error: expected 3 ms", 0, ""),
        );
    }
}
