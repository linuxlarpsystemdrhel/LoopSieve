use crate::config::{CONFIG_INPUTS, CheckSpec, within};
use crate::runner::{Prepared, resolve_executable};
use anyhow::{Context, Result, ensure};
use globset::{GlobBuilder, GlobSetBuilder};
use sha2::{Digest, Sha256};
use std::collections::BTreeSet;
use std::fs::{self, File};
use std::io::{BufReader, Read};
use std::path::{Component, Path, PathBuf};
use walkdir::WalkDir;

const FILE_LIMIT: u64 = 128 * 1024 * 1024;
const INPUT_LIMIT: usize = 20_000;
const ENVIRONMENT: &[&str] = &[
    "PATH",
    "VIRTUAL_ENV",
    "PYTHONPATH",
    "PYTHONHOME",
    "LOOPSIEVE_PYTHON",
    "NODE_ENV",
    "RUSTFLAGS",
    "CARGO_TARGET_DIR",
    "GOFLAGS",
    "CFLAGS",
    "CXXFLAGS",
    "JAVA_HOME",
    "CI",
];

fn excluded(path: &Path) -> bool {
    path.file_name()
        .and_then(|name| name.to_str())
        .is_some_and(|name| {
            name.starts_with(".venv-")
                || matches!(
                    name,
                    ".git"
                        | ".private"
                        | ".loopsieve"
                        | ".local-models"
                        | ".venv"
                        | "venv"
                        | "target"
                        | "node_modules"
                        | "__pycache__"
                        | ".pytest_cache"
                        | ".mypy_cache"
                        | ".ruff_cache"
                )
        })
}

fn file_hash(path: &Path) -> Result<String> {
    let current = fs::symlink_metadata(path)?;
    ensure!(
        current.is_file() && current.len() <= FILE_LIMIT,
        "dependency is not a regular file within the size limit"
    );
    let file = File::open(path)?;
    let before = file.metadata()?;
    ensure!(
        before.is_file()
            && before.len() == current.len()
            && before.modified()? == current.modified()?,
        "dependency changed before hashing"
    );
    let mut reader = BufReader::new(file).take(FILE_LIMIT + 1);
    let mut hash = Sha256::new();
    let count = std::io::copy(&mut reader, &mut hash)?;
    let after = fs::symlink_metadata(path)?;
    ensure!(
        count == before.len()
            && after.is_file()
            && after.len() == before.len()
            && after.modified()? == before.modified()?,
        "dependency changed during hashing"
    );
    Ok(format!("{:x}", hash.finalize()))
}

fn inputs(root: &Path, patterns: &[String], files: &[PathBuf]) -> Result<BTreeSet<PathBuf>> {
    let mut paths = BTreeSet::new();
    let mut globs = GlobSetBuilder::new();
    let mut pattern_count = 0;
    for pattern in patterns {
        let path = Path::new(pattern);
        ensure!(
            !pattern.is_empty()
                && !path.is_absolute()
                && path
                    .components()
                    .all(|part| matches!(part, Component::Normal(_) | Component::CurDir)),
            "invalid or outside-workspace input pattern"
        );
        if pattern.contains(['*', '?', '[', '{']) {
            globs.add(GlobBuilder::new(pattern).literal_separator(true).build()?);
            pattern_count += 1;
        } else {
            let direct = within(root, path, true)?;
            if direct.is_dir() {
                globs.add(
                    GlobBuilder::new(&format!("{}/**", pattern.trim_end_matches('/')))
                        .literal_separator(true)
                        .build()?,
                );
                pattern_count += 1;
            } else {
                paths.insert(direct);
            }
        }
    }
    if pattern_count > 0 {
        let globs = globs.build()?;
        let mut found = vec![false; pattern_count];
        for (index, entry) in WalkDir::new(root)
            .into_iter()
            .filter_entry(|entry| entry.depth() == 0 || !excluded(entry.path()))
            .enumerate()
        {
            ensure!(index <= INPUT_LIMIT, "workspace scan exceeds cache limit");
            let entry = entry?;
            if entry.file_type().is_dir() {
                continue;
            }
            let relative = entry.path().strip_prefix(root)?;
            // A wildcard can also name descendants of a symlink: without tracing
            // that target a complete inventory cannot be guaranteed.
            ensure!(
                !entry.file_type().is_symlink(),
                "workspace has a symlink during wildcard input scan"
            );
            for matched in globs.matches(relative) {
                ensure!(
                    entry.file_type().is_file(),
                    "declared input is not a regular file"
                );
                found[matched] = true;
                paths.insert(entry.path().to_path_buf());
            }
        }
        ensure!(
            found.iter().all(|matched| *matched),
            "one or more input patterns have no regular file matches"
        );
    }
    for name in CONFIG_INPUTS {
        let path = root.join(name);
        if path.exists() || path.is_symlink() {
            paths.insert(within(root, &path, true)?);
        }
    }
    for path in files {
        ensure!(
            path.is_file(),
            "changed input is missing or is not a regular file"
        );
        paths.insert(path.clone());
    }
    ensure!(
        !paths.is_empty() && paths.len() <= INPUT_LIMIT,
        "declared input set is empty or too large"
    );
    Ok(paths)
}

pub(crate) fn capture(
    root: &Path,
    spec: &CheckSpec,
    run: &Prepared,
    files: &[PathBuf],
) -> Result<String> {
    ensure!(
        spec.complete_inputs && spec.deterministic && !spec.inputs.is_empty(),
        "deterministic complete inputs were not declared"
    );
    let executable = resolve_executable(&run.argv[0], &run.cwd)
        .context("cannot resolve the executable for caching")?;
    let command = run
        .argv
        .iter()
        .map(|argument| argument.to_str().context("cache requires UTF-8 arguments"))
        .collect::<Result<Vec<_>>>()?;
    let environment = ENVIRONMENT
        .iter()
        .copied()
        .chain(spec.env_keys.iter().map(String::as_str))
        .map(|key| {
            let value = std::env::var_os(key)
                .map(|s| {
                    s.into_string()
                        .map_err(|_| anyhow::anyhow!("cache requires UTF-8 environment"))
                })
                .transpose()?;
            Ok((key, value))
        })
        .collect::<Result<std::collections::BTreeMap<_, _>>>()?;
    let mut hash = Sha256::new();
    hash.update(serde_json::to_vec(&(
        1,
        spec,
        command,
        &run.cwd,
        &executable,
        file_hash(&executable)?,
        environment,
    ))?);
    for path in inputs(root, &spec.inputs, files)? {
        let key = path.strip_prefix(root)?;
        hash.update(serde_json::to_vec(&(key, file_hash(&path)?))?);
    }
    Ok(format!("{:x}", hash.finalize()))
}
