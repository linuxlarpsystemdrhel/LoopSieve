use crate::{install_cancel, print_json, root};
use anyhow::{Result, ensure};
use loopsieve_core::config::Config;
use loopsieve_core::diagnostics::redact;
use loopsieve_core::verify::verify;
use serde_json::{Value, json};
use std::io::{self, Read};
use std::path::PathBuf;

pub fn handle(workspace: Option<PathBuf>) -> Result<u8> {
    let mut payload = Vec::new();
    io::stdin()
        .lock()
        .take(1024 * 1024 + 1)
        .read_to_end(&mut payload)?;
    let input = if payload.len() <= 1024 * 1024 {
        serde_json::from_slice::<Value>(&payload).ok()
    } else {
        None
    };
    let Some(input) = input.filter(Value::is_object) else {
        print_json(json!({}))?;
        return Ok(0);
    };
    let event = match input["hook_event_name"].as_str() {
        Some("PostToolBatch") => "PostToolBatch",
        Some("PostToolUse") => "PostToolUse",
        _ => {
            print_json(json!({}))?;
            return Ok(0);
        }
    };
    let context = match context(workspace, &input, event) {
        Ok(text) => text,
        Err(error) => redact(&format!(
            "LoopSieve could not run local verification: {error:#}"
        )),
    };
    if context.is_empty() {
        print_json(json!({}))?;
    } else {
        print_json(
            json!({"hookSpecificOutput": {"hookEventName": event, "additionalContext": context}}),
        )?;
    }
    Ok(0)
}

fn context(workspace: Option<PathBuf>, input: &Value, event: &str) -> Result<String> {
    let mut files = Vec::new();
    let calls = if event == "PostToolBatch" {
        input["tool_calls"]
            .as_array()
            .map(Vec::as_slice)
            .unwrap_or_default()
    } else {
        std::slice::from_ref(input)
    };
    for call in calls {
        if matches!(
            call["tool_name"].as_str(),
            Some("Edit" | "Write" | "MultiEdit" | "NotebookEdit")
        ) && let Some(path) = ["file_path", "path", "notebook_path"]
            .iter()
            .find_map(|key| {
                call["tool_input"][key]
                    .as_str()
                    .filter(|value| !value.trim().is_empty())
            })
        {
            files.push(PathBuf::from(path));
        }
    }
    if files.is_empty() {
        return Ok(String::new());
    }
    ensure!(files.len() <= 256, "hook received too many changed files");
    // The caller chooses the trusted workspace. Payload cwd cannot select it.
    let workspace = root(workspace)?;
    let config = Config::load(&workspace)?;
    let cancelled = install_cancel()?;
    let run = verify(&workspace, &files, &config, &cancelled, None)?;
    let mut text = run.context;
    if let Some(warning) = run.state_warning {
        if !text.is_empty() {
            text.push('\n');
        }
        text.push_str(&warning);
    }
    Ok(text)
}
