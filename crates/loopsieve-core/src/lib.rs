//! Local verification and evidence for coding workflows.

pub mod agent;
pub mod catalog;
pub mod config;
pub mod diagnostics;
pub mod inference;
pub mod integration;
pub mod legacy;
pub mod mission;
pub mod models;
pub mod runner;
mod snapshot;
pub mod store;
pub mod team;
pub mod toolkit;
pub mod verify;

use sha2::{Digest, Sha256};

pub(crate) fn digest(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}
