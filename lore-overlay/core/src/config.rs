use serde::{Deserialize, Serialize};

/// Bring-your-own gateway (ADR-035): any OpenAI-compatible endpoint the operator
/// controls — a self-hosted LiteLLM proxy, a cloud vendor, or a local model.
///
/// The `api_key` is `#[serde(skip)]` so it is never written into a config file or
/// logged; in the shipped app it is read from the OS secret store at runtime.
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct GatewayConfig {
    /// OpenAI-compatible base URL, e.g. `http://localhost:4000/v1`.
    pub base_url: String,
    /// Model name as the gateway knows it.
    pub model: String,
    #[serde(skip)]
    pub api_key: String,
}

/// The repository a capture proposes into.
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct RepoConfig {
    pub owner: String,
    pub repo: String,
    #[serde(default = "default_base_branch")]
    pub base_branch: String,
}

fn default_base_branch() -> String {
    "main".to_string()
}

/// How a capture lands. The PR is the *trust boundary* (ADR-077 Gate 2), not the
/// save action — so its granularity is configurable without weakening the model.
/// In every mode the host only ever *proposes*; it never merges.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize, Default)]
#[serde(rename_all = "kebab-case")]
pub enum WriteMode {
    /// A new branch and a draft PR for every capture. Highest ceremony; suits a
    /// repo where each decision warrants its own review thread.
    PerCapture,
    /// Append each capture to one shared branch with a single rolling batch draft
    /// PR — review on the maintainer's cadence, not per artifact. The default:
    /// it keeps Gate 2 (independent merge) while removing per-doc overhead.
    #[default]
    Rolling,
    /// Commit straight to a branch, no PR — for a solo/personal repo where there
    /// is no independent reviewer and a PR would be self-approval theatre. Never
    /// targets the base branch directly; content still lands on a branch.
    Direct,
}

fn default_capture_branch() -> String {
    "capture/inbox".to_string()
}

/// The overlay's whole persisted configuration.
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Config {
    pub gateway: GatewayConfig,
    pub repo: RepoConfig,
    /// Global hotkey, in Tauri accelerator syntax.
    #[serde(default = "default_hotkey")]
    pub hotkey: String,
    /// How to invoke the `rac` engine (bundled, on PATH, or a wrapper).
    #[serde(default = "default_rac_command")]
    pub rac_command: String,
    /// How captures land (per-capture PR, rolling batch PR, or direct commit).
    #[serde(default)]
    pub write_mode: WriteMode,
    /// Branch used by `Rolling` and `Direct` modes. `PerCapture` derives its own
    /// branch per capture and ignores this.
    #[serde(default = "default_capture_branch")]
    pub capture_branch: String,
}

fn default_hotkey() -> String {
    "CmdOrCtrl+Shift+L".to_string()
}

fn default_rac_command() -> String {
    "rac".to_string()
}
