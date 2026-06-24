use crate::error::CaptureError;

/// Everything needed to open a draft pull request proposing one artifact.
#[derive(Clone, Debug)]
pub struct ProposalRequest {
    /// New branch to create off the base branch.
    pub branch: String,
    /// Repo-relative path of the artifact file.
    pub path: String,
    /// Full file content to commit.
    pub content: String,
    pub commit_message: String,
    pub pr_title: String,
    pub pr_body: String,
}

/// The opened pull request.
#[derive(Clone, Debug)]
pub struct PrResult {
    pub url: String,
    pub number: u64,
    pub draft: bool,
}

/// The write seam. A capture host only ever **proposes**: it opens a draft pull
/// request and never approves or merges (ADR-065 / ADR-077). The trait has no
/// approve or merge method by construction, so the two-gate model cannot be
/// violated by a host that uses this core.
pub trait Publisher {
    fn open_draft_pr(&self, req: &ProposalRequest) -> Result<PrResult, CaptureError>;
}

/// Real GitHub publisher over the REST API. Compiled only for the desktop app,
/// behind the `net` feature.
///
/// It is given a bearer `token` (a GitHub App installation token in the shipped
/// app; a PAT is fine for development). Obtaining that token — the desktop
/// device-flow install — is the shell's job, recorded as an open question in the
/// `lore-capture-overlay` design.
#[cfg(feature = "net")]
pub struct GithubPublisher {
    owner: String,
    repo: String,
    base_branch: String,
    token: String,
    api_base: String,
    client: reqwest::blocking::Client,
}

#[cfg(feature = "net")]
impl GithubPublisher {
    pub fn new(
        owner: impl Into<String>,
        repo: impl Into<String>,
        base_branch: impl Into<String>,
        token: impl Into<String>,
    ) -> Self {
        Self {
            owner: owner.into(),
            repo: repo.into(),
            base_branch: base_branch.into(),
            token: token.into(),
            api_base: "https://api.github.com".to_string(),
            client: reqwest::blocking::Client::new(),
        }
    }

    fn get(&self, path: &str) -> reqwest::blocking::RequestBuilder {
        self.client
            .get(format!("{}{}", self.api_base, path))
            .bearer_auth(&self.token)
            .header("Accept", "application/vnd.github+json")
            .header("User-Agent", "lore-capture-overlay")
    }

    fn post(&self, path: &str) -> reqwest::blocking::RequestBuilder {
        self.client
            .post(format!("{}{}", self.api_base, path))
            .bearer_auth(&self.token)
            .header("Accept", "application/vnd.github+json")
            .header("User-Agent", "lore-capture-overlay")
    }

    fn put(&self, path: &str) -> reqwest::blocking::RequestBuilder {
        self.client
            .put(format!("{}{}", self.api_base, path))
            .bearer_auth(&self.token)
            .header("Accept", "application/vnd.github+json")
            .header("User-Agent", "lore-capture-overlay")
    }
}

#[cfg(feature = "net")]
impl Publisher for GithubPublisher {
    fn open_draft_pr(&self, req: &ProposalRequest) -> Result<PrResult, CaptureError> {
        use base64::Engine as _;
        let err = |e: reqwest::Error| CaptureError::Publish(e.to_string());

        // 1. Base branch tip sha.
        let base_ref = self
            .get(&format!(
                "/repos/{}/{}/git/ref/heads/{}",
                self.owner, self.repo, self.base_branch
            ))
            .send()
            .map_err(err)?
            .error_for_status()
            .map_err(err)?
            .json::<serde_json::Value>()
            .map_err(err)?;
        let base_sha = base_ref["object"]["sha"]
            .as_str()
            .ok_or_else(|| CaptureError::Publish("no base sha".into()))?
            .to_string();

        // 2. Create the work branch.
        self.post(&format!("/repos/{}/{}/git/refs", self.owner, self.repo))
            .json(&serde_json::json!({
                "ref": format!("refs/heads/{}", req.branch),
                "sha": base_sha,
            }))
            .send()
            .map_err(err)?
            .error_for_status()
            .map_err(err)?;

        // 3. Write the file on the new branch.
        let content_b64 = base64::engine::general_purpose::STANDARD.encode(req.content.as_bytes());
        self.put(&format!(
            "/repos/{}/{}/contents/{}",
            self.owner, self.repo, req.path
        ))
        .json(&serde_json::json!({
            "message": req.commit_message,
            "content": content_b64,
            "branch": req.branch,
        }))
        .send()
        .map_err(err)?
        .error_for_status()
        .map_err(err)?;

        // 4. Open a DRAFT pull request. Never approves or merges.
        let pr = self
            .post(&format!("/repos/{}/{}/pulls", self.owner, self.repo))
            .json(&serde_json::json!({
                "title": req.pr_title,
                "body": req.pr_body,
                "head": req.branch,
                "base": self.base_branch,
                "draft": true,
            }))
            .send()
            .map_err(err)?
            .error_for_status()
            .map_err(err)?
            .json::<serde_json::Value>()
            .map_err(err)?;

        Ok(PrResult {
            url: pr["html_url"].as_str().unwrap_or_default().to_string(),
            number: pr["number"].as_u64().unwrap_or_default(),
            draft: pr["draft"].as_bool().unwrap_or(false),
        })
    }
}
