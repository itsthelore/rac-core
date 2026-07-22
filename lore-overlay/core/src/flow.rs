use crate::config::{RepoConfig, WriteMode};
use crate::error::CaptureError;
use crate::gateway::Gateway;
use crate::github::{CommitRequest, PrRequest, PrResult, Publisher};
use crate::rac::Rac;

/// A proposed artifact, produced from raw intent, awaiting the author's fidelity
/// confirmation (Gate 1). Nothing has been written or pushed yet.
#[derive(Clone, Debug)]
pub struct Proposal {
    pub artifact_type: String,
    pub title: String,
    pub body: String,
}

/// The result of publishing a confirmed proposal. The artifact is committed to a
/// branch and, unless the write mode is `Direct`, proposed as a **draft** pull
/// request. It is never landed — an independent maintainer's merge is the trust
/// boundary (Gate 2).
#[derive(Clone, Debug)]
pub struct CaptureOutcome {
    pub path: String,
    pub minted_id: String,
    /// The branch the artifact was committed to.
    pub branch: String,
    /// How it landed.
    pub mode: WriteMode,
    /// The draft PR, when the mode opens one (`None` for `Direct`).
    pub pr: Option<PrResult>,
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

    /// Borrow the publisher — lets a host (or a test) inspect the write seam.
    pub fn publisher(&self) -> &P {
        &self.publisher
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
    /// validate, and commit it to `branch`. Then, unless `mode` is `Direct`,
    /// ensure a **draft** pull request — reusing an open one in `Rolling` mode so
    /// successive captures share a single batch PR. Refuses to proceed if the
    /// publisher ever returns a non-draft PR (Gate 2 is the independent merge).
    pub fn publish(
        &self,
        proposal: &Proposal,
        dest_path: &str,
        branch: &str,
        mode: WriteMode,
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

        // Save is a commit (ADR-077): the artifact lands on a branch first.
        self.publisher.commit_file(&CommitRequest {
            branch: branch.to_string(),
            base_branch: self.repo.base_branch.clone(),
            path: dest_path.to_string(),
            content: filled,
            message: format!("capture: propose {}", proposal.title),
        })?;

        // Promotion is a PR — its granularity follows the write mode. `Direct`
        // skips it (a solo repo with no independent reviewer); the others ensure
        // a draft PR, which `Rolling` shares across captures as a batch.
        let pr = match mode {
            WriteMode::Direct => None,
            WriteMode::PerCapture | WriteMode::Rolling => {
                let mut pr_body = format!(
                    "Proposed via the Lore capture overlay. Fidelity confirmed by the author; \
                     this is a **draft** awaiting an independent maintainer's review and merge \
                     (ADR-077).\n\nArtifact: `{path}` ({id})\n",
                    path = dest_path,
                    id = minted_id
                );
                if let Some(trailer) = coauthor_trailer {
                    pr_body.push('\n');
                    pr_body.push_str(trailer);
                    pr_body.push('\n');
                }
                // A stable title in `Rolling` so the same batch PR is recognisable.
                let pr_title = match mode {
                    WriteMode::Rolling => "capture: proposed artifacts (batch)".to_string(),
                    _ => format!("capture: {}", proposal.title),
                };
                let pr = self.publisher.ensure_draft_pr(&PrRequest {
                    branch: branch.to_string(),
                    base_branch: self.repo.base_branch.clone(),
                    title: pr_title,
                    body: pr_body,
                })?;
                if !pr.draft {
                    return Err(CaptureError::Publish(
                        "refusing to proceed: capture must open a DRAFT pull request (ADR-077)"
                            .into(),
                    ));
                }
                Some(pr)
            }
        };

        Ok(CaptureOutcome {
            path: dest_path.to_string(),
            minted_id,
            branch: branch.to_string(),
            mode,
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
