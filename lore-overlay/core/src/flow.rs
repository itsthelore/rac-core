use crate::config::RepoConfig;
use crate::error::CaptureError;
use crate::gateway::Gateway;
use crate::github::{PrResult, ProposalRequest, Publisher};
use crate::rac::Rac;

/// A proposed artifact, produced from raw intent, awaiting the author's fidelity
/// confirmation (Gate 1). Nothing has been written or pushed yet.
#[derive(Clone, Debug)]
pub struct Proposal {
    pub artifact_type: String,
    pub title: String,
    pub body: String,
}

/// The result of publishing a confirmed proposal: a **draft** pull request. It is
/// not landed — an independent maintainer's merge is the trust boundary (Gate 2).
#[derive(Clone, Debug)]
pub struct CaptureOutcome {
    pub path: String,
    pub minted_id: String,
    pub pr: PrResult,
}

/// Orchestrates the capture flow over the three seams. Generic over the traits so
/// the core is exercised with fakes in tests and with the real clients in the app.
pub struct CaptureFlow<R: Rac, G: Gateway, P: Publisher> {
    rac: R,
    gateway: G,
    publisher: P,
    repo: RepoConfig,
}

impl<R: Rac, G: Gateway, P: Publisher> CaptureFlow<R, G, P> {
    pub fn new(rac: R, gateway: G, publisher: P, repo: RepoConfig) -> Self {
        Self {
            rac,
            gateway,
            publisher,
            repo,
        }
    }

    pub fn repo(&self) -> &RepoConfig {
        &self.repo
    }

    /// Gate-1 preparation: turn raw `intent` into a [`Proposal`]. Reads the real
    /// schema and drafts through the gateway. No file is written, nothing is
    /// pushed — the author reviews the proposal next.
    pub fn propose(&self, artifact_type: &str, intent: &str) -> Result<Proposal, CaptureError> {
        let schema = self.rac.schema(artifact_type)?;
        let drafted = self.gateway.draft(artifact_type, &schema, intent)?;
        Ok(Proposal {
            artifact_type: artifact_type.to_string(),
            title: drafted.title,
            body: drafted.body,
        })
    }

    /// After the author confirms the proposal is faithful (Gate 1), scaffold the
    /// file (minting the id), fill the body while keeping the frontmatter,
    /// validate, and open a **draft** pull request. Refuses to proceed if the
    /// publisher ever returns a non-draft PR (Gate 2 is the independent merge).
    pub fn publish(
        &self,
        proposal: &Proposal,
        dest_path: &str,
        branch: &str,
        coauthor_trailer: Option<&str>,
    ) -> Result<CaptureOutcome, CaptureError> {
        let stdout = self.rac.new_artifact(&proposal.artifact_type, dest_path)?;
        let minted_id = parse_minted_id(&stdout).ok_or_else(|| {
            CaptureError::Parse("could not find the minted id in `rac new` output".into())
        })?;

        let scaffold = std::fs::read_to_string(dest_path)?;
        let filled = fill_body(&scaffold, &proposal.title, &proposal.body)?;
        std::fs::write(dest_path, &filled)?;

        // Deterministic close before we propose anything.
        self.rac.validate(dest_path)?;

        let mut pr_body = format!(
            "Proposed via the Lore capture overlay. Fidelity confirmed by the author; this is a \
             **draft** awaiting an independent maintainer's review and merge (ADR-077).\n\n\
             Artifact: `{path}` ({id})\n",
            path = dest_path,
            id = minted_id
        );
        if let Some(trailer) = coauthor_trailer {
            pr_body.push('\n');
            pr_body.push_str(trailer);
            pr_body.push('\n');
        }

        let req = ProposalRequest {
            branch: branch.to_string(),
            path: dest_path.to_string(),
            content: filled,
            commit_message: format!("capture: propose {}", proposal.title),
            pr_title: format!("capture: {}", proposal.title),
            pr_body,
        };
        let pr = self.publisher.open_draft_pr(&req)?;
        if !pr.draft {
            return Err(CaptureError::Publish(
                "refusing to proceed: capture must open a DRAFT pull request (ADR-077)".into(),
            ));
        }
        Ok(CaptureOutcome {
            path: dest_path.to_string(),
            minted_id,
            pr,
        })
    }
}

/// Parse the opaque id that `rac new` reports (a line like `ID: RAC-XXXX`, or any
/// bare `RAC-…` token in the output).
pub fn parse_minted_id(stdout: &str) -> Option<String> {
    for line in stdout.lines() {
        let line = line.trim();
        if let Some(rest) = line.strip_prefix("ID:") {
            return Some(rest.trim().to_string());
        }
        if let Some(tok) = line.split_whitespace().find(|t| t.starts_with("RAC-")) {
            return Some(tok.trim_end_matches(['.', ',']).to_string());
        }
    }
    None
}

/// Replace the scaffold's body with the drafted title + body, keeping the `---`
/// frontmatter block (which carries the minted id and type) byte-for-byte.
fn fill_body(scaffold: &str, title: &str, body: &str) -> Result<String, CaptureError> {
    let rest = scaffold
        .strip_prefix("---\n")
        .ok_or_else(|| CaptureError::Parse("scaffold has no frontmatter".into()))?;
    let end = rest
        .find("\n---\n")
        .ok_or_else(|| CaptureError::Parse("scaffold frontmatter is unterminated".into()))?;
    let frontmatter = &rest[..end];
    Ok(format!(
        "---\n{frontmatter}\n---\n# {title}\n\n{body}\n",
        frontmatter = frontmatter,
        title = title.trim(),
        body = body.trim_end()
    ))
}
