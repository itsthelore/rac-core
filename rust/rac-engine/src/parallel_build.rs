//! Parallel cold build of the derived read-model (ADR-107/ADR-108).
//!
//! Native shape of `services/parallel_build.py` + `parallel_merge.py`: the
//! per-document work (parse, classify, index row, token vectors, live/scope
//! projection) fans out across rayon workers as compact *fragments*; the
//! parent merge runs only the cross-document steps (graph resolution,
//! inbound fill, portfolio) — in sorted-path order, so the store bytes are
//! worker-count-invariant by construction (no pickling boundary exists
//! in-process; ADR-114).
//!
//! Correctness never depends on the parallel rung: below the file-count
//! threshold, on a 1–2 core box, or on ANY worker fault (a panic in a
//! fragment task — exercised by `RAC_PARALLEL_BUILD_FAULT`), the build
//! falls back to the authoritative serial floor, whose partial results are
//! never written.

use std::path::PathBuf;

use crate::derived::{build_derived_index_from_items, DerivedIndex, DECISION_TYPE};
use crate::relationships::{relationships_from_corpus, CorpusItem};
use crate::resolve::{entry_from_item, field_tokens_of, is_live_decision, IndexEntry};
use crate::retrieve::{scope_rows_from_items, ScopeRow};

const TIMING_ENV: &str = "RAC_TIMING";
/// Fault-injection hook: when set, every fragment task panics — exercising
/// the fault → serial-floor degrade in a real parallel run. Never set in
/// production.
const FAULT_ENV: &str = "RAC_PARALLEL_BUILD_FAULT";
/// Below this file count the fan-out's coordination overhead outweighs the
/// win, so the cold build stays on the serial floor (the oracle's measured
/// crossover, kept for contract fidelity).
pub const DEFAULT_MIN_PARALLEL_FILES: usize = 5_000;
const MIN_FILES_ENV: &str = "RAC_PARALLEL_BUILD_MIN_FILES";

/// Per-phase cold-build timings for the `RAC_TIMING` scorecard line.
#[derive(Default)]
pub struct BuildStats {
    pub files: usize,
    pub workers: usize,
    pub parse_ms: f64,
    pub derive_ms: f64,
    pub write_ms: f64,
}

fn min_parallel_files() -> usize {
    let Some(raw) = std::env::var_os(MIN_FILES_ENV) else {
        return DEFAULT_MIN_PARALLEL_FILES;
    };
    match raw.to_string_lossy().trim().parse::<i64>() {
        Ok(value) if value >= 0 => value as usize,
        _ => DEFAULT_MIN_PARALLEL_FILES,
    }
}

/// How many workers to use — 1 means the serial floor. An explicit count
/// (the worker-invariance lever) is honoured up to the file count; the
/// default policy stays serial on a small box or below the threshold.
fn resolve_workers(workers: Option<usize>, n_files: usize) -> usize {
    if n_files <= 1 {
        return 1;
    }
    if let Some(w) = workers {
        return w.max(1).min(n_files);
    }
    let cpu = std::thread::available_parallelism()
        .map(std::num::NonZeroUsize::get)
        .unwrap_or(1);
    if cpu <= 2 || n_files < min_parallel_files() {
        return 1;
    }
    cpu.min(n_files)
}

/// One document's compact derived projection — the unit workers emit.
struct DocFragment {
    item: CorpusItem,
    index_entry: IndexEntry, // inbound stays 0; the merge fills it
    field_tokens: crate::resolve::FieldTokens,
    is_live_decision: bool,
    scope_row: Option<ScopeRow>,
}

fn fragment_for(path_display: &str) -> DocFragment {
    if std::env::var_os(FAULT_ENV).is_some() {
        panic!("parallel-build worker fault (injected)");
    }
    let artifact = crate::parse::parse_file(path_display);
    let spec = crate::spec::spec_for(&crate::classify::classify(&artifact).artifact_type);
    let item = CorpusItem {
        path: path_display.to_string(),
        artifact,
        spec,
    };
    let index_entry = entry_from_item(&item, 0);
    let field_tokens = field_tokens_of(&index_entry);
    let live = item.spec.map(|s| s.name == DECISION_TYPE).unwrap_or(false)
        && is_live_decision(&item.artifact);
    let scope_row = scope_rows_from_items(std::slice::from_ref(&item)).into_iter().next();
    DocFragment {
        item,
        index_entry,
        field_tokens,
        is_live_decision: live,
        scope_row,
    }
}

/// Fan the parse + per-doc derive across `n_workers`, or None on any fault.
fn fragments_parallel(paths: &[String], n_workers: usize) -> Option<Vec<DocFragment>> {
    let pool = rayon::ThreadPoolBuilder::new()
        .num_threads(n_workers)
        .build()
        .ok()?;
    let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
        pool.install(|| {
            use rayon::prelude::*;
            paths
                .par_iter()
                .map(|path| fragment_for(path))
                .collect::<Vec<DocFragment>>()
        })
    }));
    // A partially-derived result is discarded whole — the store is never
    // written from a faulted fan-out.
    result.ok()
}

/// Reproduce the derived read-model from per-document fragments: only the
/// cross-document steps run here, in sorted-path order.
fn reproduce(fragments: Vec<DocFragment>, directory: &str, recursive: bool) -> DerivedIndex {
    let mut items = Vec::with_capacity(fragments.len());
    let mut index_entries = Vec::with_capacity(fragments.len());
    let mut field_tokens = Vec::with_capacity(fragments.len());
    let mut live_decision_paths = Vec::new();
    let mut scope_rows = Vec::new();
    for fragment in fragments {
        if fragment.is_live_decision {
            live_decision_paths.push(fragment.index_entry.path.clone());
        }
        if let Some(row) = fragment.scope_row {
            scope_rows.push(row);
        }
        items.push(fragment.item);
        index_entries.push(fragment.index_entry);
        field_tokens.push(fragment.field_tokens);
    }
    // The cross-document steps: graph resolution, inbound fill, portfolio.
    let relationships = relationships_from_corpus(&items);
    let mut inbound: std::collections::HashMap<&str, i64> = std::collections::HashMap::new();
    for rel in &relationships {
        if let Some(resolved) = &rel.resolved_path {
            *inbound.entry(resolved.as_str()).or_insert(0) += 1;
        }
    }
    for entry in &mut index_entries {
        entry.inbound_count = inbound.get(entry.path.as_str()).copied().unwrap_or(0);
    }
    let summary = crate::portfolio::portfolio_from_corpus(directory, &items, recursive);
    DerivedIndex {
        index_entries,
        field_tokens,
        relationships,
        live_decision_paths,
        portfolio_summary: crate::output::portfolio_summary_value(&summary),
        scope_rows,
    }
}

/// Build the derived read-model with a parallel parse AND per-doc derive —
/// byte-identical to `derived::build_derived_index` for any worker count.
pub fn build_derived_index_parallel(
    directory: &str,
    recursive: bool,
    workers: Option<usize>,
) -> (DerivedIndex, BuildStats) {
    let t0 = std::time::Instant::now();
    let paths: Vec<String> = crate::walk::find_markdown_files(directory, recursive)
        .into_iter()
        .map(|e| e.display)
        .collect();
    let n_workers = resolve_workers(workers, paths.len());
    let fragments = if n_workers > 1 {
        fragments_parallel(&paths, n_workers)
    } else {
        None
    };
    if let Some(fragments) = fragments {
        let used = n_workers;
        let t1 = std::time::Instant::now();
        let n_files = fragments.len();
        let derived = reproduce(fragments, directory, recursive);
        let t2 = std::time::Instant::now();
        return (
            derived,
            BuildStats {
                files: n_files,
                workers: used,
                parse_ms: (t1 - t0).as_secs_f64() * 1000.0,
                derive_ms: (t2 - t1).as_secs_f64() * 1000.0,
                write_ms: 0.0,
            },
        );
    }
    // Serial floor: the authoritative walk + derive; a fault above lands here.
    let items = crate::relationships::corpus_items(directory, recursive);
    let t1 = std::time::Instant::now();
    let derived = build_derived_index_from_items(directory, &items, recursive);
    let t2 = std::time::Instant::now();
    (
        derived,
        BuildStats {
            files: items.len(),
            workers: 1,
            parse_ms: (t1 - t0).as_secs_f64() * 1000.0,
            derive_ms: (t2 - t1).as_secs_f64() * 1000.0,
            write_ms: 0.0,
        },
    )
}

/// Write the cold-build scorecard line to stderr when `RAC_TIMING` is set —
/// env-gated, stderr-only, byte-shaped like the oracle's (ADR-107).
pub fn emit_build_timing(stats: &BuildStats) {
    if std::env::var_os(TIMING_ENV).is_none() {
        return;
    }
    eprintln!(
        "rac-timing: build_parse_ms={:.3} build_derive_ms={:.3} build_write_ms={:.3} workers={} files={}",
        stats.parse_ms, stats.derive_ms, stats.write_ms, stats.workers, stats.files
    );
}

/// The paths type alias for the freshness tracker's explicit-list parse
/// (INDEX-PLAN B6): parse a known path list through the one true per-file
/// path, parallel when it pays; entries in list order.
pub fn parallel_parse_paths(paths: &[PathBuf]) -> (Vec<CorpusItem>, usize) {
    let displays: Vec<String> = paths
        .iter()
        .map(|p| p.to_string_lossy().into_owned())
        .collect();
    use rayon::prelude::*;
    let items: Vec<CorpusItem> = displays
        .par_iter()
        .map(|path| {
            let artifact = crate::parse::parse_file(path);
            let spec =
                crate::spec::spec_for(&crate::classify::classify(&artifact).artifact_type);
            CorpusItem {
                path: path.clone(),
                artifact,
                spec,
            }
        })
        .collect();
    let workers = std::thread::available_parallelism()
        .map(std::num::NonZeroUsize::get)
        .unwrap_or(1);
    (items, workers)
}
