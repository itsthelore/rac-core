//! Server-lifetime serving freshness (ADR-105) — port of
//! `services/freshness.py` `FreshnessTracker` for the long-lived MCP server
//! (INDEX-PLAN B6).
//!
//! Detection rests on the stat-manifest scan (ADR-114 defers the inotify
//! accelerator — it only ever asserted *clean*, so its absence is
//! behavior-neutral; `mode()` reports `"stat"`). Whatever the rung, the
//! served read-model is re-derived from the tracker's incrementally
//! maintained parsed snapshot, byte-identical to a fresh whole-corpus walk
//! at the current corpus state.

use std::collections::{HashMap, HashSet};
use std::path::PathBuf;

use crate::derived::{build_derived_index_from_items, DerivedIndex, SCHEMA_VERSION};
use crate::derived_cache::{corpus_hash_from_complete_manifest, stat_scan};
use crate::index_store::{open_store, write_store, FileState, MmapIndexReader};
use crate::relationships::CorpusItem;

pub const MODE_STAT: &str = "stat";

/// What the tracker currently serves: the memory-mapped base (delta-empty),
/// or the re-derived snapshot bundle (the delta window).
pub enum TrackerModel {
    View(MmapIndexReader),
    Snapshot(DerivedIndex),
}

pub struct FreshnessTracker {
    cache_dir: PathBuf,
    root_str: String,
    threshold: Option<usize>,

    manifest: Vec<(String, FileState)>,
    items: HashMap<String, CorpusItem>, // rel -> parsed snapshot entry
    model: Option<TrackerModel>,
    hash: Option<String>,
    base_hash: Option<String>,
    base_generation: u64,
    delta_paths: HashSet<String>,
    /// ADR-107 RSS finalization: after compaction the resident parsed
    /// snapshot is shed and the mapped base is the whole answer; the next
    /// change repopulates by a full re-parse on demand.
    snapshot_shed: bool,
    last_parse_workers: usize,
}

impl FreshnessTracker {
    pub fn new(cache_dir: PathBuf, root: &str, threshold: Option<usize>) -> Self {
        Self {
            cache_dir,
            root_str: root.to_string(),
            threshold,
            manifest: Vec::new(),
            items: HashMap::new(),
            model: None,
            hash: None,
            base_hash: None,
            base_generation: 0,
            delta_paths: HashSet::new(),
            snapshot_shed: false,
            last_parse_workers: 1,
        }
    }

    // --- observable state (scorecards and pinning tests) ------------------

    pub fn mode(&self) -> &'static str {
        MODE_STAT
    }

    pub fn base_generation(&self) -> u64 {
        self.base_generation
    }

    pub fn delta_size(&self) -> usize {
        self.delta_paths.len()
    }

    pub fn corpus_hash(&self) -> Option<&str> {
        self.hash.as_deref()
    }

    // --- the serving surface ----------------------------------------------

    /// The current read-model, freshened through the detection ladder. An
    /// unchanged corpus returns the cached model with no re-derive.
    pub fn read_model(&mut self, verify: bool) -> &TrackerModel {
        let cold = self.model.is_none();
        let detect_started = crate::timing::start();
        let changed = self.detect(verify);
        crate::timing::emit_since(
            "tracker.detect",
            detect_started,
            &[("files", self.manifest.len() as u64), ("changed", changed.len() as u64)],
        );
        if changed.is_empty() && !cold {
            return self.model.as_ref().expect("warm model");
        }
        if !cold {
            let recompute_started = crate::timing::start();
            self.apply(&changed);
            self.rebuild_model();
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
        self.apply(&changed);
        let derive_start = std::time::Instant::now();
        self.rebuild_model();
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

    // --- detection ----------------------------------------------------------

    fn detect(&mut self, verify: bool) -> std::collections::BTreeSet<String> {
        let confirm_all = self.model.is_none() || verify;
        let (new_manifest, changed) =
            stat_scan(&self.root_str, &self.manifest, confirm_all, true);
        self.manifest = new_manifest;
        changed
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
        if self.delta_paths.len() >= self.threshold_for(self.manifest.len()) {
            self.compact();
        }
    }

    fn compact(&mut self) {
        let hash = self.hash.clone().expect("hash set");
        let derived_owned;
        let derived = match &self.model {
            Some(TrackerModel::Snapshot(derived)) => derived,
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
        // ADR-107 RSS finalization: shed the resident parsed snapshot.
        self.items = HashMap::new();
        self.snapshot_shed = true;
    }
}

fn rel_of(root_str: &str, display_path: &str) -> String {
    let root = crate::walk::normalize_root(root_str);
    display_path
        .strip_prefix(&format!("{root}/"))
        .unwrap_or(display_path)
        .to_string()
}
