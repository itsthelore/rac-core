//! Preview-only P6 base-plus-delta document generation.
//!
//! The immutable base is shared by `Arc`; staging a change clones only the
//! current overlay.  A live document is selected as:
//!
//! `(base - tombstones) + upserts`
//!
//! P6.2 adds an independently staged identity/status projection and exact
//! resolution over the overlay. P6.3 adds token rows, postings, filters, and
//! exact global search statistics. The complete derived model remains as the
//! mutation and graph-signal referee while later slices move graph, scope, and
//! summary structures behind the same publication boundary.

use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::sync::Arc;

use crate::derived::DerivedIndex;
use crate::pycompat::{py_casefold, py_strip};
use crate::relationships::CorpusItem;
use crate::resolve::{
    artifact_status, entry_from_item, entry_has_tags, field_tokens_of, identity_entry_from_item,
    is_retired_status, match_entry_with_fields, rank_and_build, resolved_from_entry, tokenize,
    CorpusStats, FieldTokens, IndexEntry, ResolutionResult, SearchResult, OUTCOME_DUPLICATE,
    OUTCOME_NOT_FOUND, OUTCOME_RESOLVED,
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

/// Searchable row owned by the P6.3 generation. Graph-derived inbound counts
/// remain supplied by the complete referee until the later graph slice.
#[derive(Clone)]
pub struct SearchRow {
    pub entry: IndexEntry,
    pub fields: FieldTokens,
    pub status: String,
}

impl SearchRow {
    fn from_item(item: &CorpusItem) -> Self {
        let entry = entry_from_item(item, 0);
        Self {
            fields: field_tokens_of(&entry),
            status: artifact_status(&item.artifact),
            entry,
        }
    }
}

/// Immutable compacted token/posting base plus a cumulative search overlay.
#[derive(Clone, Default)]
pub struct SearchGeneration {
    base: Arc<BTreeMap<String, Arc<SearchRow>>>,
    base_postings: Arc<BTreeMap<String, Vec<String>>>,
    base_length_sums: [i64; 6],
    upserts: BTreeMap<String, Arc<SearchRow>>,
    tombstones: BTreeSet<String>,
}

impl SearchGeneration {
    pub fn empty() -> Self {
        Self::default()
    }

    pub fn from_items<'a>(items: impl IntoIterator<Item = (&'a str, &'a CorpusItem)>) -> Self {
        let base: BTreeMap<String, Arc<SearchRow>> = items
            .into_iter()
            .map(|(path, item)| (path.to_string(), Arc::new(SearchRow::from_item(item))))
            .collect();
        Self {
            base_postings: Arc::new(postings_for(&base)),
            base_length_sums: length_sums(base.values().map(AsRef::as_ref)),
            base: Arc::new(base),
            upserts: BTreeMap::new(),
            tombstones: BTreeSet::new(),
        }
    }

    pub fn stage(
        &self,
        changed: &BTreeSet<String>,
        parsed: &BTreeMap<String, CorpusItem>,
    ) -> Self {
        let mut next = self.clone();
        for path in changed {
            if let Some(item) = parsed.get(path) {
                next
                    .upserts
                    .insert(path.clone(), Arc::new(SearchRow::from_item(item)));
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

    pub fn promote(&mut self) {
        let mut base = self.base.as_ref().clone();
        for path in &self.tombstones {
            base.remove(path);
        }
        for (path, row) in &self.upserts {
            base.insert(path.clone(), Arc::clone(row));
        }
        self.base_postings = Arc::new(postings_for(&base));
        self.base_length_sums = length_sums(base.values().map(AsRef::as_ref));
        self.base = Arc::new(base);
        self.upserts.clear();
        self.tombstones.clear();
    }

    pub fn search(
        &self,
        query: &str,
        artifact_type: Option<&str>,
        tags: &[String],
        live_only: bool,
        referee_entries: &[IndexEntry],
    ) -> SearchResult {
        let terms = tokenize(query);
        if terms.is_empty() {
            return empty_search(query, artifact_type);
        }
        let distinct: BTreeSet<&str> = terms.iter().map(String::as_str).collect();
        let mut candidates: Option<BTreeSet<String>> = None;
        for term in distinct {
            let paths = self.paths_for_term(term);
            candidates = Some(match candidates {
                Some(current) => current.intersection(&paths).cloned().collect(),
                None => paths,
            });
            if candidates.as_ref().is_some_and(BTreeSet::is_empty) {
                return empty_search(query, artifact_type);
            }
        }

        let tag_filter: Vec<String> = tags.iter().map(|tag| py_casefold(tag)).collect();
        let inbound_by_path: HashMap<&str, i64> = referee_entries
            .iter()
            .map(|entry| (entry.path.as_str(), entry.inbound_count))
            .collect();
        let mut prepared = Vec::new();
        for path in candidates.unwrap_or_default() {
            let Some(row) = self.row(&path) else {
                continue;
            };
            if artifact_type.is_some_and(|wanted| row.entry.artifact_type != wanted) {
                continue;
            }
            if !tag_filter.is_empty() && !entry_has_tags(&row.entry, &tag_filter) {
                continue;
            }
            if live_only && is_retired_status(&row.entry.artifact_type, &row.status) {
                continue;
            }
            let Some(tier) = match_entry_with_fields(&row.entry, &row.fields, &terms) else {
                continue;
            };
            let Some(inbound_count) = inbound_by_path.get(row.entry.path.as_str()) else {
                return empty_search(query, artifact_type);
            };
            let mut entry = row.entry.clone();
            entry.inbound_count = *inbound_count;
            prepared.push((entry, &row.fields, tier));
        }
        if prepared.is_empty() {
            return empty_search(query, artifact_type);
        }
        let stats = self.stats(&terms);
        let matched = prepared
            .iter()
            .map(|(entry, fields, tier)| (entry, *fields, tier.clone()))
            .collect();
        rank_and_build(query, artifact_type, matched, &terms, &stats)
    }

    fn row(&self, path: &str) -> Option<&SearchRow> {
        self.upserts.get(path).map(AsRef::as_ref).or_else(|| {
            (!self.tombstones.contains(path))
                .then(|| self.base.get(path).map(AsRef::as_ref))
                .flatten()
        })
    }

    fn paths_for_term(&self, term: &str) -> BTreeSet<String> {
        let mut paths = BTreeSet::new();
        for (token, posting) in self.base_postings.range(term.to_string()..) {
            if !token.starts_with(term) {
                break;
            }
            paths.extend(posting.iter().filter(|path| {
                !self.tombstones.contains(*path) && !self.upserts.contains_key(*path)
            }).cloned());
        }
        for (path, row) in &self.upserts {
            if row_has_term(row, term) {
                paths.insert(path.clone());
            }
        }
        paths
    }

    fn stats(&self, terms: &[String]) -> CorpusStats {
        let mut df = HashMap::new();
        for term in terms {
            let count = self.paths_for_term(term).len() as i64;
            *df.entry(term.clone()).or_insert(0) += count;
        }
        let mut sums = self.base_length_sums;
        for path in self.tombstones.iter().chain(self.upserts.keys()) {
            if let Some(row) = self.base.get(path) {
                subtract_lengths(&mut sums, &row.fields);
            }
        }
        for row in self.upserts.values() {
            add_lengths(&mut sums, &row.fields);
        }
        let replaced = self
            .upserts
            .keys()
            .filter(|path| self.base.contains_key(*path))
            .count();
        let n = self.base.len() - self.tombstones.len() - replaced + self.upserts.len();
        let mut avglen = [0.0; 6];
        if n != 0 {
            for (average, sum) in avglen.iter_mut().zip(sums) {
                *average = sum as f64 / n as f64;
            }
        }
        CorpusStats {
            n: n as i64,
            df,
            avglen,
        }
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

fn empty_search(query: &str, artifact_type: Option<&str>) -> SearchResult {
    SearchResult {
        query: query.to_string(),
        artifact_type: artifact_type.map(str::to_string),
        matches: Vec::new(),
    }
}

fn field_lengths(fields: &FieldTokens) -> [i64; 6] {
    [
        fields.id.len() as i64,
        fields.title.len() as i64,
        fields.path.len() as i64,
        fields.heading.len() as i64,
        fields.body.len() as i64,
        fields.tags.len() as i64,
    ]
}

fn add_lengths(sums: &mut [i64; 6], fields: &FieldTokens) {
    for (sum, length) in sums.iter_mut().zip(field_lengths(fields)) {
        *sum += length;
    }
}

fn subtract_lengths(sums: &mut [i64; 6], fields: &FieldTokens) {
    for (sum, length) in sums.iter_mut().zip(field_lengths(fields)) {
        *sum -= length;
    }
}

fn length_sums<'a>(rows: impl IntoIterator<Item = &'a SearchRow>) -> [i64; 6] {
    let mut sums = [0; 6];
    for row in rows {
        add_lengths(&mut sums, &row.fields);
    }
    sums
}

fn row_has_term(row: &SearchRow, term: &str) -> bool {
    all_tokens(&row.fields).any(|token| token.starts_with(term))
}

fn all_tokens(fields: &FieldTokens) -> impl Iterator<Item = &str> {
    fields
        .id
        .iter()
        .chain(&fields.title)
        .chain(&fields.path)
        .chain(&fields.heading)
        .chain(&fields.body)
        .chain(&fields.tags)
        .map(String::as_str)
}

fn postings_for(rows: &BTreeMap<String, Arc<SearchRow>>) -> BTreeMap<String, Vec<String>> {
    let mut postings: BTreeMap<String, BTreeSet<String>> = BTreeMap::new();
    for (path, row) in rows {
        for token in all_tokens(&row.fields) {
            postings
                .entry(token.to_string())
                .or_default()
                .insert(path.clone());
        }
    }
    postings
        .into_iter()
        .map(|(token, paths)| (token, paths.into_iter().collect()))
        .collect()
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
    pub search: SearchGeneration,
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

    fn tagged_item(path: &str, id: &str, status: &str, tag: &str) -> CorpusItem {
        let text = DOC
            .replace("ADR-1", id)
            .replace("Accepted", status)
            .replacen(
                "type: decision\n---",
                &format!("type: decision\ntags: [{tag}]\n---"),
                1,
            );
        let artifact = crate::parse::parse_text(&text, path);
        let spec = crate::spec::spec_for(&crate::classify::classify(&artifact).artifact_type);
        CorpusItem {
            path: path.to_string(),
            artifact,
            spec,
        }
    }

    fn assert_search_matches_fresh(
        search: &SearchGeneration,
        items: &BTreeMap<String, CorpusItem>,
        query: &str,
        artifact_type: Option<&str>,
        tags: &[String],
        live_only: bool,
    ) {
        let ordered: Vec<CorpusItem> = items.values().cloned().collect();
        let referee = crate::resolve::index_from_items(&ordered);
        let expected = crate::resolve::search_index_filtered(
            &referee,
            query,
            artifact_type,
            tags,
            live_only,
        );
        let actual = search.search(query, artifact_type, tags, live_only, &referee);
        assert_eq!(
            crate::output::search_result_value(&actual, true),
            crate::output::search_result_value(&expected, true),
            "query={query} type={artifact_type:?} tags={tags:?} live={live_only}"
        );
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

    #[test]
    fn search_overlay_matches_fresh_stats_filters_and_ranking() {
        let mut items = BTreeMap::from([
            (
                "a.md".to_string(),
                tagged_item("a.md", "RAC-111111111111", "Accepted", "alpha"),
            ),
            (
                "b.md".to_string(),
                tagged_item("b.md", "RAC-222222222222", "Superseded", "beta"),
            ),
        ]);
        let mut search = SearchGeneration::from_items(
            items.iter().map(|(path, item)| (path.as_str(), item)),
        );
        for (query, artifact_type, tags, live_only) in [
            ("delta", None, vec![], false),
            ("rac 111111111111", Some("decision"), vec![], false),
            ("delta delta", None, vec![], false),
            ("delta", None, vec!["alpha".to_string()], false),
            ("zzzz-no-match", None, vec![], false),
        ] {
            assert_search_matches_fresh(
                &search,
                &items,
                query,
                artifact_type,
                &tags,
                live_only,
            );
        }

        let shared_base = Arc::clone(&search.base);
        let shared_postings = Arc::clone(&search.base_postings);
        let changed = BTreeSet::from([
            "a.md".to_string(),
            "b.md".to_string(),
            "c.md".to_string(),
        ]);
        let parsed = BTreeMap::from([
            (
                "b.md".to_string(),
                tagged_item("b.md", "RAC-333333333333", "Accepted", "alpha"),
            ),
            (
                "c.md".to_string(),
                tagged_item("c.md", "RAC-444444444444", "Accepted", "gamma"),
            ),
        ]);
        search = search.stage(&changed, &parsed);
        assert!(Arc::ptr_eq(&shared_base, &search.base));
        assert!(Arc::ptr_eq(&shared_postings, &search.base_postings));
        items.remove("a.md");
        items.extend(parsed);
        for query in ["delta", "rac 333333333333", "delta delta"] {
            assert_search_matches_fresh(&search, &items, query, None, &[], false);
        }
        assert_search_matches_fresh(
            &search,
            &items,
            "delta",
            None,
            &["alpha".to_string()],
            true,
        );
        assert_eq!(search.base_len(), 2);
        assert_eq!(search.upsert_len(), 2);
        assert_eq!(search.tombstone_len(), 1);

        search.promote();
        assert_eq!(search.base_len(), 2);
        assert_eq!(search.upsert_len(), 0);
        assert_eq!(search.tombstone_len(), 0);
        assert_search_matches_fresh(&search, &items, "delta", None, &[], false);
    }
}
