use crate::{print_json, root};
use anyhow::Result;
use clap::Subcommand;
use loopsieve_core::catalog;
use loopsieve_core::inference::Ollama;
use loopsieve_core::models::{self, DEFAULT_LIMIT, Download};
use serde_json::json;
use std::path::PathBuf;

#[derive(Subcommand)]
pub enum Command {
    /// List the bundled model catalog or query installed models at a supplied endpoint.
    List {
        #[arg(long)]
        endpoint: Option<String>,
    },
    Status {
        #[arg(long, default_value = "http://127.0.0.1:11434")]
        endpoint: String,
    },
    Show {
        model: String,
    },
    Memory {
        model: String,
        #[arg(long, default_value = "q4_k_m")]
        quantization: String,
        #[arg(long)]
        context: Option<u64>,
    },
    Verify {
        path: PathBuf,
        #[arg(long)]
        sha256: String,
        #[arg(long, default_value_t = DEFAULT_LIMIT)]
        max_bytes: u64,
    },
    /// Start a trusted llama.cpp executable bound to loopback.
    Serve {
        #[command(flatten)]
        options: crate::server::Options,
    },
    Download {
        filename: String,
        #[arg(long)]
        url: String,
        #[arg(long)]
        sha256: String,
        #[arg(long)]
        license: String,
        #[arg(long)]
        accept_license: bool,
        #[arg(long)]
        approve_download: bool,
        #[arg(long, default_value_t = DEFAULT_LIMIT)]
        max_bytes: u64,
    },
}

pub fn handle(command: Option<&Command>, workspace: Option<PathBuf>) -> Result<u8> {
    match command {
        None | Some(Command::List { endpoint: None }) => print_json(catalog::entries("models")?)?,
        Some(Command::List {
            endpoint: Some(endpoint),
        }) => print_json(Ollama::new("list", endpoint)?.models()?)?,
        Some(Command::Status { endpoint }) => {
            let models = Ollama::new("list", endpoint)?.models()?;
            print_json(json!({"provider":"ollama", "status":"READY", "model_count":models.len()}))?;
        }
        Some(Command::Show { model }) => print_json(catalog::entry("models", model)?)?,
        Some(Command::Memory {
            model,
            quantization,
            context,
        }) => estimate(model, quantization, *context)?,
        Some(Command::Verify {
            path,
            sha256,
            max_bytes,
        }) => print_json(models::verify_file(path, sha256, *max_bytes)?)?,
        Some(Command::Serve { options }) => {
            let cancel = crate::install_cancel()?;
            crate::server::launch(options, &cancel)?;
        }
        Some(Command::Download {
            filename,
            url,
            sha256,
            license,
            accept_license,
            approve_download,
            max_bytes,
        }) => {
            let root = root(workspace)?;
            let request = Download {
                name: filename,
                url,
                sha256,
                license,
                accepted: *accept_license,
                approved: *approve_download,
                limit: *max_bytes,
            };
            print_json(models::download(&root, request)?)?;
        }
    }
    Ok(0)
}

pub fn estimate(model: &str, quantization: &str, context: Option<u64>) -> Result<()> {
    print_json(models::estimate(model, quantization, context)?)
}
