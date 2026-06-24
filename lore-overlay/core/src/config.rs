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
}

fn default_hotkey() -> String {
    "CmdOrCtrl+Shift+L".to_string()
}

fn default_rac_command() -> String {
    "rac".to_string()
}
