//! Bounded subprocess supervision for explicitly trusted check commands.

use crate::config::{CheckSpec, within};
use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::VecDeque;
use std::ffi::{OsStr, OsString};
use std::io::{self, Read};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::{Duration, Instant};

#[derive(Debug, Clone, Copy, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum Status {
    Pass,
    CachedPass,
    Fail,
    Timeout,
    Error,
    Blocked,
    Cancelled,
}

impl Status {
    pub fn passed(self) -> bool {
        matches!(self, Self::Pass | Self::CachedPass)
    }
}

#[derive(Debug)]
pub(crate) struct Prepared {
    pub cwd: PathBuf,
    pub argv: Vec<OsString>,
}

pub(crate) fn prepare(root: &Path, spec: &CheckSpec, files: &[PathBuf]) -> Result<Prepared> {
    let cwd = within(root, Path::new(&spec.cwd), true)?;
    ensure!(cwd.is_dir(), "check working directory must be a directory");
    let mut argv = Vec::new();
    for argument in &spec.command {
        match argument.as_str() {
            "{python}" => argv.push(std::env::var_os("LOOPSIEVE_PYTHON").unwrap_or_else(|| {
                if cfg!(windows) {
                    "python.exe".into()
                } else {
                    "python3".into()
                }
            })),
            "{files}" => {
                for file in files {
                    let relative = file.strip_prefix(&cwd).unwrap_or(file);
                    let safe = if relative.as_os_str().to_string_lossy().starts_with('-') {
                        Path::new(".").join(relative)
                    } else {
                        relative.to_path_buf()
                    };
                    argv.push(safe.into_os_string());
                }
            }
            other if other.contains("{root}") => argv.push(
                other
                    .replace(
                        "{root}",
                        root.to_str()
                            .context("workspace path must be valid UTF-8")?,
                    )
                    .into(),
            ),
            other => argv.push(other.into()),
        }
    }
    ensure!(
        argv.first().is_some_and(|a| !a.is_empty()),
        "command expands to an empty argv"
    );
    Ok(Prepared { cwd, argv })
}

pub(crate) struct Execution {
    pub status: Status,
    pub exit_code: Option<i32>,
    pub duration_ms: u64,
    pub output: String,
    pub omitted: usize,
    pub output_digest: String,
}

impl Execution {
    pub(crate) fn rejected(status: Status, message: String) -> Self {
        Self {
            status,
            exit_code: None,
            duration_ms: 0,
            output_digest: crate::digest(message.as_bytes()),
            output: message,
            omitted: 0,
        }
    }
}

struct Capture {
    limit: usize,
    head: Vec<u8>,
    tail: VecDeque<u8>,
    size: usize,
    hash: Sha256,
}

impl Capture {
    fn new(limit: usize) -> Self {
        Self {
            limit,
            head: Vec::new(),
            tail: VecDeque::new(),
            size: 0,
            hash: Sha256::new(),
        }
    }

    fn append(&mut self, data: &[u8]) {
        self.hash.update(data);
        self.size += data.len();
        let head_space = self.limit / 2 - self.head.len();
        let split = head_space.min(data.len());
        self.head.extend(&data[..split]);
        let remainder = &data[split..];
        let tail_limit = self.limit - self.limit / 2;
        if remainder.len() >= tail_limit {
            self.tail.clear();
            self.tail.extend(&remainder[remainder.len() - tail_limit..]);
        } else {
            let drop = (self.tail.len() + remainder.len()).saturating_sub(tail_limit);
            self.tail.drain(..drop);
            self.tail.extend(remainder);
        }
    }

    fn finish(mut self) -> (String, usize, String) {
        let omitted = self.size - self.head.len() - self.tail.len();
        if omitted != 0 {
            self.head
                .extend(format!("\n... {omitted} bytes omitted ...\n").as_bytes());
        }
        self.head.extend(self.tail);
        (
            String::from_utf8_lossy(&self.head).into_owned(),
            omitted,
            format!("{:x}", self.hash.finalize()),
        )
    }
}

pub(crate) fn execute(prepared: &Prepared, spec: &CheckSpec, cancelled: &AtomicBool) -> Execution {
    if cancelled.load(Ordering::Relaxed) {
        return Execution::rejected(Status::Cancelled, "check cancelled before start".into());
    }
    let start = Instant::now();
    let result = supervise(prepared, spec, cancelled);
    match result {
        Ok((status, exit_code, capture)) => {
            let (output, omitted, output_digest) = capture.finish();
            Execution {
                status,
                exit_code,
                duration_ms: start.elapsed().as_millis() as u64,
                output,
                omitted,
                output_digest,
            }
        }
        Err(error) => {
            let mut result =
                Execution::rejected(Status::Error, format!("unable to supervise check: {error}"));
            result.duration_ms = start.elapsed().as_millis() as u64;
            result
        }
    }
}

struct Supervised(Child);

impl Supervised {
    fn stop(&mut self) {
        #[cfg(unix)]
        if let Ok(pgid) = i32::try_from(self.0.id()) {
            // The child was placed in a process group whose ID is its own PID.
            unsafe { libc::kill(-pgid, libc::SIGKILL) };
        }
        let _ = self.0.kill();
        let _ = self.0.wait();
    }
}

impl Drop for Supervised {
    fn drop(&mut self) {
        if !matches!(self.0.try_wait(), Ok(Some(_))) {
            self.stop();
        }
    }
}

fn supervise(
    prepared: &Prepared,
    spec: &CheckSpec,
    cancelled: &AtomicBool,
) -> io::Result<(Status, Option<i32>, Capture)> {
    let (reader, writer) = io::pipe()?;
    let mut command = Command::new(&prepared.argv[0]);
    command
        .current_dir(&prepared.cwd)
        .args(&prepared.argv[1..])
        .stdin(Stdio::null())
        .stdout(Stdio::from(writer.try_clone()?))
        .stderr(Stdio::from(writer));
    #[cfg(unix)]
    {
        use std::os::unix::process::CommandExt;
        command.process_group(0);
    }
    let mut reader = OutputReader::new(reader)?;
    let mut child = Supervised(command.spawn()?);
    drop(command); // The parent must release its copies of the pipe writers.
    let deadline = Instant::now() + Duration::from_secs(spec.timeout_seconds);
    let mut capture = Capture::new(spec.max_output_chars);
    let mut exited_at = None;
    loop {
        let closed = reader.drain(&mut capture)?;
        let code = child.0.try_wait()?;
        if let Some(code) = code {
            let elapsed = exited_at.get_or_insert_with(Instant::now).elapsed();
            if closed || elapsed >= Duration::from_millis(150) {
                if !closed {
                    child.stop();
                }
                return Ok((
                    if code.success() {
                        Status::Pass
                    } else {
                        Status::Fail
                    },
                    code.code(),
                    capture,
                ));
            }
        } else if cancelled.load(Ordering::Relaxed) || Instant::now() >= deadline {
            let status = if cancelled.load(Ordering::Relaxed) {
                Status::Cancelled
            } else {
                Status::Timeout
            };
            child.stop();
            reader.drain(&mut capture)?;
            return Ok((status, None, capture));
        }
        std::thread::sleep(Duration::from_millis(2));
    }
}

#[cfg(unix)]
struct OutputReader(io::PipeReader);

#[cfg(unix)]
impl OutputReader {
    fn new(reader: io::PipeReader) -> io::Result<Self> {
        use std::os::fd::AsRawFd;
        let fd = reader.as_raw_fd();
        // Both operations use a descriptor owned by reader for the entire call.
        let flags = unsafe { libc::fcntl(fd, libc::F_GETFL) };
        if flags < 0 || unsafe { libc::fcntl(fd, libc::F_SETFL, flags | libc::O_NONBLOCK) } < 0 {
            return Err(io::Error::last_os_error());
        }
        Ok(Self(reader))
    }

    fn drain(&mut self, capture: &mut Capture) -> io::Result<bool> {
        let mut bytes = [0u8; 8192];
        for _ in 0..16 {
            match self.0.read(&mut bytes) {
                Ok(0) => return Ok(true),
                Ok(n) => capture.append(&bytes[..n]),
                Err(err) if err.kind() == io::ErrorKind::WouldBlock => return Ok(false),
                Err(err) if err.kind() == io::ErrorKind::Interrupted => continue,
                Err(err) => return Err(err),
            }
        }
        Ok(false)
    }
}

#[cfg(not(unix))]
struct OutputReader(std::sync::mpsc::Receiver<io::Result<Vec<u8>>>);

#[cfg(not(unix))]
impl OutputReader {
    fn new(mut reader: io::PipeReader) -> io::Result<Self> {
        let (send, receive) = std::sync::mpsc::sync_channel(8);
        std::thread::Builder::new()
            .name("check-output".into())
            .spawn(move || {
                let mut bytes = [0u8; 8192];
                loop {
                    match reader.read(&mut bytes) {
                        Ok(0) => break,
                        Ok(n) => {
                            if send.send(Ok(bytes[..n].to_vec())).is_err() {
                                break;
                            }
                        }
                        Err(error) if error.kind() == io::ErrorKind::Interrupted => continue,
                        Err(error) => {
                            let _ = send.send(Err(error));
                            break;
                        }
                    }
                }
            })?;
        Ok(Self(receive))
    }

    fn drain(&mut self, capture: &mut Capture) -> io::Result<bool> {
        use std::sync::mpsc::TryRecvError;
        for _ in 0..16 {
            match self.0.try_recv() {
                Ok(value) => capture.append(&value?),
                Err(TryRecvError::Empty) => return Ok(false),
                Err(TryRecvError::Disconnected) => return Ok(true),
            }
        }
        Ok(false)
    }
}

pub(crate) fn resolve_executable(program: &OsStr, cwd: &Path) -> Option<PathBuf> {
    let path = Path::new(program);
    if path.is_absolute() {
        return path.canonicalize().ok().filter(|p| p.is_file());
    }
    if cfg!(windows) {
        return None;
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let executable = |path: PathBuf| {
            path.metadata()
                .is_ok_and(|m| m.is_file() && m.permissions().mode() & 0o111 != 0)
        };
        if path.components().count() > 1 || program.to_str()?.contains('/') {
            return executable(cwd.join(path))
                .then(|| cwd.join(path).canonicalize().ok())
                .flatten();
        }
        let search = std::env::var_os("PATH")?;
        std::env::split_paths(&search)
            .map(|dir| cwd.join(dir).join(path))
            .find(|candidate| executable(candidate.clone()))?
            .canonicalize()
            .ok()
    }
    #[cfg(not(unix))]
    {
        None
    }
}
