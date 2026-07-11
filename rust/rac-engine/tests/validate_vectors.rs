//! Oracle-vector conformance tests for `rac_engine::validate`.
//!
//! Vectors: tests/vectors/validate.json — every .md under rac/ and tests/,
//! generated from the Python oracle by rust/spec/gen_vectors_validate.py.
//! Three configurations replay byte-exactly:
//! - bare:    validate(product)
//! - github:  validate(product, ticketing_provider="github")
//! - product: validate_product(product, start=<parent>) (repo config applied)

use rac_engine::parse::{parse_file, Issue};
use rac_engine::validate::{validate, validate_product};
use serde_json::{json, Value};

const VECTORS: &str = include_str!("vectors/validate.json");

fn issue_rows(issues: &[Issue]) -> Value {
    Value::Array(
        issues
            .iter()
            .map(|i| json!([i.severity, i.code, i.message, i.line]))
            .collect(),
    )
}

fn parent(path: &str) -> String {
    match path.rfind('/') {
        Some(0) => "/".to_string(),
        Some(i) => path[..i].to_string(),
        None => ".".to_string(),
    }
}

#[test]
fn validate_matches_oracle() {
    let root: Value = serde_json::from_str(VECTORS).expect("vectors parse");
    let cases = root["cases"].as_array().expect("cases");
    assert!(!cases.is_empty());
    for case in cases {
        let path = case["path"].as_str().unwrap();
        let artifact = parse_file(path);

        assert_eq!(
            issue_rows(&validate(&artifact, None, None)),
            case["bare"],
            "{path}: bare validate"
        );
        assert_eq!(
            issue_rows(&validate(&artifact, Some("github"), None)),
            case["github"],
            "{path}: github-provider validate"
        );
        assert_eq!(
            issue_rows(&validate_product(&artifact, &parent(path))),
            case["product"],
            "{path}: validate_product"
        );
    }
}
