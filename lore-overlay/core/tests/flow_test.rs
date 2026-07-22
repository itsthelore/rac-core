//! Hermetic tests for the capture flow.
//!
//! The three external seams (rac / gateway / GitHub) are faked, so the suite runs
//! offline and deterministically while still exercising the real logic: schema →
//! draft → scaffold → fill-keeping-frontmatter → validate → commit → (maybe) open
//! a *draft* PR. The write-mode tests cover per-capture, rolling batch, and direct
//! commit. One extra test exercises the real `RacClient` shell when `LORE_TEST_RAC`
//! is set.

use lore_capture_core::{
    parse_minted_id, CaptureError, CaptureFlow, CommitRequest, CommitResult, DraftedArtifact,
    Gateway, PrRequest, PrResult, Publisher, Rac, RacClient, RepoConfig, WriteMode,
};
use std::cell::RefCell;

/// Emulates `rac new` by writing a real scaffold (frontmatter + minted id), and
/// `rac validate` by a trivial structural check — enough to drive the flow.
struct FakeRac;
impl Rac for FakeRac {
    fn schema(&self, _t: &str) -> Result<String, CaptureError> {
        Ok(r#"{"required":["context","decision","consequences"]}"#.to_string())
    }
    fn new_artifact(&self, _t: &str, path: &str) -> Result<String, CaptureError> {
        let scaffold =
            "---\nschema_version: 1\nid: RAC-FAKE12345\ntype: decision\n---\n# Title\n\n## Context\n\nTODO\n";
        std::fs::write(path, scaffold)?;
        Ok("Created decision artifact: x\nID: RAC-FAKE12345\n".to_string())
    }
    fn validate(&self, path: &str) -> Result<(), CaptureError> {
        let s = std::fs::read_to_string(path)?;
        if s.starts_with("---\n") && s.contains("\n# ") {
            Ok(())
        } else {
            Err(CaptureError::Rac("invalid".into()))
        }
    }
}

struct FakeGateway;
impl Gateway for FakeGateway {
    fn draft(
        &self,
        _t: &str,
        _schema: &str,
        intent: &str,
    ) -> Result<DraftedArtifact, CaptureError> {
        Ok(DraftedArtifact {
            title: "ADR-099: Example Decision".to_string(),
            body: format!(
                "## Context\n\n{intent}\n\n## Decision\n\nWe will do the thing.\n\n## Consequences\n\nTrade-offs accepted."
            ),
        })
    }
}

/// Records every commit and PR request, and emulates a single rolling batch PR:
/// the first `ensure_draft_pr` opens PR #999, later calls for the same branch
/// return that same PR rather than opening another.
#[derive(Default)]
struct FakePublisher {
    commits: RefCell<Vec<CommitRequest>>,
    prs: RefCell<Vec<PrRequest>>,
    open_branch: RefCell<Option<String>>,
}
impl Publisher for FakePublisher {
    fn commit_file(&self, req: &CommitRequest) -> Result<CommitResult, CaptureError> {
        self.commits.borrow_mut().push(req.clone());
        Ok(CommitResult {
            branch: req.branch.clone(),
            commit_url: format!("https://example.com/commit/{}", self.commits.borrow().len()),
        })
    }
    fn ensure_draft_pr(&self, req: &PrRequest) -> Result<PrResult, CaptureError> {
        self.prs.borrow_mut().push(req.clone());
        let already_open = self.open_branch.borrow().as_deref() == Some(req.branch.as_str());
        if !already_open {
            *self.open_branch.borrow_mut() = Some(req.branch.clone());
        }
        Ok(PrResult {
            url: "https://github.com/itsthelore/rac-core/pull/999".to_string(),
            number: 999,
            draft: true,
        })
    }
}

/// A publisher that (incorrectly) reports a non-draft PR — the flow must refuse it.
struct NonDraftPublisher;
impl Publisher for NonDraftPublisher {
    fn commit_file(&self, req: &CommitRequest) -> Result<CommitResult, CaptureError> {
        Ok(CommitResult {
            branch: req.branch.clone(),
            commit_url: "x".to_string(),
        })
    }
    fn ensure_draft_pr(&self, _req: &PrRequest) -> Result<PrResult, CaptureError> {
        Ok(PrResult {
            url: "x".to_string(),
            number: 1,
            draft: false,
        })
    }
}

fn repo() -> RepoConfig {
    RepoConfig {
        owner: "itsthelore".to_string(),
        repo: "rac-core".to_string(),
        base_branch: "main".to_string(),
    }
}

fn temp_path(name: &str) -> std::path::PathBuf {
    let dir =
        std::env::temp_dir().join(format!("lore-overlay-test-{}-{}", std::process::id(), name));
    std::fs::create_dir_all(&dir).unwrap();
    dir.join("artifact.md")
}

#[test]
fn per_capture_keeps_frontmatter_and_opens_a_draft_pr() {
    let path = temp_path("happy");
    let path_str = path.to_str().unwrap().to_string();

    let flow = CaptureFlow::new(FakeRac, FakeGateway, FakePublisher::default(), repo());

    // Gate 1: propose. No file yet.
    let proposal = flow
        .propose("decision", "We decided to adopt the capture overlay.")
        .unwrap();
    assert!(proposal.title.starts_with("ADR-099"));
    assert!(proposal
        .body
        .contains("We decided to adopt the capture overlay."));
    assert!(!path.exists(), "propose() must not write the artifact file");

    // Gate 2 prep: publish commits and opens a draft PR.
    let outcome = flow
        .publish(
            &proposal,
            &path_str,
            "capture/adr-099",
            WriteMode::PerCapture,
            Some("Co-authored-by: Author <author@example.com>"),
        )
        .unwrap();

    assert_eq!(outcome.minted_id, "RAC-FAKE12345");
    assert_eq!(outcome.branch, "capture/adr-099");
    assert_eq!(outcome.mode, WriteMode::PerCapture);
    let pr = outcome.pr.expect("per-capture opens a PR");
    assert!(pr.draft, "capture must open a DRAFT pull request");
    assert_eq!(pr.number, 999);

    // The written file keeps the minted frontmatter and uses the drafted body.
    let written = std::fs::read_to_string(&path).unwrap();
    assert!(
        written.starts_with("---\nschema_version: 1\nid: RAC-FAKE12345\ntype: decision\n---\n"),
        "frontmatter (and the minted id) must be preserved, got:\n{written}"
    );
    assert!(written.contains("# ADR-099: Example Decision"));
    assert!(written.contains("## Decision"));
    assert!(
        !written.contains("# Title"),
        "the scaffold's placeholder title must be replaced"
    );

    let _ = std::fs::remove_dir_all(path.parent().unwrap());
}

#[test]
fn rolling_appends_to_one_branch_and_reuses_a_single_batch_pr() {
    let path_a = temp_path("rolling-a");
    let path_b = temp_path("rolling-b");
    let publisher = FakePublisher::default();
    let flow = CaptureFlow::new(FakeRac, FakeGateway, publisher, repo());

    let p1 = flow.propose("decision", "first decision").unwrap();
    let out1 = flow
        .publish(
            &p1,
            path_a.to_str().unwrap(),
            "capture/inbox",
            WriteMode::Rolling,
            None,
        )
        .unwrap();
    let p2 = flow.propose("decision", "second decision").unwrap();
    let out2 = flow
        .publish(
            &p2,
            path_b.to_str().unwrap(),
            "capture/inbox",
            WriteMode::Rolling,
            None,
        )
        .unwrap();

    // Both captures land on the one shared branch and share the one batch PR.
    assert_eq!(out1.branch, "capture/inbox");
    assert_eq!(out2.branch, "capture/inbox");
    assert_eq!(out1.pr.as_ref().unwrap().number, 999);
    assert_eq!(out2.pr.as_ref().unwrap().number, 999);

    // Two commits, both to capture/inbox; the PR was opened once and then reused.
    let pubref = flow.publisher();
    assert_eq!(pubref.commits.borrow().len(), 2);
    assert!(pubref
        .commits
        .borrow()
        .iter()
        .all(|c| c.branch == "capture/inbox"));
    assert_eq!(
        pubref.prs.borrow().len(),
        2,
        "ensure_draft_pr called per capture"
    );
    assert!(pubref
        .prs
        .borrow()
        .iter()
        .all(|p| p.title.contains("batch")));

    let _ = std::fs::remove_dir_all(path_a.parent().unwrap());
    let _ = std::fs::remove_dir_all(path_b.parent().unwrap());
}

#[test]
fn direct_commits_without_opening_a_pull_request() {
    let path = temp_path("direct");
    let flow = CaptureFlow::new(FakeRac, FakeGateway, FakePublisher::default(), repo());
    let p = flow.propose("decision", "solo repo decision").unwrap();
    let outcome = flow
        .publish(
            &p,
            path.to_str().unwrap(),
            "capture/inbox",
            WriteMode::Direct,
            None,
        )
        .unwrap();

    assert_eq!(outcome.mode, WriteMode::Direct);
    assert!(outcome.pr.is_none(), "direct mode must not open a PR");
    let pubref = flow.publisher();
    assert_eq!(pubref.commits.borrow().len(), 1, "direct still commits");
    assert!(
        pubref.prs.borrow().is_empty(),
        "direct must not call ensure_draft_pr"
    );

    let _ = std::fs::remove_dir_all(path.parent().unwrap());
}

#[test]
fn publish_refuses_a_non_draft_pull_request() {
    let path = temp_path("nondraft");
    let path_str = path.to_str().unwrap().to_string();
    let flow = CaptureFlow::new(FakeRac, FakeGateway, NonDraftPublisher, repo());
    let proposal = flow.propose("decision", "something").unwrap();
    let err = flow
        .publish(
            &proposal,
            &path_str,
            "capture/x",
            WriteMode::PerCapture,
            None,
        )
        .unwrap_err();
    match err {
        CaptureError::Publish(m) => assert!(m.contains("DRAFT")),
        other => panic!("expected a Publish error, got {other:?}"),
    }
    let _ = std::fs::remove_dir_all(path.parent().unwrap());
}

#[test]
fn parses_minted_id_from_rac_new_output() {
    assert_eq!(
        parse_minted_id("Created decision artifact: x\nID: RAC-ABC123\nEdit the TODOs"),
        Some("RAC-ABC123".to_string())
    );
    assert_eq!(
        parse_minted_id("scaffolded RAC-XYZ789."),
        Some("RAC-XYZ789".to_string())
    );
    assert_eq!(parse_minted_id("no id here"), None);
}

/// Exercises the real `RacClient` shell against an actual `rac` when configured.
/// `LORE_TEST_RAC` is a whitespace-separated command, e.g.
/// `env PYTHONPATH=/abs/src python /abs/racrun.py`. Skipped (passes) when unset,
/// so the suite stays hermetic by default.
#[test]
fn real_rac_client_reads_schema_when_configured() {
    let Ok(cmd) = std::env::var("LORE_TEST_RAC") else {
        eprintln!("skipping: set LORE_TEST_RAC to exercise the real rac shell");
        return;
    };
    let mut parts = cmd.split_whitespace();
    let program = parts.next().expect("LORE_TEST_RAC is empty").to_string();
    let base_args: Vec<String> = parts.map(|s| s.to_string()).collect();
    let rac = RacClient::new(program).with_base_args(base_args);
    let schema = Rac::schema(&rac, "decision").expect("rac schema decision --json");
    assert!(
        schema.contains("decision") || schema.contains("required"),
        "unexpected schema output: {schema}"
    );
}
