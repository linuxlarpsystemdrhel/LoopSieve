//! Read-only dashboard for loopback connections.

use anyhow::{Result, bail, ensure};
use loopsieve_core::agent::Runtime;
use loopsieve_core::config::Config;
use loopsieve_core::store::{State, Store};
use serde_json::{Value, json};
use std::io::{BufRead, BufReader, Read, Write};
use std::net::{TcpListener, TcpStream};
use std::path::Path;
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::{Duration, Instant};

pub fn launch(root: &Path, config: &Config, port: u16, cancelled: &AtomicBool) -> Result<()> {
    ensure!(port > 0, "dashboard port must be nonzero");
    let listener = TcpListener::bind((std::net::Ipv4Addr::LOCALHOST, port))?;
    listener.set_nonblocking(true)?;
    let authority = format!("127.0.0.1:{port}");
    let runtime = Runtime::open(root, config)?;
    let store = Store::new(root, config);
    println!("LoopSieve dashboard · http://{authority}");
    std::io::stdout().flush()?;
    while !cancelled.load(Ordering::Relaxed) {
        match listener.accept() {
            Ok((mut stream, _)) => {
                let _ = serve(&mut stream, &authority, &runtime, &store);
            }
            Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                std::thread::sleep(Duration::from_millis(30))
            }
            Err(error) if error.kind() == std::io::ErrorKind::Interrupted => continue,
            Err(error) => return Err(error.into()),
        }
    }
    Ok(())
}

fn serve(
    stream: &mut TcpStream,
    authority: &str,
    runtime: &Runtime<'_>,
    store: &Store,
) -> Result<()> {
    stream.set_nonblocking(false)?;
    stream.set_write_timeout(Some(Duration::from_secs(1)))?;
    let reader = RequestReader {
        stream,
        deadline: Instant::now() + Duration::from_secs(2),
    };
    let request = request_path(BufReader::new(reader), authority);
    let (status, mime, body) = match request.as_deref() {
        Err(_) => (
            "400 Bad Request",
            "text/plain",
            "Invalid local request".into(),
        ),
        Ok("/") => (
            "200 OK",
            "text/html; charset=utf-8",
            include_str!("dashboard.html").into(),
        ),
        Ok("/api/dashboard") => match dashboard(runtime, store) {
            Ok(data) => ("200 OK", "application/json", serde_json::to_string(&data)?),
            Err(_) => (
                "500 Internal Server Error",
                "text/plain",
                "Local state is unavailable".into(),
            ),
        },
        _ => ("404 Not Found", "text/plain", "Route not found".into()),
    };
    write!(
        stream,
        "HTTP/1.1 {status}\r\nContent-Type: {mime}\r\nContent-Length: {}\r\nConnection: close\r\nCache-Control: no-store\r\nX-Content-Type-Options: nosniff\r\nContent-Security-Policy: default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'\r\n\r\n{body}",
        body.len()
    )?;
    Ok(())
}

struct RequestReader<'a> {
    stream: &'a TcpStream,
    deadline: Instant,
}

impl Read for RequestReader<'_> {
    fn read(&mut self, buffer: &mut [u8]) -> std::io::Result<usize> {
        let remaining = self.deadline.saturating_duration_since(Instant::now());
        if remaining.is_zero() {
            return Err(std::io::ErrorKind::TimedOut.into());
        }
        self.stream.set_read_timeout(Some(remaining))?;
        self.stream.read(buffer)
    }
}

fn request_path(reader: impl BufRead, authority: &str) -> Result<String> {
    let mut reader = reader.take(8193);
    let mut line = String::new();
    reader.read_line(&mut line)?;
    let fields: Vec<_> = line.trim_end_matches("\r\n").split(' ').collect();
    let ["GET", path, "HTTP/1.1"] = fields.as_slice() else {
        bail!("expected a GET request");
    };
    let mut host = false;
    let expected_origin = format!("http://{authority}");
    loop {
        let mut line = String::new();
        ensure!(reader.read_line(&mut line)? > 0, "incomplete headers");
        if line == "\r\n" {
            break;
        }
        let (header, value) = line
            .trim_end_matches("\r\n")
            .split_once(':')
            .ok_or_else(|| anyhow::anyhow!("invalid header"))?;
        let value = value.trim();
        if header.eq_ignore_ascii_case("host") {
            ensure!(
                !host && value == authority,
                "invalid or repeated local host"
            );
            host = true;
        } else if header.eq_ignore_ascii_case("origin") {
            ensure!(value == expected_origin, "invalid local origin");
        } else if header.eq_ignore_ascii_case("content-length") {
            ensure!(value == "0", "request body is unsupported");
        } else if header.eq_ignore_ascii_case("transfer-encoding") {
            bail!("request body is unsupported");
        }
    }
    ensure!(
        host && reader.limit() > 0,
        "missing local host or headers exceeded size limit"
    );
    Ok((*path).into())
}

fn dashboard(runtime: &Runtime<'_>, store: &Store) -> Result<Value> {
    let state: State = store.read()?;
    let sessions = runtime.list()?.into_iter().take(200).map(|row| json!({
        "id":row["id"], "agent_id":row["agent_id"], "status":row["status"], "step":row["step"],
    })).collect::<Vec<_>>();
    let checks = state.history.last().map(|entry| entry.run.checks.iter().map(|check| json!({
        "name":loopsieve_core::diagnostics::redact(&check.name), "duration_ms":check.duration_ms,"status":check.status,"delta":check.delta,
    })).collect::<Vec<_>>()).unwrap_or_default();
    Ok(json!({"stats":state.stats,"sessions":sessions,"checks":checks}))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn dashboard_accepts_only_local_get_requests_with_bounded_headers() {
        let host = "127.0.0.1:8765";
        assert_eq!(
            request_path(&b"GET / HTTP/1.1\r\nHost: 127.0.0.1:8765\r\n\r\n"[..], host).unwrap(),
            "/"
        );
        for invalid in [
            "GET / HTTP/1.1\r\nHost: untrusted.invalid\r\n\r\n",
            "POST / HTTP/1.1\r\nHost: 127.0.0.1:8765\r\n\r\n",
            "GET / HTTP/1.1\r\nHost: 127.0.0.1:8765\r\nOrigin: http://untrusted.invalid\r\n\r\n",
        ] {
            assert!(request_path(invalid.as_bytes(), host).is_err());
        }
        let oversized = format!(
            "GET / HTTP/1.1\r\nHost: {host}\r\nX-Filler: {}\r\n\r\n",
            "x".repeat(9000)
        );
        assert!(request_path(oversized.as_bytes(), host).is_err());
    }
}
