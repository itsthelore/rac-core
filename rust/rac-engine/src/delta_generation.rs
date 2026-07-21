//! Preview-only P6 base-plus-delta document generation.
//!
//! The immutable base is shared by `Arc`; staging a change clones only the
//! current overlay.  A live document is selected as:
//!
//! `(base - tombstones) + upserts`
//!
//! P6.2 adds an independently staged identity/status projection and exact
//! resolution over the overlay. The complete derived model remains as the
//! mutation referee while later slices move postings, graph, scope, and
//! summary structures behind the same publication boundary.

use std::collections::{BTreeMap, BTreeSet};
use std::sync::Arc;

use crate::derived::DerivedIndex;
use crate::pycompat::{py_casefold, py_strip};
use crate::relationships::CorpusItem;
use crate::resolve::{
    artifact_status, identity_entry_from_item, resolved_from_entry, IndexEntry, ResolutionResult,
    OUTCOME_DUPLICATE, OUTCOME_NOT_FOUND, OUTCOME_RESOLVED,
};

/// The identity/status projection for one parsed artifact. Rows are shared by
/// `Arc` so compaction promotes unchanged identities without rebuilding them.
#[derive(Clone)]
pub struct IdentityRow {
    pub entry: IndexEntry,
    pub status: String,
}

impl IdentityRow {
    fn from_item(item: &CorpusItem) -> Self {
        Self {
            entry: identity_entry_from_item(item),
            status: artifact_status(&item.artifact),
        }
    }
}

/// Immutable base identity rows plus a cumulative changeset-bound overlay.
///
/// The compacted alias map stays shared. Point resolution consults that map,
/// masks base rows changed in the overlay, and scans only the (bounded) delta
/// aliases. Staging therefore never clones or walks the full base.
#[derive(Clone, Default)]
pub struct IdentityGeneration {
    base: Arc<BTreeMap<String, Arc<IdentityRow>>>,
    base_aliases: Arc<BTreeMap<String, Vec<String>>>,
    upserts: BTreeMap<String, Arc<IdentityRow>>,
    tombstones: BTreeSet<String>,
}

impl IdentityGeneration {
    pub fn empty() -> Self {
        Self::default()
    }

    pub fn stage(&self, changed: &BTreeSet<String>, parsed: &BTreeMap<String, CorpusItem>) -> Self {
        let mut next = self.clone();
        for path in changed {
            if let Some(item) = parsed.get(path) {
                next.upserts
                    .insert(path.clone(), Arc::new(IdentityRow::from_item(item)));
                next.tombstones.remove(path);
            } else {
                next.upserts.remove(path);
                if next.base.contains_key(path) {
                    next.tombstones.insert(path.clone());
                } else {
                    next.tombstones.remove(path);
                }
            }
        }
        next
    }

    pub fn from_items<'a>(items: impl IntoIterator<Item = (&'a str, &'a CorpusItem)>) -> Self {
        let base: BTreeMap<String, Arc<IdentityRow>> = items
            .into_iter()
            .map(|(path, item)| (path.to_string(), Arc::new(IdentityRow::from_item(item))))
            .collect();
        Self {
            base_aliases: Arc::new(alias_map(&base)),
            base: Arc::new(base),
            upserts: BTreeMap::new(),
            tombstones: BTreeSet::new(),
        }
    }

    pub fn promote(&mut self) {
        let mut base = self.base.as_ref().clone();
        for path in &self.tombstones {
            base.remove(path);
        }
        for (path, row) in &self.upserts {
            base.insert(path.clone(), Arc::clone(row));
        }
        self.base_aliases = Arc::new(alias_map(&base));
        self.base = Arc::new(base);
        self.upserts.clear();
        self.tombstones.clear();
    }

    pub fn resolve(&self, artifact_id: &str) -> ResolutionResult {
        let wanted = py_casefold(py_strip(artifact_id));
        let mut matches: Vec<&IndexEntry> = self
            .base_aliases
            .get(&wanted)
            .into_iter()
            .flatten()
            .filter(|path| !self.tombstones.contains(*path) && !self.upserts.contains_key(*path))
            .filter_map(|path| self.base.get(path).map(|row| &row.entry))
            .collect();
        matches.extend(
            self.upserts
                .values()
                .filter(|row| {
                    row.entry
                        .aliases
                        .iter()
                        .any(|alias| py_casefold(alias) == wanted)
                })
                .map(|row| &row.entry),
        );
        if matches.is_empty() {
            return ResolutionResult {
                artifact_id: artifact_id.to_string(),
                outcome: OUTCOME_NOT_FOUND,
                artifact: None,
                duplicate_paths: Vec::new(),
            };
        }
        if matches.len() > 1 {
            let mut duplicate_paths: Vec<String> =
                matches.iter().map(|entry| entry.path.clone()).collect();
            duplicate_paths.sort();
            return ResolutionResult {
                artifact_id: artifact_id.to_string(),
                outcome: OUTCOME_DUPLICATE,
                artifact: None,
                duplicate_paths,
            };
        }
        ResolutionResult {
            artifact_id: artifact_id.to_string(),
            outcome: OUTCOME_RESOLVED,
            artifact: Some(resolved_from_entry(matches[0])),
            duplicate_paths: Vec::new(),
        }
    }

    pub fn status_for_path(&self, path: &str) -> Option<&str> {
        if let Some(row) = self.upserts.get(path) {
            return Some(&row.status);
        }
        if self.tombstones.contains(path) {
            return None;
        }
        self.base.get(path).map(|row| row.status.as_str())
    }

    pub fn base_len(&self) -> usize {
        self.base.len()
    }

    pub fn upsert_len(&self) -> usize {
        self.upserts.len()
    }

    pub fn tombstone_len(&self) -> usize {
        self.tombstones.len()
    }
}

fn alias_map(rows: &BTreeMap<String, Arc<IdentityRow>>) -> BTreeMap<String, Vec<String>> {
    let mut aliases: BTreeMap<String, Vec<String>> = BTreeMap::new();
    for (path, row) in rows {
        for alias in &row.entry.aliases {
            aliases
                .entry(py_casefold(alias))
                .or_default()
                .push(path.clone());
        }
    }
    aliases
}

/// Parsed documents for an immutable base plus one cumulative overlay.
#[derive(Clone, Default)]
pub struct DeltaDocuments {
    base: Arc<BTreeMap<String, CorpusItem>>,
    upserts: BTreeMap<String, CorpusItem>,
    tombstones: BTreeSet<String>,
}

impl DeltaDocuments {
    pub fn empty() -> Self {
        Self::default()
    }

    /// Stage one detected change set without mutating the served generation.
    pub fn stage(
        &self,
        changed: &BTreeSet<String>,
        mut parsed: BTreeMap<String, CorpusItem>,
    ) -> Self {
        let mut next = self.clone();
        for path in changed {
            if let Some(item) = parsed.remove(path) {
                next.upserts.insert(path.clone(), item);
                next.tombstones.remove(path);
            } else {
                next.upserts.remove(path);
                if next.base.contains_key(path) {
                    next.tombstones.insert(path.clone());
                } else {
                    // Adding and deleting a path within one uncompacted
                    // window leaves no trace in the base-relative overlay.
                    next.tombstones.remove(path);
                }
            }
        }
        next
    }

    /// Materialize in canonical manifest order for the still-full P6.1
    /// derivation referee.
    pub fn ordered_items<'a>(
        &self,
        ordered_paths: impl IntoIterator<Item = &'a str>,
    ) -> Vec<CorpusItem> {
        ordered_paths
            .into_iter()
            .filter_map(|path| {
                self.upserts
                    .get(path)
                    .or_else(|| {
                        if self.tombstones.contains(path) {
                            None
                        } else {
                            self.base.get(path)
                        }
                    })
                    .cloned()
            })
            .collect()
    }

    /// Fold the overlay into a new immutable base after durable compaction.
    pub fn promote<'a>(&mut self, ordered_paths: impl IntoIterator<Item = &'a str>) {
        let live = ordered_paths
            .into_iter()
            .filter_map(|path| {
                self.upserts
                    .get(path)
                    .or_else(|| {
                        if self.tombstones.contains(path) {
                            None
                        } else {
                            self.base.get(path)
                        }
                    })
                    .cloned()
                    .map(|item| (path.to_string(), item))
            })
            .collect();
        self.base = Arc::new(live);
        self.upserts.clear();
        self.tombstones.clear();
    }

    pub fn base_len(&self) -> usize {
        self.base.len()
    }

    pub fn upsert_len(&self) -> usize {
        self.upserts.len()
    }

    pub fn tombstone_len(&self) -> usize {
        self.tombstones.len()
    }

    pub fn delta_len(&self) -> usize {
        self.upserts.len() + self.tombstones.len()
    }

    pub fn changed_paths(&self) -> Vec<String> {
        self.upserts
            .keys()
            .chain(self.tombstones.iter())
            .cloned()
            .collect::<BTreeSet<_>>()
            .into_iter()
            .collect()
    }
}

/// One fully-derived, immutable logical generation published atomically.
pub struct DeltaGeneration {
    pub base_generation: u64,
    pub serving_generation: u64,
    pub changed_paths: Vec<String>,
    pub identity: IdentityGeneration,
    pub derived: DerivedIndex,
}

#[cfg(test)]
mod tests {
    use super::*;

    const DOC: &str = "---\nschema_version: 1\nid: ADR-1\ntype: decision\n---\n# ADR-1: Delta\n\n## Context\n\nTest.\n\n## Decision\n\nKeep.\n\n## Consequences\n\nNone.\n\n## Status\n\nAccepted\n";

    fn item(path: &str, id: &str, status: &str) -> CorpusItem {
        let text = DOC.replace("ADR-1", id).replace("Accepted", status);
        let artifact = crate::parse::parse_text(&text, path);
        let spec = crate::spec::spec_for(&crate::classify::classify(&artifact).artifact_type);
        CorpusItem {
            path: path.to_string(),
            artifact,
            spec,
        }
    }

    #[test]
    fn overlay_stage_promote_and_changed_order_are_canonical() {
        let initial = BTreeMap::from([
            (
                "b.md".to_string(),
                item("b.md", "RAC-111111111111", "Accepted"),
            ),
            (
                "d.md".to_string(),
                item("d.md", "RAC-222222222222", "Accepted"),
            ),
        ]);
        let mut documents = DeltaDocuments::empty().stage(
            &BTreeSet::from(["b.md".to_string(), "d.md".to_string()]),
            initial,
        );
        documents.promote(["b.md", "d.md"]);

        documents = documents.stage(
            &BTreeSet::from(["a.md".to_string(), "b.md".to_string(), "d.md".to_string()]),
            BTreeMap::from([
                (
                    "a.md".to_string(),
                    item("a.md", "RAC-333333333333", "Proposed"),
                ),
                (
                    "d.md".to_string(),
                    item("d.md", "RAC-222222222222", "Accepted"),
                ),
            ]),
        );
        assert_eq!(documents.base_len(), 2);
        assert_eq!(documents.upsert_len(), 2);
        assert_eq!(documents.tombstone_len(), 1);
        assert_eq!(documents.changed_paths(), vec!["a.md", "b.md", "d.md"]);
        let live: Vec<String> = documents
            .ordered_items(["a.md", "d.md"])
            .into_iter()
            .map(|item| item.path)
            .collect();
        assert_eq!(live, vec!["a.md", "d.md"]);

        documents.promote(["a.md", "d.md"]);
        assert_eq!(documents.base_len(), 2);
        assert_eq!(documents.delta_len(), 0);
    }

    #[test]
    fn identity_overlay_resolves_masks_duplicates_and_promotes() {
        let base_items = BTreeMap::from([
            (
                "b.md".to_string(),
                item("b.md", "RAC-111111111111", "Accepted"),
            ),
            (
                "d.md".to_string(),
                item("d.md", "RAC-222222222222", "Accepted"),
            ),
        ]);
        let mut identity = IdentityGeneration::from_items(
            base_items.iter().map(|(path, item)| (path.as_str(), item)),
        );
        assert_eq!(
            identity.resolve(" rac-111111111111 ").outcome,
            OUTCOME_RESOLVED
        );
        assert_eq!(identity.status_for_path("b.md"), Some("Accepted"));

        let changed = BTreeSet::from(["a.md".to_string(), "b.md".to_string(), "d.md".to_string()]);
        let parsed = BTreeMap::from([
            (
                "a.md".to_string(),
                item("a.md", "RAC-333333333333", "Proposed"),
            ),
            (
                "d.md".to_string(),
                item("d.md", "RAC-333333333333", "Accepted"),
            ),
        ]);
        let shared_base = Arc::clone(&identity.base);
        let shared_aliases = Arc::clone(&identity.base_aliases);
        identity = identity.stage(&changed, &parsed);
        assert!(Arc::ptr_eq(&shared_base, &identity.base));
        assert!(Arc::ptr_eq(&shared_aliases, &identity.base_aliases));
        assert_eq!(
            identity.resolve("RAC-111111111111").outcome,
            OUTCOME_NOT_FOUND
        );
        let duplicate = identity.resolve("RAC-333333333333");
        assert_eq!(duplicate.outcome, OUTCOME_DUPLICATE);
        assert_eq!(duplicate.duplicate_paths, vec!["a.md", "d.md"]);
        assert_eq!(identity.status_for_path("a.md"), Some("Proposed"));
        assert_eq!(identity.status_for_path("b.md"), None);
        assert_eq!(identity.base_len(), 2);
        assert_eq!(identity.upsert_len(), 2);
        assert_eq!(identity.tombstone_len(), 1);

        identity.promote();
        assert_eq!(identity.base_len(), 2);
        assert_eq!(identity.upsert_len(), 0);
        assert_eq!(identity.tombstone_len(), 0);
        assert_eq!(
            identity.resolve("RAC-333333333333").duplicate_paths,
            vec!["a.md", "d.md"]
        );
    }
}
