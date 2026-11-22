//! Evidence reflects the subprocess outcome, even if local state is unavailable.

use crate::config::{CheckSpec, Config, within};
use crate::diagnostics::{self, Diagnostic, bounded, redact};
use crate::runner::{self, Execution, Status};
use crate::snapshot;
use crate::store::{CacheEntry, State, Store};
use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum Delta {
    Passed,
    NewFailure,
    UnchangedFailure,
    ModifiedFailure,
    Resolved,
    Regression,
    InfrastructureFailure,
    Unverified,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Check {
    pub name: String,
    pub status: Status,
    pub exit_code: Option<i32>,
    pub duration_ms: u64,
    pub delta: Delta,
    pub fingerprint: Option<String>,
    pub omitted_bytes: usize,
    pub diagnostics: Vec<Diagnostic>,
    pub excerpt: String,
    pub cache_reason: String,
    pub verified_at_unix: Option<u64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Run {
    pub timestamp_unix: u64,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub task_id: Option<String>,
    pub files: Vec<String>,
    pub checks: Vec<Check>,
    pub context: String,
    pub reason: Option<String>,
    pub state_warning: Option<String>,
}

impl Run {
    pub fn passed(&self) -> bool {
        !self.checks.is_empty() && self.checks.iter().all(|r| r.status.passed())
    }

    pub fn exit_code(&self) -> u8 {
        if self.checks.is_empty() {
            2
        } else if self.passed() {
            0
        } else {
            1
        }
    }
}

fn now() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs()
}

fn run_check(
    root: &Path,
    spec: &CheckSpec,
    config: &Config,
    files: &[PathBuf],
    cached: Option<&CacheEntry>,
    cancelled: &AtomicBool,
) -> Result<(Check, Option<Option<CacheEntry>>)> {
    let mut update = Some(None);
    let mut cache_reason = String::new();
    let mut stamp = None;
    let execution = match runner::prepare(root, spec, files) {
        _ if cancelled.load(Ordering::Relaxed) => {
            update = None;
            Execution::rejected(Status::Cancelled, "check cancelled before start".into())
        }
        Err(err) => Execution::rejected(Status::Blocked, format!("invalid check paths: {err:#}")),
        Ok(prepared) => {
            let snapshot = snapshot::capture(root, spec, &prepared, files);
            if let Some((_, hit)) = snapshot
                .as_ref()
                .ok()
                .zip(cached)
                .filter(|(key, hit)| &hit.key == *key && !cancelled.load(Ordering::Relaxed))
            {
                stamp = Some(hit.verified_at_unix);
                update = None;
                cache_reason = "validated declared-input cache hit".into();
                Execution::rejected(Status::CachedPass, String::new())
            } else {
                let result = runner::execute(&prepared, spec, cancelled);
                if result.status == Status::Pass {
                    stamp = Some(now());
                } else if result.status == Status::Cancelled {
                    update = None;
                }
                cache_reason = match (snapshot, stamp) {
                    (Ok(before), Some(verified_at_unix)) => {
                        if snapshot::capture(root, spec, &prepared, files)
                            .is_ok_and(|after| after == before)
                        {
                            update = Some(Some(CacheEntry {
                                key: before,
                                verified_at_unix,
                            }));
                            "stable declared inputs before and after execution".into()
                        } else {
                            "inputs changed or became unverifiable during execution".into()
                        }
                    }
                    (Ok(_), None) => "only successful checks can be cached".into(),
                    (Err(err), _) => err.to_string(),
                };
                result
            }
        }
    };
    let fingerprint = if execution.status == Status::Fail {
        let content = diagnostics::identity(
            &execution.output,
            execution.omitted,
            &execution.output_digest,
        );
        Some(crate::digest(&serde_json::to_vec(&(
            spec,
            execution.exit_code,
            content,
        ))?))
    } else {
        None
    };
    let excerpt = bounded(
        &diagnostics::excerpt(&execution.output, config.max_diagnostic_lines),
        config.max_context_chars.min(4096),
    );
    let diagnostics = if execution.status.passed() {
        vec![]
    } else {
        diagnostics::records(&redact(&execution.output), root)
            .into_iter()
            .take(16)
            .map(|mut item| {
                item.file = bounded(&item.file, 512);
                item.message = bounded(&item.message, 512);
                item.severity = bounded(&item.severity, 80);
                item.code = item.code.map(|code| bounded(&code, 80));
                item
            })
            .collect()
    };
    Ok((
        Check {
            name: spec.name.clone(),
            status: execution.status,
            exit_code: execution.exit_code,
            duration_ms: execution.duration_ms,
            delta: Delta::Unverified,
            fingerprint,
            omitted_bytes: execution.omitted,
            diagnostics,
            excerpt,
            cache_reason: redact(&cache_reason),
            verified_at_unix: stamp,
        },
        update,
    ))
}

fn delta(check: &Check, previous: Option<&Check>) -> Delta {
    match check.status {
        Status::Pass | Status::CachedPass => {
            if previous.is_some_and(|last| last.status == Status::Fail) {
                Delta::Resolved
            } else {
                Delta::Passed
            }
        }
        Status::Fail => match previous.map(|last| (last.status, &last.fingerprint)) {
            Some((Status::Fail, prior)) if prior == &check.fingerprint => Delta::UnchangedFailure,
            Some((Status::Fail, _)) => Delta::ModifiedFailure,
            Some((status, _)) if status.passed() => Delta::Regression,
            _ => Delta::NewFailure,
        },
        Status::Error | Status::Timeout => Delta::InfrastructureFailure,
        Status::Blocked | Status::Cancelled => Delta::Unverified,
    }
}

fn summarize(run: &mut Run, config: &Config, state: &State) {
    let mut sections = Vec::new();
    if let Some(reason) = &run.reason {
        sections.push(format!("LoopSieve: {reason}."));
    }
    for check in &mut run.checks {
        let previous = state
            .history
            .iter()
            .rev()
            .flat_map(|entry| entry.run.checks.iter())
            .find(|prior| {
                prior.name == check.name && (prior.status.passed() || prior.status == Status::Fail)
            });
        check.delta = delta(check, previous);
        if !config.include_success_context && check.delta == Delta::Passed {
            continue;
        }
        let mut message = format!(
            "[{}] {:?} ({:?})",
            redact(&check.name),
            check.status,
            check.delta
        );
        if check.delta == Delta::UnchangedFailure && config.deduplicate_failures {
            message.push_str(" — same diagnostic; repeated output omitted from summary");
        } else if !check.status.passed() && !check.excerpt.is_empty() {
            message.push('\n');
            message.push_str(&check.excerpt);
        }
        sections.push(message);
    }
    run.context = bounded(&sections.join("\n"), config.max_context_chars);
}

pub fn verify(
    root: &Path,
    paths: &[PathBuf],
    config: &Config,
    cancelled: &AtomicBool,
    task_id: Option<&str>,
) -> Result<Run> {
    let root = &root.canonicalize().context("workspace unavailable")?;
    let mut files = BTreeSet::new();
    for file in paths {
        files.insert(
            within(root, file, false)
                .with_context(|| format!("invalid changed file: {}", file.display()))?,
        );
    }
    let files: Vec<_> = files.into_iter().collect();
    let mut run = Run {
        timestamp_unix: now(),
        task_id: task_id.map(redact),
        files: files
            .iter()
            .map(|p| redact(&p.strip_prefix(root).unwrap_or(p).to_string_lossy()))
            .collect(),
        checks: Vec::new(),
        context: String::new(),
        state_warning: None,
        reason: None,
    };
    let checks: Vec<_> = config
        .checks
        .iter()
        .filter(|spec| !files.is_empty() && spec.matches(&files))
        .collect();
    if checks.is_empty() {
        run.reason = Some(if files.is_empty() {
            "no changed files".into()
        } else {
            "no matching checks".into()
        });
        summarize(&mut run, config, &State::default());
        return Ok(run);
    }
    let store = Store::new(root, config);
    let mut read_warning = None;
    let before = store.read().unwrap_or_else(|err| {
        read_warning = Some(format!("Rust state unavailable: {err:#}"));
        State::default()
    });
    let mut updates = BTreeMap::new();
    for spec in checks {
        let (result, update) = run_check(
            root,
            spec,
            config,
            &files,
            before.cache.get(&spec.name),
            cancelled,
        )?;
        if let Some(entry) = update {
            updates.insert(spec.name.clone(), entry);
        }
        run.checks.push(result);
    }
    let save = store.update(|state| {
        summarize(&mut run, config, state);
        if state.epoch == before.epoch && read_warning.is_none() {
            for (name, entry) in updates {
                if let Some(entry) = entry {
                    state.cache.insert(name, entry);
                } else {
                    state.cache.remove(&name);
                }
            }
        }
        state.stats.runs = state.stats.runs.saturating_add(1);
        if run.passed() {
            state.stats.passed_runs = state.stats.passed_runs.saturating_add(1);
        } else {
            state.stats.failed_runs = state.stats.failed_runs.saturating_add(1);
        }
        for check in &run.checks {
            if check.status == Status::CachedPass {
                state.stats.cached_checks = state.stats.cached_checks.saturating_add(1);
            }
            if check.delta == Delta::UnchangedFailure && config.deduplicate_failures {
                state.stats.repeats = state.stats.repeats.saturating_add(1);
            }
        }
        run.state_warning = read_warning;
        state.append(run.clone())
    });
    if let Err(err) = save {
        summarize(&mut run, config, &State::default());
        run.state_warning = Some(redact(&format!("could not save Rust state: {err:#}")));
    }
    Ok(run)
}
