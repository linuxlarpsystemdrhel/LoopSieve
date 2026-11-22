use crate::{install_cancel, print_json};
use anyhow::Result;
use clap::{Args, Subcommand};
use loopsieve_core::agent::{Grants, Runtime, Session, Status, Transition};
use loopsieve_core::config::Config;
use loopsieve_core::inference::Ollama;
use loopsieve_core::legacy::ImportedSession;
use std::path::Path;
use uuid::Uuid;

#[derive(Args, Clone)]
pub struct Options {
    #[arg(long, default_value = "ollama", value_parser = ["ollama"])]
    provider: String,
    #[arg(long, default_value = "llama3.2:3b")]
    model: String,
    #[arg(long, default_value = "http://127.0.0.1:11434")]
    endpoint: String,
    #[arg(long)]
    role: Option<String>,
    #[arg(long, default_value_t = 8)]
    steps: u32,
    /// Allow exact-match patches to existing workspace files.
    #[arg(long)]
    allow_writes: bool,
    /// Allow configured project checks to execute with the current account's permissions.
    #[arg(long)]
    allow_checks: bool,
}

impl Options {
    pub fn create(&self, runtime: &Runtime<'_>, task: &str) -> Result<Session> {
        let model = Ollama::new(&self.model, &self.endpoint)?;
        runtime.create(task, self.role.as_deref(), model, self.steps, self.grants())
    }

    pub fn import(&self, runtime: &Runtime<'_>, archive: ImportedSession) -> Result<Session> {
        let model = Ollama::new(&self.model, &self.endpoint)?;
        runtime.import(
            archive,
            self.role.as_deref(),
            model,
            self.steps,
            self.grants(),
        )
    }

    fn grants(&self) -> Grants {
        Grants {
            allow_writes: self.allow_writes,
            allow_checks: self.allow_checks,
            write_paths: None,
        }
    }
}

#[derive(Subcommand)]
pub enum Command {
    /// Persist a new session without calling a model.
    New {
        task: String,
        #[command(flatten)]
        options: Options,
    },
    /// Create a new session and execute until completion or its step budget.
    Run {
        task: String,
        #[command(flatten)]
        options: Options,
    },
    /// Execute one turn in an existing session.
    Step {
        session: Uuid,
    },
    /// Continue a ready or paused session until completion or its step budget.
    Resume {
        session: Uuid,
    },
    Pause {
        session: Uuid,
    },
    Cancel {
        session: Uuid,
    },
    /// Recover a turn whose process stopped unexpectedly.
    Recover {
        session: Uuid,
    },
    Sessions,
    Inspect {
        session: Uuid,
    },
    Checkpoints {
        session: Uuid,
    },
    /// Restore an existing checkpoint if the file still matches the recorded edit.
    Restore {
        session: Uuid,
        #[arg(long)]
        checkpoint: usize,
        #[arg(long)]
        approve_restore: bool,
    },
}

pub fn handle(root: &Path, config: &Config, command: Command) -> Result<u8> {
    let runtime = Runtime::open(root, config)?;
    let session = match command {
        Command::New { task, options } => options.create(&runtime, &task)?,
        Command::Run { task, options } => {
            let cancelled = install_cancel()?;
            let session = options.create(&runtime, &task)?;
            eprintln!("Session {}", session.id);
            runtime.run(session.id, &cancelled)?
        }
        Command::Step { session } => {
            let cancelled = install_cancel()?;
            runtime.step(session, &cancelled)?
        }
        Command::Resume { session } => {
            let cancelled = install_cancel()?;
            let current = runtime.get(session)?;
            if matches!(current.status, Status::Paused | Status::Blocked) {
                runtime.transition(session, Transition::Resume)?;
            }
            runtime.run(session, &cancelled)?
        }
        Command::Pause { session } => runtime.transition(session, Transition::Pause)?,
        Command::Cancel { session } => {
            print_json(runtime.transition(session, Transition::Cancel)?.details())?;
            return Ok(0);
        }
        Command::Recover { session } => runtime.transition(session, Transition::Recover)?,
        Command::Restore {
            session,
            checkpoint,
            approve_restore,
        } => {
            print_json(
                runtime
                    .restore(session, checkpoint, approve_restore)?
                    .details(),
            )?;
            return Ok(0);
        }
        Command::Sessions => {
            print_json(runtime.list()?)?;
            return Ok(0);
        }
        Command::Inspect { session } => {
            print_json(runtime.get(session)?.details())?;
            return Ok(0);
        }
        Command::Checkpoints { session } => {
            print_json(runtime.get(session)?.checkpoint_list())?;
            return Ok(0);
        }
    };
    print_json(session.details())?;
    Ok(match session.status {
        Status::Failed | Status::Blocked => 1,
        Status::Cancelled => 130,
        _ => 0,
    })
}
