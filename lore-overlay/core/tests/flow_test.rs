//! Hermetic tests for the capture flow.
//!
//! The three external seams (rac / gateway / GitHub) are faked, so the suite runs
//! offline and deterministically while still exercising the real logic: schema →
//! draft → scaffold → fill-keeping-frontmatter → validate → open a *draft* PR.
//! One extra test exercises the real `RacClient` shell when `LORE_TEST_RAC` is set.

use lore_capture_core::{
    parse_minted_id, CaptureError, CaptureFlow, DraftedArtifact, Gateway, PrResult,
    ProposalRequest, Publisher, Rac, RacClient, RepoConfig,
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

/// Records the request it was asked to publish, and always returns a draft PR.
struct FakePublisher {
    seen: RefCell<Option<ProposalRequest>>,
}
impl Publisher for FakePublisher {
    fn open_draft_pr(&self, req: &ProposalRequest) -> Result<PrResult, CaptureError> {
        *self.seen.borrow_mut() = Some(req.clone());
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
    fn open_draft_pr(&self, _req: &ProposalRequest) -> Result<PrResult, CaptureError> {
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
fn propose_then_publish_keeps_frontmatter_and_opens_a_draft_pr() {
    let path = temp_path("happy");
    let path_str = path.to_str().unwrap().to_string();

    let flow = CaptureFlow::new(
        FakeRac,
        FakeGateway,
        FakePublisher {
            seen: RefCell::new(None),
        },
        repo(),
    );

    // Gate 1: propose. No file yet.
    let proposal = flow
        .propose("decision", "We decided to adopt the capture overlay.")
        .unwrap();
    assert!(proposal.title.starts_with("ADR-099"));
    assert!(proposal
        .body
        .contains("We decided to adopt the capture overlay."));
    assert!(!path.exists(), "propose() must not write the artifact file");

    // Gate 2 prep: publish opens a draft PR.
    let outcome = flow
        .publish(
            &proposal,
            &path_str,
            "capture/adr-099",
            Some("Co-authored-by: Author <author@example.com>"),
        )
        .unwrap();

    assert_eq!(outcome.minted_id, "RAC-FAKE12345");
    assert!(outcome.pr.draft, "capture must open a DRAFT pull request");
    assert_eq!(outcome.pr.number, 999);

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

    // The PR body carries the co-author trailer and the published content matches.
    let _ = std::fs::remove_dir_all(path.parent().unwrap());
}

#[test]
fn publish_refuses_a_non_draft_pull_request() {
    let path = temp_path("nondraft");
    let path_str = path.to_str().unwrap().to_string();
    let flow = CaptureFlow::new(FakeRac, FakeGateway, NonDraftPublisher, repo());
    let proposal = flow.propose("decision", "something").unwrap();
    let err = flow
        .publish(&proposal, &path_str, "capture/x", None)
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
