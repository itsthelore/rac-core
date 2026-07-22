//! AST diff (`decided.services.diff`): compare two parsed products and classify
//! the changes. Pure AST work — no git, no revisions, no raw-text diffing.
//!
//! - Requirements match by ID: same ID + same text -> unchanged (omitted);
//!   same ID, different text -> modified; ID only in the new -> added; ID
//!   only in the old -> removed.
//! - Metrics and risks are ordered set-difference, de-duped, preserving
//!   source order.

use crate::markdown::Requirement;
use crate::parse::Artifact;

/// `RequirementChange` — a requirement whose text changed (same ID). Field
/// order mirrors the Python dataclass (`id, old_text, new_text`).
#[derive(Debug, Clone)]
pub struct RequirementChange {
    pub id: String,
    pub old_text: String,
    pub new_text: String,
}

/// `Diff` — the classified differences between two products.
#[derive(Debug, Clone, Default)]
pub struct Diff {
    pub added_requirements: Vec<Requirement>,
    pub removed_requirements: Vec<Requirement>,
    pub modified_requirements: Vec<RequirementChange>,
    pub added_metrics: Vec<String>,
    pub removed_metrics: Vec<String>,
    pub added_risks: Vec<String>,
    pub removed_risks: Vec<String>,
}

impl Diff {
    /// True when nothing changed across any comparison unit.
    pub fn is_empty(&self) -> bool {
        self.added_requirements.is_empty()
            && self.removed_requirements.is_empty()
            && self.modified_requirements.is_empty()
            && self.added_metrics.is_empty()
            && self.removed_metrics.is_empty()
            && self.added_risks.is_empty()
            && self.removed_risks.is_empty()
    }
}

/// `_by_id(requirements)` — Python dict comprehension semantics: on a
/// duplicate ID the LAST occurrence wins the value, but the key keeps its
/// FIRST-insertion position (dict key order).
fn by_id(requirements: &[Requirement]) -> Vec<(&str, &Requirement)> {
    let mut out: Vec<(&str, &Requirement)> = Vec::new();
    for r in requirements {
        if let Some(slot) = out.iter_mut().find(|(id, _)| *id == r.id) {
            slot.1 = r;
        } else {
            out.push((r.id.as_str(), r));
        }
    }
    out
}

/// `_ordered_difference(a, b)` — items in `a` not present in `b`, preserving
/// `a`'s order, de-duped.
fn ordered_difference(a: &[String], b: &[String]) -> Vec<String> {
    let mut seen: Vec<&str> = Vec::new();
    let mut out: Vec<String> = Vec::new();
    for item in a {
        if !b.contains(item) && !seen.contains(&item.as_str()) {
            seen.push(item.as_str());
            out.push(item.clone());
        }
    }
    out
}

/// `diff(old, new)` — the classified `Diff` between two products.
pub fn diff(old: &Artifact, new: &Artifact) -> Diff {
    let old_reqs = by_id(&old.product.requirements);
    let new_reqs = by_id(&new.product.requirements);

    let mut result = Diff::default();

    // Added / modified: iterate new (preserves new-file order).
    for (req_id, new_req) in &new_reqs {
        match old_reqs.iter().find(|(id, _)| id == req_id) {
            None => result.added_requirements.push((*new_req).clone()),
            Some((_, old_req)) if old_req.text != new_req.text => {
                result.modified_requirements.push(RequirementChange {
                    id: (*req_id).to_string(),
                    old_text: old_req.text.clone(),
                    new_text: new_req.text.clone(),
                });
            }
            Some(_) => {}
        }
    }

    // Removed: in old but not new (preserves old-file order).
    for (req_id, old_req) in &old_reqs {
        if !new_reqs.iter().any(|(id, _)| id == req_id) {
            result.removed_requirements.push((*old_req).clone());
        }
    }

    result.added_metrics =
        ordered_difference(&new.product.success_metrics, &old.product.success_metrics);
    result.removed_metrics =
        ordered_difference(&old.product.success_metrics, &new.product.success_metrics);
    result.added_risks = ordered_difference(&new.product.risks, &old.product.risks);
    result.removed_risks = ordered_difference(&old.product.risks, &new.product.risks);

    result
}
