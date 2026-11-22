use crate::{agent::Options, install_cancel, print_json};
use anyhow::{Result, ensure};
use loopsieve_core::agent::Runtime;
use loopsieve_core::config::Config;
use loopsieve_core::diagnostics::redact;
use loopsieve_core::store::Store;
use loopsieve_core::verify::verify;
use std::io::{self, IsTerminal, Write};
use std::path::{Path, PathBuf};
use std::sync::atomic::Ordering;

pub fn show(root: &Path, config: &Config) -> Result<()> {
    let store = Store::new(root, config);
    let runtime = Runtime::open(root, config)?;
    let interactive = io::stdin().is_terminal() && io::stdout().is_terminal();
    println!(
        "LoopSieve workbench · {}",
        redact(&root.display().to_string())
    );
    overview(&store)?;
    if !interactive {
        return Ok(());
    }
    let cancelled = install_cancel()?;
    println!("Enter report, sessions, check FILE, or quit.");
    while !cancelled.load(Ordering::Relaxed) {
        let Some(line) = prompt("loopsieve> ")? else {
            break;
        };
        let line = line.trim();
        let result = match line {
            "quit" | "q" => break,
            "report" => overview(&store),
            "sessions" => runtime.list().and_then(print_json),
            "" => continue,
            _ if line.starts_with("check ") => verify(
                root,
                &[PathBuf::from(line[6..].trim())],
                config,
                &cancelled,
                None,
            )
            .map(|run| {
                println!("{}", run.context);
                if let Some(warning) = run.state_warning {
                    eprintln!("{warning}");
                }
            }),
            _ => {
                println!("Enter report, sessions, check FILE, or quit.");
                continue;
            }
        };
        if let Err(error) = result {
            eprintln!("{}", redact(&format!("{error:#}")));
        }
    }
    Ok(())
}

pub fn chat(root: &Path, config: &Config, options: Options) -> Result<()> {
    ensure!(
        io::stdin().is_terminal() && io::stdout().is_terminal(),
        "chat requires a terminal; use agent run for automation"
    );
    let runtime = Runtime::open(root, config)?;
    let cancelled = install_cancel()?;
    println!("LoopSieve local agent · Enter a task, /sessions, /resume ID, or /quit.");
    while !cancelled.load(Ordering::Relaxed) {
        let Some(line) = prompt("task> ")? else {
            break;
        };
        let task = line.trim();
        let result = match task {
            "/quit" => break,
            "/sessions" => runtime.list().and_then(print_json),
            "" => continue,
            _ if task.starts_with("/resume ") => (|| {
                let id = task[8..].trim().parse()?;
                print_json(runtime.run(id, &cancelled)?.details())
            })(),
            _ => options.create(&runtime, task).and_then(|session| {
                println!("Session {}", session.id);
                let session = runtime.run(session.id, &cancelled)?;
                println!("{:?}", session.status);
                if let Some(text) = session.last_observation() {
                    println!("{text}");
                }
                Ok(())
            }),
        };
        if let Err(error) = result {
            eprintln!("{}", redact(&format!("{error:#}")));
        }
    }
    Ok(())
}

fn overview(store: &Store) -> Result<()> {
    let state = store.read()?;
    println!(
        "Checks · {} runs · {} passed · {} failed · {} cache hits",
        state.stats.runs,
        state.stats.passed_runs,
        state.stats.failed_runs,
        state.stats.cached_checks
    );
    if let Some(last) = state.history.last() {
        println!("{}", last.run.context);
    }
    Ok(())
}

fn prompt(label: &str) -> Result<Option<String>> {
    print!("{label}");
    io::stdout().flush()?;
    let mut line = String::new();
    Ok((io::stdin().read_line(&mut line)? != 0).then_some(line))
}
