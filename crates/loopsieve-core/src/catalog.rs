//! Reuse the project manifests as data without requiring a Python installation.

use anyhow::{Context, Result, ensure};
use serde_json::Value;
use std::sync::OnceLock;

fn catalog() -> &'static Value {
    static CATALOG: OnceLock<Value> = OnceLock::new();
    CATALOG.get_or_init(|| {
        serde_json::from_str(include_str!(concat!(env!("OUT_DIR"), "/catalog.json")))
            .expect("build-time validated catalog")
    })
}

pub fn entries(group: &str) -> Result<&'static [Value]> {
    let document = &catalog()[group];
    let key = if group == "innovations" {
        "items"
    } else {
        group
    };
    document
        .as_array()
        .or_else(|| document[key].as_array())
        .map(Vec::as_slice)
        .context("unknown catalog group")
}

pub fn entry(group: &str, id: &str) -> Result<&'static Value> {
    entries(group)?
        .iter()
        .find(|item| item["id"].as_str() == Some(id))
        .context("unknown catalog entry")
}

pub fn select_role(task: &str) -> Result<&'static Value> {
    let tokens: std::collections::BTreeSet<_> = task
        .split(|character: char| !character.is_alphanumeric())
        .filter(|token| !token.is_empty())
        .map(str::to_lowercase)
        .collect();
    let mut best = entry("agents", "001-chief-architect")?;
    let mut most = 0;
    for role in entries("agents")? {
        let hits = role["keywords"]
            .as_array()
            .into_iter()
            .flatten()
            .filter_map(Value::as_str)
            .filter(|word| {
                word.split_whitespace()
                    .all(|token| tokens.contains(&token.to_lowercase()))
            })
            .count();
        if hits > most {
            best = role;
            most = hits;
        }
    }
    ensure!(best["id"].is_string(), "selected role has no ID");
    Ok(best)
}
