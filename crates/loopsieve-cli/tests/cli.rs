use serde_json::{Value, json};
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};
use tempfile::TempDir;

fn binary() -> Command {
    Command::new(env!("CARGO_BIN_EXE_loopsieve-rs"))
}

fn run(root: &Path, args: &[&str]) -> Output {
    binary()
        .arg("--root")
        .arg(root)
        .args(args)
        .env_remove("LOOPSIEVE_RUST_STATE_DIR")
        .output()
        .unwrap()
}

fn value(output: &Output) -> Value {
    serde_json::from_slice(&output.stdout).unwrap_or_else(|error| {
        panic!(
            "{error}; stdout: {}; stderr: {}",
            String::from_utf8_lossy(&output.stdout),
            String::from_utf8_lossy(&output.stderr)
        )
    })
}

fn config(root: &Path, checks: Value) {
    fs::write(
        root.join(".loopsieve.json"),
        json!({"version": 1, "checks": checks}).to_string(),
    )
    .unwrap();
}

fn check(root: &Path, expected: i32) -> Value {
    let output = run(root, &["check", "--json", "source.rs"]);
    assert_eq!(
        output.status.code(),
        Some(expected),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    value(&output)
}

#[test]
fn fixtures_match_python_baseline() {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../benchmarks");
    let expected: Value =
        serde_json::from_slice(&fs::read(root.join("results.json")).unwrap()).unwrap();
    for fixture in expected["tests"].as_array().unwrap() {
        let path = root
            .join("fixtures")
            .join(fixture["fixture"].as_str().unwrap());
        let output = binary()
            .args(["benchmark", "--json"])
            .arg(path)
            .output()
            .unwrap();
        assert!(output.status.success());
        let actual = value(&output);
        for key in [
            "iterations",
            "raw_chars",
            "loopsieve_chars",
            "repeated_failures_suppressed",
            "diagnostic_context_reduction_ratio",
        ] {
            assert_eq!(actual[key], fixture[key], "{}", fixture["fixture"]);
        }
    }
}

#[test]
fn init_is_non_overwriting_and_detects_rust() {
    let project = TempDir::new().unwrap();
    fs::write(project.path().join("Cargo.toml"), "[workspace]\n").unwrap();
    assert!(run(project.path(), &["init"]).status.success());
    let file = project.path().join(".loopsieve.json");
    let initial = fs::read(&file).unwrap();
    let saved: Value = serde_json::from_slice(&initial).unwrap();
    assert_eq!(saved["checks"][0]["name"], "cargo check");
    assert_eq!(run(project.path(), &["init"]).status.code(), Some(2));
    assert_eq!(fs::read(&file).unwrap(), initial);
}

#[test]
fn invalid_config_and_unknown_checks_are_explicit() {
    let project = TempDir::new().unwrap();
    config(
        project.path(),
        json!([{"name":"invalid","command":["git"],"timeout_seconds":0}]),
    );
    let output = run(project.path(), &["check", "source.rs"]);
    assert_eq!(output.status.code(), Some(2));
    assert!(String::from_utf8_lossy(&output.stderr).contains("timeout_seconds"));
    config(project.path(), json!([]));
    let report = check(project.path(), 2);
    assert_eq!(report["reason"], "no matching checks");
    let outside = run(project.path(), &["check", "../outside.rs"]);
    assert_eq!(outside.status.code(), Some(2));
}

#[test]
fn named_manifest_has_distinct_strategies_and_rejects_cycles() {
    let project = TempDir::new().unwrap();
    let task = |id, priority, seconds, depends_on| {
        json!({
            "id": id, "files":["source.rs"], "checks":["unit"], "priority":priority,
            "estimated_seconds":seconds, "depends_on":depends_on,
        })
    };
    let manifest = project.path().join("mission.json");
    let plan = |strategy| {
        binary()
            .args(["plan", "--strategy", strategy])
            .arg(&manifest)
            .output()
            .unwrap()
    };
    fs::write(
        &manifest,
        json!({"tasks":[
            task("short", 0, 1, Vec::<&str>::new()), task("urgent", 9, 1, vec![]),
            task("long", 0, 5, vec![]), task("tail", 0, 10, vec!["long"])
        ]})
        .to_string(),
    )
    .unwrap();
    assert_eq!(
        value(&plan("fifo")),
        json!(["short", "urgent", "long", "tail"])
    );
    assert_eq!(
        value(&plan("priority")),
        json!(["urgent", "short", "long", "tail"])
    );
    assert_eq!(
        value(&plan("critical-path")),
        json!(["long", "tail", "short", "urgent"])
    );
    fs::write(
        &manifest,
        json!({"tasks":[task("a", 0, 1, vec!["b"]),task("b", 0, 1, vec!["a"])]}).to_string(),
    )
    .unwrap();
    let output = plan("fifo");
    assert_eq!(output.status.code(), Some(2));
    assert!(String::from_utf8_lossy(&output.stderr).contains("cycle"));
}

#[cfg(unix)]
mod unix {
    use super::*;
    use std::{io::Write, process::Stdio, thread};

    fn shell(name: &str, script: &str) -> Value {
        json!({"name":name, "command":["sh","-c",script]})
    }

    fn project() -> TempDir {
        let project = TempDir::new().unwrap();
        fs::write(project.path().join("source.rs"), "fn main() {}\n").unwrap();
        project
    }

    #[test]
    fn non_utf8_workspace_can_run_commands_without_root_expansion() {
        use std::ffi::OsStr;
        use std::os::unix::ffi::OsStrExt;

        let scratch = TempDir::new().unwrap();
        let root = scratch.path().join(OsStr::from_bytes(b"workspace-\xff"));
        fs::create_dir(&root).unwrap();
        fs::write(root.join("source.rs"), "fn main() {}\n").unwrap();
        config(&root, json!([shell("fixture", "test -f source.rs")]));
        assert_eq!(check(&root, 0)["checks"][0]["status"], "PASS");
    }

    #[test]
    fn hook_verifies_edits_and_ignores_unrelated_events() {
        let project = project();
        let root = project.path();
        config(
            root,
            json!([shell("fixture", "printf hook-failure; exit 4")]),
        );
        let hook = |payload: Value| {
            let mut child = binary()
                .arg("--root")
                .arg(root)
                .arg("hook")
                .env_remove("LOOPSIEVE_RUST_STATE_DIR")
                .stdin(Stdio::piped())
                .stdout(Stdio::piped())
                .spawn()
                .unwrap();
            child
                .stdin
                .take()
                .unwrap()
                .write_all(payload.to_string().as_bytes())
                .unwrap();
            let output = child.wait_with_output().unwrap();
            assert!(output.status.success());
            value(&output)
        };
        let ignored =
            hook(json!({"hook_event_name":"PostToolUse","tool_name":"Read","tool_input":{}}));
        assert_eq!(ignored, json!({}));
        let edited = hook(json!({"hook_event_name":"PostToolUse","cwd":"/",
            "tool_name":"Edit","tool_input":{"file_path":"source.rs"}}));
        assert_eq!(edited["hookSpecificOutput"]["hookEventName"], "PostToolUse");
        assert!(
            edited["hookSpecificOutput"]["additionalContext"]
                .as_str()
                .unwrap()
                .contains("hook-failure")
        );
    }

    #[test]
    fn diagnostic_delta_retains_changed_column_and_tracks_regression() {
        let project = project();
        let root = project.path();
        config(
            root,
            json!([shell("fixture", "cat outcome; exit $(cat code)")]),
        );
        fs::write(root.join("code"), "1").unwrap();
        fs::write(
            root.join("outcome"),
            "source.rs:2:4: error[E0001]: wrong type\n",
        )
        .unwrap();
        let first = check(root, 1);
        assert_eq!(first["checks"][0]["delta"], "NEW_FAILURE");
        assert_eq!(first["checks"][0]["diagnostics"][0]["column"], 4);
        assert_eq!(first["checks"][0]["diagnostics"][0]["code"], "E0001");
        let repeat = check(root, 1);
        assert_eq!(repeat["checks"][0]["delta"], "UNCHANGED_FAILURE");
        assert!(!repeat["context"].as_str().unwrap().contains("wrong type"));
        fs::write(
            root.join("outcome"),
            "source.rs:2:8: error[E0001]: wrong type\n",
        )
        .unwrap();
        assert_eq!(check(root, 1)["checks"][0]["delta"], "MODIFIED_FAILURE");
        fs::write(root.join("code"), "0").unwrap();
        assert_eq!(check(root, 0)["checks"][0]["delta"], "RESOLVED");
        fs::write(root.join("code"), "1").unwrap();
        assert_eq!(check(root, 1)["checks"][0]["delta"], "REGRESSION");
    }

    #[test]
    fn cached_success_requires_identical_input_and_supports_invalidation() {
        let project = project();
        let root = project.path();
        let mut spec = shell("fixture", "test $(cat dependency) = ok");
        spec["inputs"] = json!(["dependency"]);
        spec["deterministic"] = json!(true);
        spec["complete_inputs"] = json!(true);
        fs::write(root.join("dependency"), "ok").unwrap();
        config(root, json!([spec]));
        assert_eq!(check(root, 0)["checks"][0]["status"], "PASS");
        assert_eq!(check(root, 0)["checks"][0]["status"], "CACHED_PASS");
        assert!(
            run(root, &["cache", "invalidate", "--check", "fixture"])
                .status
                .success()
        );
        assert_eq!(check(root, 0)["checks"][0]["status"], "PASS");
        fs::write(root.join("dependency"), "bad").unwrap();
        assert_eq!(check(root, 1)["checks"][0]["status"], "FAIL");
        assert_eq!(value(&run(root, &["cache", "inspect"])), json!({}));
    }

    #[test]
    fn input_mutation_during_execution_prevents_positive_cache() {
        let project = project();
        let root = project.path();
        let mut spec = shell("mutates", "printf changed > dependency");
        spec["inputs"] = json!(["dependency"]);
        spec["deterministic"] = json!(true);
        spec["complete_inputs"] = json!(true);
        fs::write(root.join("dependency"), "original").unwrap();
        config(root, json!([spec]));
        assert!(
            check(root, 0)["checks"][0]["cache_reason"]
                .as_str()
                .unwrap()
                .contains("during execution")
        );
        fs::write(root.join("dependency"), "original").unwrap();
        assert_eq!(check(root, 0)["checks"][0]["status"], "PASS");
        assert_eq!(value(&run(root, &["cache", "inspect"])), json!({}));
    }

    #[test]
    fn directory_and_recursive_glob_detect_new_inputs() {
        let project = project();
        let root = project.path();
        fs::create_dir(root.join("src")).unwrap();
        fs::write(root.join("src/first.rs"), "fn entry() {}").unwrap();
        let mut spec = shell("fixture", "true");
        spec["inputs"] = json!(["src", "src/**/*.rs"]);
        spec["deterministic"] = json!(true);
        spec["complete_inputs"] = json!(true);
        config(root, json!([spec]));
        assert_eq!(check(root, 0)["checks"][0]["status"], "PASS");
        assert_eq!(check(root, 0)["checks"][0]["status"], "CACHED_PASS");
        fs::write(root.join("src/second.rs"), "fn more() {}").unwrap();
        assert_eq!(check(root, 0)["checks"][0]["status"], "PASS");
    }

    #[test]
    fn state_and_working_directory_symlinks_do_not_escape() {
        let project = project();
        let outside = TempDir::new().unwrap();
        let root = project.path();
        std::os::unix::fs::symlink(outside.path(), root.join(".loopsieve")).unwrap();
        config(root, json!([shell("fixture", "printf observed; exit 3")]));
        let result = check(root, 1);
        assert_eq!(result["checks"][0]["status"], "FAIL");
        assert!(
            result["state_warning"]
                .as_str()
                .unwrap()
                .contains("symlink")
        );
        assert!(fs::read_dir(outside.path()).unwrap().next().is_none());
        let mut spec = shell("fixture", "touch unexpected");
        spec["cwd"] = json!(".loopsieve");
        config(root, json!([spec]));
        assert_eq!(check(root, 1)["checks"][0]["status"], "BLOCKED");
        assert!(!outside.path().join("unexpected").exists());
    }

    #[test]
    fn timeout_and_infrastructure_error_are_observable() {
        let project = project();
        let root = project.path();
        let mut spec = shell("timeout", "printf 'before timeout'; sleep 8");
        spec["timeout_seconds"] = json!(1);
        config(
            root,
            json!([spec,{"name":"missing","command":["./tool-missing-in-fixture"]}]),
        );
        let output = check(root, 1);
        assert_eq!(output["checks"][0]["status"], "TIMEOUT");
        assert_eq!(output["checks"][0]["delta"], "INFRASTRUCTURE_FAILURE");
        assert!(
            output["checks"][0]["excerpt"]
                .as_str()
                .unwrap()
                .contains("before timeout")
        );
        assert_eq!(output["checks"][1]["status"], "ERROR");
    }

    #[test]
    fn interrupt_cancels_the_active_check_without_returning_cached_success() {
        use std::time::{Duration, Instant};

        let project = project();
        let root = project.path();
        let mut cached = shell("cached", "true");
        cached["inputs"] = json!(["source.rs"]);
        cached["complete_inputs"] = json!(true);
        cached["deterministic"] = json!(true);
        config(
            root,
            json!([
                shell("fixture", "test -e delay || exit 0; touch ready; sleep 8"),
                cached
            ]),
        );
        assert_eq!(check(root, 0)["checks"][1]["status"], "PASS");
        assert_eq!(check(root, 0)["checks"][1]["status"], "CACHED_PASS");
        fs::write(root.join("delay"), "").unwrap();
        let child = binary()
            .arg("--root")
            .arg(root)
            .args(["check", "--json", "source.rs"])
            .env_remove("LOOPSIEVE_RUST_STATE_DIR")
            .stdout(Stdio::piped())
            .spawn()
            .unwrap();
        let deadline = Instant::now() + Duration::from_secs(3);
        while !root.join("ready").exists() && Instant::now() < deadline {
            thread::sleep(Duration::from_millis(10));
        }
        let status = Command::new("kill")
            .args(["-s", "INT", &child.id().to_string()])
            .status()
            .unwrap();
        assert!(status.success());
        let output = child.wait_with_output().unwrap();
        assert_eq!(output.status.code(), Some(1));
        let result = value(&output);
        assert_eq!(result["checks"][0]["status"], "CANCELLED");
        assert_eq!(result["checks"][1]["status"], "CANCELLED");
        assert!(value(&run(root, &["cache", "inspect"]))["cached"].is_object());
    }

    #[test]
    fn excessive_output_retains_the_final_error() {
        let project = project();
        let root = project.path();
        let mut spec = shell(
            "fixture",
            "printf 'start\n'; yes noise | head -n 50000; printf 'ERROR terminal cause\n'; exit 1",
        );
        spec["max_output_chars"] = json!(501);
        config(root, json!([spec]));
        let response = check(root, 1);
        let result = &response["checks"][0];
        assert!(result["omitted_bytes"].as_u64().unwrap() > 100_000);
        let excerpt = result["excerpt"].as_str().unwrap();
        assert!(excerpt.len() < 600 && excerpt.contains("terminal cause"));
    }
    #[test]
    fn secrets_and_terminal_sequences_are_not_saved() {
        let project = project();
        let root = project.path();
        let token = ["ghp_", &"x".repeat(36)].concat();
        let script = format!("printf '\\033[31mBearer {token}\\033[0m\\n'; exit 1");
        config(root, json!([shell("fixture", &script)]));
        let report = check(root, 1);
        assert!(report["context"].as_str().unwrap().contains("[REDACTED]"));
        let evidence = run(root, &["evidence", "export"]);
        let stdout = String::from_utf8(evidence.stdout).unwrap();
        assert!(!stdout.contains(&token));
        assert!(!stdout.contains("\u{001b}"));
    }

    #[test]
    fn parallel_checks_merge_state_and_detect_tampering() {
        let project = project();
        let root = project.path();
        config(root, json!([shell("fixture", "sleep 0.04; printf ok")]));
        thread::scope(|scope| {
            let children: Vec<_> = (0..12).map(|_| scope.spawn(|| check(root, 0))).collect();
            for child in children {
                child.join().unwrap();
            }
        });
        let report = value(&run(root, &["report", "--json"]));
        assert_eq!(report["stats"]["runs"], 12);
        assert_eq!(report["history"].as_array().unwrap().len(), 12);
        assert!(run(root, &["evidence", "verify"]).status.success());
        let doctor = run(root, &["doctor"]);
        let output = String::from_utf8(doctor.stdout).unwrap();
        let state_path = output
            .lines()
            .find_map(|line| line.strip_prefix("Rust state: "))
            .unwrap();
        let state_path = Path::new(state_path.rsplit_once(" (").unwrap().0);
        let mut state: Value = serde_json::from_slice(&fs::read(state_path).unwrap()).unwrap();
        state["history"][0]["run"]["context"] = json!("changed");
        fs::write(state_path, state.to_string()).unwrap();
        assert_eq!(run(root, &["evidence", "verify"]).status.code(), Some(2));
        assert!(
            check(root, 0)["state_warning"]
                .as_str()
                .unwrap()
                .contains("digest mismatch")
        );
    }

    #[test]
    fn failed_mission_blocks_dependent_check_and_keeps_independent_evidence() {
        let project = project();
        let root = project.path();
        config(
            root,
            json!([
                shell("fail", "exit 1"),
                shell("blocked", "touch should-not-run"),
                shell("pass", "true")
            ]),
        );
        let manifest = root.join("mission.json");
        fs::write(
            &manifest,
            json!({"tasks":[
                {"id":"fail","files":["source.rs"],"checks":["fail"]},
                {"id":"dependent","files":["source.rs"],"checks":["blocked"],"depends_on":["fail"]},
                {"id":"independent","files":["source.rs"],"checks":["pass"]}
            ]})
            .to_string(),
        )
        .unwrap();
        let output = run(root, &["run", "mission.json"]);
        // Relative manifest paths are resolved by the caller, as with ordinary files.
        assert_eq!(output.status.code(), Some(2));
        let output = run(root, &["run", manifest.to_str().unwrap()]);
        assert_eq!(output.status.code(), Some(1));
        let result = value(&output);
        assert_eq!(result[0]["status"], "FAILED");
        assert_eq!(result[1]["status"], "BLOCKED");
        assert_eq!(result[2]["status"], "VERIFIED");
        assert_eq!(result[2]["run"]["task_id"], "independent");
        assert!(!root.join("should-not-run").exists());
        assert_eq!(value(&run(root, &["report", "--json"]))["stats"]["runs"], 2);
    }
}
