//! Bounded internal regression coverage for P3's three grounding read paths.
//!
//! Cross-engine contract bytes belong to rac-spec (ADR-120). This suite checks
//! the Rust implementation invariant that fresh, mutation-window, and mapped
//! models produce the same pre-serialization payload over stable fixtures.

use std::fs;
use std::path::Path;

use rac_engine::derived::{build_derived_index, SCHEMA_VERSION};
use rac_engine::index_store::{corpus_content_hash, open_store, write_store};
use rac_engine::retrieve::{
    retrieve_grounding, retrieve_grounding_from_derived, retrieve_grounding_from_store,
};

struct Case {
    task: &'static str,
    scope: Option<&'static str>,
    top_k: i64,
    budget: i64,
    live_only: bool,
}

#[test]
fn fresh_snapshot_and_mapped_grounding_are_identical() {
    let fixture_root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../fixtures/retrieve");
    let matrices = [
        (
            "chain",
            &[
                Case {
                    task: "widget",
                    scope: None,
                    top_k: 5,
                    budget: 10_000,
                    live_only: true,
                },
                Case {
                    task: "widget",
                    scope: None,
                    top_k: 5,
                    budget: 10_000,
                    live_only: false,
                },
                Case {
                    task: "storage",
                    scope: Some("src/api/handlers.py"),
                    top_k: 5,
                    budget: 10_000,
                    live_only: true,
                },
                Case {
                    task: "naming",
                    scope: Some("docs/guide.md"),
                    top_k: 5,
                    budget: 10_000,
                    live_only: true,
                },
                Case {
                    task: "widget",
                    scope: None,
                    top_k: 1,
                    budget: 200,
                    live_only: true,
                },
                Case {
                    task: "frobnication pipeline",
                    scope: None,
                    top_k: 5,
                    budget: 10_000,
                    live_only: false,
                },
            ][..],
        ),
        (
            "mixed",
            &[
                Case {
                    task: "gadget sync",
                    scope: None,
                    top_k: 5,
                    budget: 10_000,
                    live_only: true,
                },
                Case {
                    task: "gadget sync",
                    scope: None,
                    top_k: 5,
                    budget: 10_000,
                    live_only: false,
                },
                Case {
                    task: "café Straße",
                    scope: None,
                    top_k: 5,
                    budget: 10_000,
                    live_only: true,
                },
                Case {
                    task: "gadget",
                    scope: None,
                    top_k: 2,
                    budget: 150,
                    live_only: true,
                },
                Case {
                    task: "crlf design",
                    scope: None,
                    top_k: 5,
                    budget: 10_000,
                    live_only: true,
                },
            ][..],
        ),
    ];

    for (directory_index, (fixture, cases)) in matrices.iter().enumerate() {
        let directory = fixture_root
            .join(fixture)
            .canonicalize()
            .expect("fixture root");
        let directory = directory.to_string_lossy();
        let derived = build_derived_index(&directory, true);
        let corpus_hash = corpus_content_hash(&directory, true);
        let cache = std::env::temp_dir().join(format!(
            "rac-grounding-model-{}-{directory_index}",
            std::process::id()
        ));
        let _ = fs::remove_dir_all(&cache);
        assert!(write_store(&cache, &corpus_hash, SCHEMA_VERSION, &derived));
        let reader = open_store(&cache, &corpus_hash, SCHEMA_VERSION).expect("grounding store");

        for case in *cases {
            let fresh = retrieve_grounding(
                &directory,
                case.task,
                case.scope,
                case.top_k,
                case.budget,
                case.live_only,
            );
            let snapshot = retrieve_grounding_from_derived(
                &directory,
                case.task,
                case.scope,
                case.top_k,
                case.budget,
                case.live_only,
                &derived,
            );
            let mapped = retrieve_grounding_from_store(
                &directory,
                case.task,
                case.scope,
                case.top_k,
                case.budget,
                case.live_only,
                &reader,
            );
            let label = format!(
                "fixture={fixture} task={:?} scope={:?}",
                case.task, case.scope
            );
            assert_eq!(snapshot, fresh, "snapshot mismatch: {label}");
            assert_eq!(mapped, fresh, "mapped mismatch: {label}");
        }
        drop(reader);
        let _ = fs::remove_dir_all(&cache);
    }
}
