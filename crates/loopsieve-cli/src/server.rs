use anyhow::{Context, Result, bail, ensure};
use clap::{Args, ValueEnum};
use loopsieve_core::inference::local_health;
use loopsieve_core::models;
use std::fs;
use std::net::{Ipv4Addr, TcpListener};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::{Duration, Instant};

#[derive(Args)]
pub struct Options {
    #[arg(long, default_value = "llama-server")]
    server: PathBuf,
    #[arg(long)]
    weights: PathBuf,
    #[arg(long)]
    sha256: Option<String>,
    #[arg(long, default_value = "local-model")]
    model: String,
    #[arg(long, default_value_t = 8080)]
    port: u16,
    #[arg(long, default_value_t = 8192)]
    context_tokens: u32,
    #[arg(long, default_value_t = 4)]
    threads: u16,
    #[arg(long, value_enum, default_value = "cpu")]
    device: Device,
    #[arg(long, default_value_t = 120)]
    startup_timeout: u64,
}

#[derive(Clone, Copy, ValueEnum)]
enum Device {
    Auto,
    Cpu,
    Gpu,
}

pub fn launch(options: &Options, cancelled: &AtomicBool) -> Result<()> {
    ensure!(
        !options.model.trim().is_empty()
            && options.model.len() <= 128
            && !options.model.chars().any(char::is_control),
        "invalid local model alias"
    );
    ensure!(
        options.port != 0
            && (1..=256).contains(&options.threads)
            && (1..=10_000_000).contains(&options.context_tokens)
            && (1..=600).contains(&options.startup_timeout),
        "invalid local model process limits"
    );
    let weights = options
        .weights
        .canonicalize()
        .context("model weights were not found")?;
    let metadata = fs::metadata(&weights)?;
    ensure!(
        weights
            .extension()
            .is_some_and(|value| value.eq_ignore_ascii_case("gguf"))
            && metadata.is_file()
            && metadata.len() > 0,
        "weights must be a nonempty GGUF file"
    );
    if let Some(sha256) = &options.sha256 {
        models::verify_file(&weights, sha256, 128 * 1024 * 1024 * 1024)?;
    }
    drop(
        TcpListener::bind((Ipv4Addr::LOCALHOST, options.port))
            .context("local model port is unavailable")?,
    );
    let gpu_layers = match options.device {
        Device::Auto => "auto",
        Device::Cpu => "0",
        Device::Gpu => "all",
    };
    let mut command = Command::new(&options.server);
    command
        .arg("--model")
        .arg(&weights)
        .args([
            "--alias",
            &options.model,
            "--host",
            "127.0.0.1",
            "--port",
            &options.port.to_string(),
            "--ctx-size",
            &options.context_tokens.to_string(),
            "--threads",
            &options.threads.to_string(),
            "--gpu-layers",
            gpu_layers,
            "--no-webui",
            "--parallel",
            "1",
        ])
        .stdin(Stdio::null());
    for (key, _) in std::env::vars_os() {
        if key
            .to_string_lossy()
            .to_ascii_uppercase()
            .starts_with("LLAMA_")
        {
            command.env_remove(key);
        }
    }
    let mut process = ServerProcess(
        command
            .spawn()
            .context("cannot start a trusted llama-server executable")?,
    );
    let deadline = Instant::now() + Duration::from_secs(options.startup_timeout);
    let mut ready = false;
    while !cancelled.load(Ordering::Relaxed) {
        if let Some(status) = process.0.try_wait()? {
            ensure!(
                ready && status.success(),
                "llama-server exited with {status}"
            );
            break;
        }
        if !ready {
            if local_health(options.port) {
                ready = true;
                println!("llama-server ready · http://127.0.0.1:{}", options.port);
            } else if Instant::now() >= deadline {
                bail!("llama-server did not become ready before its startup deadline");
            }
        }
        std::thread::sleep(Duration::from_millis(100));
    }
    Ok(())
}

struct ServerProcess(Child);
impl Drop for ServerProcess {
    fn drop(&mut self) {
        if self.0.try_wait().is_ok_and(|status| status.is_none()) {
            let _ = self.0.kill();
            let _ = self.0.wait();
        }
    }
}
