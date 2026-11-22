use serde_json::{Value, json};
use std::fs;
use std::io::{BufRead, BufReader, Read, Write};
use std::net::TcpListener;
use std::path::Path;
use std::process::{Command, Output};
use std::thread::{self, JoinHandle};
use std::time::{Duration, Instant};
use tempfile::TempDir;

fn run(root: &Path, args: &[&str], expected: i32) -> Output {
    let output = Command::new(env!("CARGO_BIN_EXE_loopsieve"))
        .arg("--root")
        .arg(root)
        .args(args)
        .env_remove("LOOPSIEVE_RUST_STATE_DIR")
        .output()
        .unwrap();
    assert_eq!(
        output.status.code(),
        Some(expected),
        "{}\n{}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    );
    output
}

fn value(output: &Output) -> Value {
    serde_json::from_slice(&output.stdout).unwrap()
}

fn server(
    responses: Vec<(&'static str, &'static str, String)>,
) -> (String, JoinHandle<Vec<Value>>) {
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let endpoint = format!("http://{}", listener.local_addr().unwrap());
    listener.set_nonblocking(true).unwrap();
    let requests = thread::spawn(move || {
        responses.into_iter().map(|(path, response_header, body)| {
            let deadline = Instant::now() + Duration::from_secs(8);
            let mut connection = loop {
                match listener.accept() {
                    Ok((connection, _)) => break connection,
                    Err(error) if error.kind() == std::io::ErrorKind::WouldBlock && Instant::now() < deadline => thread::sleep(Duration::from_millis(5)),
                    Err(error) => panic!("expected a request to {path}: {error}"),
                }
            };
            connection.set_read_timeout(Some(Duration::from_secs(5))).unwrap();
            let mut reader = BufReader::new(&mut connection);
            let mut line = String::new();
            reader.read_line(&mut line).unwrap();
            assert_eq!(line.split_whitespace().nth(1), Some(path));
            let mut length = 0;
            loop {
                line.clear();
                assert_ne!(reader.read_line(&mut line).unwrap(), 0);
                if line == "\r\n" { break; }
                if let Some(text) = line.to_ascii_lowercase().strip_prefix("content-length:") { length = text.trim().parse().unwrap(); }
            }
            let mut request = vec![0; length];
            reader.read_exact(&mut request).unwrap();
            write!(connection, "HTTP/1.1 {response_header}\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}", body.len()).unwrap();
            if request.is_empty() { Value::Null } else { serde_json::from_slice(&request).unwrap() }
        }).collect()
    });
    (endpoint, requests)
}

fn decisions(actions: Vec<Value>) -> (String, JoinHandle<Vec<Value>>) {
    server(
        actions
            .into_iter()
            .map(|action| {
                (
                    "/api/chat",
                    "200 OK\r\nContent-Type: application/json",
                    json!({"message":{"content":action.to_string()}}).to_string(),
                )
            })
            .collect(),
    )
}

#[test]
fn native_binary_embeds_catalogs_and_opens_workbench() {
    let project = TempDir::new().unwrap();
    let root = project.path();
    assert_eq!(
        value(&run(root, &["agents", "list"], 0))
            .as_array()
            .unwrap()
            .len(),
        100
    );
    assert_eq!(
        value(&run(root, &["catalog", "innovations"], 0))
            .as_array()
            .unwrap()
            .len(),
        100
    );
    assert!(
        String::from_utf8(run(root, &["tui"], 0).stdout)
            .unwrap()
            .contains("0 runs")
    );
}

#[test]
fn native_hook_updates_only_its_handler_and_preserves_user_settings() {
    let project = TempDir::new().unwrap();
    let root = project.path();
    fs::create_dir(root.join(".claude")).unwrap();
    let path = root.join(".claude/settings.local.json");
    let settings = json!({"unrelated":true, "hooks":{"PostToolUse":[{"matcher":"Shell", "hooks":[{"type":"command", "command":"other-check"}]}]}});
    fs::write(&path, settings.to_string()).unwrap();
    for _ in 0..2 {
        assert_eq!(
            value(&run(root, &["claude", "install"], 0))["installed"],
            true
        );
    }
    let installed: Value = serde_json::from_slice(&fs::read(&path).unwrap()).unwrap();
    assert_eq!(
        installed["hooks"]["PostToolUse"].as_array().unwrap().len(),
        2
    );
    assert_eq!(
        value(&run(root, &["uninstall-hook"], 0))["installed"],
        false
    );
    assert_eq!(
        serde_json::from_slice::<Value>(&fs::read(&path).unwrap()).unwrap(),
        settings
    );
    fs::write(&path, "invalid json").unwrap();
    run(root, &["install-hook"], 2);
    assert_eq!(fs::read_to_string(&path).unwrap(), "invalid json");
}

#[test]
fn mcp_inspection_reports_transports_without_config_values() {
    let project = TempDir::new().unwrap();
    fs::write(
        project.path().join(".mcp.json"),
        json!({"mcpServers":{
            "fixture":{"command":"internal-command","env":{"TOKEN":"fixture-private"}},
            "remote":{"type":"http","url":"https://example.invalid/private"}
        }})
        .to_string(),
    )
    .unwrap();
    let output = run(project.path(), &["mcp"], 0);
    assert_eq!(value(&output)[0]["transport"], "stdio");
    let text = String::from_utf8(output.stdout).unwrap();
    assert!(
        !text.contains("fixture-private")
            && !text.contains("internal-command")
            && !text.contains("example.invalid")
    );
}

#[test]
fn native_session_pause_resume_and_cancel_never_require_a_model_call() {
    let project = TempDir::new().unwrap();
    let root = project.path();
    let output = value(&run(
        root,
        &[
            "agent",
            "new",
            "inspect Rust source",
            "--endpoint",
            "http://127.0.0.1:1",
        ],
        0,
    ));
    let id = output["session"]["id"].as_str().unwrap();
    assert_eq!(
        value(&run(root, &["agent", "pause", id], 0))["session"]["status"],
        "PAUSED"
    );
    run(root, &["agent", "step", id], 2);
    assert_eq!(
        value(&run(root, &["agent", "cancel", id], 0))["session"]["status"],
        "CANCELLED"
    );
    assert_eq!(value(&run(root, &["agent", "sessions"], 0))[0]["id"], id);
}

#[test]
fn loopback_models_inventory_and_redirect_rejection() {
    let project = TempDir::new().unwrap();
    let root = project.path();
    let (endpoint, requests) = server(vec![(
        "/api/tags",
        "200 OK",
        json!({"models":[{"name":"fixture:3b"}]}).to_string(),
    )]);
    assert_eq!(
        value(&run(root, &["models", "list", "--endpoint", &endpoint], 0)),
        json!(["fixture:3b"])
    );
    assert_eq!(requests.join().unwrap(), vec![Value::Null]);
    let (endpoint, requests) = server(vec![(
        "/api/tags",
        "302 Found\r\nLocation: http://127.0.0.1:1/redirect",
        String::new(),
    )]);
    let result = run(root, &["models", "list", "--endpoint", &endpoint], 2);
    assert!(
        String::from_utf8(result.stderr)
            .unwrap()
            .contains("HTTP 302")
    );
    requests.join().unwrap();
}

#[cfg(unix)]
fn fixture() -> TempDir {
    let project = TempDir::new().unwrap();
    let root = project.path();
    fs::write(root.join("source.rs"), "old\n").unwrap();
    fs::write(root.join(".loopsieve.json"), json!({"checks":[{"name":"fixture", "kinds":["rust"],
       "command":["sh","-c","test \"$(cat source.rs)\" = new || { printf 'fixture check failed'; exit 1; }"]}]}).to_string()).unwrap();
    project
}

#[cfg(unix)]
#[test]
fn loopback_llamacpp_advice_keeps_check_exit_and_observes_stream() {
    let project = fixture();
    let root = project.path();
    let body = format!(
        "data: {}\n\ndata: {}\n\ndata: [DONE]\n\n",
        json!({"choices":[{"delta":{"content":"Cause: fixture failed"}}]}),
        json!({"usage":{"completion_tokens":4}})
    );
    let (endpoint, requests) = server(vec![(
        "/v1/chat/completions",
        "200 OK\r\nContent-Type: text/event-stream",
        body,
    )]);
    let config = root.join("local.json");
    fs::write(
        &config,
        json!({"model":"fixture", "endpoint":endpoint}).to_string(),
    )
    .unwrap();
    let output = value(&run(
        root,
        &[
            "check",
            "--explain",
            "--llm-config",
            config.to_str().unwrap(),
            "--prompt-cache",
            "--json",
            "source.rs",
        ],
        1,
    ));
    assert_eq!(output["checks"][0]["status"], "FAIL");
    assert_eq!(output["advice"]["text"], "Cause: fixture failed");
    assert_eq!(output["advice"]["completion_tokens"], 4);
    let request = requests.join().unwrap();
    assert_eq!(request[0]["cache_prompt"], true);
    assert!(
        request[0]["messages"][1]["content"]
            .as_str()
            .unwrap()
            .contains("fixture check failed")
    );
    let (endpoint, requests) = server(vec![(
        "/v1/chat/completions",
        "200 OK\r\nContent-Type: text/event-stream",
        "data: {}\n\n".into(),
    )]);
    fs::write(
        &config,
        json!({"model":"fixture", "endpoint":endpoint}).to_string(),
    )
    .unwrap();
    let incomplete = value(&run(
        root,
        &[
            "check",
            "--explain",
            "--llm-config",
            config.to_str().unwrap(),
            "--json",
            "source.rs",
        ],
        1,
    ));
    assert!(
        incomplete["advice_error"]
            .as_str()
            .unwrap()
            .contains("incomplete")
    );
    requests.join().unwrap();
}

#[cfg(unix)]
#[test]
fn loopback_agent_repairs_verifies_and_restores_with_digest_guard() {
    let project = fixture();
    let root = project.path();
    let (endpoint, requests) = decisions(vec![
        json!({"action":"patch", "path":"source.rs", "find":"old", "replace":"new"}),
        json!({"action":"finish", "summary":"premature claim"}),
        json!({"action":"verify", "files":["source.rs"]}),
        json!({"action":"finish", "summary":"fixture verified"}),
    ]);
    let result = value(&run(
        root,
        &[
            "agent",
            "run",
            "edit Rust fixture",
            "--role",
            "005-rust-engineer",
            "--steps",
            "4",
            "--allow-writes",
            "--allow-checks",
            "--endpoint",
            &endpoint,
        ],
        0,
    ));
    let id = result["session"]["id"].as_str().unwrap();
    assert_eq!(result["session"]["status"], "COMPLETED");
    assert_eq!(result["session"]["changes_verified"], true);
    assert_eq!(result["events"][2]["kind"], "action_error");
    assert_eq!(result["checkpoints"][0]["applied"], true);
    assert_eq!(fs::read_to_string(root.join("source.rs")).unwrap(), "new\n");
    assert_eq!(requests.join().unwrap().len(), 4);
    run(root, &["agent", "restore", id, "--checkpoint", "1"], 2);
    fs::write(root.join("source.rs"), "user edit\n").unwrap();
    run(
        root,
        &[
            "agent",
            "restore",
            id,
            "--checkpoint",
            "1",
            "--approve-restore",
        ],
        2,
    );
    assert_eq!(
        fs::read_to_string(root.join("source.rs")).unwrap(),
        "user edit\n"
    );
    fs::write(root.join("source.rs"), "new\n").unwrap();
    run(
        root,
        &[
            "agent",
            "restore",
            id,
            "--checkpoint",
            "1",
            "--approve-restore",
        ],
        0,
    );
    assert_eq!(fs::read_to_string(root.join("source.rs")).unwrap(), "old\n");
}

#[cfg(unix)]
#[test]
fn loopback_agent_denies_writes_protected_reads_and_extra_action_fields() {
    let project = fixture();
    let root = project.path();
    fs::write(root.join("service.env"), "private fixture").unwrap();
    let (endpoint, requests) = decisions(vec![
        json!({"action":"patch", "path":"source.rs", "find":"old", "replace":"new"}),
        json!({"action":"inspect", "path":"service.env"}),
        json!({"action":"verify", "files":["source.rs"]}),
        json!({"action":"tree", "command":"untrusted extra field"}),
    ]);
    let result = value(&run(
        root,
        &[
            "agent",
            "run",
            "inspect fixture",
            "--steps",
            "4",
            "--endpoint",
            &endpoint,
        ],
        1,
    ));
    let events = result["events"].as_array().unwrap();
    assert_eq!(result["session"]["status"], "BLOCKED");
    assert_eq!(
        events
            .iter()
            .map(|event| event["kind"].as_str().unwrap())
            .collect::<Vec<_>>(),
        vec![
            "created",
            "action_error",
            "action_error",
            "action_error",
            "provider_error"
        ]
    );
    assert_eq!(fs::read_to_string(root.join("source.rs")).unwrap(), "old\n");
    assert!(
        !json!(requests.join().unwrap())
            .to_string()
            .contains("private fixture")
    );
}

#[test]
fn offline_models_and_read_only_tools_work_without_a_model_process() {
    let project = TempDir::new().unwrap();
    let root = project.path();
    fs::write(root.join("fixture.gguf"), "abc").unwrap();
    let expected = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad";
    let path = root.join("fixture.gguf");
    assert_eq!(
        value(&run(
            root,
            &[
                "models",
                "verify",
                path.to_str().unwrap(),
                "--sha256",
                expected
            ],
            0
        ))["bytes"],
        3
    );
    run(
        root,
        &[
            "models",
            "verify",
            path.to_str().unwrap(),
            "--sha256",
            expected,
            "--max-bytes",
            "2",
        ],
        2,
    );
    let estimate = value(&run(
        root,
        &["models", "memory", "llama3.2:3b", "--context", "1024"],
        0,
    ));
    assert_eq!(estimate["kind"], "ESTIMATE_NOT_MEASUREMENT");
    assert_eq!(estimate["context_tokens"], 1024);
    assert!(
        value(&run(root, &["models", "list"], 0))
            .as_array()
            .unwrap()
            .iter()
            .any(|model| model["id"] == "llama3.2:3b")
    );
    fs::write(root.join("source.rs"), "fn fixture() {}\n").unwrap();
    assert_eq!(
        value(&run(
            root,
            &[
                "tools",
                "run",
                "file_read",
                "--args",
                r#"{"path":"source.rs"}"#
            ],
            0
        ))["result"],
        "fn fixture() {}\n"
    );
    run(
        root,
        &[
            "tools",
            "run",
            "file_read",
            "--args",
            r#"{"path":"fixture.gguf"}"#,
        ],
        2,
    );
}

#[test]
fn native_legacy_report_reads_statistics_only() {
    let project = TempDir::new().unwrap();
    let root = project.path();
    let state = root.join("legacy.json");
    fs::write(&state, json!({"stats":{"runs":2,"cached_checks":"1","negative":-1}, "cache":{"entry":"sensitive local data"}}).to_string()).unwrap();
    let output = run(root, &["legacy", "report", state.to_str().unwrap()], 0);
    assert_eq!(value(&output), json!({"runs":2,"cached_checks":1}));
}

#[test]
fn loopback_team_blocks_dependencies_and_enforces_declared_paths() {
    let project = TempDir::new().unwrap();
    let root = project.path();
    fs::write(root.join("source.rs"), "old\n").unwrap();
    fs::write(root.join("other.rs"), "old\n").unwrap();
    let manifest = root.join("team.json");
    fs::write(
        &manifest,
        json!({"tasks":[
            {"id":"first","task":"edit a fixture","write_set":["source.rs"], "max_steps":1},
            {"id":"after","task":"dependent task","depends_on":["first"]},
            {"id":"independent","task":"observe local source","model":"alternate"}
        ]})
        .to_string(),
    )
    .unwrap();
    let (endpoint, requests) = decisions(vec![
        json!({"action":"patch", "path":"other.rs", "find":"old", "replace":"wrong"}),
        json!({"action":"finish", "summary":"read-only independent task"}),
    ]);
    let output = value(&run(
        root,
        &[
            "team",
            manifest.to_str().unwrap(),
            "--allow-writes",
            "--endpoint",
            &endpoint,
        ],
        1,
    ));
    assert_eq!(output["tasks"][0]["status"], "FAILED");
    assert_eq!(output["tasks"][1]["status"], "BLOCKED");
    assert_eq!(output["tasks"][2]["status"], "COMPLETED");
    assert_eq!(fs::read_to_string(root.join("other.rs")).unwrap(), "old\n");
    assert_eq!(requests.join().unwrap()[1]["model"], "alternate");
}

#[test]
fn native_init_detects_declared_node_and_python_checks() {
    let project = TempDir::new().unwrap();
    let root = project.path();
    fs::write(
        root.join("package.json"),
        r#"{"scripts":{"lint":"fixture","test":"unused"}}"#,
    )
    .unwrap();
    fs::write(root.join("requirements.txt"), "pytest\nruff\n").unwrap();
    run(root, &["init"], 0);
    let settings: Value =
        serde_json::from_slice(&fs::read(root.join(".loopsieve.json")).unwrap()).unwrap();
    let names = settings["checks"]
        .as_array()
        .unwrap()
        .iter()
        .map(|check| check["name"].as_str().unwrap())
        .collect::<Vec<_>>();
    assert_eq!(names, vec!["python syntax", "pytest", "ruff", "npm lint"]);
}
