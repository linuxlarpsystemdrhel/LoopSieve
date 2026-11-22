//! Declarative scheduling for named verification tasks.

use crate::config::Config;
use crate::verify::{Run, verify};
use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};
use std::io::Read;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};

#[derive(Debug, Deserialize)]
pub struct Mission {
    pub tasks: Vec<Task>,
}

#[derive(Debug, Deserialize)]
pub struct Task {
    pub id: String,
    pub files: Vec<PathBuf>,
    pub checks: Vec<String>,
    #[serde(default)]
    pub depends_on: Vec<String>,
    #[serde(default)]
    pub priority: i32,
    #[serde(default = "default_estimate")]
    pub estimated_seconds: u32,
}

fn default_estimate() -> u32 {
    1
}

#[derive(Debug, Clone, Copy)]
pub enum Strategy {
    Fifo,
    Priority,
    CriticalPath,
}

#[derive(Debug, Serialize, PartialEq, Eq)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum TaskStatus {
    Verified,
    Failed,
    Blocked,
    Cancelled,
    Unverified,
}

#[derive(Debug, Serialize)]
pub struct Outcome {
    pub id: String,
    pub status: TaskStatus,
    pub reason: Option<String>,
    pub run: Option<Run>,
}

impl Mission {
    pub fn load(reader: impl Read) -> Result<Self> {
        let mut bytes = Vec::new();
        reader.take(1024 * 1024 + 1).read_to_end(&mut bytes)?;
        ensure!(bytes.len() <= 1024 * 1024, "mission exceeds 1 MiB");
        let mission = serde_json::from_slice(&bytes)?;
        Ok(mission)
    }

    pub fn order(&self, strategy: Strategy) -> Result<Vec<usize>> {
        for task in &self.tasks {
            ensure!(
                !task.checks.is_empty() && !task.files.is_empty(),
                "task {} needs checks and files",
                task.id
            );
        }
        let scheduled: Vec<_> = self
            .tasks
            .iter()
            .map(|task| Scheduled {
                id: &task.id,
                depends_on: &task.depends_on,
                priority: task.priority,
                estimated_seconds: task.estimated_seconds,
            })
            .collect();
        schedule(&scheduled, strategy)
    }

    pub fn run(
        &self,
        root: &Path,
        config: &Config,
        strategy: Strategy,
        cancelled: &AtomicBool,
    ) -> Result<Vec<Outcome>> {
        let order = self.order(strategy)?;
        // Validate every task's check references before starting any command.
        let mut configs = Vec::new();
        for task in &self.tasks {
            let mut task_config = config.clone();
            task_config
                .checks
                .retain(|check| task.checks.contains(&check.name));
            ensure!(
                task_config.checks.len() == task.checks.len()
                    && task_config
                        .checks
                        .iter()
                        .all(|check| check.matches(&task.files)),
                "task {} references an unknown, disabled, repeated or nonmatching check",
                task.id
            );
            for path in &task.files {
                crate::config::within(root, path, false)?;
            }
            configs.push(task_config);
        }
        let mut outcomes = Vec::new();
        let mut verified = BTreeSet::new();
        for i in order {
            let task = &self.tasks[i];
            let (status, reason, run) = if cancelled.load(Ordering::Relaxed) {
                (
                    TaskStatus::Cancelled,
                    Some("mission cancelled".into()),
                    None,
                )
            } else if task
                .depends_on
                .iter()
                .any(|parent| !verified.contains(parent))
            {
                (
                    TaskStatus::Blocked,
                    Some("a dependency has no verified outcome".into()),
                    None,
                )
            } else {
                let run = verify(root, &task.files, &configs[i], cancelled, Some(&task.id))?;
                let status = if cancelled.load(Ordering::Relaxed) {
                    TaskStatus::Cancelled
                } else if !run.checks.is_empty() && !run.passed() {
                    TaskStatus::Failed
                } else if run.state_warning.is_some() || run.checks.is_empty() {
                    TaskStatus::Unverified
                } else {
                    TaskStatus::Verified
                };
                (status, None, Some(run))
            };
            if status == TaskStatus::Verified {
                verified.insert(task.id.clone());
            }
            outcomes.push(Outcome {
                id: crate::diagnostics::redact(&task.id),
                status,
                reason,
                run,
            });
        }
        Ok(outcomes)
    }
}

pub(crate) struct Scheduled<'a> {
    pub id: &'a str,
    pub depends_on: &'a [String],
    pub priority: i32,
    pub estimated_seconds: u32,
}

pub(crate) fn schedule(tasks: &[Scheduled<'_>], strategy: Strategy) -> Result<Vec<usize>> {
    ensure!(
        (1..=256).contains(&tasks.len()),
        "mission must have 1..=256 tasks"
    );
    let mut identifiers = BTreeMap::new();
    for (index, task) in tasks.iter().enumerate() {
        ensure!(
            !task.id.trim().is_empty()
                && task.id.len() <= 128
                && !task.id.contains(char::is_control),
            "invalid task ID"
        );
        ensure!(
            task.estimated_seconds > 0,
            "estimated_seconds must be positive"
        );
        ensure!(
            identifiers.insert(task.id, index).is_none(),
            "duplicate task {}",
            task.id
        );
    }
    let mut parents = vec![BTreeSet::new(); tasks.len()];
    let mut children = vec![Vec::new(); tasks.len()];
    for (index, task) in tasks.iter().enumerate() {
        for id in task.depends_on {
            let parent = *identifiers
                .get(id.as_str())
                .with_context(|| format!("unknown dependency {id}"))?;
            ensure!(parents[index].insert(parent), "duplicate dependency {id}");
            children[parent].push(index);
        }
    }
    let linear = topological(&parents, &children, |i| i)?;
    let mut longest = vec![0u64; tasks.len()];
    for &i in linear.iter().rev() {
        longest[i] = u64::from(tasks[i].estimated_seconds)
            + children[i]
                .iter()
                .map(|&c| longest[c])
                .max()
                .unwrap_or_default();
    }
    match strategy {
        Strategy::Fifo => Ok(linear),
        Strategy::Priority => topological(&parents, &children, |i| {
            (std::cmp::Reverse(tasks[i].priority), i)
        }),
        Strategy::CriticalPath => {
            topological(&parents, &children, |i| (std::cmp::Reverse(longest[i]), i))
        }
    }
}

fn topological<K: Ord>(
    parents: &[BTreeSet<usize>],
    children: &[Vec<usize>],
    key: impl Fn(usize) -> K,
) -> Result<Vec<usize>> {
    let mut pending: Vec<_> = parents.iter().map(BTreeSet::len).collect();
    let mut ready: BTreeSet<_> = pending
        .iter()
        .enumerate()
        .filter(|&(_, &count)| count == 0)
        .map(|(i, _)| (key(i), i))
        .collect();
    let mut result = Vec::new();
    while let Some((_, index)) = ready.pop_first() {
        result.push(index);
        for &child in &children[index] {
            pending[child] -= 1;
            if pending[child] == 0 {
                ready.insert((key(child), child));
            }
        }
    }
    ensure!(
        result.len() == parents.len(),
        "mission dependency graph contains a cycle"
    );
    Ok(result)
}
