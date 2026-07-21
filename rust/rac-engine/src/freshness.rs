//! Server-lifetime serving freshness (ADR-105) — port of
//! `services/freshness.py` `FreshnessTracker` for the long-lived MCP server
//! (INDEX-PLAN B6).
//!
//! Detection uses an event-driven clean accelerator where the platform can
//! provide a synchronous barrier, otherwise the stat-manifest scan. Events
//! never compute the changed set: any dirty or uncertain signal falls back to
//! the authoritative scan. Whatever the rung, the served read-model is
//! re-derived from the tracker's incrementally maintained parsed snapshot,
//! byte-identical to a fresh whole-corpus walk at the current corpus state.

use std::collections::{BTreeMap, BTreeSet, HashMap, HashSet};
use std::path::PathBuf;

use crate::delta_generation::{
    DeltaDocuments, DeltaGeneration, GraphGeneration, IdentityGeneration, SearchGeneration,
};
use crate::derived::{build_derived_index_from_items, DerivedIndex, SCHEMA_VERSION};
use crate::derived_cache::{corpus_hash_from_complete_manifest, stat_scan};
use crate::freshness_watch::EventWatch;
use crate::index_store::{open_store, write_store, FileState, MmapIndexReader};
use crate::relationships::CorpusItem;

/// What the tracker currently serves: the memory-mapped base (delta-empty),
/// or the re-derived snapshot bundle (the delta window).
pub enum TrackerModel {
    View(MmapIndexReader),
    Snapshot(DerivedIndex),
    /// P6 preview generation. The document overlay is immutable for the
    /// lifetime of this served model and is published only after its complete
    /// derived referee has been built.
    Delta(Box<DeltaGeneration>),
}

pub struct FreshnessTracker {
    cache_dir: PathBuf,
    root_str: String,
    threshold: Option<usize>,
    watcher: EventWatch,

    manifest: Vec<(String, FileState)>,
    items: HashMap<String, CorpusItem>, // rel -> parsed snapshot entry
    model: Option<TrackerModel>,
    hash: Option<String>,
    base_hash: Option<String>,
    base_generation: u64,
    /// Logical served-corpus generation. Unlike `base_generation`, this also
    /// advances for mutation-window snapshots that have not compacted.
    serving_generation: u64,
    delta_paths: HashSet<String>,
    /// Present only for the opt-in P6 preview. Default serving retains the
    /// established snapshot lifecycle until the later delta slices pass the
    /// referee and scale gates.
    delta_documents: Option<DeltaDocuments>,
    delta_identity: Option<IdentityGeneration>,
    delta_search: Option<SearchGeneration>,
    delta_graph: Option<GraphGeneration>,
    /// ADR-107 RSS finalization: after compaction the resident parsed
    /// snapshot is shed and the mapped base is the whole answer; the next
    /// change repopulates by a full re-parse on demand.
    snapshot_shed: bool,
    last_parse_workers: usize,
    last_parse_files: usize,
    last_detect_scanned: bool,
}

impl FreshnessTracker {
    pub fn new(cache_dir: PathBuf, root: &str, threshold: Option<usize>) -> Self {
        Self::new_with_watcher(cache_dir, root, threshold, true)
    }

    /// Force the authoritative stat rung. Used by fallback/parity tests and
    /// remains the behavior on platforms without a synchronous watcher.
    pub fn new_stat(cache_dir: PathBuf, root: &str, threshold: Option<usize>) -> Self {
        Self::new_with_watcher(cache_dir, root, threshold, false)
    }

    fn new_with_watcher(
        cache_dir: PathBuf,
        root: &str,
        threshold: Option<usize>,
        watcher_enabled: bool,
    ) -> Self {
        Self {
            cache_dir,
            root_str: root.to_string(),
            threshold,
            watcher: EventWatch::new(root, watcher_enabled),
            manifest: Vec::new(),
            items: HashMap::new(),
            model: None,
            hash: None,
            base_hash: None,
            base_generation: 0,
            serving_generation: 0,
            delta_paths: HashSet::new(),
            delta_documents: None,
            delta_identity: None,
            delta_search: None,
            delta_graph: None,
            snapshot_shed: false,
            last_parse_workers: 1,
            last_parse_files: 0,
            last_detect_scanned: false,
        }
    }

    /// Opt in to the P6 generation preview. This is intentionally a
    /// separate constructor so normal MCP serving cannot adopt the preview by
    /// accident.
    pub fn new_delta_preview(
        cache_dir: PathBuf,
        root: &str,
        threshold: Option<usize>,
    ) -> Self {
        let mut tracker = Self::new_with_watcher(cache_dir, root, threshold, true);
        tracker.delta_documents = Some(DeltaDocuments::empty());
        tracker.delta_identity = Some(IdentityGeneration::empty());
        tracker.delta_search = Some(SearchGeneration::empty());
        tracker.delta_graph = Some(GraphGeneration::empty());
        tracker
    }

    // --- observable state (scorecards and pinning tests) ------------------

    pub fn mode(&self) -> &'static str {
        self.watcher.mode()
    }

    pub fn base_generation(&self) -> u64 {
        self.base_generation
    }

    pub fn serving_generation(&self) -> u64 {
        self.serving_generation
    }

    pub fn delta_size(&self) -> usize {
        self.delta_documents
            .as_ref()
            .map_or_else(|| self.delta_paths.len(), DeltaDocuments::delta_len)
    }

    pub fn delta_preview_enabled(&self) -> bool {
        self.delta_documents.is_some()
    }

    pub fn delta_base_documents(&self) -> usize {
        self.delta_documents
            .as_ref()
            .map_or(0, DeltaDocuments::base_len)
    }

    pub fn delta_upserts(&self) -> usize {
        self.delta_documents
            .as_ref()
            .map_or(0, DeltaDocuments::upsert_len)
    }

    pub fn delta_tombstones(&self) -> usize {
        self.delta_documents
            .as_ref()
            .map_or(0, DeltaDocuments::tombstone_len)
    }

    pub fn last_parse_files(&self) -> usize {
        self.last_parse_files
    }

    pub fn corpus_hash(&self) -> Option<&str> {
        self.hash.as_deref()
    }

    pub fn last_detect_scanned(&self) -> bool {
        self.last_detect_scanned
    }

    // --- the serving surface ----------------------------------------------

    /// The current read-model, freshened through the detection ladder. An
    /// unchanged corpus returns the cached model with no re-derive.
    pub fn read_model(&mut self, verify: bool) -> &TrackerModel {
        let cold = self.model.is_none();
        let detect_started = crate::timing::start();
        let (changed, scanned) = self.detect(verify);
        self.last_detect_scanned = scanned;
        crate::timing::emit_since(
            "tracker.detect",
            detect_started,
            &[
                ("files", self.manifest.len() as u64),
                ("changed", changed.len() as u64),
                ("scanned", u64::from(scanned)),
            ],
        );
        if changed.is_empty() && !cold {
            return self.model.as_ref().expect("warm model");
        }
        if !cold {
            let recompute_started = crate::timing::start();
            if self.delta_documents.is_some() {
                self.rebuild_delta_preview(&changed);
            } else {
                self.apply(&changed);
                self.rebuild_model();
            }
            self.maybe_compact();
            crate::timing::emit_since(
                "tracker.recompute",
                recompute_started,
                &[("changed", changed.len() as u64), ("cold", 0)],
            );
            return self.model.as_ref().expect("rebuilt model");
        }
        // Cold start: the whole corpus parsed from nothing; the three cold
        // phases feed the RAC_TIMING scorecard (ADR-107).
        let parse_start = std::time::Instant::now();
        if self.delta_documents.is_some() {
            self.rebuild_delta_preview(&changed);
        } else {
            self.apply(&changed);
        }
        let derive_start = std::time::Instant::now();
        if self.delta_documents.is_none() {
            self.rebuild_model();
        }
        let write_start = std::time::Instant::now();
        self.maybe_compact();
        let end = std::time::Instant::now();
        crate::timing::emit_since(
            "tracker.recompute",
            Some(parse_start),
            &[("changed", changed.len() as u64), ("cold", 1)],
        );
        crate::parallel_build::emit_build_timing(&crate::parallel_build::BuildStats {
            files: self.manifest.len(),
            workers: self.last_parse_workers,
            parse_ms: (derive_start - parse_start).as_secs_f64() * 1000.0,
            derive_ms: (write_start - derive_start).as_secs_f64() * 1000.0,
            write_ms: (end - write_start).as_secs_f64() * 1000.0,
        });
        self.model.as_ref().expect("cold model")
    }

    /// Freshen and return the logical corpus generation with its model. Server
    /// lifetime derived views use the generation as their invalidation key.
    pub fn read_model_with_generation(&mut self, verify: bool) -> (u64, &TrackerModel) {
        self.read_model(verify);
        (
            self.serving_generation,
            self.model.as_ref().expect("freshened model"),
        )
    }

    // --- detection ----------------------------------------------------------

    fn detect(&mut self, verify: bool) -> (std::collections::BTreeSet<String>, bool) {
        let confirm_all = self.model.is_none() || verify;
        if !confirm_all && self.watcher.is_clean() {
            return (std::collections::BTreeSet::new(), false);
        }

        let mut all_changed = std::collections::BTreeSet::new();
        // A stable bracket is the barrier: if an event arrives while scanning,
        // scan again. Under continuous writes, leave the watcher unacknowledged
        // after the bounded retries so the next call scans again.
        for _ in 0..3 {
            self.watcher.prepare_scan();
            let before = self.watcher.checkpoint();
            let (new_manifest, changed) =
                stat_scan(&self.root_str, &self.manifest, confirm_all, true);
            self.manifest = new_manifest;
            all_changed.extend(changed);
            let Some(before) = before else {
                return (all_changed, true);
            };
            if self.watcher.acknowledge_if_stable(before) {
                return (all_changed, true);
            }
        }
        (all_changed, true)
    }

    // --- applying the changed set -------------------------------------------

    fn apply(&mut self, changed: &std::collections::BTreeSet<String>) {
        let current: HashSet<&str> = self.manifest.iter().map(|(rel, _)| rel.as_str()).collect();
        if self.snapshot_shed {
            self.reparse_full();
            self.snapshot_shed = false;
        } else {
            let root = PathBuf::from(&self.root_str);
            let present: Vec<PathBuf> = changed
                .iter()
                .filter(|rel| current.contains(rel.as_str()))
                .map(|rel| root.join(rel))
                .collect();
            for rel in changed {
                if !current.contains(rel.as_str()) {
                    self.items.remove(rel); // removed
                }
            }
            let (parsed, workers) = crate::parallel_build::parallel_parse_paths(&present);
            self.last_parse_workers = workers;
            self.last_parse_files = present.len();
            for item in parsed {
                let rel = rel_of(&self.root_str, &item.path);
                self.items.insert(rel, item);
            }
        }
        let current: HashSet<String> = self
            .manifest
            .iter()
            .map(|(rel, _)| rel.clone())
            .collect();
        self.items.retain(|rel, _| current.contains(rel));
        if !changed.is_empty() {
            self.delta_paths.extend(changed.iter().cloned());
        }
        self.hash = Some(corpus_hash_from_complete_manifest(&self.manifest));
    }

    fn reparse_full(&mut self) {
        let root = PathBuf::from(&self.root_str);
        let paths: Vec<PathBuf> = self.manifest.iter().map(|(rel, _)| root.join(rel)).collect();
        let (parsed, workers) = crate::parallel_build::parallel_parse_paths(&paths);
        self.last_parse_workers = workers;
        self.last_parse_files = paths.len();
        self.items = parsed
            .into_iter()
            .map(|item| (rel_of(&self.root_str, &item.path), item))
            .collect();
    }

    /// The snapshot in walk (sorted-path) order — the fresh-walk order.
    fn ordered_items(&self) -> Vec<CorpusItem> {
        crate::walk::find_markdown_files(&self.root_str, true)
            .into_iter()
            .filter_map(|entry| self.items.get(&entry.components.join("/")).cloned())
            .collect()
    }

    fn rebuild_model(&mut self) {
        let hash = self.hash.clone().expect("hash set by apply");
        if Some(hash.as_str()) == self.base_hash.as_deref() && self.delta_paths.is_empty() {
            if let Some(view) = open_store(&self.cache_dir, &hash, SCHEMA_VERSION) {
                self.model = Some(TrackerModel::View(view));
                return;
            }
        }
        let derived =
            build_derived_index_from_items(&self.root_str, &self.ordered_items(), true);
        self.model = Some(TrackerModel::Snapshot(derived));
        self.serving_generation += 1;
    }

    /// Build a complete candidate generation from a staged document overlay,
    /// then swap every serving field only after derivation succeeds.
    fn rebuild_delta_preview(&mut self, changed: &BTreeSet<String>) {
        let current: HashSet<&str> = self.manifest.iter().map(|(rel, _)| rel.as_str()).collect();
        let root = PathBuf::from(&self.root_str);
        let present: Vec<PathBuf> = changed
            .iter()
            .filter(|rel| current.contains(rel.as_str()))
            .map(|rel| root.join(rel))
            .collect();
        let (parsed, workers) = crate::parallel_build::parallel_parse_paths(&present);
        self.last_parse_workers = workers;
        self.last_parse_files = present.len();
        let parsed: BTreeMap<String, CorpusItem> = parsed
            .into_iter()
            .map(|item| (rel_of(&self.root_str, &item.path), item))
            .collect();

        // A parser omission would make the staged generation incomplete.
        // Reparse the current corpus from an empty base instead of publishing
        // a partial overlay.
        let (candidate, identity_candidate, search_candidate, graph_candidate) =
            if parsed.len() == present.len() {
                let identity = self
                    .delta_identity
                    .as_ref()
                    .expect("preview identity")
                    .stage(changed, &parsed);
                let search = self
                    .delta_search
                    .as_ref()
                    .expect("preview search")
                    .stage(changed, &parsed);
                let graph = self
                    .delta_graph
                    .as_ref()
                    .expect("preview graph")
                    .stage(changed, &parsed, &identity);
                let documents = self
                    .delta_documents
                    .as_ref()
                    .expect("preview documents")
                    .stage(changed, parsed);
                (documents, identity, search, graph)
            } else {
                self.full_delta_candidate()
            };
        let ordered_paths: Vec<String> = self.manifest.iter().map(|(rel, _)| rel.clone()).collect();
        let ordered_items = candidate.ordered_items(ordered_paths.iter().map(String::as_str));
        let (candidate, identity_candidate, search_candidate, graph_candidate) =
            if ordered_items.len() == self.manifest.len() {
                (
                    candidate,
                    identity_candidate,
                    search_candidate,
                    graph_candidate,
                )
            } else {
                self.full_delta_candidate()
            };
        let ordered_items = candidate.ordered_items(ordered_paths.iter().map(String::as_str));
        let hash = corpus_hash_from_complete_manifest(&self.manifest);
        let serving_generation = self.serving_generation + 1;
        let generation = DeltaGeneration {
            base_generation: self.base_generation,
            serving_generation,
            changed_paths: candidate.changed_paths(),
            identity: identity_candidate.clone(),
            search: search_candidate.clone(),
            graph: graph_candidate.clone(),
            derived: build_derived_index_from_items(&self.root_str, &ordered_items, true),
        };

        self.delta_documents = Some(candidate);
        self.delta_identity = Some(identity_candidate);
        self.delta_search = Some(search_candidate);
        self.delta_graph = Some(graph_candidate);
        self.hash = Some(hash);
        self.serving_generation = serving_generation;
        self.model = Some(TrackerModel::Delta(Box::new(generation)));
    }

    fn full_delta_candidate(
        &mut self,
    ) -> (
        DeltaDocuments,
        IdentityGeneration,
        SearchGeneration,
        GraphGeneration,
    ) {
        let root = PathBuf::from(&self.root_str);
        let paths: Vec<PathBuf> = self
            .manifest
            .iter()
            .map(|(rel, _)| root.join(rel))
            .collect();
        let (parsed, workers) = crate::parallel_build::parallel_parse_paths(&paths);
        self.last_parse_workers = workers;
        self.last_parse_files = paths.len();
        let parsed: BTreeMap<String, CorpusItem> = parsed
            .into_iter()
            .map(|item| (rel_of(&self.root_str, &item.path), item))
            .collect();
        let identity =
            IdentityGeneration::from_items(parsed.iter().map(|(path, item)| (path.as_str(), item)));
        let search =
            SearchGeneration::from_items(parsed.iter().map(|(path, item)| (path.as_str(), item)));
        let graph = GraphGeneration::from_items(
            parsed.iter().map(|(path, item)| (path.as_str(), item)),
            &identity,
        );
        let changed = self.manifest.iter().map(|(rel, _)| rel.clone()).collect();
        (
            DeltaDocuments::empty().stage(&changed, parsed),
            identity,
            search,
            graph,
        )
    }

    // --- compaction -----------------------------------------------------------

    fn threshold_for(&self, base_count: usize) -> usize {
        self.threshold.unwrap_or_else(|| 10_000.max(base_count / 100))
    }

    fn maybe_compact(&mut self) {
        if self.base_hash.is_none() {
            self.compact(); // cold: establish the first base
            return;
        }
        if self.delta_size() >= self.threshold_for(self.manifest.len()) {
            self.compact();
        }
    }

    fn compact(&mut self) {
        let hash = self.hash.clone().expect("hash set");
        let derived_owned;
        let derived = match &self.model {
            Some(TrackerModel::Snapshot(derived)) => derived,
            Some(TrackerModel::Delta(generation)) => &generation.derived,
            _ => {
                derived_owned =
                    build_derived_index_from_items(&self.root_str, &self.ordered_items(), true);
                &derived_owned
            }
        };
        if !write_store(&self.cache_dir, &hash, SCHEMA_VERSION, derived) {
            return; // unwritable cache dir: keep serving the snapshot (ADR-080)
        }
        crate::derived_cache::write_marker_public(&self.cache_dir, &hash);
        let Some(view) = open_store(&self.cache_dir, &hash, SCHEMA_VERSION) else {
            return;
        };
        self.model = Some(TrackerModel::View(view));
        self.base_hash = Some(hash);
        self.base_generation += 1;
        self.delta_paths.clear();
        if let Some(documents) = self.delta_documents.as_mut() {
            let ordered_paths: Vec<&str> = self.manifest.iter().map(|(rel, _)| rel.as_str()).collect();
            documents.promote(ordered_paths);
            self.delta_identity
                .as_mut()
                .expect("preview identity")
                .promote();
            self.delta_search
                .as_mut()
                .expect("preview search")
                .promote();
            self.delta_graph
                .as_mut()
                .expect("preview graph")
                .promote();
            // P6 removes snapshot shedding for its parsed document base so
            // the first post-compaction edit remains change-bound.
            self.snapshot_shed = false;
        } else {
            // ADR-107 RSS finalization for the established default path.
            self.items = HashMap::new();
            self.snapshot_shed = true;
        }
    }
}

fn rel_of(root_str: &str, display_path: &str) -> String {
    let root = crate::walk::normalize_root(root_str);
    display_path
        .strip_prefix(&format!("{root}/"))
        .unwrap_or(display_path)
        .to_string()
}
