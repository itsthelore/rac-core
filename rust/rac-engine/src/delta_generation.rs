//! Preview-only P6 base-plus-delta document generation.
//!
//! The immutable base is shared by `Arc`; staging a change clones only the
//! current overlay.  A live document is selected as:
//!
//! `(base - tombstones) + upserts`
//!
//! This first P6 slice deliberately still derives the complete read model
//! from the live documents.  Later slices move postings, graph, scope, and
//! summary structures into the overlay without changing this publication
//! boundary.

use std::collections::{BTreeMap, BTreeSet};
use std::sync::Arc;

use crate::derived::DerivedIndex;
use crate::relationships::CorpusItem;

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
    pub derived: DerivedIndex,
}

#[cfg(test)]
mod tests {
    use super::*;

    const DOC: &str = "# ADR-1: Delta\n\n## Context\n\nTest.\n\n## Decision\n\nKeep.\n\n## Consequences\n\nNone.\n\n## Status\n\nAccepted\n";

    fn item(path: &str) -> CorpusItem {
        let artifact = crate::parse::parse_text(DOC, path);
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
            ("b.md".to_string(), item("b.md")),
            ("d.md".to_string(), item("d.md")),
        ]);
        let mut documents = DeltaDocuments::empty().stage(
            &BTreeSet::from(["b.md".to_string(), "d.md".to_string()]),
            initial,
        );
        documents.promote(["b.md", "d.md"]);

        documents = documents.stage(
            &BTreeSet::from([
                "a.md".to_string(),
                "b.md".to_string(),
                "d.md".to_string(),
            ]),
            BTreeMap::from([
                ("a.md".to_string(), item("a.md")),
                ("d.md".to_string(), item("d.md")),
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
}
