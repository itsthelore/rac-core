//! BM25F/RRF search conformance: replay `resolve.json` (oracle-generated over
//! the live `rac/` corpus) and assert EXACT f64 bit equality on the unrounded
//! `bm25` and `fused` scores, plus ranks, evidence, snippets, and final
//! ordering (PORT-CONTRACT.d/06 §7–9: the float operation order is normative;
//! a 1-ulp divergence must fail here, not round away).
//!
//! REGENERABLE — any change to `rac/` shifts the vectors; rerun
//! `.venv-oracle/bin/python rust/spec/gen_vectors_resolve.py`.

use std::fs;
use std::path::Path;

use rac_engine::resolve::{build_index, find_decisions, search_index, stats_for, IndexEntry};
use serde_json::Value;

fn vectors() -> Value {
    let path = Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/vectors/resolve.json");
    let text = fs::read_to_string(&path).expect("read resolve.json");
    serde_json::from_str(&text).expect("parse resolve.json")
}

/// The corpus paths in the vectors are relative to the repo root; run the
/// whole suite from there (one test fn, so no cwd races between threads).
fn enter_repo_root() {
    let root = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .expect("canonicalize repo root");
    std::env::set_current_dir(&root).expect("chdir to repo root");
}

fn opt_str(v: &Value) -> Option<&str> {
    if v.is_null() {
        None
    } else {
        Some(v.as_str().expect("string or null"))
    }
}

#[test]
fn bm25f_rrf_bits_match_oracle() {
    enter_repo_root();
    let data = vectors();
    let directory = data["directory"].as_str().unwrap();
    let entries: Vec<IndexEntry> = build_index(directory, true);
    assert_eq!(
        entries.len() as i64,
        data["entry_count"].as_i64().unwrap(),
        "index size diverged — regenerate the vectors after corpus changes"
    );

    for case in data["cases"].as_array().unwrap() {
        let query = case["query"].as_str().unwrap();
        let artifact_type = opt_str(&case["type"]);
        let tags: Vec<String> = case["tags"]
            .as_array()
            .unwrap()
            .iter()
            .map(|t| t.as_str().unwrap().to_string())
            .collect();
        let decisions = case["decisions"].as_bool().unwrap();
        let label = format!("query {query:?} type {artifact_type:?} tags {tags:?} decisions {decisions}");

        // Corpus-global statistics (filter-independent, contract §6).
        let stats = stats_for(&entries, query);
        assert_eq!(stats.n, case["n"].as_i64().unwrap(), "{label}: n");
        for (term, want) in case["df"].as_object().unwrap() {
            assert_eq!(
                stats.df.get(term.as_str()).copied().unwrap_or(0),
                want.as_i64().unwrap(),
                "{label}: df[{term}]"
            );
        }
        const FIELD_ORDER: [&str; 6] = ["id", "title", "path", "heading", "body", "tags"];
        for (i, name) in FIELD_ORDER.iter().enumerate() {
            let want = case["avglen_bits"][*name].as_u64().unwrap();
            assert_eq!(
                stats.avglen[i].to_bits(),
                want,
                "{label}: avglen[{name}] bits"
            );
        }

        let result = if decisions {
            find_decisions(directory, query, true)
        } else {
            search_index(&entries, query, artifact_type, &tags)
        };

        let want_matches = case["matches"].as_array().unwrap();
        assert_eq!(
            result.matches.len(),
            case["match_count"].as_u64().unwrap() as usize,
            "{label}: match count"
        );

        for (got, want) in result.matches.iter().zip(want_matches) {
            let path = want["path"].as_str().unwrap();
            assert_eq!(got.path, path, "{label}: match order");
            assert_eq!(got.id, want["id"].as_str().unwrap(), "{label}: {path}: id");
            assert_eq!(
                got.artifact_type,
                want["type"].as_str().unwrap(),
                "{label}: {path}: type"
            );
            assert_eq!(
                got.section.as_deref(),
                opt_str(&want["section"]),
                "{label}: {path}: section"
            );
            assert_eq!(
                got.snippet.as_deref(),
                opt_str(&want["snippet"]),
                "{label}: {path}: snippet"
            );

            let ev = got.evidence.as_ref().expect("search match has evidence");
            assert_eq!(ev.field, want["field"].as_str().unwrap(), "{label}: {path}: field");
            assert_eq!(ev.tier, want["tier"].as_i64().unwrap(), "{label}: {path}: tier");
            let want_terms: Vec<&str> = want["terms"]
                .as_array()
                .unwrap()
                .iter()
                .map(|t| t.as_str().unwrap())
                .collect();
            let got_terms: Vec<&str> = ev.terms.iter().map(String::as_str).collect();
            assert_eq!(got_terms, want_terms, "{label}: {path}: terms");
            assert_eq!(
                ev.lexical_rank,
                want["lexical_rank"].as_i64().unwrap(),
                "{label}: {path}: lexical_rank"
            );
            assert_eq!(
                ev.graph_rank,
                want["graph_rank"].as_i64().unwrap(),
                "{label}: {path}: graph_rank"
            );
            assert_eq!(
                ev.inbound,
                want["inbound"].as_i64().unwrap(),
                "{label}: {path}: inbound"
            );

            // The landmine assertions: exact f64 bit equality on the
            // UNROUNDED scores.
            assert_eq!(
                ev.bm25_raw.to_bits(),
                want["bm25_bits"].as_u64().unwrap(),
                "{label}: {path}: bm25 bits (got {:e})",
                ev.bm25_raw
            );
            assert_eq!(
                ev.fused_raw.to_bits(),
                want["fused_bits"].as_u64().unwrap(),
                "{label}: {path}: fused bits (got {:e})",
                ev.fused_raw
            );
        }
    }
}
