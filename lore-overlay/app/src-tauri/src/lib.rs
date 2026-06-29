//! Tauri v2 desktop shell for the Lore capture overlay (provisional name).
//!
//! **Not built or run in this repo.** It targets macOS (a non-activating
//! `NSPanel`, Developer ID signing) and was developed in a Linux container, so
//! the exact plugin API calls below are an authored scaffold, not a compiled
//! surface. The capture logic it calls — [`lore_capture_core`] — is fully tested.
//!
//! The shell's only job is the desktop affordance: a global hotkey summons a
//! modal, which runs the two-gate capture flow via the [`propose`] and [`publish`]
//! commands. All model and git work happens in the core, behind a
//! bring-your-own gateway.

use lore_capture_core::{
    CaptureFlow, Config, GatewayConfig, GithubPublisher, OpenAiGateway, Proposal, RacClient,
    RepoConfig, WriteMode,
};
use tauri::{Manager, WebviewWindow};

// --- configuration / secrets (scaffold) -------------------------------------

/// Load configuration. In the shipped app this reads persisted settings plus the
/// gateway key and a GitHub installation token from the **OS secret store**; here
/// it reads env vars so the wiring type-checks. TODO: real settings + keychain.
fn load_config() -> Config {
    Config {
        gateway: GatewayConfig {
            base_url: env("LORE_GATEWAY_URL"),
            model: env("LORE_GATEWAY_MODEL"),
            api_key: env("LORE_GATEWAY_KEY"),
        },
        repo: RepoConfig {
            owner: env("LORE_REPO_OWNER"),
            repo: env("LORE_REPO_NAME"),
            base_branch: std::env::var("LORE_REPO_BASE").unwrap_or_else(|_| "main".into()),
        },
        hotkey: std::env::var("LORE_HOTKEY").unwrap_or_else(|_| "CmdOrCtrl+Shift+L".into()),
        rac_command: std::env::var("LORE_RAC").unwrap_or_else(|_| "rac".into()),
        write_mode: match std::env::var("LORE_WRITE_MODE").as_deref() {
            Ok("per-capture") => WriteMode::PerCapture,
            Ok("direct") => WriteMode::Direct,
            _ => WriteMode::Rolling, // default: batch draft PR
        },
        capture_branch: std::env::var("LORE_CAPTURE_BRANCH")
            .unwrap_or_else(|_| "capture/inbox".into()),
    }
}

/// The branch a capture in the current mode targets (for `PerCapture`, the slug
/// is appended at publish time, so this is a label).
fn target_branch(cfg: &Config, slug: Option<&str>) -> String {
    match cfg.write_mode {
        WriteMode::PerCapture => match slug {
            Some(s) => format!("capture/{s}"),
            None => "capture/<per-capture>".to_string(),
        },
        WriteMode::Rolling | WriteMode::Direct => cfg.capture_branch.clone(),
    }
}

fn mode_label(mode: WriteMode) -> &'static str {
    match mode {
        WriteMode::PerCapture => "draft PR per capture",
        WriteMode::Rolling => "batch draft PR",
        WriteMode::Direct => "commit only",
    }
}

/// The GitHub bearer token — a GitHub App installation token (obtained via the
/// device flow) in the shipped app; a PAT works for development.
fn github_token() -> String {
    env("LORE_GITHUB_TOKEN")
}

fn env(key: &str) -> String {
    std::env::var(key).unwrap_or_default()
}

fn build_flow(cfg: &Config) -> CaptureFlow<RacClient, OpenAiGateway, GithubPublisher> {
    CaptureFlow::new(
        RacClient::new(cfg.rac_command.clone()),
        OpenAiGateway::new(&cfg.gateway),
        GithubPublisher::new(cfg.repo.owner.clone(), cfg.repo.repo.clone(), github_token()),
        cfg.repo.clone(),
    )
}

// --- the two gates, as Tauri commands ---------------------------------------

#[derive(serde::Serialize)]
struct ProposalView {
    artifact_type: String,
    title: String,
    body: String,
}

/// Gate 1 — fidelity: draft a proposal from the author's words. No file written.
#[tauri::command]
fn propose(artifact_type: String, intent: String) -> Result<ProposalView, String> {
    let cfg = load_config();
    let flow = build_flow(&cfg);
    let p = flow
        .propose(&artifact_type, &intent)
        .map_err(|e| e.to_string())?;
    Ok(ProposalView {
        artifact_type: p.artifact_type,
        title: p.title,
        body: p.body,
    })
}

#[derive(serde::Serialize)]
struct OutcomeView {
    path: String,
    minted_id: String,
    branch: String,
    mode: String,
    pr_url: String,
}

/// A read-only view of where the next capture will land, for the modal's footer.
#[derive(serde::Serialize)]
struct TargetView {
    repo: String,
    branch: String,
    mode: String,
    opens_pr: bool,
}

/// Where a capture lands under the current config — repo, branch, and mode.
#[tauri::command]
fn capture_target() -> TargetView {
    let cfg = load_config();
    TargetView {
        repo: format!("{}/{}", cfg.repo.owner, cfg.repo.repo),
        branch: target_branch(&cfg, None),
        mode: mode_label(cfg.write_mode).to_string(),
        opens_pr: cfg.write_mode != WriteMode::Direct,
    }
}

/// Gate 2 prep: after the author confirms, write + validate + commit, and (unless
/// the mode is `Direct`) ensure a DRAFT pull request. The core refuses any
/// non-draft PR; the independent merge is Gate 2. `slug` derives the per-capture
/// branch; it is ignored in rolling/direct modes.
#[tauri::command]
#[allow(clippy::too_many_arguments)]
fn publish(
    artifact_type: String,
    title: String,
    body: String,
    dest_path: String,
    slug: String,
    coauthor: Option<String>,
) -> Result<OutcomeView, String> {
    let cfg = load_config();
    let flow = build_flow(&cfg);
    let proposal = Proposal {
        artifact_type,
        title,
        body,
    };
    let branch = target_branch(&cfg, Some(&slug));
    let outcome = flow
        .publish(&proposal, &dest_path, &branch, cfg.write_mode, coauthor.as_deref())
        .map_err(|e| e.to_string())?;
    Ok(OutcomeView {
        path: outcome.path,
        minted_id: outcome.minted_id,
        branch: outcome.branch,
        mode: mode_label(outcome.mode).to_string(),
        pr_url: outcome.pr.map(|p| p.url).unwrap_or_default(),
    })
}

// --- desktop shell: a global hotkey toggles the capture modal ----------------

fn toggle(window: &WebviewWindow) {
    if window.is_visible().unwrap_or(false) {
        let _ = window.hide();
    } else {
        let _ = window.show();
        let _ = window.set_focus();
    }
}

pub fn run() {
    use tauri_plugin_global_shortcut::{
        Builder as ShortcutBuilder, GlobalShortcutExt, ShortcutState,
    };

    tauri::Builder::default()
        .plugin(
            ShortcutBuilder::new()
                .with_handler(|app, _shortcut, event| {
                    if event.state() == ShortcutState::Pressed {
                        if let Some(win) = app.get_webview_window("capture") {
                            toggle(&win);
                        }
                    }
                })
                .build(),
        )
        .setup(|app| {
            let hotkey = load_config().hotkey;
            app.global_shortcut().register(hotkey.as_str())?;
            // macOS enhancement (TODO): promote the "capture" window to a
            // non-activating NSPanel that joins all Spaces, so the overlay never
            // steals focus from the app the author is working in.
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![propose, publish, capture_target])
        .run(tauri::generate_context!())
        .expect("error while running the Lore capture overlay");
}
