//! Traceability coverage report (`rac.services.coverage`) — typed
//! completeness gaps derived from the resolved relationship graph.
//! Advisory, never a build failure: `rac coverage` always exits 0 on a
//! real directory. Three gap classes, one type and one expected edge
//! direction each:
//!
//! - **unscheduled** — a requirement with no resolved INCOMING edge from a
//!   roadmap,
//! - **unapplied** — a decision with no resolved incoming edge from a
//!   requirement or roadmap,
//! - **unscoped** — a roadmap with no resolved OUTGOING edge to a
//!   requirement.
//!
//! Self-edges (`resolved_path == source_path`) are skipped; external and
//! unresolved references contribute nothing (`resolved_path` is None).
//! Order is deterministic: gap class (unscheduled, unapplied, unscoped),
//! then ascending path.

use std::collections::{HashMap, HashSet};

use crate::identity::artifact_identifier;
use crate::relationships::{corpus_items, relationships_from_corpus};

pub const GAP_UNSCHEDULED: &str = "unscheduled";
pub const GAP_UNAPPLIED: &str = "unapplied";
pub const GAP_UNSCOPED: &str = "unscoped";

/// The per-class missing-coverage description (`_MISSING`).
fn missing_text(gap: &str) -> &'static str {
    match gap {
        GAP_UNSCHEDULED => "no roadmap schedules this requirement",
        GAP_UNAPPLIED => "no requirement or roadmap applies this decision",
        _ => "this roadmap references no requirement",
    }
}

/// One typed traceability gap (`CoverageGap`).
#[derive(Debug)]
pub struct CoverageGap {
    pub path: String,
    pub id: String,
    pub artifact_type: String,
    pub gap: &'static str,
    pub missing: &'static str,
}

/// The coverage report for a directory (`CoverageReport`).
#[derive(Debug)]
pub struct CoverageReport {
    pub directory: String,
    pub gaps: Vec<CoverageGap>,
}

impl CoverageReport {
    /// `counts` — `(unscheduled, unapplied, unscoped)`.
    pub fn counts(&self) -> (usize, usize, usize) {
        let mut out = (0usize, 0usize, 0usize);
        for gap in &self.gaps {
            match gap.gap {
                GAP_UNSCHEDULED => out.0 += 1,
                GAP_UNAPPLIED => out.1 += 1,
                _ => out.2 += 1,
            }
        }
        out
    }
}

fn class_order(gap: &str) -> usize {
    match gap {
        GAP_UNSCHEDULED => 0,
        GAP_UNAPPLIED => 1,
        _ => 2,
    }
}

/// `analyze_coverage(directory)` — always recursive, no writes, no git.
pub fn analyze_coverage(directory: &str) -> CoverageReport {
    let items = corpus_items(directory, true);
    // The identity index rows coverage reads: (path, id, type) per artifact,
    // unknown documents included with type "unknown" (they never gap).
    let index: Vec<(String, String, String)> = items
        .iter()
        .map(|item| {
            let artifact_type = item
                .spec
                .map(|s| s.name.clone())
                .unwrap_or_else(|| "unknown".to_string());
            let id = artifact_identifier(&item.artifact, item.spec, &item.path);
            (item.path.clone(), id, artifact_type)
        })
        .collect();
    let type_by_path: HashMap<&str, &str> = index
        .iter()
        .map(|(path, _, artifact_type)| (path.as_str(), artifact_type.as_str()))
        .collect();
    let relationships = relationships_from_corpus(&items);

    // Resolved incoming source types and resolved outgoing target types.
    let mut incoming_types: HashMap<&str, HashSet<&str>> = index
        .iter()
        .map(|(path, _, _)| (path.as_str(), HashSet::new()))
        .collect();
    let mut outgoing_types: HashMap<&str, HashSet<&str>> = index
        .iter()
        .map(|(path, _, _)| (path.as_str(), HashSet::new()))
        .collect();
    for rel in &relationships {
        let Some(resolved) = rel.resolved_path.as_deref() else {
            continue;
        };
        if resolved == rel.source_path {
            continue;
        }
        let source_type = type_by_path.get(rel.source_path.as_str()).copied();
        let target_type = type_by_path.get(resolved).copied();
        if let (Some(types), Some(source_type)) = (incoming_types.get_mut(resolved), source_type) {
            types.insert(source_type);
        }
        if let (Some(types), Some(target_type)) =
            (outgoing_types.get_mut(rel.source_path.as_str()), target_type)
        {
            types.insert(target_type);
        }
    }

    let mut gaps: Vec<CoverageGap> = Vec::new();
    for (path, id, artifact_type) in &index {
        let incoming = &incoming_types[path.as_str()];
        let gap = match artifact_type.as_str() {
            "requirement" if !incoming.contains("roadmap") => GAP_UNSCHEDULED,
            "decision" if !incoming.contains("requirement") && !incoming.contains("roadmap") => {
                GAP_UNAPPLIED
            }
            "roadmap" if !outgoing_types[path.as_str()].contains("requirement") => GAP_UNSCOPED,
            _ => continue,
        };
        gaps.push(CoverageGap {
            path: path.clone(),
            id: id.clone(),
            artifact_type: artifact_type.clone(),
            gap,
            missing: missing_text(gap),
        });
    }

    // Deterministic order: gap class, then ascending path (REQ-003).
    gaps.sort_by(|a, b| {
        class_order(a.gap)
            .cmp(&class_order(b.gap))
            .then_with(|| a.path.cmp(&b.path))
    });
    CoverageReport {
        directory: directory.to_string(),
        gaps,
    }
}
