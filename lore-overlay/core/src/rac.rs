use crate::error::CaptureError;
use std::process::Command;

/// The deterministic engine seam. The core shells to the `rac` CLI rather than
/// reimplementing classification or validation (ADR-063: thin client over the
/// published contract; ADR-002/067: no AI in the engine).
pub trait Rac {
    /// The JSON schema for an artifact type (`rac schema <type> --json`).
    fn schema(&self, artifact_type: &str) -> Result<String, CaptureError>;
    /// Scaffold a new artifact (`rac new <type> <path>`), minting the opaque id.
    /// Returns the command's stdout, which reports the minted id.
    fn new_artifact(&self, artifact_type: &str, path: &str) -> Result<String, CaptureError>;
    /// Deterministic close (`rac validate <path>`). `Ok(())` iff the file is valid.
    fn validate(&self, path: &str) -> Result<(), CaptureError>;
}

/// Shells out to a real `rac` binary.
///
/// `program` plus `base_args` are prefixed before every subcommand, so a wrapper
/// invocation (`env PYTHONPATH=… python racrun.py`) works as well as a bare
/// `rac` on `PATH`.
#[derive(Clone, Debug)]
pub struct RacClient {
    program: String,
    base_args: Vec<String>,
}

impl RacClient {
    pub fn new(program: impl Into<String>) -> Self {
        Self {
            program: program.into(),
            base_args: Vec::new(),
        }
    }

    /// Extra args inserted before every subcommand.
    pub fn with_base_args(mut self, args: Vec<String>) -> Self {
        self.base_args = args;
        self
    }

    fn run(&self, args: &[&str]) -> Result<std::process::Output, CaptureError> {
        Command::new(&self.program)
            .args(&self.base_args)
            .args(args)
            .output()
            .map_err(|e| CaptureError::Rac(format!("failed to run `{}`: {e}", self.program)))
    }
}

impl Rac for RacClient {
    fn schema(&self, artifact_type: &str) -> Result<String, CaptureError> {
        let out = self.run(&["schema", artifact_type, "--json"])?;
        if !out.status.success() {
            return Err(CaptureError::Rac(stderr(&out)));
        }
        Ok(String::from_utf8_lossy(&out.stdout).into_owned())
    }

    fn new_artifact(&self, artifact_type: &str, path: &str) -> Result<String, CaptureError> {
        let out = self.run(&["new", artifact_type, path])?;
        if !out.status.success() {
            return Err(CaptureError::Rac(stderr(&out)));
        }
        Ok(String::from_utf8_lossy(&out.stdout).into_owned())
    }

    fn validate(&self, path: &str) -> Result<(), CaptureError> {
        let out = self.run(&["validate", path])?;
        if out.status.success() {
            Ok(())
        } else {
            Err(CaptureError::Rac(format!(
                "{}{}",
                String::from_utf8_lossy(&out.stdout),
                stderr(&out)
            )))
        }
    }
}

fn stderr(out: &std::process::Output) -> String {
    String::from_utf8_lossy(&out.stderr).into_owned()
}
