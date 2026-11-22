use anyhow::{Context, Result, bail, ensure};
use serde::{Deserialize, Deserializer, Serialize, de::Error};
use std::collections::BTreeSet;
use std::fs::{self, File};
use std::io::{Read, Write};
use std::path::{Component, Path, PathBuf};

pub const FILE_NAME: &str = ".loopsieve.json";
pub(crate) const CONFIG_INPUTS: &[&str] = &[
    FILE_NAME,
    "Cargo.toml",
    "Cargo.lock",
    "rust-toolchain.toml",
    "rust-toolchain",
    "pyproject.toml",
    "setup.cfg",
    "requirements.txt",
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "go.mod",
    "go.sum",
    "Makefile",
    "ruff.toml",
    "pytest.ini",
    "tsconfig.json",
    ".cargo/config.toml",
    ".cargo/config",
];

fn version() -> u32 {
    1
}
fn context_limit() -> usize {
    9000
}
fn lines_limit() -> usize {
    36
}
fn timeout() -> u64 {
    120
}
fn output_limit() -> usize {
    12000
}
fn current_dir() -> String {
    ".".into()
}
fn yes() -> bool {
    true
}

fn integer<'de, D, T>(deserializer: D) -> Result<T, D::Error>
where
    D: Deserializer<'de>,
    T: Deserialize<'de> + std::str::FromStr,
    T::Err: std::fmt::Display,
{
    #[derive(Deserialize)]
    #[serde(untagged)]
    enum Integer<T> {
        Number(T),
        Text(String),
    }
    match Integer::<T>::deserialize(deserializer)? {
        Integer::Number(n) => Ok(n),
        Integer::Text(s) => s.trim().parse().map_err(D::Error::custom),
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CheckSpec {
    #[serde(default)]
    pub name: String,
    pub command: Vec<String>,
    #[serde(default)]
    pub kinds: Vec<String>,
    #[serde(default, deserialize_with = "integer")]
    pub timeout_seconds: u64,
    #[serde(default, deserialize_with = "integer")]
    pub max_output_chars: usize,
    #[serde(default = "current_dir")]
    pub cwd: String,
    #[serde(default = "yes")]
    pub enabled: bool,
    #[serde(default)]
    pub inputs: Vec<String>,
    #[serde(default)]
    pub complete_inputs: bool,
    #[serde(default)]
    pub deterministic: bool,
    #[serde(default)]
    pub env_keys: Vec<String>,
}

impl CheckSpec {
    pub fn matches(&self, files: &[PathBuf]) -> bool {
        self.enabled
            && (self.kinds.is_empty()
                || self
                    .kinds
                    .iter()
                    .any(|kind| kind == "any" || files.iter().any(|path| kind == file_kind(path))))
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Config {
    #[serde(default = "version")]
    pub version: u32,
    #[serde(default = "context_limit", deserialize_with = "integer")]
    pub max_context_chars: usize,
    #[serde(default = "lines_limit", deserialize_with = "integer")]
    pub max_diagnostic_lines: usize,
    #[serde(default = "yes")]
    pub include_success_context: bool,
    #[serde(default = "yes")]
    pub deduplicate_failures: bool,
    #[serde(default)]
    pub state_dir: Option<PathBuf>,
    #[serde(default = "timeout", deserialize_with = "integer")]
    pub timeout_seconds: u64,
    #[serde(default = "output_limit", deserialize_with = "integer")]
    pub max_output_chars: usize,
    #[serde(default)]
    pub checks: Vec<CheckSpec>,
}

impl Default for Config {
    fn default() -> Self {
        Self {
            version: version(),
            max_context_chars: context_limit(),
            max_diagnostic_lines: lines_limit(),
            include_success_context: true,
            deduplicate_failures: true,
            state_dir: None,
            timeout_seconds: timeout(),
            max_output_chars: output_limit(),
            checks: Vec::new(),
        }
    }
}

impl Config {
    pub fn load(root: &Path) -> Result<Self> {
        let path = root.join(FILE_NAME);
        match fs::symlink_metadata(&path) {
            Ok(metadata) => ensure!(metadata.is_file(), "configuration must be a regular file"),
            Err(err) if err.kind() == std::io::ErrorKind::NotFound => {
                return Ok(Self::detect(root));
            }
            Err(err) => return Err(err).context("cannot inspect project configuration"),
        }
        Self::from_reader(File::open(&path)?)
            .with_context(|| format!("invalid configuration: {}", path.display()))
    }

    pub fn from_reader(reader: impl Read) -> Result<Self> {
        let mut bytes = Vec::new();
        reader.take(1024 * 1024 + 1).read_to_end(&mut bytes)?;
        ensure!(bytes.len() <= 1024 * 1024, "configuration exceeds 1 MiB");
        let mut config: Self = serde_json::from_slice(&bytes)?;
        ensure!(
            config.version == 1,
            "unsupported configuration version {}",
            config.version
        );
        ensure!(
            (1..=1_048_576).contains(&config.max_context_chars),
            "max_context_chars must be 1..=1048576"
        );
        ensure!(
            (1..=1_048_576).contains(&config.max_diagnostic_lines),
            "max_diagnostic_lines must be 1..=1048576"
        );
        ensure!(
            (1..=86_400).contains(&config.timeout_seconds),
            "default timeout_seconds must be 1..=86400"
        );
        ensure!(
            (1..=1_048_576).contains(&config.max_output_chars),
            "default max_output_chars must be 1..=1048576"
        );
        ensure!(
            config
                .state_dir
                .as_ref()
                .is_none_or(|p| !p.as_os_str().is_empty()),
            "state_dir cannot be empty"
        );
        config.max_context_chars = config.max_context_chars.max(500);
        config.max_diagnostic_lines = config.max_diagnostic_lines.max(4);

        // Serde defaults for omitted per-check limits are resolved here. Explicit zero is invalid.
        let raw: serde_json::Value = serde_json::from_slice(&bytes)?;
        ensure!(
            config.checks.len() <= 64,
            "configuration supports at most 64 checks"
        );
        let mut names = BTreeSet::new();
        for (index, check) in config.checks.iter_mut().enumerate() {
            ensure!(
                check.command.first().is_some_and(|s| !s.trim().is_empty()),
                "checks[{index}].command needs an executable"
            );
            ensure!(
                !check.command.iter().any(|s| s.contains('\0')),
                "checks[{index}].command contains a NUL byte"
            );
            if raw["checks"][index].get("timeout_seconds").is_none() {
                check.timeout_seconds = config.timeout_seconds;
            }
            if raw["checks"][index].get("max_output_chars").is_none() {
                check.max_output_chars = config.max_output_chars;
            }
            ensure!(
                (1..=86_400).contains(&check.timeout_seconds),
                "checks[{index}].timeout_seconds must be 1..=86400"
            );
            ensure!(
                (1..=1_048_576).contains(&check.max_output_chars),
                "checks[{index}].max_output_chars must be 1..=1048576"
            );
            if raw["checks"][index].get("name").is_none() {
                check.name.clone_from(&check.command[0]);
            }
            ensure!(
                !check.name.trim().is_empty(),
                "checks[{index}].name cannot be empty"
            );
            ensure!(
                names.insert(check.name.clone()),
                "checks[{index}] has a duplicate name"
            );
            ensure!(
                check
                    .env_keys
                    .iter()
                    .all(|key| !key.is_empty() && !key.contains(['\0', '='])),
                "checks[{index}].env_keys contains an invalid name"
            );
            ensure!(
                !check.cwd.trim().is_empty(),
                "checks[{index}].cwd cannot be empty"
            );
        }
        Ok(config)
    }

    pub fn detect(root: &Path) -> Self {
        let mut config = Self::default();
        let mut add = |name: &str, command: &[&str], kinds: &[&str], seconds, max_output_chars| {
            config.checks.push(CheckSpec {
                name: name.into(),
                command: command.iter().map(|s| (*s).into()).collect(),
                kinds: kinds.iter().map(|s| (*s).into()).collect(),
                timeout_seconds: seconds,
                max_output_chars,
                cwd: current_dir(),
                enabled: true,
                inputs: vec![],
                complete_inputs: false,
                deterministic: false,
                env_keys: vec![],
            })
        };
        if root.join("Cargo.toml").is_file() {
            let mut command = vec!["cargo", "check"];
            if root.join("Cargo.lock").is_file() {
                command.push("--locked");
            }
            add(
                "cargo check",
                &command,
                &["rust", "config"],
                180,
                output_limit(),
            );
        }
        let python_manifests = ["pyproject.toml", "setup.cfg", "requirements.txt"];
        let python_declared = python_manifests
            .iter()
            .any(|name| root.join(name).is_file());
        let python_scripts = fs::read_dir(root)
            .ok()
            .into_iter()
            .flatten()
            .filter_map(Result::ok)
            .take(4096)
            .any(|entry| {
                entry
                    .path()
                    .extension()
                    .is_some_and(|extension| extension == "py")
            });
        if python_declared || python_scripts {
            add(
                "python syntax",
                &["{python}", "-m", "compileall", "-q", "{files}"],
                &["python"],
                45,
                6000,
            );
            let declarations = python_manifests
                .iter()
                .filter_map(|name| read_manifest(root, name))
                .collect::<Vec<_>>()
                .join("\n")
                .to_ascii_lowercase();
            if declarations.contains("pytest") || root.join("pytest.ini").is_file() {
                add(
                    "pytest",
                    &["{python}", "-m", "pytest", "-q"],
                    &["python", "config"],
                    180,
                    output_limit(),
                );
            }
            if declarations.contains("ruff") {
                add(
                    "ruff",
                    &["{python}", "-m", "ruff", "check", "{files}"],
                    &["python"],
                    90,
                    output_limit(),
                );
            }
            if declarations.contains("mypy") {
                add(
                    "mypy",
                    &["{python}", "-m", "mypy", "{files}"],
                    &["python"],
                    120,
                    output_limit(),
                );
            }
        }
        if let Some(manifest) = read_manifest(root, "package.json")
            .and_then(|text| serde_json::from_str::<serde_json::Value>(&text).ok())
            && let Some(scripts) = manifest["scripts"].as_object()
        {
            let mut has_check = false;
            for (script, label) in [
                ("typecheck", "npm typecheck"),
                ("lint", "npm lint"),
                ("check", "npm check"),
            ] {
                if scripts
                    .get(script)
                    .is_some_and(serde_json::Value::is_string)
                {
                    add(
                        label,
                        &["npm", "run", script, "--if-present"],
                        &["javascript", "config"],
                        120,
                        output_limit(),
                    );
                    has_check = true;
                }
            }
            if !has_check
                && scripts
                    .get("test")
                    .is_some_and(serde_json::Value::is_string)
            {
                add(
                    "npm test",
                    &["npm", "test", "--", "--run"],
                    &["javascript"],
                    180,
                    output_limit(),
                );
            }
        }
        if root.join("go.mod").is_file() {
            add(
                "go test",
                &["go", "test", "./..."],
                &["go", "config"],
                180,
                output_limit(),
            );
        }
        config
    }

    pub fn write_new(&self, root: &Path) -> Result<()> {
        let path = root.join(FILE_NAME);
        let mut temporary = tempfile::NamedTempFile::new_in(root)?;
        serde_json::to_writer_pretty(temporary.as_file_mut(), self)?;
        writeln!(temporary.as_file_mut())?;
        temporary.persist_noclobber(&path).with_context(|| {
            format!(
                "cannot create {} (check whether it already exists)",
                path.display()
            )
        })?;
        Ok(())
    }
}

fn read_manifest(root: &Path, name: &str) -> Option<String> {
    let path = root.join(name);
    if !fs::symlink_metadata(&path).ok()?.is_file() {
        return None;
    }
    let mut bytes = Vec::new();
    File::open(path)
        .ok()?
        .take(1024 * 1024 + 1)
        .read_to_end(&mut bytes)
        .ok()?;
    if bytes.len() > 1024 * 1024 {
        return None;
    }
    String::from_utf8(bytes).ok()
}

pub fn find_root(path: &Path) -> Result<PathBuf> {
    let start = fs::canonicalize(path)
        .with_context(|| format!("workspace unavailable: {}", path.display()))?;
    ensure!(start.is_dir(), "workspace must be a directory");
    if let Some(root) = start
        .ancestors()
        .find(|dir| dir.join(FILE_NAME).exists() || dir.join(".git").exists())
    {
        return Ok(root.to_path_buf());
    }
    Ok(start
        .ancestors()
        .find(|dir| {
            ["Cargo.toml", "pyproject.toml", "package.json", "go.mod"]
                .iter()
                .any(|name| dir.join(name).exists())
        })
        .unwrap_or(&start)
        .to_path_buf())
}

pub(crate) fn within(root: &Path, path: &Path, require_existing: bool) -> Result<PathBuf> {
    let path = if path.is_absolute() {
        path.strip_prefix(root)
            .context("path is outside the workspace")?
    } else {
        path
    };
    let mut current = root.to_path_buf();
    for segment in path.components() {
        let name = match segment {
            Component::CurDir => continue,
            Component::Normal(name) => name,
            _ => bail!("path contains an unsupported component"),
        };
        current.push(name);
        match fs::symlink_metadata(&current) {
            Ok(meta) => ensure!(
                !meta.file_type().is_symlink() && fs::canonicalize(&current)? == current,
                "symlink or redirected workspace path is unsupported"
            ),
            Err(err) if !require_existing && err.kind() == std::io::ErrorKind::NotFound => (),
            Err(err) => return Err(err).context("workspace path unavailable"),
        }
    }
    Ok(current)
}

fn file_kind(path: &Path) -> &'static str {
    match path
        .extension()
        .and_then(|s| s.to_str())
        .unwrap_or_default()
        .to_ascii_lowercase()
        .as_str()
    {
        "rs" => "rust",
        "py" | "pyi" => "python",
        "js" | "jsx" | "mjs" | "cjs" | "ts" | "tsx" | "vue" | "svelte" => "javascript",
        "go" => "go",
        "c" | "cc" | "cpp" | "cxx" | "h" | "hpp" | "hh" => "cpp",
        "json" | "yaml" | "yml" | "toml" | "ini" => "config",
        "md" | "mdx" | "rst" => "docs",
        _ => "other",
    }
}
