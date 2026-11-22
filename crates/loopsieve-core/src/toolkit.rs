//! Read-only tools shared by the native CLI and agent runtime.

use crate::agent::{read_text, workspace_file, workspace_tree};
use crate::config::CheckSpec;
use crate::diagnostics::{bounded, redact};
use crate::digest;
use crate::runner;
use anyhow::{Context, Result, bail, ensure};
use serde::Deserialize;
use serde_json::{Value, json};
use std::path::Path;
use std::sync::atomic::AtomicBool;

pub const TOOLS: &[(&str, &str)] = &[
    ("workspace_tree", "List bounded workspace files"),
    ("file_read", "Read a bounded UTF-8 file"),
    ("file_lines", "Return a numbered line range"),
    ("file_sha256", "Hash a bounded workspace file"),
    ("file_search_text", "Find literal text in workspace files"),
    (
        "git_diff",
        "Inspect the unstaged diff of one workspace file",
    ),
    ("file_search_name", "Find names containing a substring"),
    ("env_runtime", "Show local platform and usable CPU count"),
];

#[derive(Debug, Deserialize, Default)]
#[serde(default, deny_unknown_fields)]
pub struct Arguments {
    path: Option<String>,
    query: Option<String>,
    max_chars: Option<usize>,
    start: Option<usize>,
    count: Option<usize>,
    limit: Option<usize>,
}

pub fn run(root: &Path, name: &str, args: Arguments) -> Result<Value> {
    let result = match name {
        "workspace_tree" => json!(
            workspace_tree(root)
                .into_iter()
                .take(args.limit.unwrap_or(300).min(300))
                .collect::<Vec<_>>()
        ),
        "file_read" | "file_lines" | "file_sha256" => {
            let (_, path) =
                workspace_file(root, args.path.as_deref().context("path is required")?)?;
            let text = read_text(&path)?;
            match name {
                "file_read" => json!(bounded(
                    &redact(&text),
                    args.max_chars.unwrap_or(8000).clamp(100, 16000)
                )),
                "file_lines" => {
                    let start = args.start.unwrap_or(1).max(1);
                    let count = args.count.unwrap_or(20).min(100);
                    json!(text.lines().enumerate().skip(start - 1).take(count)
                        .map(|(index, line)| json!({"number": index + 1, "text": bounded(&redact(line), 2000)})).collect::<Vec<_>>())
                }
                _ => json!(digest(text.as_bytes())),
            }
        }
        "file_search_text" => search(
            root,
            args.query.as_deref().context("query is required")?,
            args.limit.unwrap_or(30),
        )?,
        "file_search_name" => {
            let query = args
                .query
                .as_deref()
                .context("query is required")?
                .to_lowercase();
            ensure!(
                !query.trim().is_empty() && query.len() <= 512,
                "query must contain up to 512 bytes"
            );
            json!(
                workspace_tree(root)
                    .into_iter()
                    .filter(|name| name.to_lowercase().contains(&query))
                    .take(args.limit.unwrap_or(50).min(300))
                    .collect::<Vec<_>>()
            )
        }
        "git_diff" => json!(diff(
            root,
            args.path.as_deref().context("path is required")?,
            &AtomicBool::new(false)
        )?),
        "env_runtime" => hardware(root),
        _ => bail!("tool is unavailable in the native runtime"),
    };
    Ok(result)
}

pub(crate) fn search(root: &Path, query: &str, limit: usize) -> Result<Value> {
    ensure!(
        !query.trim().is_empty() && query.len() <= 512 && !query.contains(['\n', '\r']),
        "search requires 1..=512 bytes of single-line text"
    );
    let mut rows = Vec::new();
    let limit = limit.min(50);
    for path in workspace_tree(root) {
        if rows.len() >= limit {
            break;
        }
        let Ok((_, file)) = workspace_file(root, &path) else {
            continue;
        };
        let Ok(text) = read_text(&file) else {
            continue;
        };
        rows.extend(text.lines().enumerate().filter(|(_, line)| line.contains(query)).take(limit - rows.len())
            .map(|(line, text)| json!({"path": redact(&path), "line": line + 1, "text": bounded(&redact(text), 400)})));
    }
    Ok(json!(rows))
}

pub fn hardware(root: &Path) -> Value {
    let info = std::fs::read_to_string("/proc/meminfo").unwrap_or_default();
    let ram = |name: &str| {
        info.lines().find_map(|line| {
            line.strip_prefix(name)?
                .split_whitespace()
                .next()?
                .parse::<u64>()
                .ok()
                .map(|kib| kib / 1024)
        })
    };
    let cpu = std::fs::read_to_string("/proc/cpuinfo")
        .ok()
        .and_then(|text| {
            text.lines().find_map(|line| {
                let (label, name) = line.split_once(':')?;
                (label.trim() == "model name").then(|| name.trim().to_owned())
            })
        });
    let search = [
        "nvidia-smi",
        "--query-gpu=name,memory.total,memory.free,driver_version",
        "--format=csv,noheader,nounits",
    ];
    let gpus = command(root, &search, &AtomicBool::new(false)).ok().into_iter().flat_map(|output| {
        output.lines().filter_map(|line| {
            let values: Vec<_> = line.rsplitn(4, ',').map(str::trim).collect();
            let [driver, free, total, name] = values.as_slice() else { return None; };
            Some(json!({"name":redact(name), "vram_total_mib":total.parse::<u64>().ok(),
                "vram_available_mib":free.parse::<u64>().ok(), "driver":redact(driver), "source":"nvidia-smi"}))
        }).collect::<Vec<_>>()
    }).collect::<Vec<_>>();
    json!({"os_name": std::env::consts::OS, "architecture": std::env::consts::ARCH,
        "cpu":cpu, "cpu_count":std::thread::available_parallelism().ok().map(|count| count.get()),
        "ram_total_mib":ram("MemTotal:"), "ram_available_mib":ram("MemAvailable:"), "gpus":gpus})
}

pub(crate) fn diff(root: &Path, file: &str, cancelled: &AtomicBool) -> Result<String> {
    let (path, _) = workspace_file(root, file)?;
    command(
        root,
        &[
            "git",
            "--no-pager",
            "--literal-pathspecs",
            "diff",
            "--no-ext-diff",
            "--no-textconv",
            "--",
            &path,
        ],
        cancelled,
    )
}

fn command(root: &Path, argv: &[&str], cancelled: &AtomicBool) -> Result<String> {
    let spec = CheckSpec {
        name: argv[0].into(),
        command: argv.iter().map(|value| (*value).into()).collect(),
        kinds: vec![],
        timeout_seconds: 5,
        max_output_chars: 12_000,
        cwd: ".".into(),
        enabled: true,
        inputs: vec![],
        complete_inputs: false,
        deterministic: false,
        env_keys: vec![],
    };
    let prepared = runner::prepare(root, &spec, &[])?;
    let result = runner::execute(&prepared, &spec, cancelled);
    ensure!(
        result.status.passed(),
        "{} did not return a successful result",
        argv[0]
    );
    Ok(redact(&result.output))
}
