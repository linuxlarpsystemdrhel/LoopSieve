//! Versioned, local verification history with an OS lock and atomic writes.

use crate::config::{Config, within};
use crate::digest;
use crate::verify::Run;
use anyhow::{Context, Result, bail, ensure};
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
use std::fs::{self, File, OpenOptions, TryLockError};
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::time::{Duration, Instant};

const VERSION: u32 = 1;
const MAX_HISTORY: usize = 32;
const MAX_STATE: u64 = 16 * 1024 * 1024;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CacheEntry {
    pub key: String,
    pub verified_at_unix: u64,
}

#[derive(Default, Debug, Serialize, Deserialize)]
pub struct Stats {
    pub runs: u64,
    pub passed_runs: u64,
    pub failed_runs: u64,
    pub cached_checks: u64,
    pub repeats: u64,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct Entry {
    pub previous: String,
    pub digest: String,
    pub run: Run,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct State {
    pub version: u32,
    pub stats: Stats,
    #[serde(default)]
    pub(crate) epoch: u64,
    pub cache: BTreeMap<String, CacheEntry>,
    pub anchor: String,
    pub history: Vec<Entry>,
}

impl Default for State {
    fn default() -> Self {
        Self {
            version: VERSION,
            stats: Stats::default(),
            epoch: 0,
            cache: BTreeMap::new(),
            anchor: String::new(),
            history: Vec::new(),
        }
    }
}

impl State {
    pub fn verify_history(&self) -> Result<()> {
        let mut previous = self.anchor.as_str();
        for (index, entry) in self.history.iter().enumerate() {
            ensure!(
                entry.previous == previous,
                "history link broken at entry {}",
                index + 1
            );
            ensure!(
                entry.digest == entry_digest(previous, &entry.run)?,
                "history digest mismatch at entry {}",
                index + 1
            );
            previous = &entry.digest;
        }
        Ok(())
    }

    pub(crate) fn append(&mut self, run: Run) -> Result<()> {
        let previous = self
            .history
            .last()
            .map(|entry| &entry.digest)
            .unwrap_or(&self.anchor)
            .clone();
        let digest = entry_digest(&previous, &run)?;
        self.history.push(Entry {
            previous,
            digest,
            run,
        });
        while self.history.len() > MAX_HISTORY {
            self.anchor = self.history.remove(0).digest;
        }
        Ok(())
    }
}

fn entry_digest(previous: &str, run: &Run) -> Result<String> {
    Ok(digest(&serde_json::to_vec(&(previous, run))?))
}

pub struct Store {
    path: PathBuf,
    workspace: Option<PathBuf>,
}

impl Store {
    pub fn new(root: &Path, config: &Config) -> Self {
        let base = std::env::var_os("LOOPSIEVE_RUST_STATE_DIR")
            .map(PathBuf::from)
            .or_else(|| config.state_dir.clone())
            .unwrap_or_else(|| PathBuf::from(".loopsieve"));
        let key = digest(root.as_os_str().as_encoded_bytes());
        Self {
            workspace: base.is_relative().then(|| root.to_path_buf()),
            path: root
                .join(base)
                .join("rust-v1")
                .join(&key[..24])
                .join("state.json"),
        }
    }

    pub fn path(&self) -> &Path {
        &self.path
    }

    pub(crate) fn validate_paths(&self) -> Result<()> {
        for path in [&self.path, &self.path.with_extension("lock")] {
            if let Some(root) = &self.workspace {
                within(root, path, false)?;
            }
            match fs::symlink_metadata(path) {
                Ok(metadata) => ensure!(
                    metadata.is_file(),
                    "Rust state and lock must be regular files"
                ),
                Err(err) if err.kind() == std::io::ErrorKind::NotFound => (),
                Err(err) => return Err(err).context("cannot inspect Rust state path"),
            }
        }
        Ok(())
    }

    pub fn read(&self) -> Result<State> {
        self.validate_paths()?;
        let lock = match OpenOptions::new()
            .read(true)
            .write(true)
            .open(self.path.with_extension("lock"))
        {
            Ok(lock) => Some(lock),
            Err(err) if err.kind() == std::io::ErrorKind::NotFound => None,
            Err(err) => return Err(err).context("cannot read Rust state lock"),
        };
        if let Some(file) = &lock {
            lock_state(file, false)?;
        }
        self.read_unlocked()
    }

    fn read_unlocked(&self) -> Result<State> {
        let file = match File::open(&self.path) {
            Ok(file) => file,
            Err(err) if err.kind() == std::io::ErrorKind::NotFound => return Ok(State::default()),
            Err(err) => return Err(err).context("cannot read Rust state"),
        };
        let mut bytes = Vec::new();
        file.take(MAX_STATE + 1).read_to_end(&mut bytes)?;
        ensure!(bytes.len() as u64 <= MAX_STATE, "state file exceeds 16 MiB");
        let state: State = serde_json::from_slice(&bytes).context("cannot parse Rust state")?;
        ensure!(
            state.version == VERSION,
            "unsupported Rust state version {}",
            state.version
        );
        state.verify_history()?;
        Ok(state)
    }

    pub(crate) fn update<T>(&self, change: impl FnOnce(&mut State) -> Result<T>) -> Result<T> {
        self.validate_paths()?;
        let parent = self.path.parent().context("state path has no parent")?;
        fs::create_dir_all(parent)?;
        let lock = OpenOptions::new()
            .read(true)
            .write(true)
            .create(true)
            .truncate(false)
            .open(self.path.with_extension("lock"))?;
        lock_state(&lock, true)?;
        let mut state = self.read_unlocked()?;
        let result = change(&mut state)?;
        let mut bytes = serde_json::to_vec(&state)?;
        while bytes.len() as u64 >= MAX_STATE && state.history.len() > 1 {
            state.anchor = state.history.remove(0).digest;
            bytes = serde_json::to_vec(&state)?;
        }
        ensure!(
            (bytes.len() as u64) < MAX_STATE,
            "Rust state exceeds storage limit"
        );
        let mut temporary = tempfile::NamedTempFile::new_in(parent)?;
        temporary.write_all(&bytes)?;
        temporary.write_all(b"\n")?;
        temporary.as_file().sync_all()?;
        temporary
            .persist(&self.path)
            .context("cannot replace Rust state atomically")?;
        Ok(result)
    }

    pub fn invalidate(&self, check: Option<&str>) -> Result<usize> {
        self.update(|state| {
            let before = state.cache.len();
            state.epoch = state.epoch.wrapping_add(1);
            if let Some(name) = check {
                state.cache.remove(name);
            } else {
                state.cache.clear();
            }
            Ok(before - state.cache.len())
        })
    }
}

pub(crate) fn lock_state(file: &File, exclusive: bool) -> Result<()> {
    let deadline = Instant::now() + Duration::from_secs(5);
    loop {
        let attempt = if exclusive {
            file.try_lock()
        } else {
            file.try_lock_shared()
        };
        match attempt {
            Ok(()) => return Ok(()),
            Err(TryLockError::WouldBlock) if Instant::now() < deadline => {
                std::thread::sleep(Duration::from_millis(10))
            }
            Err(TryLockError::WouldBlock) => bail!("Rust state is locked by another process"),
            Err(TryLockError::Error(err)) => return Err(err).context("cannot lock Rust state"),
        }
    }
}
