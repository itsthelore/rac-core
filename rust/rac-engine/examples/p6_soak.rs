//! ADR-119 S1 bounded lifecycle soak and byte-equality certification.
//!
//! Run against a disposable generated corpus:
//!
//! `p6_soak <corpus> <cache-root> [rounds]`

use std::fs;
use std::path::{Path, PathBuf};

use rac_engine::derived::{build_derived_index, DerivedIndex, SCHEMA_VERSION};
use rac_engine::freshness::{FreshnessTracker, TrackerModel};
use rac_engine::index_store::{store_dir, write_store};
use serde_json::json;

fn first_markdown(root: &Path) -> PathBuf {
    rac_engine::walk::find_markdown_files(&root.to_string_lossy(), true)
        .into_iter()
        .next()
        .map(|entry| root.join(entry.components.join("/")))
        .expect("corpus must contain at least one markdown file")
}

fn store_hashes(cache: &Path, key: &str) -> Vec<(String, String)> {
    let mut hashes: Vec<(String, String)> = fs::read_dir(store_dir(cache, key))
        .expect("read persisted store")
        .map(|entry| {
            let entry = entry.expect("read store entry");
            let bytes = fs::read(entry.path()).expect("read store segment");
            (
                entry.file_name().to_string_lossy().into_owned(),
                rac_engine::sha256::hexdigest(&bytes),
            )
        })
        .collect();
    hashes.sort();
    hashes
}

fn assert_valid(root: &str) {
    let items = rac_engine::relationships::corpus_items(root, true);
    for item in &items {
        let Some(spec) = item.spec else {
            continue;
        };
        let issues = rac_engine::validate::validate(&item.artifact, None, Some(&spec.name));
        assert!(
            !rac_engine::validate::has_errors(&issues),
            "{} must remain valid: {issues:?}",
            item.path
        );
    }
    let relationships = rac_engine::relationships::validate_relationships(root, true);
    assert!(
        relationships.ok(),
        "relationship validation must remain clean: {:?}",
        relationships.issues
    );
}

fn certify_generation(
    tracker: &mut FreshnessTracker,
    verify: bool,
    root: &str,
    tracker_cache: &Path,
    referee_root: &Path,
    stage: &str,
) {
    let materialized: Option<DerivedIndex> = match tracker.read_model(verify) {
        TrackerModel::Delta(generation) => Some(generation.materialize_derived(root, true)),
        TrackerModel::View(_) => None,
        TrackerModel::Snapshot(_) => panic!("S1 delta soak served a snapshot at {stage}"),
    };
    let key = tracker
        .corpus_hash()
        .expect("fresh generation must have a corpus hash")
        .to_string();
    let candidate_cache = referee_root.join(stage).join("candidate");
    let fresh_cache = referee_root.join(stage).join("fresh");
    let _ = fs::remove_dir_all(&candidate_cache);
    let _ = fs::remove_dir_all(&fresh_cache);

    let fresh = build_derived_index(root, true);
    assert!(write_store(&fresh_cache, &key, SCHEMA_VERSION, &fresh));
    let candidate_cache = if let Some(candidate) = materialized {
        assert!(write_store(
            &candidate_cache,
            &key,
            SCHEMA_VERSION,
            &candidate,
        ));
        candidate_cache.as_path()
    } else {
        tracker_cache
    };
    assert_eq!(
        store_hashes(candidate_cache, &key),
        store_hashes(&fresh_cache, &key),
        "persisted segments diverged from a fresh no-cache derivation at {stage}"
    );
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() < 3 {
        eprintln!("usage: p6_soak <corpus> <cache-root> [rounds]");
        std::process::exit(2);
    }
    let corpus = PathBuf::from(&args[1]);
    let cache_root = PathBuf::from(&args[2]);
    let rounds: usize = args
        .get(3)
        .and_then(|value| value.parse().ok())
        .unwrap_or(3);
    let root = corpus.to_string_lossy().into_owned();
    let mutation_cache = cache_root.join("mutation");
    let referee_root = cache_root.join("referees");
    let _ = fs::remove_dir_all(&cache_root);
    fs::create_dir_all(&cache_root).expect("create soak cache");
    assert_valid(&root);

    let mut tracker = FreshnessTracker::new(
        mutation_cache.clone(),
        &root,
        Some(rounds.saturating_mul(16).saturating_add(100)),
    );
    certify_generation(
        &mut tracker,
        true,
        &root,
        &mutation_cache,
        &referee_root,
        "cold",
    );
    let mut warm_reads = 0;
    for _ in 0..100 {
        tracker.read_model(false);
        warm_reads += 1;
    }

    let target = first_markdown(&corpus);
    let original = fs::read(&target).expect("read mutation target");
    let mut transitions = 0;
    for round in 0..rounds {
        let mut edited = original.clone();
        edited.extend_from_slice(format!("\n<!-- p6-soak-{round} -->\n").as_bytes());
        fs::write(&target, &edited).expect("write edit");
        certify_generation(
            &mut tracker,
            true,
            &root,
            &mutation_cache,
            &referee_root,
            &format!("round-{round}-edit"),
        );
        assert_eq!(tracker.last_parse_files(), 1);
        transitions += 1;

        fs::write(&target, &original).expect("restore edit");
        certify_generation(
            &mut tracker,
            true,
            &root,
            &mutation_cache,
            &referee_root,
            &format!("round-{round}-restore"),
        );
        assert_eq!(tracker.last_parse_files(), 1);
        transitions += 1;

        let added = corpus.join(format!("p6-soak-added-{round}.md"));
        let added_text = format!(
            "---\nschema_version: 1\nid: RAC-Z9SCAE{round:06}\ntype: decision\n---\n# Soak {round}\n\n## Context\n\nBounded soak.\n\n## Decision\n\nCertify.\n\n## Consequences\n\nEvidence.\n\n## Status\n\nAccepted\n"
        );
        fs::write(&added, added_text).expect("write added artifact");
        certify_generation(
            &mut tracker,
            true,
            &root,
            &mutation_cache,
            &referee_root,
            &format!("round-{round}-add"),
        );
        assert_eq!(tracker.last_parse_files(), 1);
        transitions += 1;

        fs::remove_file(&added).expect("delete added artifact");
        certify_generation(
            &mut tracker,
            true,
            &root,
            &mutation_cache,
            &referee_root,
            &format!("round-{round}-delete"),
        );
        assert_eq!(tracker.last_parse_files(), 0);
        transitions += 1;

        let renamed = target.with_extension(format!("soak-{round}.md"));
        fs::rename(&target, &renamed).expect("rename target");
        certify_generation(
            &mut tracker,
            true,
            &root,
            &mutation_cache,
            &referee_root,
            &format!("round-{round}-rename"),
        );
        assert_eq!(tracker.last_parse_files(), 1);
        transitions += 1;
        fs::rename(&renamed, &target).expect("restore target name");
        certify_generation(
            &mut tracker,
            true,
            &root,
            &mutation_cache,
            &referee_root,
            &format!("round-{round}-rename-back"),
        );
        assert_eq!(tracker.last_parse_files(), 1);
        transitions += 1;
    }

    let compaction_cache = cache_root.join("compaction");
    let compaction_referees = cache_root.join("compaction-referees");
    let mut compact = FreshnessTracker::new(compaction_cache.clone(), &root, Some(1));
    certify_generation(
        &mut compact,
        true,
        &root,
        &compaction_cache,
        &compaction_referees,
        "compact-cold",
    );
    let mut edited = original.clone();
    edited.extend_from_slice(b"\n<!-- p6-soak-compaction -->\n");
    fs::write(&target, &edited).expect("write compaction edit");
    certify_generation(
        &mut compact,
        true,
        &root,
        &compaction_cache,
        &compaction_referees,
        "compact-edit",
    );
    assert_eq!(compact.last_parse_files(), 1);
    assert_eq!(compact.delta_size(), 0);
    fs::write(&target, &original).expect("write first post-compaction edit");
    certify_generation(
        &mut compact,
        true,
        &root,
        &compaction_cache,
        &compaction_referees,
        "compact-post-edit",
    );
    assert_eq!(compact.last_parse_files(), 1);
    assert_eq!(compact.delta_size(), 0);
    assert_valid(&root);

    println!(
        "{}",
        serde_json::to_string_pretty(&json!({
            "schema_version": "1",
            "files": rac_engine::walk::find_markdown_files(&root, true).len(),
            "rounds": rounds,
            "warm_reads": warm_reads,
            "certified_transitions": transitions + 3,
            "valid": true,
            "deterministic": true,
            "fresh": true,
            "cache_no_cache_equal": true,
            "persisted_segments_byte_equal": true,
            "post_compaction_parse_files": compact.last_parse_files(),
        }))
        .unwrap()
    );
}
