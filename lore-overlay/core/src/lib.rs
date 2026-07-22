//! `lore-capture-core` — the platform-agnostic "brain" of the Lore capture
//! overlay (provisional name; see `lore-overlay/README.md`).
//!
//! It implements the capture flow that the desktop shell (Tauri) wraps, and that
//! any other host could reuse: take an author's raw intent, draft a typed
//! artifact through a bring-your-own gateway, validate it deterministically with
//! the `rac` engine, and **propose** it as a draft pull request. It never lands
//! anything.
//!
//! ## The two-gate write model (ADR-077)
//!
//! - **Gate 1 — fidelity.** [`CaptureFlow::propose`] turns intent into a
//!   [`Proposal`] the author confirms in the host UI. This is a data-quality
//!   check, not a trust boundary; no file is written and nothing is pushed.
//! - **Gate 2 — trust boundary.** [`CaptureFlow::publish`] writes the artifact,
//!   validates it, commits it to a branch, and (unless the [`WriteMode`] is
//!   `Direct`) ensures a **draft** pull request. The independent maintainer's
//!   merge is the trust boundary. The PR's *granularity* is configurable —
//!   per-capture, a rolling batch, or none — but the [`Publisher`] trait has no
//!   approve/merge method by construction, so the host can only *propose* in
//!   every mode.
//!
//! The model call (gateway) and git writes (publisher) live behind traits so the
//! core is testable offline; the concrete network implementations are compiled
//! only under the `net` feature.

mod config;
mod error;
mod flow;
mod gateway;
mod github;
mod rac;

pub use config::{Config, GatewayConfig, RepoConfig, WriteMode};
pub use error::CaptureError;
pub use flow::{parse_minted_id, CaptureFlow, CaptureOutcome, Proposal};
pub use gateway::{DraftedArtifact, Gateway};
pub use github::{CommitRequest, CommitResult, PrRequest, PrResult, Publisher};
pub use rac::{Rac, RacClient};

#[cfg(feature = "net")]
pub use gateway::OpenAiGateway;
#[cfg(feature = "net")]
pub use github::GithubPublisher;
