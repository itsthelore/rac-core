//! ADR-119 P6 scale-certification harness.
//!
//! Run against a disposable generated corpus. The harness restores every
//! mutation it makes, but the cache directory is intentionally retained for
//! inspection.

use std::fs;
use std::path::{Path, PathBuf};
use std::time::Instant;

use rac_engine::freshness::FreshnessTracker;
use serde_json::{json, Value};

fn elapsed_ms(start: Instant) -> f64 {
    start.elapsed().as_secs_f64() * 1000.0
}

fn timed_read(tracker: &mut FreshnessTracker, verify: bool) -> f64 {
    let start = Instant::now();
    tracker.read_model(verify);
    elapsed_ms(start)
}

fn distribution(values: &[f64]) -> Value {
    let mut sorted = values.to_vec();
    sorted.sort_by(f64::total_cmp);
    let percentile = |p: f64| {
        let index = ((sorted.len() as f64 * p).ceil() as usize)
            .saturating_sub(1)
            .min(sorted.len().saturating_sub(1));
        sorted.get(index).copied().unwrap_or(0.0)
    };
    json!({"p50_ms": percentile(0.50), "p95_ms": percentile(0.95)})
}

fn first_markdown(root: &Path) -> PathBuf {
    rac_engine::walk::find_markdown_files(&root.to_string_lossy(), true)
        .into_iter()
        .next()
        .map(|entry| root.join(entry.components.join("/")))
        .expect("corpus must contain at least one markdown file")
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() < 4 || !matches!(args[1].as_str(), "snapshot" | "delta") {
        eprintln!("usage: p6_scale <snapshot|delta> <corpus> <cache-dir> [iterations]");
        std::process::exit(2);
    }
    let mode = &args[1];
    let root = PathBuf::from(&args[2]);
    let cache = PathBuf::from(&args[3]);
    let iterations: usize = args.get(4).and_then(|v| v.parse().ok()).unwrap_or(7);
    let root_text = root.to_string_lossy().into_owned();
    let file_count = rac_engine::walk::find_markdown_files(&root_text, true).len();
    let threshold = file_count.saturating_add(iterations).saturating_add(10);
    let mut tracker = if mode == "delta" {
        FreshnessTracker::new_delta_preview(cache.clone(), &root_text, Some(threshold))
    } else {
        FreshnessTracker::new(cache.clone(), &root_text, Some(threshold))
    };

    let cold_ms = timed_read(&mut tracker, true);
    let warm_ms: Vec<f64> = (0..iterations)
        .map(|_| timed_read(&mut tracker, false))
        .collect();

    let target = first_markdown(&root);
    let original = fs::read(&target).expect("read mutation target");
    let mut edited = original.clone();
    edited.extend_from_slice(b"\n<!-- p6-scale-edit -->\n");
    let mut edit_ms = Vec::new();
    for _ in 0..iterations {
        fs::write(&target, &edited).expect("write edit");
        edit_ms.push(timed_read(&mut tracker, true));
        fs::write(&target, &original).expect("restore edit");
        timed_read(&mut tracker, true);
    }

    let added = root.join("p6-scale-added.md");
    let added_text = "---\nschema_version: 1\nid: RAC-Z9SCAE000001\ntype: decision\n---\n# Scale Probe\n\n## Context\n\nBenchmark.\n\n## Decision\n\nMeasure.\n\n## Consequences\n\nEvidence.\n\n## Status\n\nAccepted\n";
    let mut add_ms = Vec::new();
    let mut delete_ms = Vec::new();
    for _ in 0..iterations {
        fs::write(&added, added_text).expect("write added probe");
        add_ms.push(timed_read(&mut tracker, true));
        fs::remove_file(&added).expect("remove added probe");
        delete_ms.push(timed_read(&mut tracker, true));
    }

    let renamed = target.with_extension("p6-scale-renamed.md");
    let mut rename_ms = Vec::new();
    for _ in 0..iterations {
        fs::rename(&target, &renamed).expect("rename probe");
        rename_ms.push(timed_read(&mut tracker, true));
        fs::rename(&renamed, &target).expect("restore rename probe");
        timed_read(&mut tracker, true);
    }

    let mut compact_tracker = if mode == "delta" {
        FreshnessTracker::new_delta_preview(cache.join("compact"), &root_text, Some(1))
    } else {
        FreshnessTracker::new(cache.join("compact"), &root_text, Some(1))
    };
    timed_read(&mut compact_tracker, true);
    fs::write(&target, &edited).expect("write compaction edit");
    let compact_ms = timed_read(&mut compact_tracker, true);
    fs::write(&target, &original).expect("restore compaction edit");

    let summary = json!({
        "warm": distribution(&warm_ms),
        "edit": distribution(&edit_ms),
        "add": distribution(&add_ms),
        "delete": distribution(&delete_ms),
        "rename": distribution(&rename_ms),
    });
    let output: Value = json!({
        "schema_version": "1",
        "mode": mode,
        "corpus": root_text,
        "files": file_count,
        "iterations": iterations,
        "cold_ms": cold_ms,
        "warm_ms": warm_ms,
        "edit_ms": edit_ms,
        "add_ms": add_ms,
        "delete_ms": delete_ms,
        "rename_ms": rename_ms,
        "compact_ms": compact_ms,
        "summary": summary,
        "last_parse_files": tracker.last_parse_files(),
        "delta_size": tracker.delta_size(),
    });
    println!("{}", serde_json::to_string_pretty(&output).unwrap());
}
