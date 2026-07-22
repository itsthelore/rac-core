use crate::error::CaptureError;

/// A commit of one artifact onto a branch. The branch is created from
/// `base_branch` if it does not yet exist; an existing file is updated in place,
/// so `Rolling` mode appends successive captures to the same branch.
#[derive(Clone, Debug)]
pub struct CommitRequest {
    pub branch: String,
    pub base_branch: String,
    /// Repo-relative path of the artifact file.
    pub path: String,
    /// Full file content to commit.
    pub content: String,
    pub message: String,
}

/// The result of committing an artifact onto a branch.
#[derive(Clone, Debug)]
pub struct CommitResult {
    pub branch: String,
    /// The commit URL, when the backend reports one.
    pub commit_url: String,
}

/// A request to ensure a DRAFT pull request exists for `branch` → `base_branch`.
#[derive(Clone, Debug)]
pub struct PrRequest {
    pub branch: String,
    pub base_branch: String,
    pub title: String,
    pub body: String,
}

/// The opened (or already-open) pull request.
#[derive(Clone, Debug)]
pub struct PrResult {
    pub url: String,
    pub number: u64,
    pub draft: bool,
}

/// The write seam. A capture host only ever **proposes**: it commits to a branch
/// and, when the write mode calls for it, ensures a *draft* pull request exists.
/// The trait has **no approve or merge method by construction**, so the two-gate
/// model (ADR-065 / ADR-077) cannot be violated by a host built on this core —
/// in any write mode.
pub trait Publisher {
    /// Commit `content` at `path` on `branch`, creating the branch from
    /// `base_branch` if it does not exist. Idempotent: re-committing updates the
    /// file in place rather than failing.
    fn commit_file(&self, req: &CommitRequest) -> Result<CommitResult, CaptureError>;

    /// Ensure a DRAFT pull request is open for `branch`. Returns the existing PR
    /// if one is already open (so `Rolling` mode reuses a single batch PR), else
    /// opens a new draft. Never approves or merges.
    fn ensure_draft_pr(&self, req: &PrRequest) -> Result<PrResult, CaptureError>;
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
    token: String,
    api_base: String,
    client: reqwest::blocking::Client,
}

#[cfg(feature = "net")]
impl GithubPublisher {
    /// The base branch each capture targets is carried per-request (it can differ
    /// by write mode), so it is not stored on the publisher.
    pub fn new(
        owner: impl Into<String>,
        repo: impl Into<String>,
        token: impl Into<String>,
    ) -> Self {
        Self {
            owner: owner.into(),
            repo: repo.into(),
            token: token.into(),
            api_base: "https://api.github.com".to_string(),
            client: reqwest::blocking::Client::new(),
        }
    }

    fn get(&self, path: &str) -> reqwest::blocking::RequestBuilder {
        self.req(self.client.get(format!("{}{}", self.api_base, path)))
    }

    fn post(&self, path: &str) -> reqwest::blocking::RequestBuilder {
        self.req(self.client.post(format!("{}{}", self.api_base, path)))
    }

    fn put(&self, path: &str) -> reqwest::blocking::RequestBuilder {
        self.req(self.client.put(format!("{}{}", self.api_base, path)))
    }

    fn req(&self, b: reqwest::blocking::RequestBuilder) -> reqwest::blocking::RequestBuilder {
        b.bearer_auth(&self.token)
            .header("Accept", "application/vnd.github+json")
            .header("User-Agent", "lore-capture-overlay")
    }

    /// Tip sha of an existing branch, or `None` if the branch does not exist.
    fn branch_sha(&self, branch: &str) -> Result<Option<String>, CaptureError> {
        let err = |e: reqwest::Error| CaptureError::Publish(e.to_string());
        let resp = self
            .get(&format!(
                "/repos/{}/{}/git/ref/heads/{}",
                self.owner, self.repo, branch
            ))
            .send()
            .map_err(err)?;
        if resp.status() == reqwest::StatusCode::NOT_FOUND {
            return Ok(None);
        }
        let json = resp
            .error_for_status()
            .map_err(err)?
            .json::<serde_json::Value>()
            .map_err(err)?;
        Ok(json["object"]["sha"].as_str().map(|s| s.to_string()))
    }

    /// The blob sha of `path` on `branch`, or `None` if the file is absent
    /// (needed to update an existing file in `Rolling` mode).
    fn file_sha(&self, branch: &str, path: &str) -> Result<Option<String>, CaptureError> {
        let err = |e: reqwest::Error| CaptureError::Publish(e.to_string());
        let resp = self
            .get(&format!(
                "/repos/{}/{}/contents/{}?ref={}",
                self.owner, self.repo, path, branch
            ))
            .send()
            .map_err(err)?;
        if resp.status() == reqwest::StatusCode::NOT_FOUND {
            return Ok(None);
        }
        let json = resp
            .error_for_status()
            .map_err(err)?
            .json::<serde_json::Value>()
            .map_err(err)?;
        Ok(json["sha"].as_str().map(|s| s.to_string()))
    }
}

#[cfg(feature = "net")]
impl Publisher for GithubPublisher {
    fn commit_file(&self, req: &CommitRequest) -> Result<CommitResult, CaptureError> {
        use base64::Engine as _;
        let err = |e: reqwest::Error| CaptureError::Publish(e.to_string());

        // Create the branch from the base tip if it does not already exist;
        // an existing branch (Rolling) is reused so captures accumulate.
        if self.branch_sha(&req.branch)?.is_none() {
            let base_sha = self
                .branch_sha(&req.base_branch)?
                .ok_or_else(|| CaptureError::Publish("base branch not found".into()))?;
            self.post(&format!("/repos/{}/{}/git/refs", self.owner, self.repo))
                .json(&serde_json::json!({
                    "ref": format!("refs/heads/{}", req.branch),
                    "sha": base_sha,
                }))
                .send()
                .map_err(err)?
                .error_for_status()
                .map_err(err)?;
        }

        // Write (or update) the file on the branch.
        let content_b64 = base64::engine::general_purpose::STANDARD.encode(req.content.as_bytes());
        let mut body = serde_json::json!({
            "message": req.message,
            "content": content_b64,
            "branch": req.branch,
        });
        if let Some(sha) = self.file_sha(&req.branch, &req.path)? {
            body["sha"] = serde_json::Value::String(sha);
        }
        let commit = self
            .put(&format!(
                "/repos/{}/{}/contents/{}",
                self.owner, self.repo, req.path
            ))
            .json(&body)
            .send()
            .map_err(err)?
            .error_for_status()
            .map_err(err)?
            .json::<serde_json::Value>()
            .map_err(err)?;

        Ok(CommitResult {
            branch: req.branch.clone(),
            commit_url: commit["commit"]["html_url"]
                .as_str()
                .unwrap_or_default()
                .to_string(),
        })
    }

    fn ensure_draft_pr(&self, req: &PrRequest) -> Result<PrResult, CaptureError> {
        let err = |e: reqwest::Error| CaptureError::Publish(e.to_string());

        // Reuse an already-open PR for this branch (the rolling batch PR).
        let open = self
            .get(&format!(
                "/repos/{}/{}/pulls?state=open&head={}:{}",
                self.owner, self.repo, self.owner, req.branch
            ))
            .send()
            .map_err(err)?
            .error_for_status()
            .map_err(err)?
            .json::<serde_json::Value>()
            .map_err(err)?;
        if let Some(pr) = open.as_array().and_then(|a| a.first()) {
            return Ok(PrResult {
                url: pr["html_url"].as_str().unwrap_or_default().to_string(),
                number: pr["number"].as_u64().unwrap_or_default(),
                draft: pr["draft"].as_bool().unwrap_or(false),
            });
        }

        // Otherwise open a new DRAFT pull request. Never approves or merges.
        let pr = self
            .post(&format!("/repos/{}/{}/pulls", self.owner, self.repo))
            .json(&serde_json::json!({
                "title": req.title,
                "body": req.body,
                "head": req.branch,
                "base": req.base_branch,
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
