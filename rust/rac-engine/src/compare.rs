//! Repository state comparison (`decided.services.compare`): `load_state` walks
//! one directory into a fully analysed `RepoState`; `compare_states` derives
//! every delta between two states — changed artifacts, validation delta,
//! relationship delta, statistics delta. Artifacts are matched by
//! corpus-relative path (`os.path.relpath(entry.path, directory)`), so the
//! two states may live anywhere on disk (a working tree and a materialized
//! git revision, or two fixture directories). A rename reports as removed
//! plus added.
//!
//! Numbers come from the existing analyses exactly as in the oracle:
//! validation counts from the portfolio summary (validated WITHOUT the
//! ticketing provider), per-file statuses from the directory-validation
//! path (WITH the provider) — the two are kept distinct on purpose.

use std::collections::{BTreeSet, HashMap};

use crate::commands::{STATUS_INVALID, STATUS_SKIPPED, STATUS_VALID};
use crate::diff::{diff as diff_products, Diff};
use crate::identity::artifact_identifier;
use crate::parse::Artifact;
use crate::portfolio::{portfolio_from_corpus, PortfolioSummary};
use crate::pycompat::py_relpath;
use crate::relationships::{
    corpus_items, relationships_from_corpus, rows_from_corpus_items, validation_from_rows,
    Relationship, RelationshipIssue, RelationshipSummary,
};
use crate::validate::{
    apply_overrides, has_errors, load_overrides, load_ticketing_provider, validate,
};

// Stable change kinds (part of the watchkeeper JSON contract, ADR-007).
pub const CHANGE_ADDED: &str = "added";
pub const CHANGE_MODIFIED: &str = "modified";
pub const CHANGE_REMOVED: &str = "removed";

fn change_order(kind: &str) -> u8 {
    match kind {
        CHANGE_ADDED => 0,
        CHANGE_MODIFIED => 1,
        _ => 2,
    }
}

/// One relationship-validation finding, keyed for cross-state set diffing —
/// fields mirror `RelationshipIssue` with paths made corpus-relative so the
/// same broken reference compares equal across a materialized base revision
/// and the working tree.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RelationshipIssueRef {
    pub code: String,
    pub relationship: Option<String>,
    pub target: Option<String>,
    pub path: String, // corpus-relative source ("" for repository-level findings)
    pub identifier: Option<String>,
}

type IssueKey<'a> = (&'a str, &'a str, &'a str, &'a str, &'a str);

fn issue_sort_key(r: &RelationshipIssueRef) -> IssueKey<'_> {
    (
        &r.code,
        &r.path,
        r.relationship.as_deref().unwrap_or(""),
        r.target.as_deref().unwrap_or(""),
        r.identifier.as_deref().unwrap_or(""),
    )
}

/// The per-path artifact join the comparison reads: index identity +
/// directory-validation status (`valid`/`invalid`/`skipped`).
#[derive(Debug, Clone)]
pub struct StateArtifact {
    pub id: String,
    pub type_name: String, // canonical artifact name, or "unknown"
    pub title: Option<String>,
    pub status: &'static str,
}

/// One corpus file in a state: its corpus-relative key, parsed product,
/// raw bytes (the change detector), and artifact join.
pub struct StateEntry {
    pub rel: String,
    pub artifact: Artifact,
    pub raw: Vec<u8>,
    pub info: StateArtifact,
}

/// One fully analysed repository state, keyed by corpus-relative path.
pub struct RepoState {
    pub label: String,
    pub directory: String,
    pub portfolio: PortfolioSummary,
    /// Every declared reference, resolved (source/resolved paths are the
    /// walk's display paths — relativize with [`RepoState::rel_of`]).
    pub relationships: Vec<Relationship>,
    /// Walk-ordered entries; paths are unique.
    pub entries: Vec<StateEntry>,
    /// Relationship-validation findings, corpus-relative and sorted.
    pub issues: Vec<RelationshipIssueRef>,
}

impl RepoState {
    pub fn entry(&self, rel: &str) -> Option<&StateEntry> {
        self.entries.iter().find(|e| e.rel == rel)
    }

    /// `os.path.relpath(path, state.directory)` for display paths.
    pub fn rel_of(&self, path: &str) -> String {
        py_relpath(path, &self.directory)
    }
}

fn issue_ref(issue: &RelationshipIssue, directory: &str) -> RelationshipIssueRef {
    let path = if let Some(source) = &issue.source_path {
        py_relpath(source, directory)
    } else if issue.paths.as_ref().is_some_and(|p| !p.is_empty()) {
        // Duplicate-identifier findings span files; key on the sorted set.
        let mut rels: Vec<String> = issue
            .paths
            .as_ref()
            .unwrap()
            .iter()
            .map(|p| py_relpath(p, directory))
            .collect();
        rels.sort();
        rels.join(", ")
    } else {
        String::new()
    };
    RelationshipIssueRef {
        code: issue.code.clone(),
        relationship: issue.relationship.clone(),
        target: issue.target.clone(),
        path,
        identifier: issue.identifier.clone(),
    }
}

/// `load_state(directory, label)` — walk `directory` once and analyse it as
/// one comparison side.
pub fn load_state(directory: &str, label: &str) -> RepoState {
    let items = corpus_items(directory, true);
    let rows = rows_from_corpus_items(&items);
    let portfolio = portfolio_from_corpus(directory, &items, true);
    let relationships = relationships_from_corpus(&items);
    let rel_validation = validation_from_rows(directory, &rows, true);

    let overrides = load_overrides(directory);
    let provider = load_ticketing_provider(directory);

    let mut entries: Vec<StateEntry> = Vec::with_capacity(items.len());
    for item in items {
        let rel = py_relpath(&item.path, directory);
        let type_name = item
            .spec
            .map(|s| s.name.clone())
            .unwrap_or_else(|| "unknown".to_string());
        let status = if item.spec.is_none() {
            STATUS_SKIPPED
        } else {
            let issues = apply_overrides(
                validate(&item.artifact, provider.as_deref(), Some(&type_name)),
                &type_name,
                &overrides,
            );
            if has_errors(&issues) {
                STATUS_INVALID
            } else {
                STATUS_VALID
            }
        };
        let info = StateArtifact {
            id: artifact_identifier(&item.artifact, item.spec, &item.path),
            type_name,
            title: item.artifact.product.title.clone(),
            status,
        };
        // The oracle re-reads each file (`read_text`) as the change
        // detector; byte equality == decoded-text equality for the valid
        // UTF-8 the corpus contract requires.
        let raw = std::fs::read(&item.path).unwrap_or_default();
        entries.push(StateEntry {
            rel,
            artifact: item.artifact,
            raw,
            info,
        });
    }

    let mut issues: Vec<RelationshipIssueRef> = rel_validation
        .issues
        .iter()
        .map(|issue| issue_ref(issue, directory))
        .collect();
    issues.sort_by(|a, b| issue_sort_key(a).cmp(&issue_sort_key(b)));

    RepoState {
        label: label.to_string(),
        directory: directory.to_string(),
        portfolio,
        relationships,
        entries,
        issues,
    }
}

/// One artifact that differs between the base and head states.
#[derive(Debug)]
pub struct ArtifactChange {
    pub change: &'static str, // CHANGE_ADDED | CHANGE_MODIFIED | CHANGE_REMOVED
    pub type_name: String,    // canonical artifact name, or "unknown"
    pub id: Option<String>,
    pub title: Option<String>,
    pub path: String, // corpus-relative (the matching key)
    pub base_status: Option<&'static str>,
    pub head_status: Option<&'static str>,
    pub diff: Option<Diff>, // requirement-level diff for modified artifacts
}

/// How validation outcomes moved between the states.
pub struct ValidationDelta {
    pub base_valid: usize,
    pub base_invalid: usize,
    pub head_valid: usize,
    pub head_invalid: usize,
    pub newly_invalid: Vec<String>,
    pub newly_valid: Vec<String>,
}

/// How relationship integrity moved between the states.
pub struct RelationshipDelta {
    pub base: RelationshipSummary,
    pub head: RelationshipSummary,
    pub new_issues: Vec<RelationshipIssueRef>,
    pub resolved_issues: Vec<RelationshipIssueRef>,
}

/// How repository-level artifact counts moved between the states.
pub struct StatsDelta {
    pub by_type: Vec<(String, (usize, usize))>, // type -> (base, head)
    pub total: (usize, usize),
}

/// Everything that changed between a base and a head repository state.
pub struct RepositoryComparison {
    pub base: RepoState,
    pub head: RepoState,
    pub changes: Vec<ArtifactChange>,
    pub validation: ValidationDelta,
    pub relationships: RelationshipDelta,
    pub stats: StatsDelta,
}

fn make_change(
    kind: &'static str,
    rel: &str,
    artifact: Option<&StateArtifact>,
    base_status: Option<&'static str>,
    head_status: Option<&'static str>,
    diff: Option<Diff>,
) -> ArtifactChange {
    ArtifactChange {
        change: kind,
        type_name: artifact
            .map(|a| a.type_name.clone())
            .unwrap_or_else(|| "unknown".to_string()),
        id: artifact.map(|a| a.id.clone()),
        title: artifact.and_then(|a| a.title.clone()),
        path: rel.to_string(),
        base_status,
        head_status,
        diff,
    }
}

/// One difference set the issue delta needs: items of `from` not present in
/// `other`, unique, sorted by the Python tuple key (set-difference-then-sort
/// semantics).
fn issue_difference(
    from: &[RelationshipIssueRef],
    other: &[RelationshipIssueRef],
) -> Vec<RelationshipIssueRef> {
    let mut out: Vec<RelationshipIssueRef> = Vec::new();
    for issue in from {
        if !other.contains(issue) && !out.contains(issue) {
            out.push(issue.clone());
        }
    }
    out.sort_by(|a, b| issue_sort_key(a).cmp(&issue_sort_key(b)));
    out
}

/// `compare_states(base, head)` — derive every delta between two states.
pub fn compare_states(base: RepoState, head: RepoState) -> RepositoryComparison {
    let base_paths: BTreeSet<&str> = base.entries.iter().map(|e| e.rel.as_str()).collect();
    let head_paths: BTreeSet<&str> = head.entries.iter().map(|e| e.rel.as_str()).collect();

    let mut changes: Vec<ArtifactChange> = Vec::new();
    for rel in head_paths.difference(&base_paths) {
        let entry = head.entry(rel).expect("head entry present");
        changes.push(make_change(
            CHANGE_ADDED,
            rel,
            Some(&entry.info),
            None,
            Some(entry.info.status),
            None,
        ));
    }
    for rel in base_paths.intersection(&head_paths) {
        let base_entry = base.entry(rel).expect("base entry present");
        let head_entry = head.entry(rel).expect("head entry present");
        if base_entry.raw == head_entry.raw {
            continue;
        }
        let product_diff = diff_products(&base_entry.artifact, &head_entry.artifact);
        changes.push(make_change(
            CHANGE_MODIFIED,
            rel,
            Some(&head_entry.info),
            Some(base_entry.info.status),
            Some(head_entry.info.status),
            if product_diff.is_empty() {
                None
            } else {
                Some(product_diff)
            },
        ));
    }
    for rel in base_paths.difference(&head_paths) {
        let entry = base.entry(rel).expect("base entry present");
        changes.push(make_change(
            CHANGE_REMOVED,
            rel,
            Some(&entry.info),
            Some(entry.info.status),
            None,
            None,
        ));
    }
    changes.sort_by(|a, b| {
        change_order(a.change)
            .cmp(&change_order(b.change))
            .then_with(|| a.path.cmp(&b.path))
    });

    let base_status: HashMap<&str, &'static str> = base
        .entries
        .iter()
        .map(|e| (e.rel.as_str(), e.info.status))
        .collect();
    let mut newly_invalid: Vec<String> = head
        .entries
        .iter()
        .filter(|e| {
            e.info.status == STATUS_INVALID
                && base_status
                    .get(e.rel.as_str())
                    .map(|s| *s != STATUS_INVALID)
                    .unwrap_or(true)
        })
        .map(|e| e.rel.clone())
        .collect();
    newly_invalid.sort();
    let mut newly_valid: Vec<String> = head
        .entries
        .iter()
        .filter(|e| {
            e.info.status == STATUS_VALID
                && base_status.get(e.rel.as_str()) == Some(&STATUS_INVALID)
        })
        .map(|e| e.rel.clone())
        .collect();
    newly_valid.sort();
    let validation = ValidationDelta {
        base_valid: base.portfolio.valid_artifacts,
        base_invalid: base.portfolio.invalid_artifacts,
        head_valid: head.portfolio.valid_artifacts,
        head_invalid: head.portfolio.invalid_artifacts,
        newly_invalid,
        newly_valid,
    };

    let relationships = RelationshipDelta {
        base: base.portfolio.relationships.clone(),
        head: head.portfolio.relationships.clone(),
        new_issues: issue_difference(&head.issues, &base.issues),
        resolved_issues: issue_difference(&base.issues, &head.issues),
    };

    // Head's by_type order first, then base-only types (both portfolios
    // carry the six standard slots, so this is head order in practice).
    let mut by_type: Vec<(String, (usize, usize))> = Vec::new();
    for (name, head_count) in &head.portfolio.by_type {
        let base_count = base
            .portfolio
            .by_type
            .iter()
            .find(|(n, _)| n == name)
            .map(|(_, c)| *c)
            .unwrap_or(0);
        by_type.push((name.clone(), (base_count, *head_count)));
    }
    for (name, base_count) in &base.portfolio.by_type {
        if !by_type.iter().any(|(n, _)| n == name) {
            by_type.push((name.clone(), (*base_count, 0)));
        }
    }
    let stats = StatsDelta {
        by_type,
        total: (
            base.portfolio.total_artifacts(),
            head.portfolio.total_artifacts(),
        ),
    };

    RepositoryComparison {
        base,
        head,
        changes,
        validation,
        relationships,
        stats,
    }
}
