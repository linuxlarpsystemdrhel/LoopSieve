//! Offline model estimates and explicitly authorized, checksum-pinned files.

use crate::catalog;
use crate::config::within;
use anyhow::{Context, Result, bail, ensure};
use serde::Serialize;
use sha2::{Digest, Sha256};
use std::fs::{self, File};
use std::io::{self, Read};
use std::path::{Component, Path};
use std::time::Duration;
use url::Url;

pub const DEFAULT_LIMIT: u64 = 20 * 1024 * 1024 * 1024;

#[derive(Serialize)]
pub struct Estimate {
    kind: &'static str,
    quantization: String,
    bits_per_weight: f64,
    context_tokens: u64,
    weights_mib: f64,
    kv_cache_mib: f64,
    compute_buffers_mib: f64,
    runtime_overhead_mib: f64,
    safety_margin_mib: f64,
    total_mib: f64,
}

pub fn estimate(id: &str, quantization: &str, context: Option<u64>) -> Result<Estimate> {
    let model = catalog::entry("models", id)?;
    let quantization = quantization.to_ascii_lowercase().replace('-', "_");
    let bits = match quantization.as_str() {
        "q8_0" => 8.5,
        "q6_k" => 6.56,
        "q5_k_m" => 5.5,
        "q4_k_m" => 4.5,
        "q4_k_s" => 4.3,
        "iq4_xs" => 4.25,
        "q3_k_m" => 3.5,
        "q3_k_s" | "iq3_xs" => 3.3,
        "iq2_m" => 2.7,
        "q2_k" => 2.6,
        "iq1_m" => 1.75,
        _ => bail!("unknown quantization profile"),
    };
    let tokens = context.unwrap_or_else(|| model["context_tokens"].as_u64().unwrap_or(8192));
    let layers = model["layers"]
        .as_u64()
        .filter(|n| *n > 0)
        .context("invalid layer count")?;
    let heads = model["kv_heads"]
        .as_u64()
        .filter(|n| *n > 0)
        .context("invalid KV head count")?;
    let dimension = model["head_dim"]
        .as_u64()
        .filter(|n| *n > 0)
        .context("invalid head dimension")?;
    let parameters = model["params_b"]
        .as_f64()
        .filter(|n| *n > 0.0)
        .context("invalid model size")?;
    ensure!(
        (1..=10_000_000).contains(&tokens),
        "context must be 1..=10000000 tokens"
    );
    let mib = 1024.0 * 1024.0;
    let weights = parameters * 1e9 * bits / 8.0 / mib;
    let cache = 4.0 * layers as f64 * heads as f64 * dimension as f64 * tokens as f64 / mib;
    let compute = (weights * 0.04).max(256.0);
    let runtime = 512.0;
    let subtotal = weights + cache + compute + runtime;
    Ok(Estimate {
        kind: "ESTIMATE_NOT_MEASUREMENT",
        quantization,
        bits_per_weight: bits,
        context_tokens: tokens,
        weights_mib: weights,
        kv_cache_mib: cache,
        compute_buffers_mib: compute,
        runtime_overhead_mib: runtime,
        safety_margin_mib: subtotal * 0.12,
        total_mib: subtotal * 1.12,
    })
}

#[derive(Serialize)]
pub struct VerifiedFile {
    pub sha256: String,
    pub bytes: u64,
}

fn checksum(expected: &str) -> Result<String> {
    ensure!(
        expected.len() == 64 && expected.bytes().all(|byte| byte.is_ascii_hexdigit()),
        "expected exactly 64 hexadecimal SHA-256 characters"
    );
    Ok(expected.to_ascii_lowercase())
}

fn transfer(
    mut input: impl Read,
    mut output: impl io::Write,
    expected: &str,
    limit: u64,
) -> Result<VerifiedFile> {
    let mut hasher = Sha256::new();
    let mut bytes = 0u64;
    let mut buffer = vec![0; 128 * 1024];
    loop {
        let read = match input.read(&mut buffer) {
            Ok(read) => read,
            Err(error) if error.kind() == io::ErrorKind::Interrupted => continue,
            Err(error) => return Err(error.into()),
        };
        if read == 0 {
            break;
        }
        bytes += read as u64;
        ensure!(
            bytes <= limit,
            "model file exceeds the configured byte limit"
        );
        hasher.update(&buffer[..read]);
        output.write_all(&buffer[..read])?;
    }
    let sha256 = format!("{:x}", hasher.finalize());
    ensure!(sha256 == expected, "model file SHA-256 mismatch");
    Ok(VerifiedFile { sha256, bytes })
}

pub fn verify_file(path: &Path, sha256: &str, limit: u64) -> Result<VerifiedFile> {
    let expected = checksum(sha256)?;
    let metadata = fs::metadata(path)?;
    ensure!(
        metadata.is_file() && metadata.len() <= limit,
        "model must be a regular file within the byte limit"
    );
    let file = File::open(path)?;
    transfer(file, io::sink(), &expected, limit)
}

pub struct Download<'a> {
    pub name: &'a str,
    pub url: &'a str,
    pub sha256: &'a str,
    pub license: &'a str,
    pub accepted: bool,
    pub approved: bool,
    pub limit: u64,
}

pub fn download(root: &Path, request: Download<'_>) -> Result<VerifiedFile> {
    ensure!(
        request.accepted && request.approved && !request.license.trim().is_empty(),
        "model download requires --license, --accept-license and --approve-download"
    );
    let expected = checksum(request.sha256)?;
    let filename = Path::new(request.name);
    ensure!(
        matches!(
            filename.components().collect::<Vec<_>>().as_slice(),
            [Component::Normal(_)]
        ) && !request.name.starts_with('.')
            && !request.name.contains(['\\', ':', '/'])
            && !request.name.chars().any(char::is_control)
            && request.name.ends_with(".gguf"),
        "expected a plain .gguf filename"
    );
    ensure!(
        (1..=128 * 1024 * 1024 * 1024).contains(&request.limit),
        "max-bytes must be positive and no larger than 128 GiB"
    );
    let mut url = checked_url(request.url)?;
    let relative = Path::new(".local-models").join(filename);
    let path = within(root, &relative, false)?;
    ensure!(!path.try_exists()?, "model artifact already exists");
    let agent = ureq::AgentBuilder::new()
        .redirects(0)
        .try_proxy_from_env(false)
        .timeout_connect(Duration::from_secs(15))
        .timeout_read(Duration::from_secs(60))
        .timeout(Duration::from_secs(7200))
        .build();
    let mut redirects = 0;
    let response = loop {
        let response = agent
            .get(url.as_str())
            .call()
            .map_err(|_| anyhow::anyhow!("model download request failed"))?;
        match response.status() {
            200 => break response,
            301 | 302 | 303 | 307 | 308 if redirects < 5 => {
                let target = response
                    .header("Location")
                    .context("model download redirect missing Location")?;
                let relative = url
                    .join(target)
                    .map_err(|_| anyhow::anyhow!("invalid model redirect"))?;
                url = checked_url(relative.as_str())?;
                redirects += 1;
            }
            status => bail!("unexpected model download HTTP status {status}"),
        }
    };
    if let Some(length) = response.header("Content-Length") {
        ensure!(
            length.parse::<u64>()? <= request.limit,
            "model response exceeds the configured byte limit"
        );
    }
    let directory = path.parent().context("model directory is unavailable")?;
    fs::create_dir_all(directory)?;
    let mut temporary = tempfile::NamedTempFile::new_in(directory)?;
    let verified = transfer(
        response.into_reader(),
        temporary.as_file_mut(),
        &expected,
        request.limit,
    )?;
    temporary.as_file().sync_all()?;
    ensure!(
        within(root, &relative, false)? == path,
        "model directory changed during download"
    );
    temporary.persist_noclobber(path)?;
    Ok(verified)
}

fn checked_url(raw: &str) -> Result<Url> {
    let url = Url::parse(raw).map_err(|_| anyhow::anyhow!("invalid model download URL"))?;
    ensure!(
        url.scheme() == "https"
            && url.host().is_some()
            && url.username().is_empty()
            && url.password().is_none()
            && url.fragment().is_none(),
        "model download requires an HTTPS URL without embedded credentials or fragments"
    );
    Ok(url)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn transfer_checks_digest_and_byte_limit() {
        let data = b"test model fixture";
        let expected = crate::digest(data);
        let mut out = Vec::new();
        let verified = transfer(&data[..], &mut out, &expected, 100).unwrap();
        assert_eq!(verified.bytes, data.len() as u64);
        assert_eq!(out, data);
        assert!(transfer(&data[..], io::sink(), &expected, 1).is_err());
        assert!(transfer(&data[..], io::sink(), &crate::digest(b"incorrect"), 100).is_err());
    }

    #[test]
    fn model_distribution_requires_https_and_operator_consent() {
        let project = tempfile::tempdir().unwrap();
        let hash = crate::digest(b"fixture");
        let request = Download {
            name: "fixture.gguf",
            url: "http://example.invalid/fixture.gguf",
            sha256: &hash,
            license: "fixture",
            accepted: true,
            approved: true,
            limit: 100,
        };
        assert!(download(project.path(), request).is_err());
        let request = Download {
            url: "https://example.invalid/fixture.gguf",
            approved: false,
            name: "fixture.gguf",
            sha256: &hash,
            license: "fixture",
            accepted: true,
            limit: 100,
        };
        assert!(download(project.path(), request).is_err());
        assert!(!project.path().join(".local-models").exists());
    }
}
