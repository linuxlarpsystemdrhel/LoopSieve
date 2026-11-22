//! Sequential local model teams with declared write sets and durable per-task sessions.

use crate::agent::{Grants, Runtime, Status, validate_request, workspace_file};
use crate::config::Config;
use crate::diagnostics::redact;
use crate::inference::{Ollama, json_file};
use crate::mission::{Scheduled, Strategy, schedule};
use anyhow::{Result, ensure};
use serde::Deserialize;
use serde_json::{Value, json};
use std::collections::{BTreeMap, BTreeSet};
use std::path::Path;
use std::sync::atomic::{AtomicBool, Ordering};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Team {
    tasks: Vec<WorkItem>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct WorkItem {
    id: String,
    task: String,
    agent_id: Option<String>,
    model: Option<String>,
    max_steps: Option<u32>,
    #[serde(default)]
    depends_on: Vec<String>,
    #[serde(default)]
    write_set: Vec<String>,
    #[serde(default)]
    priority: i32,
    estimated_seconds: Option<u32>,
}

pub struct Options<'a> {
    pub model: &'a str,
    pub endpoint: &'a str,
    pub steps: u32,
    pub allow_writes: bool,
    pub allow_checks: bool,
    pub strategy: Strategy,
}

impl Team {
    pub fn load(path: &Path) -> Result<Self> {
        json_file(path, 1024 * 1024)
    }

    pub fn run(
        &self,
        root: &Path,
        config: &Config,
        options: Options<'_>,
        cancelled: &AtomicBool,
    ) -> Result<(Vec<Value>, bool)> {
        ensure!(
            (1..=20).contains(&self.tasks.len()),
            "a native team supports 1..=20 tasks"
        );
        let tasks = self
            .tasks
            .iter()
            .map(|item| Scheduled {
                id: &item.id,
                depends_on: &item.depends_on,
                priority: item.priority,
                estimated_seconds: item.estimated_seconds.unwrap_or(1),
            })
            .collect::<Vec<_>>();
        let order = schedule(&tasks, options.strategy)?;
        let mut claimed = BTreeMap::new();
        let mut prepared = Vec::new();
        for item in &self.tasks {
            let steps = item.max_steps.unwrap_or(options.steps);
            validate_request(&item.task, item.agent_id.as_deref(), steps)?;
            let provider = Ollama::new(
                item.model.as_deref().unwrap_or(options.model),
                options.endpoint,
            )?;
            ensure!(
                item.write_set.len() <= 64,
                "team write sets support at most 64 files"
            );
            ensure!(
                item.write_set.is_empty() || options.allow_writes,
                "the team must grant writes for declared write sets"
            );
            let mut scope = BTreeSet::new();
            for path in &item.write_set {
                let (canonical, _) = workspace_file(root, path)?;
                ensure!(
                    claimed.insert(canonical.clone(), &item.id).is_none(),
                    "overlapping team write sets for {canonical}"
                );
                scope.insert(canonical);
            }
            let grants = Grants {
                allow_writes: !scope.is_empty(),
                allow_checks: options.allow_checks,
                write_paths: Some(scope),
            };
            prepared.push((Some(provider), grants, steps));
        }
        let runtime = Runtime::open(root, config)?;
        let mut completed = BTreeSet::new();
        let mut outcomes = Vec::new();
        for index in order {
            let item = &self.tasks[index];
            let id = redact(&item.id);
            if cancelled.load(Ordering::Relaxed) {
                outcomes.push(json!({"id":id,"status":"CANCELLED"}));
            } else if !item
                .depends_on
                .iter()
                .all(|dependency| completed.contains(dependency))
            {
                outcomes.push(
                    json!({"id":id,"status":"BLOCKED","reason":"a dependency did not complete"}),
                );
            } else {
                let (model, grants, steps) = &mut prepared[index];
                let session = runtime.create(
                    &item.task,
                    item.agent_id.as_deref(),
                    model.take().expect("one dispatch per task"),
                    *steps,
                    std::mem::take(grants),
                )?;
                let result = runtime.run(session.id, cancelled)?;
                if result.status == Status::Completed {
                    completed.insert(item.id.clone());
                }
                outcomes.push(json!({"id":id,"status":result.status,"session":result.summary()}));
            }
        }
        Ok((outcomes, completed.len() == self.tasks.len()))
    }
}
