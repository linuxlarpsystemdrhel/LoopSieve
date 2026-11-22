//! Local editor integration and inspection of existing MCP declarations.

use crate::config::within;
use crate::diagnostics::redact;
use crate::inference::json_file;
use crate::store::lock_state;
use anyhow::{Context, Result, ensure};
use serde_json::{Value, json};
use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::Path;

const SETTINGS: &str = ".claude/settings.local.json";
const EVENT: &str = "PostToolUse";
const MARKER: &str = "LoopSieve native verification";

pub fn claude_status(root: &Path) -> Result<Value> {
    let path = within(root, Path::new(SETTINGS), false)?;
    let settings = read_settings(&path)?;
    let installed = settings["hooks"][EVENT]
        .as_array()
        .into_iter()
        .flatten()
        .any(|group| {
            group["hooks"]
                .as_array()
                .into_iter()
                .flatten()
                .any(is_managed)
        });
    Ok(json!({"installed": installed, "settings_path": SETTINGS, "event": EVENT}))
}

pub fn configure_claude(root: &Path, binary: Option<&Path>, timeout: u32) -> Result<Value> {
    let path = within(root, Path::new(SETTINGS), false)?;
    if binary.is_none() && !path.exists() {
        return claude_status(root);
    }
    let directory = path.parent().context("settings directory is unavailable")?;
    fs::create_dir_all(directory)?;
    let lock_path = within(root, Path::new(".claude/.loopsieve-hook.lock"), false)?;
    let lock = OpenOptions::new()
        .read(true)
        .write(true)
        .create(true)
        .truncate(false)
        .open(lock_path)?;
    lock_state(&lock, true)?;
    let mut settings = read_settings(&path)?;
    let before = settings.clone();
    let hooks = settings
        .as_object_mut()
        .context("Claude settings must contain an object")?
        .entry("hooks")
        .or_insert_with(|| json!({}))
        .as_object_mut()
        .context("Claude hooks must contain an object")?;
    if binary.is_none() && !hooks.contains_key(EVENT) {
        return claude_status(root);
    }
    let groups = hooks
        .entry(EVENT)
        .or_insert_with(|| json!([]))
        .as_array_mut()
        .context("Claude PostToolUse hooks must contain an array")?;
    groups.retain_mut(|group| {
        let Some(handlers) = group.get_mut("hooks").and_then(Value::as_array_mut) else {
            return true;
        };
        let before = handlers.len();
        handlers.retain(|handler| !is_managed(handler));
        before == handlers.len() || !handlers.is_empty()
    });
    if let Some(binary) = binary {
        ensure!(
            (1..=600).contains(&timeout),
            "hook timeout must be 1..=600 seconds"
        );
        let command = format!(
            "{} hook --root {}",
            shell_quote(binary)?,
            shell_quote(root)?
        );
        groups.push(json!({"matcher": "Edit|Write|MultiEdit|NotebookEdit", "hooks": [{"type":"command", "command":command, "timeout":timeout, "statusMessage":MARKER}]}));
    } else if groups.is_empty() {
        hooks.remove(EVENT);
    }
    if settings != before {
        let mut temporary = tempfile::NamedTempFile::new_in(directory)?;
        if let Ok(metadata) = path.metadata() {
            temporary
                .as_file()
                .set_permissions(metadata.permissions())?;
        }
        serde_json::to_writer_pretty(temporary.as_file_mut(), &settings)?;
        writeln!(temporary.as_file_mut())?;
        temporary.as_file().sync_all()?;
        temporary.persist(&path)?;
    }
    claude_status(root)
}

fn shell_quote(path: &Path) -> Result<String> {
    let path = path.to_str().context("hook path must be valid UTF-8")?;
    ensure!(
        !path.chars().any(char::is_control),
        "hook path contains control characters"
    );
    #[cfg(windows)]
    let path = path
        .strip_prefix(r"\\?\")
        .unwrap_or(path)
        .replace('\\', "/");
    Ok(format!("'{}'", path.replace('\'', "'\"'\"'")))
}

fn is_managed(handler: &Value) -> bool {
    handler["type"].as_str() == Some("command") && handler["statusMessage"].as_str() == Some(MARKER)
}

fn read_settings(path: &Path) -> Result<Value> {
    match fs::symlink_metadata(path) {
        Ok(meta) => {
            ensure!(meta.is_file(), "Claude settings must be a regular file");
            let content: Value = json_file(path, 1024 * 1024)?;
            ensure!(
                content.is_object(),
                "Claude settings must contain an object"
            );
            Ok(content)
        }
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(json!({})),
        Err(error) => Err(error.into()),
    }
}

pub fn mcp_servers(root: &Path) -> Result<Vec<Value>> {
    let mut result = Vec::new();
    for source in [".mcp.json", ".claude/mcp.json", ".cursor/mcp.json"] {
        let path = within(root, Path::new(source), false)?;
        if !path.try_exists()? {
            continue;
        }
        let config: Value =
            json_file(&path, 1024 * 1024).with_context(|| format!("invalid MCP file {source}"))?;
        let servers = config["mcpServers"]
            .as_object()
            .context("MCP configuration must have an mcpServers object")?;
        for (name, value) in servers {
            let protocol = match value["type"].as_str() {
                Some("stdio") => "stdio",
                Some("http") => "http",
                Some("sse") => "sse",
                None if value["command"].is_string() => "stdio",
                _ => "unknown",
            };
            result.push(json!({"name":redact(name), "source":source, "transport":protocol}));
        }
    }
    Ok(result)
}
