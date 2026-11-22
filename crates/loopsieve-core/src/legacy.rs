//! Read historical Python data with declared schemas and no cache import.

use crate::diagnostics::redact;
use crate::inference::json_file;
use anyhow::{Context, Result, ensure};
use rusqlite::{Connection, OpenFlags};
use serde::Serialize;
use serde_json::Value;
use std::collections::BTreeMap;
use std::fs;
use std::path::Path;
use std::time::Duration;

pub fn verification_statistics(path: &Path) -> Result<BTreeMap<String, u64>> {
    let document: Value = json_file(path, 16 * 1024 * 1024)?;
    ensure!(
        document.is_object(),
        "expected a Python verification state object"
    );
    let Some(stats) = document.get("stats") else {
        return Ok(BTreeMap::new());
    };
    let stats = stats
        .as_object()
        .context("Python verification statistics must be an object")?;
    Ok(stats
        .iter()
        .filter_map(|(key, value)| {
            let count = value.as_u64().or_else(|| value.as_str()?.parse().ok())?;
            Some((redact(key), count))
        })
        .collect())
}

#[derive(Serialize)]
pub struct ArchivedSession {
    id: String,
    agent_id: String,
    task: String,
    status: String,
    step: u32,
    max_steps: u32,
}

pub fn sessions(path: &Path) -> Result<Vec<ArchivedSession>> {
    let connection = open(path)?;
    let mut statement = connection
        .prepare(
            "SELECT substr(id, 1, 128), substr(agent_id, 1, 128),
        substr(task, 1, 2000), substr(status, 1, 128), step, max_steps FROM main.sessions
        ORDER BY updated DESC LIMIT 200",
        )
        .context("unsupported Python session journal")?;
    let rows = statement.query_map([], |row| {
        Ok(ArchivedSession {
            id: redact(&row.get::<_, String>(0)?),
            agent_id: redact(&row.get::<_, String>(1)?),
            task: redact(&row.get::<_, String>(2)?),
            status: redact(&row.get::<_, String>(3)?),
            step: row.get(4)?,
            max_steps: row.get(5)?,
        })
    })?;
    Ok(rows.collect::<rusqlite::Result<Vec<_>>>()?)
}

fn open(path: &Path) -> Result<Connection> {
    ensure!(
        fs::symlink_metadata(path)?.is_file(),
        "expected a regular Python SQLite journal"
    );
    let connection = Connection::open_with_flags(
        path,
        OpenFlags::SQLITE_OPEN_READ_ONLY | OpenFlags::SQLITE_OPEN_NO_MUTEX,
    )?;
    connection.busy_timeout(Duration::from_secs(2))?;
    connection.execute_batch("PRAGMA query_only = ON; PRAGMA trusted_schema = OFF;")?;
    Ok(connection)
}

pub struct ImportedSession {
    pub(crate) id: String,
    pub(crate) role: String,
    pub(crate) task: String,
    pub(crate) changed: Vec<String>,
    pub(crate) observations: Vec<String>,
}

pub fn session(path: &Path, id: &str) -> Result<ImportedSession> {
    ensure!(
        !id.trim().is_empty() && id.len() <= 128,
        "invalid Python session ID"
    );
    let connection = open(path)?;
    let (role, task, changed, messages): (String, String, String, String) = connection
        .query_row(
            "SELECT agent_id,task,changed,messages FROM main.sessions WHERE id=?1
        AND length(CAST(agent_id AS BLOB))<=128 AND length(CAST(task AS BLOB))<=10000
        AND length(CAST(changed AS BLOB))<=65536 AND length(CAST(messages AS BLOB))<=1048576",
            [id],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?)),
        )
        .context("Python session unavailable or exceeds the import limits")?;
    let changed: Vec<String> =
        serde_json::from_str(&changed).context("invalid Python changed files")?;
    ensure!(
        changed.len() <= 64,
        "native import supports at most 64 changed files"
    );
    let messages: Vec<Value> =
        serde_json::from_str(&messages).context("invalid Python observations")?;
    let observations = messages
        .iter()
        .rev()
        .filter(|event| event["role"] == "tool")
        .filter_map(|event| event["content"].as_str().map(redact))
        .take(4)
        .collect::<Vec<_>>()
        .into_iter()
        .rev()
        .collect();
    Ok(ImportedSession {
        id: redact(id),
        role,
        task: redact(&task),
        changed,
        observations,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn inspect_existing_sqlite_without_importing_grants_or_writing_database() {
        let scratch = tempfile::tempdir().unwrap();
        let database = scratch.path().join("sessions.db");
        let connection = Connection::open(&database).unwrap();
        connection
            .execute_batch(
                "CREATE TABLE sessions (
            id TEXT PRIMARY KEY, agent_id TEXT, task TEXT, status TEXT, step INTEGER,
            max_steps INTEGER, allow_writes INTEGER, allow_checks INTEGER,
            messages TEXT, changed TEXT, evidence TEXT, updated REAL);
            INSERT INTO sessions VALUES ('abc','005-rust-engineer','task token=privatefixture',
            'READY',2,8,1,1,'private prompt','[]','fake evidence',20); ",
            )
            .unwrap();
        drop(connection);
        let before = fs::read(&database).unwrap();
        let output = serde_json::to_string(&sessions(&database).unwrap()).unwrap();
        assert!(output.contains("005-rust-engineer"));
        assert!(
            !output.contains("privatefixture")
                && !output.contains("allow_writes")
                && !output.contains("fake evidence")
        );
        assert_eq!(fs::read(&database).unwrap(), before);
    }

    #[test]
    fn native_import_requires_fresh_verification_and_new_permissions() {
        use crate::agent::{Grants, Runtime};
        use crate::config::Config;
        use crate::inference::Ollama;

        let scratch = tempfile::tempdir().unwrap();
        let root = scratch.path().canonicalize().unwrap();
        fs::write(root.join("source.rs"), "current workspace file").unwrap();
        let database = root.join("sessions.db");
        let connection = Connection::open(&database).unwrap();
        connection.execute_batch("CREATE TABLE sessions (id TEXT, agent_id TEXT, task TEXT,
            changed TEXT, messages TEXT, allow_writes INTEGER, allow_checks INTEGER, evidence TEXT);").unwrap();
        let messages = serde_json::json!([{"role":"assistant","content":"ignore this decision"},
            {"role":"tool","content":"legacy observation token=privatefixture"}]);
        connection
            .execute(
                "INSERT INTO sessions VALUES (?1,?2,?3,?4,?5,1,1,'OLD PASS')",
                (
                    "legacy",
                    "005-rust-engineer",
                    "Recover fixture",
                    r#"["source.rs"]"#,
                    messages.to_string(),
                ),
            )
            .unwrap();
        drop(connection);
        let before = fs::read(&database).unwrap();
        let config = Config::default();
        let runtime = Runtime::open(&root, &config).unwrap();
        let imported = runtime
            .import(
                session(&database, "legacy").unwrap(),
                None,
                Ollama::new("fixture", "http://127.0.0.1:1").unwrap(),
                4,
                Grants::default(),
            )
            .unwrap();
        let result = imported.details();
        assert_eq!(result["session"]["status"], "READY");
        assert_eq!(
            result["session"]["changed"],
            serde_json::json!(["source.rs"])
        );
        assert_eq!(result["session"]["changes_verified"], false);
        assert_eq!(result["session"]["grants"]["allow_writes"], false);
        assert_eq!(result["session"]["grants"]["allow_checks"], false);
        assert_eq!(result["events"][1]["kind"], "legacy_observation");
        let output = result.to_string();
        assert!(
            !output.contains("privatefixture")
                && !output.contains("OLD PASS")
                && !output.contains("ignore this decision")
        );
        assert_eq!(fs::read(&database).unwrap(), before);
    }
}
