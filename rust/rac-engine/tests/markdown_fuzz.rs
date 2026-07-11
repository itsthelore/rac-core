//! Optional differential-fuzz replay for `rac_engine::markdown` (phase-3
//! hook). Generate cases with rust/spec/fuzz_vectors_markdown.py, which
//! writes tests/vectors/markdown_fuzz.json (not committed); this test
//! replays the file when present and passes trivially when absent.

use rac_engine::markdown::{
    consumed_events, parse_with_cap, split_frontmatter, Product, DEFAULT_MAX_FILE_BYTES,
};
use serde_json::{json, Value};

fn product_value(p: &Product) -> Value {
    json!({
        "title": p.title,
        "extra_title_lines": p.extra_title_lines,
        "problem": p.problem,
        "requirements": p.requirements.iter()
            .map(|r| json!([r.id, r.text, r.line]))
            .collect::<Vec<_>>(),
        "malformed_requirements": p.malformed_requirements.iter()
            .map(|m| json!([m.raw, m.line, m.bad_id, m.empty_text]))
            .collect::<Vec<_>>(),
        "success_metrics": p.success_metrics,
        "risks": p.risks,
        "sections": p.sections.iter()
            .map(|(k, v)| json!([k, v]))
            .collect::<Vec<_>>(),
        "search_sections": p.search_sections.iter()
            .map(|s| json!([s.heading, s.lines]))
            .collect::<Vec<_>>(),
        "has": [
            p.has_problem_section,
            p.has_requirements_section,
            p.has_metrics_section,
            p.has_risks_section,
        ],
        "source_path": p.source_path,
        "frontmatter_raw": p.frontmatter_raw,
        "metadata_issues": p.metadata_issues.iter()
            .map(|i| json!([i.severity, i.code, i.message, i.line]))
            .collect::<Vec<_>>(),
        "parse_issues": p.parse_issues.iter()
            .map(|i| json!([i.severity, i.code, i.message, i.line]))
            .collect::<Vec<_>>(),
    })
}

fn events_value(body: &str) -> Value {
    Value::Array(
        consumed_events(body)
            .into_iter()
            .map(|e| json!([if e.heading { "h" } else { "b" }, e.tag, e.line, e.content]))
            .collect(),
    )
}

#[test]
fn fuzz_vectors_match_oracle_when_present() {
    let path = format!(
        "{}/tests/vectors/markdown_fuzz.json",
        env!("CARGO_MANIFEST_DIR")
    );
    let text = match std::fs::read_to_string(&path) {
        Ok(t) => t,
        Err(_) => {
            eprintln!("markdown_fuzz.json absent; skipping fuzz replay");
            return;
        }
    };
    let v: Value = serde_json::from_str(&text).expect("fuzz vector file parses");
    let cases = v["cases"].as_array().expect("cases present");
    let mut failures = 0usize;
    for case in cases {
        let name = case["name"].as_str().unwrap();
        let doc = case["text"].as_str().unwrap();
        let split = split_frontmatter(doc);
        let got_split = json!({
            "raw": split.raw,
            "line_offset": split.line_offset,
            "unterminated": split.unterminated,
        });
        if got_split != case["split"] {
            failures += 1;
            eprintln!("case {name}: split mismatch for text {doc:?}");
            continue;
        }
        let got_events = events_value(&split.body);
        if got_events != case["events"] {
            failures += 1;
            eprintln!(
                "case {name}: events mismatch for text {doc:?}\n  rust:   {got_events}\n  oracle: {}",
                case["events"]
            );
            continue;
        }
        let product = parse_with_cap(doc, "", DEFAULT_MAX_FILE_BYTES);
        let got = product_value(&product);
        if got != case["product"] {
            failures += 1;
            eprintln!(
                "case {name}: product mismatch for text {doc:?}\n  rust:   {got}\n  oracle: {}",
                case["product"]
            );
        }
    }
    assert_eq!(failures, 0, "{failures} fuzz case(s) diverged");
}
