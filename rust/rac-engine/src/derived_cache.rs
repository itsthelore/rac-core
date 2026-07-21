//! Content-addressed derived-index cache (ADR-099/ADR-112) — port of
//! `services/derived_cache.py` `DerivedIndexCache.load_or_build` plus the
//! stat-manifest freshness rungs of `services/freshness.py` the one-shot
//! path consumes (INDEX-PLAN B3).
//!
//! Every failure mode degrades to a fresh build: enabling the cache can only
//! change latency, never an answer or an exit code (ADR-080).

use std::collections::BTreeSet;
use std::path::{Path, PathBuf};
use rayon::prelude::*;

use crate::derived::{DerivedIndex, SCHEMA_VERSION};
use crate::index_store::{
    manifest_root_key, open_freshness_manifest, open_store, remove_store, store_dir,
    write_freshness_manifest, write_store, FileState, MmapIndexReader,
};
use crate::walk::find_markdown_files;

pub const CACHE_DIR_ENV: &str = "RAC_CACHE_DIR";

/// Whether the persistent cache is active for this invocation (ADR-112):
/// on by default; `--no-cache` per invocation, non-empty `RAC_NO_CACHE`
/// environment-wide.
pub fn cache_enabled(cache_flag: bool) -> bool {
    cache_flag && std::env::var("RAC_NO_CACHE").unwrap_or_default().is_empty()
}

/// The derived-cache directory ladder: `RAC_CACHE_DIR` >
/// `$XDG_CACHE_HOME/rac/derived` > `~/.cache/rac/derived` >
/// `<tmp>/rac-cache/rac/derived` (the homeless floor — never raises).
pub fn default_cache_dir() -> PathBuf {
    if let Ok(dir) = std::env::var(CACHE_DIR_ENV) {
        if !dir.is_empty() {
            return PathBuf::from(dir);
        }
    }
    let base = match std::env::var("XDG_CACHE_HOME") {
        Ok(xdg) if !xdg.is_empty() => PathBuf::from(xdg),
        _ => match std::env::var("HOME") {
            Ok(home) if !home.is_empty() => Path::new(&home).join(".cache"),
            _ => std::env::temp_dir().join("rac-cache"),
        },
    };
    base.join("rac").join("derived")
}

// ---------------------------------------------------------------------------
// Freshness rungs (services/freshness.py stat_scan + hash recomposition)
// ---------------------------------------------------------------------------

fn stat_pair(path: &Path) -> Option<(u64, u64)> {
    use std::os::unix::fs::MetadataExt;
    let meta = std::fs::metadata(path).ok()?;
    let mtime_ns = (meta.mtime() as i128) * 1_000_000_000 + i128::from(meta.mtime_nsec());
    Some((meta.len(), mtime_ns as u64))
}

/// Diff the corpus against `prev_manifest` by stat, content-confirming
/// changes. Returns the rebuilt manifest (scan order) and the changed set.
pub fn stat_scan(
    root_str: &str,
    prev_manifest: &[(String, FileState)],
    content_confirm_all: bool,
    recursive: bool,
) -> (Vec<(String, FileState)>, BTreeSet<String>) {
    let prev: std::collections::HashMap<&str, &FileState> = prev_manifest
        .iter()
        .map(|(rel, state)| (rel.as_str(), state))
        .collect();
    let discovery_started = crate::timing::start();
    let entries = find_markdown_files(root_str, recursive);
    crate::timing::emit_since(
        "stat.discovery",
        discovery_started,
        &[("files", entries.len() as u64)],
    );
    // Metadata probes dominate the warm scan at large corpus sizes and are
    // independent. Indexed parallel collection preserves walk order, which is
    // part of the manifest/hash contract.
    let metadata_started = crate::timing::start();
    let scan_entry = |entry: &crate::walk::WalkEntry| {
        let rel = entry.components.join("/");
        let Some((size, mtime_ns)) = stat_pair(&entry.abs) else {
            return None; // vanished between enumeration and stat
        };
        if !content_confirm_all {
            if let Some(prev_state) = prev.get(rel.as_str()) {
                if prev_state.size == size && prev_state.mtime_ns == mtime_ns {
                    return Some((rel, (*prev_state).clone(), false)); // S5 accepted
                }
            }
        }
        let digest = crate::index_store::content_hash(&entry.abs);
        let changed_content = match prev.get(rel.as_str()) {
            Some(prev_state) => prev_state.content_hash != digest,
            None => true,
        };
        Some((
            rel.clone(),
            FileState {
                content_hash: digest,
                size,
                mtime_ns,
            },
            changed_content,
        ))
    };
    let scanned: Vec<Option<(String, FileState, bool)>> =
        entries.par_iter().map(scan_entry).collect();
    crate::timing::emit_since(
        "stat.metadata",
        metadata_started,
        &[("files", entries.len() as u64)],
    );
    let mut changed: BTreeSet<String> = BTreeSet::new();
    let mut new_manifest: Vec<(String, FileState)> = Vec::with_capacity(scanned.len());
    for (rel, state, changed_content) in scanned.into_iter().flatten() {
        if changed_content {
            changed.insert(rel.clone());
        }
        new_manifest.push((rel, state));
    }
    let present: std::collections::HashSet<&str> =
        new_manifest.iter().map(|(rel, _)| rel.as_str()).collect();
    for (rel, _) in prev_manifest {
        if !present.contains(rel.as_str()) {
            changed.insert(rel.clone()); // removed — enumeration is truth
        }
    }
    (new_manifest, changed)
}

/// Reproduce `corpus_content_hash` from the manifest's cached hashes.
pub fn corpus_hash_from_manifest(
    root_str: &str,
    manifest: &[(String, FileState)],
    recursive: bool,
) -> String {
    let by_rel: std::collections::HashMap<&str, &FileState> = manifest
        .iter()
        .map(|(rel, state)| (rel.as_str(), state))
        .collect();
    let mut hasher = crate::sha256::Sha256::new();
    for entry in find_markdown_files(root_str, recursive) {
        let rel = entry.components.join("/");
        let digest = match by_rel.get(rel.as_str()) {
            Some(state) => state.content_hash.clone(),
            None => crate::index_store::content_hash(&entry.abs),
        };
        hasher.update(rel.as_bytes());
        hasher.update(b"\0");
        hasher.update(digest.as_bytes());
        hasher.update(b"\0");
    }
    hasher.hexdigest()
}

/// Recompose the corpus hash from a complete scan-order manifest without a
/// second filesystem walk. `stat_scan` always returns exactly this shape.
pub fn corpus_hash_from_complete_manifest(manifest: &[(String, FileState)]) -> String {
    let mut hasher = crate::sha256::Sha256::new();
    for (rel, state) in manifest {
        hasher.update(rel.as_bytes());
        hasher.update(b"\0");
        hasher.update(state.content_hash.as_bytes());
        hasher.update(b"\0");
    }
    hasher.hexdigest()
}

// ---------------------------------------------------------------------------
// Marker file — the fail-closed schema gate beside the store.
// ---------------------------------------------------------------------------

fn marker_path(cache_dir: &Path, corpus_hash: &str) -> PathBuf {
    cache_dir.join(format!("{corpus_hash}.json"))
}

fn marker_valid(cache_dir: &Path, corpus_hash: &str) -> bool {
    let Ok(text) = std::fs::read_to_string(marker_path(cache_dir, corpus_hash)) else {
        return false;
    };
    let Ok(value) = serde_json::from_str::<serde_json::Value>(&text) else {
        return false;
    };
    value
        .as_object()
        .and_then(|obj| obj.get("schema_version"))
        .and_then(|v| v.as_str())
        == Some(SCHEMA_VERSION)
}

/// The tracker's compaction gate (INDEX-PLAN B6): write the marker for an
/// already-landed store.
pub fn write_marker_public(cache_dir: &Path, corpus_hash: &str) -> bool {
    write_marker(cache_dir, corpus_hash, true)
}

fn write_marker(cache_dir: &Path, corpus_hash: &str, store_written: bool) -> bool {
    if !store_written {
        return false;
    }
    if std::fs::create_dir_all(cache_dir).is_err() {
        return false;
    }
    // json.dumps default separators over an insertion-ordered dict.
    let payload =
        format!("{{\"schema_version\": \"{SCHEMA_VERSION}\", \"corpus_hash\": \"{corpus_hash}\"}}");
    let tmp = cache_dir.join(format!(
        ".{corpus_hash}.{}.tmp",
        std::process::id()
    ));
    if std::fs::write(&tmp, payload).is_err() {
        let _ = std::fs::remove_file(&tmp);
        return false;
    }
    if std::fs::rename(&tmp, marker_path(cache_dir, corpus_hash)).is_err() {
        let _ = std::fs::remove_file(&tmp);
        return false;
    }
    true
}

// ---------------------------------------------------------------------------
// load_or_build — the whole cache surface.
// ---------------------------------------------------------------------------

/// What `load_or_build` returns: a memory-mapped store view (the warm path),
/// or the freshly built structures when the store could not be written or
/// reopened (ADR-080 — never a failure).
pub enum ReadModel {
    View(MmapIndexReader),
    Fresh(DerivedIndex),
}

pub struct DerivedIndexCache {
    pub cache_dir: PathBuf,
}

impl Default for DerivedIndexCache {
    fn default() -> Self {
        Self {
            cache_dir: default_cache_dir(),
        }
    }
}

impl DerivedIndexCache {
    pub fn load_or_build(&self, directory: &str, recursive: bool, verify: bool) -> ReadModel {
        // Freshness: the key is recomputed every call through the persisted
        // stat manifest (ADR-112); `verify` or a missing manifest forces the
        // content-confirm-all floor, and the rewrite self-heals either way.
        let root_key = manifest_root_key(directory, recursive);
        let prev = if verify {
            None
        } else {
            open_freshness_manifest(&self.cache_dir, &root_key)
        };
        let manifest_missing = prev.is_none();
        let confirm_all = verify || manifest_missing;
        let prev_manifest = prev.unwrap_or_default();
        let scan_started = crate::timing::start();
        let (manifest, changed) = stat_scan(directory, &prev_manifest, confirm_all, recursive);
        crate::timing::emit_since(
            "cache.discovery_stat",
            scan_started,
            &[
                ("files", manifest.len() as u64),
                ("changed", changed.len() as u64),
            ],
        );
        let hash_started = crate::timing::start();
        let corpus_hash = corpus_hash_from_complete_manifest(&manifest);
        crate::timing::emit_since(
            "cache.corpus_hash",
            hash_started,
            &[("files", manifest.len() as u64)],
        );
        // Best-effort persistence: the manifest is a latency structure only.
        let manifest_started = crate::timing::start();
        let manifest_dirty = manifest_missing || manifest != prev_manifest;
        let manifest_written =
            !manifest_dirty || write_freshness_manifest(&self.cache_dir, &root_key, &manifest);
        crate::timing::emit_since(
            "cache.manifest_write",
            manifest_started,
            &[
                ("files", manifest.len() as u64),
                ("dirty", u64::from(manifest_dirty)),
                ("success", u64::from(manifest_written)),
            ],
        );
        if marker_valid(&self.cache_dir, &corpus_hash) {
            let open_started = crate::timing::start();
            if let Some(view) = open_store(&self.cache_dir, &corpus_hash, SCHEMA_VERSION) {
                crate::timing::emit_since(
                    "cache.store_open",
                    open_started,
                    &[("hit", 1), ("documents", u64::from(view.doc_count))],
                );
                return ReadModel::View(view);
            }
            crate::timing::emit_since("cache.store_open", open_started, &[("hit", 0)]);
            // Marker claimed a store but it is unusable: clear it so the
            // rebuild below writes fresh rather than skipping the dead dir.
            remove_store(&self.cache_dir, &corpus_hash);
        }
        // Cold miss: build the store from nothing with the parallel fragment
        // fan-out (ADR-107/108) — byte-identical to the serial build, only
        // faster to produce; the RAC_TIMING scorecard line rides here.
        let build_started = crate::timing::start();
        let (derived, mut stats) =
            crate::parallel_build::build_derived_index_parallel(directory, recursive, None);
        crate::timing::emit_since(
            "cache.cold_build",
            build_started,
            &[("documents", derived.index_entries.len() as u64)],
        );
        let write_start = std::time::Instant::now();
        let store_write_started = crate::timing::start();
        let store_written = write_store(&self.cache_dir, &corpus_hash, SCHEMA_VERSION, &derived);
        crate::timing::emit_since(
            "cache.store_write",
            store_write_started,
            &[("written", u64::from(store_written))],
        );
        stats.write_ms = write_start.elapsed().as_secs_f64() * 1000.0;
        crate::parallel_build::emit_build_timing(&stats);
        if write_marker(&self.cache_dir, &corpus_hash, store_written) {
            if let Some(view) = open_store(&self.cache_dir, &corpus_hash, SCHEMA_VERSION) {
                return ReadModel::View(view);
            }
        }
        ReadModel::Fresh(derived)
    }

    /// Whether a store directory currently exists for `corpus_hash`.
    pub fn store_present(&self, corpus_hash: &str) -> bool {
        store_dir(&self.cache_dir, corpus_hash).is_dir()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn complete_manifest_hash_uses_scan_order_and_content_only() {
        let manifest = vec![
            (
                "a.md".to_string(),
                FileState {
                    content_hash: "hash-a".to_string(),
                    size: 10,
                    mtime_ns: 20,
                },
            ),
            (
                "nested/b.md".to_string(),
                FileState {
                    content_hash: "hash-b".to_string(),
                    size: 30,
                    mtime_ns: 40,
                },
            ),
        ];

        assert_eq!(
            corpus_hash_from_complete_manifest(&manifest),
            crate::sha256::hexdigest(b"a.md\0hash-a\0nested/b.md\0hash-b\0")
        );

        let mut stat_only_change = manifest.clone();
        stat_only_change[0].1.size += 1;
        stat_only_change[0].1.mtime_ns += 1;
        assert_eq!(
            corpus_hash_from_complete_manifest(&manifest),
            corpus_hash_from_complete_manifest(&stat_only_change)
        );
    }
}
