//! FreshnessTracker state pins (INDEX-PLAN B6): cold start establishes the
//! mapped base; a change opens the delta window and serves the re-derived
//! snapshot; crossing the compaction threshold folds the window into a
//! fresh base, bumps the generation, and sheds the resident snapshot.

use std::fs;
use std::path::PathBuf;

use rac_engine::freshness::{FreshnessTracker, TrackerModel};

fn scratch(tag: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!("rac-tracker-{tag}-{}", std::process::id()));
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(&dir).expect("scratch");
    dir
}

const DOC: &str = "# ADR-1: Widget Base\n\n## Context\n\nBase.\n\n## Decision\n\nKeep.\n\n## Consequences\n\nNone.\n\n## Status\n\nAccepted\n";

#[test]
fn base_delta_compaction_lifecycle() {
    let corpus = scratch("corpus");
    let cache = scratch("cache");
    fs::write(corpus.join("adr-1-base.md"), DOC).unwrap();
    let root = corpus.to_string_lossy().into_owned();

    // Threshold 2: the second delta path triggers compaction — observable
    // without a 10k-file corpus.
    let mut tracker = FreshnessTracker::new(cache.clone(), &root, Some(2));
    assert_eq!(tracker.mode(), "stat");

    // Cold: full scan, first base written and served from the map.
    assert!(matches!(tracker.read_model(false), TrackerModel::View(_)));
    assert_eq!(tracker.base_generation(), 1);
    assert_eq!(tracker.serving_generation(), 1);
    assert_eq!(tracker.delta_size(), 0);
    let cold_hash = tracker.corpus_hash().unwrap().to_string();

    // Unchanged corpus: the cached model is returned, nothing moves.
    assert!(matches!(tracker.read_model(false), TrackerModel::View(_)));
    assert_eq!(tracker.base_generation(), 1);
    assert_eq!(tracker.serving_generation(), 1);

    // One change: the delta window opens; serving switches to the
    // re-derived snapshot (no base rewrite below the threshold).
    fs::write(corpus.join("adr-2-two.md"), DOC.replace("ADR-1", "ADR-2")).unwrap();
    assert!(matches!(tracker.read_model(false), TrackerModel::Snapshot(_)));
    assert_eq!(tracker.base_generation(), 1);
    assert_eq!(tracker.serving_generation(), 2);
    assert_eq!(tracker.delta_size(), 1);
    assert_ne!(tracker.corpus_hash().unwrap(), cold_hash);

    // Second change crosses the threshold: compaction writes a fresh base,
    // bumps the generation, clears the window, sheds the snapshot.
    fs::write(corpus.join("adr-3-three.md"), DOC.replace("ADR-1", "ADR-3")).unwrap();
    assert!(matches!(tracker.read_model(false), TrackerModel::View(_)));
    assert_eq!(tracker.base_generation(), 2);
    assert_eq!(tracker.serving_generation(), 3);
    assert_eq!(tracker.delta_size(), 0);

    // A change after the shed re-parses on demand and still answers.
    fs::remove_file(corpus.join("adr-2-two.md")).unwrap();
    match tracker.read_model(false) {
        TrackerModel::Snapshot(derived) => {
            assert_eq!(derived.index_entries.len(), 2);
        }
        TrackerModel::View(_) => panic!("one change below threshold must serve the snapshot"),
    }
    assert_eq!(tracker.serving_generation(), 4);

    let _ = fs::remove_dir_all(&corpus);
    let _ = fs::remove_dir_all(&cache);
}
