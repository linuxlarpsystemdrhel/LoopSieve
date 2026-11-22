mod agent;
mod hook;
mod models;
mod server;
mod web;
mod workbench;

use anyhow::{Context, Result, ensure};
use clap::{Parser, Subcommand, ValueEnum};
use loopsieve_core::catalog;
use loopsieve_core::config::{Config, find_root};
use loopsieve_core::diagnostics::{benchmark, redact};
use loopsieve_core::inference::{LocalModelConfig, explain};
use loopsieve_core::integration::{claude_status, configure_claude, mcp_servers};
use loopsieve_core::legacy;
use loopsieve_core::mission::{Mission, Strategy, TaskStatus};
use loopsieve_core::store::Store;
use loopsieve_core::team::{Options as TeamOptions, Team};
use loopsieve_core::toolkit;
use loopsieve_core::verify::verify;
use serde_json::json;
use std::fs::File;
use std::io::{self, Write};
use std::path::{Path, PathBuf};
use std::process::ExitCode;
use std::sync::{
    Arc,
    atomic::{AtomicBool, Ordering},
};

#[derive(Parser)]
#[command(
    name = "loopsieve",
    version,
    about = "Local verification, diagnostics, and coding agents"
)]
struct Cli {
    /// Use this directory as the workspace root.
    #[arg(long, global = true)]
    root: Option<PathBuf>,
    #[command(subcommand)]
    command: Option<Action>,
}

#[derive(Subcommand)]
enum Action {
    /// Read a Claude Code post-edit hook event from stdin.
    Hook,
    /// Detect project checks and create a configuration.
    Init,
    /// Run trusted project checks for the listed changed files.
    Check {
        #[arg(value_name = "FILE")]
        files: Vec<PathBuf>,
        #[arg(long)]
        json: bool,
        /// Ask a configured local llama.cpp server for advisory text on failures.
        #[arg(long, requires = "llm_config")]
        explain: bool,
        #[arg(long, requires = "explain")]
        llm_config: Option<PathBuf>,
        #[arg(long, requires = "explain")]
        prompt_cache: bool,
    },
    /// Show local verification history.
    Report {
        #[arg(long)]
        json: bool,
    },
    /// Validate the workspace configuration and examine the state file.
    Doctor,
    /// Run an offline diagnostic fixture.
    Benchmark {
        fixture: PathBuf,
        #[arg(long)]
        json: bool,
    },
    /// Inspect or invalidate the Rust verification cache.
    Cache {
        #[command(subcommand)]
        command: Cache,
    },
    /// Export or validate the retained verification evidence.
    Evidence {
        #[command(subcommand)]
        command: Evidence,
    },
    /// Validate and order a declarative check mission without executing checks.
    Plan {
        manifest: PathBuf,
        #[arg(long, value_enum, default_value = "fifo")]
        strategy: Scheduling,
    },
    /// Execute a trusted check mission.
    Run {
        manifest: PathBuf,
        #[arg(long, value_enum, default_value = "fifo")]
        strategy: Scheduling,
    },
    /// Create or manage persistent local Ollama agent sessions.
    Agent {
        #[command(subcommand)]
        command: agent::Command,
    },
    /// Inspect or select the bundled agent roles.
    Agents {
        #[arg(value_enum, default_value = "list")]
        action: RoleAction,
        value: Option<String>,
    },
    /// View bundled provider profiles and their verification status.
    Providers { query: Option<String> },
    /// Inspect bundled workflows and plugins as catalog metadata.
    Catalog {
        group: CatalogGroup,
        id: Option<String>,
    },
    /// Inspect model profiles, estimates and local model files.
    Models {
        #[command(subcommand)]
        action: Option<models::Command>,
    },
    /// Estimate model memory for a quantization and context length.
    Quantization {
        #[arg(default_value = "llama3.2:3b")]
        model: String,
        #[arg(long, default_value = "q4_k_m")]
        quantization: String,
        #[arg(long)]
        context: Option<u64>,
    },
    /// Open the native terminal workbench.
    #[command(visible_alias = "ui")]
    Tui,
    /// Start or continue a local agent from the terminal.
    Chat {
        #[command(flatten)]
        options: agent::Options,
    },
    /// View or configure the native hook in local Claude Code settings.
    Claude {
        #[arg(value_enum, default_value = "status")]
        action: HookAction,
        #[arg(long, default_value_t = 180)]
        timeout: u32,
    },
    /// Install the local Claude Code hook.
    InstallHook {
        #[arg(long, default_value_t = 180)]
        timeout: u32,
    },
    /// Remove the native hook and preserve unrelated hooks.
    UninstallHook,
    /// Inspect project MCP declarations without contacting servers.
    Mcp {
        #[arg(default_value = "list", value_parser = ["list"])]
        action: String,
    },
    /// Inspect a previous Python installation's data in read-only mode.
    Legacy {
        #[command(subcommand)]
        action: LegacyAction,
    },
    /// List or run supported read-only tools.
    Tools {
        #[arg(default_value = "list", value_parser = ["list", "run"])]
        action: String,
        tool: Option<String>,
        #[arg(long, default_value = "{}")]
        args: String,
    },
    /// Inspect CPU, memory and available GPU metadata.
    Hardware,
    /// Serve the read-only dashboard on 127.0.0.1.
    Web {
        #[arg(long, default_value_t = 8765)]
        port: u16,
    },
    /// Execute a sequential team of local model sessions with dependencies.
    Team {
        manifest: PathBuf,
        #[arg(long, default_value = "llama3.2:3b")]
        model: String,
        #[arg(long, default_value = "http://127.0.0.1:11434")]
        endpoint: String,
        #[arg(long, default_value_t = 8)]
        steps: u32,
        #[arg(long, value_enum, default_value = "fifo")]
        strategy: Scheduling,
        #[arg(long)]
        allow_writes: bool,
        #[arg(long)]
        allow_checks: bool,
    },
}

#[derive(Subcommand)]
enum LegacyAction {
    Sessions {
        database: PathBuf,
    },
    Report {
        state: PathBuf,
    },
    /// Import observations and current changed paths into a new native session.
    Import {
        database: PathBuf,
        session_id: String,
        #[command(flatten)]
        options: agent::Options,
    },
}

#[derive(Clone, Copy, ValueEnum)]
enum HookAction {
    Status,
    Install,
    Uninstall,
}

#[derive(Clone, Copy, ValueEnum)]
enum RoleAction {
    List,
    Show,
    Select,
}

#[derive(Clone, Copy, ValueEnum)]
enum CatalogGroup {
    Skills,
    Plugins,
    Technologies,
    Innovations,
}

impl CatalogGroup {
    fn name(self) -> &'static str {
        match self {
            Self::Skills => "skills",
            Self::Plugins => "plugins",
            Self::Technologies => "technologies",
            Self::Innovations => "innovations",
        }
    }
}

#[derive(Subcommand)]
enum Cache {
    Inspect,
    Invalidate {
        #[arg(long)]
        check: Option<String>,
    },
}

#[derive(Subcommand)]
enum Evidence {
    Export,
    Verify,
}

#[derive(Clone, Copy, ValueEnum)]
enum Scheduling {
    Fifo,
    Priority,
    CriticalPath,
}

impl From<Scheduling> for Strategy {
    fn from(value: Scheduling) -> Self {
        match value {
            Scheduling::Fifo => Self::Fifo,
            Scheduling::Priority => Self::Priority,
            Scheduling::CriticalPath => Self::CriticalPath,
        }
    }
}

fn print_json(value: impl serde::Serialize) -> Result<()> {
    let mut out = io::stdout().lock();
    serde_json::to_writer_pretty(&mut out, &value)?;
    writeln!(out)?;
    Ok(())
}

fn root(path: Option<PathBuf>) -> Result<PathBuf> {
    if let Some(path) = path {
        let path = path
            .canonicalize()
            .context("explicit workspace is unavailable")?;
        ensure!(path.is_dir(), "workspace must be a directory");
        Ok(path)
    } else {
        find_root(&std::env::current_dir()?)
    }
}

fn install_cancel() -> Result<Arc<AtomicBool>> {
    let cancelled = Arc::new(AtomicBool::new(false));
    let signal = Arc::clone(&cancelled);
    ctrlc::set_handler(move || signal.store(true, Ordering::Relaxed))
        .context("cannot register cancellation handler")?;
    Ok(cancelled)
}

fn open(path: &Path) -> Result<File> {
    File::open(path).with_context(|| format!("cannot open {}", path.display()))
}

fn execute(cli: Cli) -> Result<u8> {
    let command = cli.command.unwrap_or(Action::Tui);
    match &command {
        Action::Hook => return hook::handle(cli.root),
        Action::Benchmark { fixture, json } => {
            let result = benchmark(open(fixture)?)?;
            if *json {
                print_json(result)?;
            } else {
                println!(
                    "{} iterations, {} repeated diagnostics, {:.2}% diagnostic characters reduced",
                    result.iterations,
                    result.repeated_failures_suppressed,
                    100.0 * result.diagnostic_context_reduction_ratio
                );
            }
            return Ok(0);
        }
        Action::Plan { manifest, strategy } => {
            let mission = Mission::load(open(manifest)?)?;
            let order = mission.order((*strategy).into())?;
            print_json(
                order
                    .iter()
                    .map(|&i| redact(&mission.tasks[i].id))
                    .collect::<Vec<_>>(),
            )?;
            return Ok(0);
        }
        Action::Agents { action, value } => {
            let value = value.as_deref().unwrap_or_default();
            match action {
                RoleAction::List => print_json(catalog::entries("agents")?.iter().filter(|item| catalog_matches(item, value)).map(|item|
                    json!({"id": item["id"], "name": item["name"], "area": item["specialization"]})).collect::<Vec<_>>())?,
                RoleAction::Show => print_json(catalog::entry("agents", value)?)?,
                RoleAction::Select => print_json(catalog::select_role(value)?)?,
            }
            return Ok(0);
        }
        Action::Providers { query } => {
            print_json(
                catalog::entries("providers")?
                    .iter()
                    .filter(|item| catalog_matches(item, query.as_deref().unwrap_or_default()))
                    .collect::<Vec<_>>(),
            )?;
            return Ok(0);
        }
        Action::Catalog { group, id } => {
            if let Some(id) = id {
                print_json(catalog::entry(group.name(), id)?)?;
            } else {
                print_json(catalog::entries(group.name())?)?;
            }
            return Ok(0);
        }
        Action::Models { action } => return models::handle(action.as_ref(), cli.root),
        Action::Quantization {
            model,
            quantization,
            context,
        } => {
            models::estimate(model, quantization, *context)?;
            return Ok(0);
        }
        Action::Legacy { action } => {
            match action {
                LegacyAction::Sessions { database } => print_json(legacy::sessions(database)?)?,
                LegacyAction::Report { state } => {
                    print_json(legacy::verification_statistics(state)?)?
                }
                LegacyAction::Import {
                    database,
                    session_id,
                    options,
                } => {
                    let root = root(cli.root)?;
                    let config = Config::load(&root)?;
                    let runtime = loopsieve_core::agent::Runtime::open(&root, &config)?;
                    print_json(
                        options
                            .import(&runtime, legacy::session(database, session_id)?)?
                            .details(),
                    )?;
                }
            }
            return Ok(0);
        }
        _ => (),
    }
    let root = root(cli.root)?;
    if matches!(command, Action::Init) {
        Config::detect(&root).write_new(&root)?;
        println!("Created {}", root.join(".loopsieve.json").display());
        return Ok(0);
    }
    let config = Config::load(&root)?;
    let store = Store::new(&root, &config);
    match command {
        Action::Check {
            files,
            json,
            explain: _,
            llm_config,
            prompt_cache,
        } => {
            let model = llm_config
                .as_deref()
                .map(LocalModelConfig::load)
                .transpose()
                .context("invalid local model configuration")?;
            let cancelled = install_cancel()?;
            let report = verify(&root, &files, &config, &cancelled, None)?;
            let code = report.exit_code();
            let advice = match model
                .as_ref()
                .filter(|_| !cancelled.load(Ordering::Relaxed))
            {
                Some(config) => explain(&report, config, prompt_cache),
                None => Ok(None),
            };
            if json {
                let mut output = serde_json::to_value(&report)?;
                match advice {
                    Ok(Some(advice)) => output["advice"] = json!(advice),
                    Err(error) => output["advice_error"] = json!(redact(&format!("{error:#}"))),
                    _ => (),
                }
                print_json(output)?;
            } else {
                if !report.context.is_empty() {
                    println!("{}", report.context);
                }
                if let Some(warning) = report.state_warning {
                    eprintln!("LoopSieve: {warning}");
                }
                match advice {
                    Ok(Some(advice)) => {
                        println!("\nLocal model suggestion (unverified)\n{}", advice.text)
                    }
                    Err(error) => {
                        eprintln!("Local model unavailable: {}", redact(&format!("{error:#}")))
                    }
                    _ => (),
                }
            }
            return Ok(code);
        }
        Action::Report { json } => {
            let state = store.read()?;
            if json {
                print_json(state)?;
            } else {
                println!(
                    "Runs: {} · Passed: {} · Failed: {} · Cache hits: {}",
                    state.stats.runs,
                    state.stats.passed_runs,
                    state.stats.failed_runs,
                    state.stats.cached_checks
                );
                if let Some(last) = state.history.last() {
                    println!("{}", last.run.context);
                }
            }
        }
        Action::Doctor => {
            let state = store.read()?;
            println!(
                "Workspace: {}\nConfiguration: {} checks\nRust state: {} ({} retained runs)",
                root.display(),
                config.checks.len(),
                store.path().display(),
                state.history.len()
            );
        }
        Action::Cache {
            command: Cache::Inspect,
        } => print_json(store.read()?.cache)?,
        Action::Cache {
            command: Cache::Invalidate { check },
        } => println!(
            "Invalidated {} Rust cache entries.",
            store.invalidate(check.as_deref())?
        ),
        Action::Evidence {
            command: Evidence::Export,
        } => print_json(store.read()?)?,
        Action::Evidence {
            command: Evidence::Verify,
        } => println!(
            "Verified {} retained evidence records.",
            store.read()?.history.len()
        ),
        Action::Run { manifest, strategy } => {
            let mission = Mission::load(open(&manifest)?)?;
            let cancelled = install_cancel()?;
            let outcomes = mission.run(&root, &config, strategy.into(), &cancelled)?;
            let code = u8::from(
                outcomes
                    .iter()
                    .any(|task| task.status != TaskStatus::Verified),
            );
            print_json(outcomes)?;
            return Ok(code);
        }
        Action::Agent { command } => return agent::handle(&root, &config, command),
        Action::Tui => workbench::show(&root, &config)?,
        Action::Chat { options } => workbench::chat(&root, &config, options)?,
        Action::Claude { action, timeout } => match action {
            HookAction::Status => print_json(claude_status(&root)?)?,
            HookAction::Install => print_json(configure_claude(
                &root,
                Some(&std::env::current_exe()?),
                timeout,
            )?)?,
            HookAction::Uninstall => print_json(configure_claude(&root, None, 0)?)?,
        },
        Action::InstallHook { timeout } => print_json(configure_claude(
            &root,
            Some(&std::env::current_exe()?),
            timeout,
        )?)?,
        Action::UninstallHook => print_json(configure_claude(&root, None, 0)?)?,
        Action::Mcp { action: _ } => print_json(mcp_servers(&root)?)?,
        Action::Tools { action, tool, args } => {
            if action == "list" {
                print_json(
                    toolkit::TOOLS
                        .iter()
                        .map(|(name, description)| json!({"name":name,"description":description}))
                        .collect::<Vec<_>>(),
                )?;
            } else {
                let name = tool.context("tool name is required")?;
                let result = toolkit::run(
                    &root,
                    &name,
                    serde_json::from_str(&args).context("invalid tool arguments")?,
                )?;
                print_json(json!({"tool":name,"result":result}))?;
            }
        }
        Action::Hardware => print_json(toolkit::hardware(&root))?,
        Action::Web { port } => {
            let cancelled = install_cancel()?;
            web::launch(&root, &config, port, &cancelled)?;
        }
        Action::Team {
            manifest,
            model,
            endpoint,
            steps,
            strategy,
            allow_writes,
            allow_checks,
        } => {
            let team = Team::load(&manifest)?;
            let cancelled = install_cancel()?;
            let options = TeamOptions {
                model: &model,
                endpoint: &endpoint,
                steps,
                allow_writes,
                allow_checks,
                strategy: strategy.into(),
            };
            let (tasks, complete) = team.run(&root, &config, options, &cancelled)?;
            print_json(json!({"complete":complete,"tasks":tasks}))?;
            return Ok(u8::from(!complete));
        }
        Action::Init
        | Action::Benchmark { .. }
        | Action::Plan { .. }
        | Action::Hook
        | Action::Agents { .. }
        | Action::Providers { .. }
        | Action::Catalog { .. }
        | Action::Models { .. }
        | Action::Quantization { .. }
        | Action::Legacy { .. } => {
            unreachable!()
        }
    }
    Ok(0)
}

fn catalog_matches(item: &serde_json::Value, query: &str) -> bool {
    if query.is_empty() {
        return true;
    }
    let query = query.to_lowercase();
    ["id", "name", "specialization"].iter().any(|key| {
        item[key]
            .as_str()
            .is_some_and(|value| value.to_lowercase().contains(&query))
    })
}

pub fn main() -> ExitCode {
    match execute(Cli::parse()) {
        Ok(code) => ExitCode::from(code),
        Err(error) => {
            eprintln!("LoopSieve: {}", redact(&format!("{error:#}")));
            ExitCode::from(2)
        }
    }
}
