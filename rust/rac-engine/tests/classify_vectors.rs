//! Oracle-vector conformance tests for `rac_engine::classify`.
//!
//! Vectors: tests/vectors/classify.json — every .md under rac/ and tests/,
//! generated from the Python oracle by rust/spec/gen_vectors_classify.py.
//! The full score breakdown (matched/missing lists, points/ceiling/fit as
//! Python repr strings) and the chosen classification must replay exactly.

use rac_engine::classify::{classify, score_artifacts};
use rac_engine::parse::parse_file;
use rac_engine::pycompat::py_float_repr;
use serde_json::Value;

const VECTORS: &str = include_str!("vectors/classify.json");

fn strs(v: &Value) -> Vec<String> {
    v.as_array()
        .unwrap()
        .iter()
        .map(|s| s.as_str().unwrap().to_string())
        .collect()
}

#[test]
fn classify_matches_oracle() {
    let root: Value = serde_json::from_str(VECTORS).expect("vectors parse");
    let cases = root["cases"].as_array().expect("cases");
    assert!(!cases.is_empty());
    for case in cases {
        let path = case["path"].as_str().unwrap();
        let artifact = parse_file(path);

        let scores = score_artifacts(&artifact);
        let expected_scores = case["scores"].as_array().unwrap();
        assert_eq!(scores.len(), expected_scores.len(), "{path}: score count");
        for (got, want) in scores.iter().zip(expected_scores) {
            assert_eq!(got.name, want["name"].as_str().unwrap(), "{path}: order");
            assert_eq!(
                got.matched_required,
                strs(&want["matched_required"]),
                "{path}: {} matched_required",
                got.name
            );
            assert_eq!(
                got.matched_recommended,
                strs(&want["matched_recommended"]),
                "{path}: {} matched_recommended",
                got.name
            );
            assert_eq!(
                got.missing,
                strs(&want["missing"]),
                "{path}: {} missing",
                got.name
            );
            assert_eq!(
                py_float_repr(got.points),
                want["points_repr"].as_str().unwrap(),
                "{path}: {} points",
                got.name
            );
            assert_eq!(
                py_float_repr(got.ceiling),
                want["ceiling_repr"].as_str().unwrap(),
                "{path}: {} ceiling",
                got.name
            );
            assert_eq!(
                py_float_repr(got.fit),
                want["fit_repr"].as_str().unwrap(),
                "{path}: {} fit",
                got.name
            );
        }

        let c = classify(&artifact);
        assert_eq!(c.artifact_type, case["type"].as_str().unwrap(), "{path}: type");
        assert_eq!(
            py_float_repr(c.confidence),
            case["confidence_repr"].as_str().unwrap(),
            "{path}: confidence"
        );
        assert_eq!(
            c.present_sections,
            strs(&case["present_sections"]),
            "{path}: present"
        );
        assert_eq!(
            c.missing_sections,
            strs(&case["missing_sections"]),
            "{path}: missing"
        );
    }
}
