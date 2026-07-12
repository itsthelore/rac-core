//! Output renderers (validate + relationships surfaces), per
//! PORT-CONTRACT.d/07: human text (code-point padding, TTY-gated ANSI),
//! `--json` via `pyjson::dumps_indent2`, and SARIF 2.1.0.

use std::fmt::Write;
use std::io::IsTerminal;
use std::sync::OnceLock;

use serde_json::{json, Map, Value};

use crate::classify::{TypeScore, CONFIDENCE_THRESHOLD};
use crate::commands::{DirectoryValidation, StdinCorpusValidation, STATUS_INVALID};
use crate::diff::Diff;
use crate::export::{CorpusExport, DocumentsExport, GraphExport};
use crate::improve::ImprovementResult;
use crate::inspect::{DirectoryInspection, InspectionResult};
use crate::markdown::Requirement;
use crate::parse::Issue;
use crate::pycompat::{
    py_float_repr, py_format_1f, py_format_percent0, py_repr_str, py_round, py_rstrip,
};
use crate::coverage::{CoverageReport, GAP_UNAPPLIED, GAP_UNSCHEDULED, GAP_UNSCOPED};
use crate::portfolio::PortfolioSummary;
use crate::pyjson::{dumps_compact, dumps_indent2, dumps_indent2_no_ascii, py_float};
use crate::retrieve::{scope_lookup_value, ScopeLookupResult};
use crate::relationships::{
    RelationshipIssue, RelationshipReport, RelationshipValidation, ISSUE_DUPLICATE_IDENTIFIER,
    ISSUE_EDGE_UNSUPPORTED, ISSUE_RELATIONSHIP_CYCLE, ISSUE_SCOPE_TARGET_NOT_FOUND,
    ISSUE_SELF_REFERENCE, ISSUE_TARGET_AMBIGUOUS, ISSUE_TARGET_NOT_FOUND, ISSUE_TARGET_SUPERSEDED,
    ISSUE_TARGET_TYPE_MISMATCH,
};
use crate::resolve::{
    Evidence, Recency, ResolutionResult, ResolvedArtifact, SearchResult, OUTCOME_RESOLVED,
};
use crate::review::{ReviewIssue, ReviewReport};
use crate::spec::{snake as spec_snake, spec_for, specs, ArtifactSpec};
use crate::stats::PortfolioStats;
use crate::validate::py_title;

/// The injectable version string (PORT-CONTRACT decision 6): `RAC_RS_VERSION`
/// when set, else the spike default.
pub fn rac_version() -> String {
    std::env::var("RAC_RS_VERSION").unwrap_or_else(|_| "0.0.0-rs".to_string())
}

// --- Minimal color (auto-disabled when not writing to a TTY) ----------------

fn use_color() -> bool {
    static USE_COLOR: OnceLock<bool> = OnceLock::new();
    *USE_COLOR.get_or_init(|| std::io::stdout().is_terminal())
}

fn c(text: &str, code: &str) -> String {
    if !use_color() {
        text.to_string()
    } else {
        format!("\u{1b}[{code}m{text}\u{1b}[0m")
    }
}

fn green(t: &str) -> String {
    c(t, "32")
}

fn red(t: &str) -> String {
    c(t, "31")
}

fn yellow(t: &str) -> String {
    c(t, "33")
}

fn bold(t: &str) -> String {
    c(t, "1")
}

fn loc(file: &str, line: Option<i64>) -> String {
    match line {
        Some(l) => format!("{file}:{l}"),
        None => file.to_string(),
    }
}

/// Code-point left-justify (Python `str.ljust`).
fn ljust(s: &str, w: usize) -> String {
    let n = s.chars().count();
    if n >= w {
        s.to_string()
    } else {
        format!("{}{}", s, " ".repeat(w - n))
    }
}

/// `PASS  <file>` / `FAIL  <file>` bold header line.
fn pass_fail_header(ok: bool, file: &str) -> String {
    if ok {
        green(&bold(&format!("PASS  {file}")))
    } else {
        red(&bold(&format!("FAIL  {file}")))
    }
}

/// One issue as its two human lines: the severity line (`error` padded with
/// three trailing spaces, `warning` with one, so the `[code]` column aligns)
/// followed by the indented message line.
fn push_issue_lines(lines: &mut Vec<String>, severity: &str, code: &str, location: &str, message: &str) {
    if severity == "error" {
        lines.push(format!("  {}   [{}] {}", red("error"), code, location));
    } else {
        lines.push(format!("  {} [{}] {}", yellow("warning"), code, location));
    }
    lines.push(format!("          {message}"));
}

// --- validate (single file) --------------------------------------------------

fn issue_value(i: &Issue) -> Value {
    let mut m = Map::new();
    m.insert("severity".into(), json!(i.severity));
    m.insert("code".into(), json!(i.code));
    m.insert("message".into(), json!(i.message));
    m.insert("line".into(), json!(i.line));
    Value::Object(m)
}

pub fn render_validation_human(source_path: &str, issues: &[Issue]) -> String {
    let errors: Vec<&Issue> = issues.iter().filter(|i| i.severity == "error").collect();
    let warnings: Vec<&Issue> = issues.iter().filter(|i| i.severity == "warning").collect();
    let file = if source_path.is_empty() {
        "<input>"
    } else {
        source_path
    };

    let mut lines: Vec<String> = Vec::new();
    lines.push(pass_fail_header(errors.is_empty(), file));

    for issue in errors.iter().chain(&warnings) {
        push_issue_lines(
            &mut lines,
            issue.severity,
            &issue.code,
            &loc(file, issue.line),
            &issue.message,
        );
    }

    lines.push(String::new());
    lines.push(format!(
        "{} error(s), {} warning(s).",
        errors.len(),
        warnings.len()
    ));
    lines.join("\n")
}

pub fn render_validation_json(source_path: &str, issues: &[Issue]) -> String {
    let errors: Vec<Value> = issues
        .iter()
        .filter(|i| i.severity == "error")
        .map(issue_value)
        .collect();
    let warnings: Vec<Value> = issues
        .iter()
        .filter(|i| i.severity == "warning")
        .map(issue_value)
        .collect();
    let mut payload = Map::new();
    payload.insert("schema_version".into(), json!("1"));
    payload.insert(
        "file".into(),
        if source_path.is_empty() {
            Value::Null
        } else {
            json!(source_path)
        },
    );
    payload.insert("valid".into(), json!(errors.is_empty()));
    payload.insert("errors".into(), Value::Array(errors));
    payload.insert("warnings".into(), Value::Array(warnings));
    dumps_indent2(&Value::Object(payload))
}

// --- validate - --corpus -------------------------------------------------------

/// `related_decisions` -> `Related Decisions`.
fn relationship_label(snake_section: &str) -> String {
    py_title(&snake_section.replace('_', " "))
}

fn ref_issue_suffix(code: &str) -> &str {
    match code {
        ISSUE_TARGET_NOT_FOUND => "not found",
        ISSUE_TARGET_AMBIGUOUS => "ambiguous",
        ISSUE_SELF_REFERENCE => "self-reference",
        ISSUE_TARGET_SUPERSEDED => "superseded",
        ISSUE_TARGET_TYPE_MISMATCH => "wrong target type",
        ISSUE_SCOPE_TARGET_NOT_FOUND => "path not found",
        other => other,
    }
}

pub fn render_stdin_corpus_human(result: &StdinCorpusValidation) -> String {
    let file = if result.source_path.is_empty() {
        "<input>"
    } else {
        &result.source_path
    };
    let errors: Vec<&Issue> = result
        .structural_issues
        .iter()
        .filter(|i| i.severity == "error")
        .collect();
    let warnings: Vec<&Issue> = result
        .structural_issues
        .iter()
        .filter(|i| i.severity == "warning")
        .collect();
    let rels = &result.relationship_issues;

    let mut lines: Vec<String> = Vec::new();
    lines.push(pass_fail_header(result.ok(), file));

    for issue in errors.iter().chain(&warnings) {
        push_issue_lines(
            &mut lines,
            issue.severity,
            &issue.code,
            &loc(file, issue.line),
            &issue.message,
        );
    }

    if !rels.is_empty() {
        lines.push(String::new());
        lines.push(bold("Corpus references"));
        let mut current_section: Option<&str> = None;
        for rel in rels {
            let section = rel.relationship.as_deref();
            if section != current_section {
                current_section = section;
                lines.push(format!("  {}:", relationship_label(section.unwrap_or(""))));
            }
            let suffix = ref_issue_suffix(&rel.code);
            lines.push(red(&format!(
                "  \u{2717} {} {}",
                rel.target.as_deref().unwrap_or(""),
                suffix
            )));
        }
    }

    lines.push(String::new());
    lines.push(format!(
        "{} error(s), {} warning(s), {} corpus reference finding(s).",
        errors.len(),
        warnings.len(),
        rels.len()
    ));
    lines.join("\n")
}

pub fn render_stdin_corpus_json(result: &StdinCorpusValidation) -> String {
    let errors: Vec<Value> = result
        .structural_issues
        .iter()
        .filter(|i| i.severity == "error")
        .map(issue_value)
        .collect();
    let warnings: Vec<Value> = result
        .structural_issues
        .iter()
        .filter(|i| i.severity == "warning")
        .map(issue_value)
        .collect();
    let mut payload = Map::new();
    payload.insert("schema_version".into(), json!("1"));
    payload.insert(
        "file".into(),
        if result.source_path.is_empty() {
            Value::Null
        } else {
            json!(result.source_path)
        },
    );
    payload.insert("valid".into(), json!(result.ok()));
    payload.insert("errors".into(), Value::Array(errors));
    payload.insert("warnings".into(), Value::Array(warnings));
    payload.insert(
        "relationship_issues".into(),
        Value::Array(
            result
                .relationship_issues
                .iter()
                .map(relationship_issue_value)
                .collect(),
        ),
    );
    dumps_indent2(&Value::Object(payload))
}

// --- validate (directory) ------------------------------------------------------

pub fn render_validate_dir_human(result: &DirectoryValidation) -> String {
    let mut lines: Vec<String> = Vec::new();
    for f in &result.files {
        if f.status != STATUS_INVALID {
            continue;
        }
        let display = match spec_for(&f.artifact_type) {
            Some(spec) => spec.display.clone(),
            None => f.artifact_type.clone(),
        };
        lines.push(format!("{}  ({display})", pass_fail_header(false, &f.path)));
        for issue in &f.issues {
            if issue.severity != "error" {
                continue;
            }
            push_issue_lines(
                &mut lines,
                issue.severity,
                &issue.code,
                &loc(&f.path, issue.line),
                &issue.message,
            );
        }
        lines.push(String::new());
    }

    if let Some(okf) = &result.okf {
        if !okf.findings.is_empty() {
            for finding in &okf.findings {
                lines.push(format!(
                    "{}  (OKF conformance)",
                    pass_fail_header(false, &finding.path)
                ));
                push_issue_lines(
                    &mut lines,
                    "error",
                    &finding.code,
                    &finding.path,
                    &finding.message,
                );
                lines.push(String::new());
            }
        }
    }

    let skipped = if result.skipped() > 0 {
        format!(", {} skipped (unknown type)", result.skipped())
    } else {
        String::new()
    };
    let verdict = if result.ok() { green("PASS") } else { red("FAIL") };
    let mut summary = format!(
        "{}  {} \u{2014} {} artifact(s) checked: {} valid, {} invalid{}.",
        verdict,
        result.directory,
        result.checked(),
        result.valid(),
        result.invalid(),
        skipped
    );
    if let Some(okf) = &result.okf {
        if okf.ok() {
            summary.push_str(" OKF v0.1: conformant.");
        } else {
            summary.push_str(&format!(
                " OKF v0.1: {} conformance issue(s).",
                okf.findings.len()
            ));
        }
    }
    lines.push(summary);
    if result.checked() == 0 && result.skipped() == 0 {
        lines.push(String::new());
        lines.push("No artifacts yet \u{2014} create your first with: rac quickstart".to_string());
    }
    lines.join("\n")
}

pub fn render_validate_dir_json(result: &DirectoryValidation) -> String {
    let mut summary = Map::new();
    summary.insert("total_files".into(), json!(result.files.len()));
    summary.insert("checked".into(), json!(result.checked()));
    summary.insert("valid".into(), json!(result.valid()));
    summary.insert("invalid".into(), json!(result.invalid()));
    summary.insert("skipped_unknown".into(), json!(result.skipped()));

    let files: Vec<Value> = result
        .files
        .iter()
        .map(|f| {
            let mut m = Map::new();
            m.insert("path".into(), json!(f.path));
            m.insert("artifact_type".into(), json!(f.artifact_type));
            m.insert("status".into(), json!(f.status));
            m.insert(
                "issues".into(),
                Value::Array(f.issues.iter().map(issue_value).collect()),
            );
            Value::Object(m)
        })
        .collect();

    let mut payload = Map::new();
    payload.insert("schema_version".into(), json!("1"));
    payload.insert("directory".into(), json!(result.directory));
    payload.insert("recursive".into(), json!(result.recursive));
    payload.insert("summary".into(), Value::Object(summary));
    payload.insert("valid".into(), json!(result.ok()));
    payload.insert("files".into(), Value::Array(files));
    if let Some(okf) = &result.okf {
        let findings: Vec<Value> = okf
            .findings
            .iter()
            .map(|f| {
                let mut m = Map::new();
                m.insert("code".into(), json!(f.code));
                m.insert("path".into(), json!(f.path));
                m.insert("message".into(), json!(f.message));
                m.insert("severity".into(), json!(f.severity));
                Value::Object(m)
            })
            .collect();
        let mut o = Map::new();
        o.insert("conformant".into(), json!(okf.ok()));
        o.insert("artifacts_checked".into(), json!(okf.artifacts_checked));
        o.insert("findings".into(), Value::Array(findings));
        payload.insert("okf".into(), Value::Object(o));
    }
    dumps_indent2(&Value::Object(payload))
}

// --- SARIF ---------------------------------------------------------------------

/// `urllib.parse.quote(uri, safe="/")` — percent-encode every byte outside
/// `A-Za-z0-9_.-~/`, uppercase hex.
fn quote_uri(uri: &str) -> String {
    let mut out = String::with_capacity(uri.len());
    for b in uri.as_bytes() {
        let ch = *b as char;
        if b.is_ascii_alphanumeric() || matches!(ch, '_' | '.' | '-' | '~' | '/') {
            out.push(ch);
        } else {
            write!(out, "%{b:02X}").unwrap();
        }
    }
    out
}

fn sarif_level(severity: &str) -> &'static str {
    match severity {
        "error" => "error",
        "warning" => "warning",
        "info" => "note",
        _ => "warning",
    }
}

struct SarifResult {
    rule_id: String,
    level: &'static str,
    message: String,
    uri: String,
    line: Option<i64>,
}

fn sarif_document(mut results: Vec<SarifResult>) -> String {
    results.sort_by(|a, b| {
        a.uri
            .cmp(&b.uri)
            .then(a.line.unwrap_or(0).cmp(&b.line.unwrap_or(0)))
            .then(a.rule_id.cmp(&b.rule_id))
            .then(a.message.cmp(&b.message))
    });

    let mut rule_ids: Vec<&str> = results.iter().map(|r| r.rule_id.as_str()).collect();
    rule_ids.sort();
    rule_ids.dedup();
    let rules: Vec<Value> = rule_ids
        .iter()
        .map(|code| {
            let mut m = Map::new();
            m.insert("id".into(), json!(code));
            Value::Object(m)
        })
        .collect();

    let result_values: Vec<Value> = results
        .iter()
        .map(|r| {
            let mut artifact_location = Map::new();
            artifact_location.insert("uri".into(), json!(r.uri));
            let mut physical = Map::new();
            physical.insert("artifactLocation".into(), Value::Object(artifact_location));
            if let Some(line) = r.line {
                let mut region = Map::new();
                region.insert("startLine".into(), json!(line));
                physical.insert("region".into(), Value::Object(region));
            }
            let mut location = Map::new();
            location.insert("physicalLocation".into(), Value::Object(physical));

            let mut message = Map::new();
            message.insert("text".into(), json!(r.message));

            let mut m = Map::new();
            m.insert("ruleId".into(), json!(r.rule_id));
            m.insert("level".into(), json!(r.level));
            m.insert("message".into(), Value::Object(message));
            m.insert(
                "locations".into(),
                Value::Array(vec![Value::Object(location)]),
            );
            Value::Object(m)
        })
        .collect();

    let mut driver = Map::new();
    driver.insert("name".into(), json!("rac"));
    driver.insert(
        "informationUri".into(),
        json!("https://github.com/itsthelore/rac-core"),
    );
    driver.insert("version".into(), json!(rac_version()));
    driver.insert("rules".into(), Value::Array(rules));

    let mut tool = Map::new();
    tool.insert("driver".into(), Value::Object(driver));

    let mut run = Map::new();
    run.insert("tool".into(), Value::Object(tool));
    run.insert("results".into(), Value::Array(result_values));

    let mut document = Map::new();
    document.insert("version".into(), json!("2.1.0"));
    document.insert(
        "$schema".into(),
        json!("https://json.schemastore.org/sarif-2.1.0.json"),
    );
    document.insert("runs".into(), Value::Array(vec![Value::Object(run)]));
    dumps_indent2(&Value::Object(document))
}

pub fn render_validate_sarif(result: &DirectoryValidation) -> String {
    let mut results: Vec<SarifResult> = Vec::new();
    for file in &result.files {
        for issue in &file.issues {
            results.push(SarifResult {
                rule_id: issue.code.clone(),
                level: sarif_level(issue.severity),
                message: issue.message.clone(),
                uri: quote_uri(&file.path),
                line: issue.line,
            });
        }
    }
    if let Some(okf) = &result.okf {
        for finding in &okf.findings {
            results.push(SarifResult {
                rule_id: finding.code.clone(),
                level: sarif_level(&finding.severity),
                message: finding.message.clone(),
                uri: quote_uri(&finding.path),
                line: None,
            });
        }
    }
    sarif_document(results)
}

fn sarif_relationship_reason(code: &str) -> &str {
    match code {
        ISSUE_TARGET_NOT_FOUND => "target not found",
        ISSUE_TARGET_AMBIGUOUS => "target is ambiguous",
        ISSUE_SELF_REFERENCE => "self-reference",
        ISSUE_TARGET_SUPERSEDED => "target is superseded",
        ISSUE_TARGET_TYPE_MISMATCH => "target is the wrong artifact type",
        ISSUE_SCOPE_TARGET_NOT_FOUND => "declared path does not exist in the repository",
        other => other,
    }
}

pub fn render_relationships_sarif(validation: &RelationshipValidation) -> String {
    let results: Vec<SarifResult> = validation
        .issues
        .iter()
        .map(|issue| {
            let label = issue.relationship.as_deref().unwrap_or("").replace('_', " ");
            let (message, uri) = if issue.code == ISSUE_DUPLICATE_IDENTIFIER {
                let paths = issue.paths.clone().unwrap_or_default();
                let message = format!(
                    "Duplicate artifact identifier '{}' in: {}",
                    issue.identifier.as_deref().unwrap_or(""),
                    paths.join(", ")
                );
                let uri = paths
                    .first()
                    .cloned()
                    .unwrap_or_else(|| issue.identifier.clone().unwrap_or_default());
                (message, uri)
            } else if issue.code == ISSUE_RELATIONSHIP_CYCLE {
                let paths = issue.paths.clone().unwrap_or_default();
                (
                    format!("{label} relationship cycle: {}", paths.join(" -> ")),
                    paths.first().cloned().unwrap_or_default(),
                )
            } else if issue.code == ISSUE_EDGE_UNSUPPORTED {
                (
                    format!("{label} not supported for this artifact type"),
                    issue.source_path.clone().unwrap_or_default(),
                )
            } else {
                let reason = sarif_relationship_reason(&issue.code);
                (
                    format!(
                        "{label}: {} \u{2014} {reason}",
                        issue.target.as_deref().unwrap_or("")
                    ),
                    issue.source_path.clone().unwrap_or_default(),
                )
            };
            SarifResult {
                rule_id: issue.code.clone(),
                level: sarif_level(crate::relationships::relationship_severity(&issue.code)),
                message,
                uri: quote_uri(&uri),
                line: None,
            }
        })
        .collect();
    sarif_document(results)
}

// --- relationships (inspection, non --validate) ------------------------------

pub fn render_relationships_json(report: &RelationshipReport) -> String {
    let mut payload = Map::new();
    payload.insert("directory".into(), json!(report.directory));
    payload.insert("recursive".into(), json!(report.recursive));
    payload.insert("total_files".into(), json!(report.total_files));
    payload.insert(
        "artifacts_with_relationships".into(),
        json!(report.artifacts_with_relationships()),
    );
    payload.insert(
        "relationship_count".into(),
        json!(report.relationship_count()),
    );
    let mut counts = Map::new();
    for (section, count) in report.counts() {
        counts.insert(section, json!(count));
    }
    payload.insert("counts".into(), Value::Object(counts));
    let artifacts: Vec<Value> = report
        .artifacts
        .iter()
        .map(|artifact| {
            let mut relationships = Map::new();
            for (section, refs) in &artifact.relationships {
                relationships.insert(section.clone(), json!(refs));
            }
            let mut m = Map::new();
            m.insert("path".into(), json!(artifact.path));
            m.insert("type".into(), json!(artifact.type_name));
            m.insert("relationships".into(), Value::Object(relationships));
            Value::Object(m)
        })
        .collect();
    payload.insert("artifacts".into(), Value::Array(artifacts));
    dumps_indent2(&Value::Object(payload))
}

pub fn render_relationships_human(report: &RelationshipReport) -> String {
    let mut lines: Vec<String> = vec![
        bold("Relationships"),
        String::new(),
        format!("Files Inspected: {}", report.total_files),
        format!(
            "Artifacts With Relationships: {}",
            report.artifacts_with_relationships()
        ),
        format!("Relationships Found: {}", report.relationship_count()),
    ];

    let counts = report.counts();
    if !counts.is_empty() {
        lines.push(String::new());
        lines.push(bold("By Type:"));
        for (section, count) in &counts {
            lines.push(format!("- {}: {count}", relationship_label(section)));
        }
    }

    for artifact in &report.artifacts {
        lines.push(String::new());
        lines.push(artifact.path.clone());
        for (section, refs) in &artifact.relationships {
            lines.push(format!("  {}:", relationship_label(section)));
            for reference in refs {
                match report.labels.get(&crate::pycompat::py_casefold(reference)) {
                    Some(resolved) => lines.push(format!("  - {reference} \u{2014} {resolved}")),
                    None => lines.push(format!("  - {reference}")),
                }
            }
        }
    }

    lines.join("\n")
}

// --- relationships --validate ----------------------------------------------------

fn relationship_issue_value(issue: &RelationshipIssue) -> Value {
    let mut m = Map::new();
    if issue.code == ISSUE_DUPLICATE_IDENTIFIER {
        m.insert("identifier".into(), json!(issue.identifier));
        m.insert("paths".into(), json!(issue.paths));
        m.insert("code".into(), json!(issue.code));
    } else if issue.code == ISSUE_EDGE_UNSUPPORTED {
        m.insert("source_path".into(), json!(issue.source_path));
        m.insert("relationship".into(), json!(issue.relationship));
        m.insert("code".into(), json!(issue.code));
    } else if issue.code == ISSUE_RELATIONSHIP_CYCLE {
        m.insert("relationship".into(), json!(issue.relationship));
        m.insert("paths".into(), json!(issue.paths));
        m.insert("code".into(), json!(issue.code));
    } else {
        m.insert("source_path".into(), json!(issue.source_path));
        m.insert("relationship".into(), json!(issue.relationship));
        m.insert("target".into(), json!(issue.target));
        m.insert("code".into(), json!(issue.code));
    }
    Value::Object(m)
}

pub fn render_relationship_validation_json(report: &RelationshipValidation) -> String {
    let mut payload = Map::new();
    payload.insert("directory".into(), json!(report.directory));
    payload.insert("recursive".into(), json!(report.recursive));
    payload.insert(
        "relationships_checked".into(),
        json!(report.relationships_checked),
    );
    payload.insert("validation_issues".into(), json!(report.issues.len()));
    payload.insert(
        "issues".into(),
        Value::Array(
            report
                .issues
                .iter()
                .map(relationship_issue_value)
                .collect(),
        ),
    );
    dumps_indent2(&Value::Object(payload))
}

pub fn render_relationship_validation_human(report: &RelationshipValidation) -> String {
    let mut lines: Vec<String> = vec![
        bold("Relationship Validation"),
        String::new(),
        format!("Relationships Checked: {}", report.relationships_checked),
        format!("Validation Issues: {}", report.issues.len()),
    ];

    let duplicates: Vec<&RelationshipIssue> = report
        .issues
        .iter()
        .filter(|i| i.code == ISSUE_DUPLICATE_IDENTIFIER)
        .collect();
    let unsupported: Vec<&RelationshipIssue> = report
        .issues
        .iter()
        .filter(|i| i.code == ISSUE_EDGE_UNSUPPORTED)
        .collect();
    let cycles: Vec<&RelationshipIssue> = report
        .issues
        .iter()
        .filter(|i| i.code == ISSUE_RELATIONSHIP_CYCLE)
        .collect();
    let references: Vec<&RelationshipIssue> = report
        .issues
        .iter()
        .filter(|i| {
            i.code != ISSUE_DUPLICATE_IDENTIFIER
                && i.code != ISSUE_EDGE_UNSUPPORTED
                && i.code != ISSUE_RELATIONSHIP_CYCLE
        })
        .collect();

    if !duplicates.is_empty() {
        lines.push(String::new());
        lines.push(bold("Duplicate Identifiers"));
        for issue in &duplicates {
            let paths = issue.paths.clone().unwrap_or_default();
            lines.push(red(&format!(
                "\u{2717} {} ({} files)",
                issue.identifier.as_deref().unwrap_or(""),
                paths.len()
            )));
            for p in &paths {
                lines.push(format!("  - {p}"));
            }
        }
    }

    if !unsupported.is_empty() {
        lines.push(String::new());
        lines.push(bold("Unsupported Relationships"));
        let mut current_source: Option<&str> = None;
        for issue in &unsupported {
            let source = issue.source_path.as_deref();
            if source != current_source {
                current_source = source;
                lines.push(String::new());
                lines.push(source.unwrap_or("<input>").to_string());
            }
            let label = relationship_label(issue.relationship.as_deref().unwrap_or(""));
            lines.push(red(&format!(
                "  \u{2717} {label} not supported for this artifact type"
            )));
        }
    }

    if !cycles.is_empty() {
        lines.push(String::new());
        lines.push(bold("Relationship Cycles"));
        for issue in &cycles {
            let label = relationship_label(issue.relationship.as_deref().unwrap_or(""));
            lines.push(red(&format!("\u{2717} {label} cycle:")));
            for p in issue.paths.clone().unwrap_or_default() {
                lines.push(format!("  - {p}"));
            }
        }
    }

    if !references.is_empty() {
        lines.push(String::new());
        lines.push(bold("Broken Relationships"));
        let mut current_source: Option<&str> = None;
        let mut current_section: Option<&str> = None;
        for issue in &references {
            let source = issue.source_path.as_deref();
            if source != current_source {
                current_source = source;
                current_section = None;
                lines.push(String::new());
                lines.push(source.unwrap_or("<input>").to_string());
            }
            let section = issue.relationship.as_deref();
            if section != current_section {
                current_section = section;
                lines.push(format!("  {}:", relationship_label(section.unwrap_or(""))));
            }
            let suffix = ref_issue_suffix(&issue.code);
            lines.push(red(&format!(
                "  \u{2717} {} {}",
                issue.target.as_deref().unwrap_or(""),
                suffix
            )));
        }
    }

    lines.join("\n")
}

// --- schema / templates ------------------------------------------------------

pub fn render_schema_list_human(names: &[&str]) -> String {
    let mut lines = vec![bold("Available Schemas:")];
    for name in names {
        lines.push(format!("- {name}"));
    }
    lines.join("\n")
}

pub fn render_schema_list_json(names: &[&str]) -> String {
    let mut m = Map::new();
    m.insert(
        "schemas".into(),
        Value::Array(names.iter().map(|n| json!(n)).collect()),
    );
    dumps_indent2(&Value::Object(m))
}

pub fn render_unknown_schema(name: &str, available: &[&str]) -> String {
    let mut lines = vec![
        format!("Unknown schema: {name}"),
        String::new(),
        "Available schemas:".to_string(),
    ];
    for schema in available {
        lines.push(format!("- {schema}"));
    }
    lines.join("\n")
}

fn snake_map_value(pairs: &[(String, Vec<String>)]) -> Value {
    let mut m = Map::new();
    for (section, values) in pairs {
        m.insert(spec_snake(section), json!(values));
    }
    Value::Object(m)
}

pub fn render_schema_json(spec: &ArtifactSpec) -> String {
    let mut m = Map::new();
    m.insert("type".into(), json!(spec.name));
    m.insert(
        "required".into(),
        Value::Array(spec.required.iter().map(|s| json!(spec_snake(s))).collect()),
    );
    m.insert(
        "recommended".into(),
        Value::Array(
            spec.recommended
                .iter()
                .map(|s| json!(spec_snake(s)))
                .collect(),
        ),
    );
    m.insert(
        "optional".into(),
        Value::Array(spec.optional.iter().map(|s| json!(spec_snake(s))).collect()),
    );
    let mut descriptions = Map::new();
    for (section, desc) in &spec.descriptions {
        descriptions.insert(spec_snake(section), json!(desc));
    }
    m.insert("descriptions".into(), Value::Object(descriptions));
    m.insert("guidance".into(), snake_map_value(&spec.guidance));
    m.insert("metadata".into(), snake_map_value(&spec.metadata));
    dumps_indent2(&Value::Object(m))
}

pub fn render_schema_human(spec: &ArtifactSpec) -> String {
    let mut lines = vec![bold(&format!("Artifact Type: {}", spec.display)), String::new()];

    let mut section_block = |title: &str, names: &[String]| {
        lines.push(bold(title));
        if names.is_empty() {
            lines.push("  (none)".to_string());
            lines.push(String::new());
            return;
        }
        for name in names {
            lines.push(format!("  - {}", py_title(name)));
            if let Some((_, description)) =
                spec.descriptions.iter().find(|(k, _)| k == name)
            {
                if !description.is_empty() {
                    lines.push(format!("      Description: {description}"));
                }
            }
            if let Some((_, guidance)) = spec.guidance.iter().find(|(k, _)| k == name) {
                if !guidance.is_empty() {
                    lines.push("      Guidance:".to_string());
                    for item in guidance {
                        lines.push(format!("        - {item}"));
                    }
                }
            }
        }
        lines.push(String::new());
    };

    section_block("Required Sections:", &spec.required);
    section_block("Recommended Sections:", &spec.recommended);
    section_block("Optional Sections:", &spec.optional);

    if !spec.metadata.is_empty() {
        lines.push(bold("Metadata Fields:"));
        for (name, values) in &spec.metadata {
            lines.push(format!("  - {}: {}", py_title(name), values.join(" | ")));
        }
    }
    lines.join("\n").trim_end().to_string()
}

/// `_metadata_default(section, values)`.
fn metadata_default(section: &str, values: &[String]) -> String {
    if section == "status" && values.iter().any(|v| v == "Proposed") {
        return "Proposed".to_string();
    }
    if section == "category" && values.iter().any(|v| v == "Other") {
        return "Other".to_string();
    }
    values.first().cloned().unwrap_or_else(|| "TODO".to_string())
}

/// `_starter_body(ref, section, metadata_values)`.
fn starter_body(spec: &ArtifactSpec, section: &str, metadata_values: &[String]) -> String {
    if !metadata_values.is_empty() {
        return metadata_default(section, metadata_values);
    }
    match spec.starter_bodies.iter().find(|(k, _)| k == section) {
        Some((_, body)) if !body.is_empty() => body.clone(),
        _ => format!("TODO: describe {section}."),
    }
}

pub fn render_schema_template(spec: &ArtifactSpec) -> String {
    let mut blocks: Vec<String> = vec!["# Title".to_string()];
    // template_sections = required + recommended.
    let sections: Vec<&String> = spec.required.iter().chain(spec.recommended.iter()).collect();
    for section in sections {
        let metadata_values: &[String] = spec
            .metadata
            .iter()
            .find(|(k, _)| k == section)
            .map(|(_, v)| v.as_slice())
            .unwrap_or(&[]);
        let body = starter_body(spec, section, metadata_values);
        let mut block = format!("## {}\n\n{}", py_title(section), body);
        let mut comments: Vec<String> = Vec::new();
        if !metadata_values.is_empty() {
            comments.push(format!("Choose one: {}", metadata_values.join(" | ")));
        }
        if let Some((_, guidance)) = spec.guidance.iter().find(|(k, _)| k == section) {
            comments.extend(guidance.iter().cloned());
        }
        if !comments.is_empty() {
            let rendered: Vec<String> =
                comments.iter().map(|c| format!("<!-- {c} -->")).collect();
            block.push_str("\n\n");
            block.push_str(&rendered.join("\n"));
        }
        blocks.push(block);
    }
    format!("{}\n", blocks.join("\n\n"))
}

// --- diff --------------------------------------------------------------------

/// One titled block of single-line `+`/`-` entries (added/removed).
fn diff_list_block(blocks: &mut Vec<String>, title: &str, items: &[String], sign: char) {
    if items.is_empty() {
        return;
    }
    let color: fn(&str) -> String = if sign == '+' { green } else { red };
    let mut lines = vec![bold(title), String::new()];
    lines.extend(items.iter().map(|item| color(&format!("{sign} {item}"))));
    blocks.push(lines.join("\n"));
}

pub fn render_diff_human(d: &Diff) -> String {
    if d.is_empty() {
        return "No changes.".to_string();
    }

    let mut blocks: Vec<String> = Vec::new();

    let req_lines = |reqs: &[Requirement]| -> Vec<String> {
        reqs.iter().map(|r| format!("{} {}", r.id, r.text)).collect()
    };

    diff_list_block(
        &mut blocks,
        "Added Requirements",
        &req_lines(&d.added_requirements),
        '+',
    );
    diff_list_block(
        &mut blocks,
        "Removed Requirements",
        &req_lines(&d.removed_requirements),
        '-',
    );

    if !d.modified_requirements.is_empty() {
        let mut lines = vec![bold("Modified Requirements"), String::new()];
        for (i, c) in d.modified_requirements.iter().enumerate() {
            if i > 0 {
                lines.push(String::new());
            }
            lines.push(format!("~ {}", c.id));
            lines.push(String::new());
            lines.push("Before:".to_string());
            lines.push(red(&c.old_text));
            lines.push(String::new());
            lines.push("After:".to_string());
            lines.push(green(&c.new_text));
        }
        blocks.push(lines.join("\n"));
    }

    diff_list_block(&mut blocks, "Added Metrics", &d.added_metrics, '+');
    diff_list_block(&mut blocks, "Removed Metrics", &d.removed_metrics, '-');
    diff_list_block(&mut blocks, "Added Risks", &d.added_risks, '+');
    diff_list_block(&mut blocks, "Removed Risks", &d.removed_risks, '-');

    // Blank line between blocks.
    blocks.join("\n\n")
}

/// `asdict(Requirement)` — field order `id, text, line`.
fn requirement_value(r: &Requirement) -> Value {
    let mut m = Map::new();
    m.insert("id".into(), json!(r.id));
    m.insert("text".into(), json!(r.text));
    m.insert("line".into(), json!(r.line));
    Value::Object(m)
}

/// `render_diff_json` — fixed key order; `old`/`new` echo the raw argv paths.
pub fn render_diff_json(d: &Diff, old_path: &str, new_path: &str) -> String {
    let mut m = Map::new();
    m.insert("old".into(), json!(old_path));
    m.insert("new".into(), json!(new_path));
    m.insert(
        "added_requirements".into(),
        Value::Array(d.added_requirements.iter().map(requirement_value).collect()),
    );
    m.insert(
        "removed_requirements".into(),
        Value::Array(d.removed_requirements.iter().map(requirement_value).collect()),
    );
    m.insert(
        "modified_requirements".into(),
        Value::Array(
            d.modified_requirements
                .iter()
                .map(|c| {
                    let mut cm = Map::new();
                    cm.insert("id".into(), json!(c.id));
                    cm.insert("old_text".into(), json!(c.old_text));
                    cm.insert("new_text".into(), json!(c.new_text));
                    Value::Object(cm)
                })
                .collect(),
        ),
    );
    m.insert("added_metrics".into(), json!(d.added_metrics));
    m.insert("removed_metrics".into(), json!(d.removed_metrics));
    m.insert("added_risks".into(), json!(d.added_risks));
    m.insert("removed_risks".into(), json!(d.removed_risks));
    dumps_indent2(&Value::Object(m))
}

// --- inspect -----------------------------------------------------------------

/// Add a Relationships block when the artifact declares related artifacts.
fn append_relationships(lines: &mut Vec<String>, result: &InspectionResult) {
    if result.relationships.is_empty() {
        return;
    }
    lines.push(String::new());
    lines.push(bold("Relationships:"));
    for (section, refs) in &result.relationships {
        lines.push(format!("  {}:", relationship_label(section)));
        for r in refs {
            lines.push(format!("    - {r}"));
        }
    }
}

/// Add Status / Category / Supersedes lines when a decision declares them.
fn append_decision_metadata(lines: &mut Vec<String>, result: &InspectionResult) {
    let pairs = [
        ("Status", result.status.as_deref()),
        ("Category", result.category.as_deref()),
        ("Supersedes", result.supersedes.as_deref()),
    ];
    // `if value` — truthy filter, so an empty string is dropped too.
    let shown: Vec<(&str, &str)> = pairs
        .iter()
        .filter_map(|(label, value)| value.filter(|v| !v.is_empty()).map(|v| (*label, v)))
        .collect();
    if !shown.is_empty() {
        lines.push(String::new());
        lines.push(bold("Decision Metadata:"));
        for (label, value) in shown {
            lines.push(format!("  {label}: {value}"));
        }
    }
}

pub fn render_inspect_human(result: &InspectionResult) -> String {
    let mut lines = vec![
        bold(&format!(
            "Artifact Type: {}",
            py_title(&result.artifact_type)
        )),
        format!("Confidence: {}", py_format_percent0(result.confidence)),
        String::new(),
        bold("Present Sections:"),
    ];
    if result.present_sections.is_empty() {
        lines.push("  (none)".to_string());
    } else {
        for s in &result.present_sections {
            lines.push(green(&format!("  \u{2713} {}", py_title(s))));
        }
    }
    if !result.missing_sections.is_empty() {
        lines.push(String::new());
        lines.push(bold("Missing Sections:"));
        for s in &result.missing_sections {
            lines.push(red(&format!("  \u{2717} {}", py_title(s))));
        }
    }
    append_decision_metadata(&mut lines, result);
    append_relationships(&mut lines, result);
    lines.join("\n")
}

/// Python `f"{x:g}"` for the score arithmetic operands. `points`/`ceiling`
/// are small multiples of 0.5 (bounded by section counts), so the general
/// format never reaches scientific notation: integral values drop the
/// decimal, halves render as `n.5`.
fn format_g(x: f64) -> String {
    if x.fract() == 0.0 {
        format!("{}", x as i64)
    } else {
        py_float_repr(x)
    }
}

/// Explainable single-file output: matches, misses, and the score math.
pub fn render_inspect_verbose(result: &InspectionResult, scores: &[TypeScore]) -> String {
    // The TypeScore matching the chosen type, or scores[0] for Unknown.
    let chosen = scores
        .iter()
        .find(|s| s.name == result.artifact_type)
        .or_else(|| scores.first());

    let mut lines = vec![
        bold(&format!(
            "Artifact Type: {}",
            py_title(&result.artifact_type)
        )),
        format!("Confidence: {}", py_format_percent0(result.confidence)),
    ];
    let Some(chosen) = chosen else {
        return lines.join("\n");
    };
    if result.artifact_type == "unknown" {
        let display = spec_for(&chosen.name)
            .map(|s| s.display.clone())
            .unwrap_or_else(|| py_title(&chosen.name));
        lines.push(format!("Closest match: {display}"));
    }

    let block = |title: &str, names: &[String], lines: &mut Vec<String>| {
        lines.push(String::new());
        lines.push(bold(title));
        if names.is_empty() {
            lines.push("  (none)".to_string());
        } else {
            for s in names {
                lines.push(green(&format!("  \u{2713} {}", py_title(s))));
            }
        }
    };

    block("Required Matches:", &chosen.matched_required, &mut lines);
    block("Recommended Matches:", &chosen.matched_recommended, &mut lines);
    if !chosen.missing.is_empty() {
        lines.push(String::new());
        lines.push(bold("Missing:"));
        for s in &chosen.missing {
            lines.push(red(&format!("  \u{2717} {}", py_title(s))));
        }
    }

    let req = chosen.matched_required.len();
    let rec = chosen.matched_recommended.len();
    lines.push(String::new());
    lines.push(format!(
        "{} {req} + 0.5 \u{d7} {rec} = {} / {} = {}",
        bold("Score:"),
        format_g(chosen.points),
        format_g(chosen.ceiling),
        py_float_repr(py_round(chosen.fit, 2))
    ));
    if result.artifact_type == "unknown" {
        lines.push(format!(
            "(below the {} threshold \u{2192} Unknown)",
            py_format_percent0(CONFIDENCE_THRESHOLD)
        ));
    }
    lines.join("\n")
}

pub fn render_dir_inspect_human(d: &DirectoryInspection) -> String {
    let counts = d.counts();
    let count_of = |name: &str| -> usize {
        counts
            .iter()
            .find(|(n, _)| *n == name)
            .map(|(_, c)| *c)
            .unwrap_or(0)
    };
    let mut lines = vec![
        bold(&format!("Files Inspected: {}", d.total_files())),
        String::new(),
    ];
    for spec in specs() {
        lines.push(format!("{}s: {}", spec.display, count_of(&spec.name)));
    }
    lines.push(format!("Unknown: {}", count_of("unknown")));
    lines.join("\n")
}

/// `InspectionResult.to_dict()` — additive-friendly: decision metadata and
/// `relationships` appear only when present.
pub fn render_inspect_json(result: &InspectionResult) -> String {
    let mut m = Map::new();
    m.insert("type".into(), json!(result.artifact_type));
    m.insert("confidence".into(), py_float(result.confidence));
    m.insert(
        "present_sections".into(),
        Value::Array(
            result
                .present_sections
                .iter()
                .map(|s| json!(spec_snake(s)))
                .collect(),
        ),
    );
    m.insert(
        "missing_sections".into(),
        Value::Array(
            result
                .missing_sections
                .iter()
                .map(|s| json!(spec_snake(s)))
                .collect(),
        ),
    );
    // `if value is not None` — an empty string IS emitted here (unlike human).
    for (key, value) in [
        ("status", &result.status),
        ("category", &result.category),
        ("supersedes", &result.supersedes),
    ] {
        if let Some(v) = value {
            m.insert(key.into(), json!(v));
        }
    }
    if !result.relationships.is_empty() {
        let mut rel = Map::new();
        for (section, refs) in &result.relationships {
            rel.insert(section.clone(), json!(refs));
        }
        m.insert("relationships".into(), Value::Object(rel));
    }
    dumps_indent2(&Value::Object(m))
}

pub fn render_dir_inspect_json(d: &DirectoryInspection) -> String {
    let mut counts = Map::new();
    for (name, count) in d.counts() {
        counts.insert(name.to_string(), json!(count));
    }
    let mut summary = Map::new();
    summary.insert("total_files".into(), json!(d.total_files()));
    summary.insert("counts".into(), Value::Object(counts));
    summary.insert("unknown".into(), json!(d.unknown_count()));
    let mut m = Map::new();
    m.insert("schema_version".into(), json!("1"));
    m.insert("directory".into(), json!(d.directory));
    m.insert("recursive".into(), json!(d.recursive));
    m.insert("summary".into(), Value::Object(summary));
    m.insert(
        "files".into(),
        Value::Array(
            d.files
                .iter()
                .map(|f| {
                    let mut fm = Map::new();
                    fm.insert("path".into(), json!(f.path));
                    fm.insert("type".into(), json!(f.artifact_type));
                    fm.insert("confidence".into(), py_float(f.confidence));
                    Value::Object(fm)
                })
                .collect(),
        ),
    );
    dumps_indent2(&Value::Object(m))
}

// --- improve -----------------------------------------------------------------

/// Shown when guidance cannot be produced (`_UNKNOWN_MESSAGE`).
const UNKNOWN_MESSAGE: &str =
    "Unable to generate improvement guidance.\nArtifact type could not be determined.";

/// `_unsupported_message(result)` — a known but unsupported artifact type.
/// Unreachable today (all five specs support improve); ported for fidelity.
fn unsupported_message(result: &ImprovementResult) -> String {
    format!(
        "Artifact Type: {}\n\nImprovement guidance is not currently available for this artifact type.",
        py_title(&result.artifact_type)
    )
}

pub fn render_improve_human(result: &ImprovementResult) -> String {
    if result.artifact_type == "unknown" {
        return UNKNOWN_MESSAGE.to_string();
    }
    if !result.supported {
        return unsupported_message(result);
    }

    let mut lines = vec![
        bold(&format!(
            "Artifact Type: {}",
            py_title(&result.artifact_type)
        )),
        String::new(),
    ];
    if result.missing_required.is_empty() && result.missing_recommended.is_empty() {
        lines.push("Nothing to improve \u{2014} all expected sections present.".to_string());
        return lines.join("\n");
    }

    let block = |title: &str, names: &[String], lines: &mut Vec<String>| {
        lines.push(bold(title));
        if names.is_empty() {
            lines.push("  (none)".to_string());
        } else {
            for s in names {
                lines.push(format!("  - {}", py_title(s)));
                if let Some((_, questions)) = result.guidance.iter().find(|(k, _)| k == s) {
                    for q in questions {
                        lines.push(format!("      \u{2022} {q}"));
                    }
                }
            }
        }
        lines.push(String::new());
    };

    block("Missing Required:", &result.missing_required, &mut lines);
    block("Missing Recommended:", &result.missing_recommended, &mut lines);
    py_rstrip(&lines.join("\n")).to_string()
}

/// `ImprovementResult.to_dict()` — `{type, missing_required,
/// missing_recommended, guidance}`, sections snake_cased.
pub fn render_improve_json(result: &ImprovementResult) -> String {
    let mut m = Map::new();
    m.insert("type".into(), json!(result.artifact_type));
    m.insert(
        "missing_required".into(),
        Value::Array(
            result
                .missing_required
                .iter()
                .map(|s| json!(spec_snake(s)))
                .collect(),
        ),
    );
    m.insert(
        "missing_recommended".into(),
        Value::Array(
            result
                .missing_recommended
                .iter()
                .map(|s| json!(spec_snake(s)))
                .collect(),
        ),
    );
    m.insert("guidance".into(), snake_map_value(&result.guidance));
    dumps_indent2(&Value::Object(m))
}

/// Markdown templates for the missing sections (required first).
pub fn render_improve_template(result: &ImprovementResult) -> String {
    if result.artifact_type == "unknown" {
        return UNKNOWN_MESSAGE.to_string();
    }
    if !result.supported {
        return unsupported_message(result);
    }

    let missing: Vec<&String> = result
        .missing_required
        .iter()
        .chain(result.missing_recommended.iter())
        .collect();
    if missing.is_empty() {
        return "# Nothing to add \u{2014} all expected sections present.".to_string();
    }

    let mut blocks: Vec<String> = Vec::new();
    for section in missing {
        let mut block = format!("## {}\n\n_TODO_", py_title(section));
        if let Some((_, questions)) = result.guidance.iter().find(|(k, _)| k == section) {
            if !questions.is_empty() {
                let rendered: Vec<String> =
                    questions.iter().map(|q| format!("<!-- {q} -->")).collect();
                block.push_str("\n\n");
                block.push_str(&rendered.join("\n"));
            }
        }
        blocks.push(block);
    }
    format!("{}\n", blocks.join("\n\n"))
}

pub fn render_templates_human(names: &[&str]) -> String {
    let mut lines = vec![bold("Available artifact templates:"), String::new()];
    for name in names {
        lines.push(format!("- {name}"));
    }
    lines.join("\n")
}

pub fn render_templates_json(names: &[&str]) -> String {
    let mut m = Map::new();
    m.insert("schema_version".into(), json!("1"));
    m.insert(
        "templates".into(),
        Value::Array(names.iter().map(|n| json!(n)).collect()),
    );
    dumps_indent2(&Value::Object(m))
}

// --- stats -------------------------------------------------------------------

const EMPTY_CORPUS_HINT: &str = "No artifacts yet — create your first with: rac quickstart";

fn invalid_files_json(items: &[(&str, &[String])]) -> Value {
    Value::Array(
        items
            .iter()
            .map(|(path, codes)| {
                let mut m = Map::new();
                m.insert("file".into(), json!(path));
                m.insert("errors".into(), json!(codes));
                Value::Object(m)
            })
            .collect(),
    )
}

pub fn render_stats_json(s: &PortfolioStats) -> String {
    let mut payload = Map::new();
    payload.insert("directory".into(), json!(s.directory));
    payload.insert("empty".into(), json!(s.is_empty()));
    payload.insert("features".into(), json!(s.files_found()));
    payload.insert("valid_features".into(), json!(s.valid_features()));
    payload.insert("invalid_features".into(), json!(s.invalid_features()));
    payload.insert("requirements".into(), json!(s.total_requirements()));
    payload.insert("metrics".into(), json!(s.total_metrics()));
    payload.insert("risks".into(), json!(s.total_risks()));
    payload.insert(
        "features_missing_metrics".into(),
        json!(s.missing_metrics().len()),
    );
    payload.insert(
        "features_missing_risks".into(),
        json!(s.missing_risks().len()),
    );
    payload.insert("missing_metrics".into(), json!(s.missing_metrics()));
    payload.insert("missing_risks".into(), json!(s.missing_risks()));
    payload.insert(
        "average_requirements_per_feature".into(),
        crate::pyjson::py_float(py_round(s.average_requirements(), 1)),
    );
    payload.insert(
        "largest_feature".into(),
        match s.largest_feature() {
            Some(f) => {
                let mut m = Map::new();
                m.insert("name".into(), json!(f.name));
                m.insert("requirements".into(), json!(f.requirements));
                Value::Object(m)
            }
            None => Value::Null,
        },
    );
    payload.insert(
        "requirements_by_feature".into(),
        Value::Array(
            s.requirements_by_feature()
                .iter()
                .map(|f| {
                    let mut m = Map::new();
                    m.insert("name".into(), json!(f.name));
                    m.insert("requirements".into(), json!(f.requirements));
                    Value::Object(m)
                })
                .collect(),
        ),
    );
    let invalid: Vec<(&str, &[String])> = s
        .invalid()
        .iter()
        .map(|f| (f.path.as_str(), f.error_codes.as_slice()))
        .collect();
    payload.insert("invalid".into(), invalid_files_json(&invalid));

    if !s.decisions.is_empty() {
        let mut m = Map::new();
        m.insert("count".into(), json!(s.decision_count()));
        let mut by_status = Map::new();
        for (k, c) in s.decision_status_counts() {
            by_status.insert(k, json!(c));
        }
        m.insert("by_status".into(), Value::Object(by_status));
        let mut by_category = Map::new();
        for (k, c) in s.decision_category_counts() {
            by_category.insert(k, json!(c));
        }
        m.insert("by_category".into(), Value::Object(by_category));
        payload.insert("decisions".into(), Value::Object(m));
    }

    let mut family = |key: &str, count: usize, valid: usize, invalid: Vec<(&str, &[String])>| {
        let mut m = Map::new();
        m.insert("count".into(), json!(count));
        m.insert("valid".into(), json!(valid));
        m.insert("invalid".into(), invalid_files_json(&invalid));
        payload.insert(key.into(), Value::Object(m));
    };

    if !s.roadmaps.is_empty() {
        let invalid: Vec<(&str, &[String])> = s
            .invalid_roadmaps()
            .iter()
            .map(|r| (r.path.as_str(), r.error_codes.as_slice()))
            .collect();
        family("roadmaps", s.roadmap_count(), s.valid_roadmaps(), invalid);
    }
    if !s.prompts.is_empty() {
        let invalid: Vec<(&str, &[String])> = s
            .invalid_prompts()
            .iter()
            .map(|p| (p.path.as_str(), p.error_codes.as_slice()))
            .collect();
        family("prompts", s.prompt_count(), s.valid_prompts(), invalid);
    }
    if !s.designs.is_empty() {
        let invalid: Vec<(&str, &[String])> = s
            .invalid_designs()
            .iter()
            .map(|d| (d.path.as_str(), d.error_codes.as_slice()))
            .collect();
        family("designs", s.design_count(), s.valid_designs(), invalid);
    }

    if !s.unrecognized.is_empty() {
        let mut m = Map::new();
        m.insert("count".into(), json!(s.unrecognized_count()));
        m.insert(
            "files".into(),
            Value::Array(
                s.unrecognized
                    .iter()
                    .map(|u| {
                        let mut fm = Map::new();
                        fm.insert("file".into(), json!(u.path));
                        fm.insert("name".into(), json!(u.name));
                        fm.insert("confidence".into(), crate::pyjson::py_float(py_round(u.confidence, 2)));
                        Value::Object(fm)
                    })
                    .collect(),
            ),
        );
        payload.insert("unrecognized".into(), Value::Object(m));
    }

    if !s.relationship_counts.is_empty() {
        let mut m = Map::new();
        for (section, count) in &s.relationship_counts {
            m.insert(crate::spec::snake(section), json!(count));
        }
        payload.insert("relationships".into(), Value::Object(m));
    }

    dumps_indent2(&Value::Object(payload))
}

/// `  <red path> — <error codes | "unknown">` invalid-list line.
fn invalid_reason_line(path: &str, error_codes: &[String]) -> String {
    let reasons = if error_codes.is_empty() {
        "unknown".to_string()
    } else {
        error_codes.join(", ")
    };
    format!("  {} \u{2014} {reasons}", red(path))
}

pub fn render_stats_human(s: &PortfolioStats) -> String {
    let mut lines: Vec<String> = vec![
        bold("Portfolio Overview"),
        "==================".to_string(),
        String::new(),
        format!("Features: {}", s.files_found()),
        format!("Requirements: {}", s.total_requirements()),
        format!("Metrics: {}", s.total_metrics()),
        format!("Risks: {}", s.total_risks()),
        String::new(),
        bold("Quality"),
        "=======".to_string(),
        String::new(),
    ];

    let mut missing_block = |label: &str, names: &[&str]| {
        lines.push(format!("{label}: {}", names.len()));
        for name in names {
            lines.push(format!("  - {name}"));
        }
    };
    missing_block("Features Missing Metrics", &s.missing_metrics());
    missing_block("Features Missing Risks", &s.missing_risks());
    lines.push(format!(
        "Average Requirements Per Feature: {}",
        py_format_1f(s.average_requirements())
    ));

    match s.largest_feature() {
        Some(f) => lines.push(format!(
            "Largest Feature: {} ({} requirements)",
            f.name, f.requirements
        )),
        None => lines.push("Largest Feature: (none)".to_string()),
    }

    lines.push(String::new());
    lines.push(bold("Requirements by Feature"));
    lines.push("=======================".to_string());
    lines.push(String::new());
    let by_feature = s.requirements_by_feature();
    if !by_feature.is_empty() {
        let width = by_feature.iter().map(|f| f.name.chars().count()).max().unwrap_or(0) + 4;
        for f in &by_feature {
            lines.push(format!("{}{}", ljust(&f.name, width), f.requirements));
        }
    } else {
        lines.push("(none)".to_string());
    }

    let invalid = s.invalid();
    if !invalid.is_empty() {
        lines.push(String::new());
        lines.push(bold(&format!("Invalid Features ({})", invalid.len())));
        for f in &invalid {
            lines.push(invalid_reason_line(&f.path, &f.error_codes));
        }
    }

    if !s.decisions.is_empty() {
        lines.push(String::new());
        lines.push(bold("Decisions"));
        lines.push("=========".to_string());
        lines.push(String::new());
        lines.push(format!("Total: {}", s.decision_count()));
        let mut breakdown = |label: &str, counts: &[(String, usize)]| {
            lines.push(String::new());
            lines.push(bold(label));
            if counts.is_empty() {
                lines.push("  (none recorded)".to_string());
            } else {
                for (name, count) in counts {
                    lines.push(format!("  - {name}: {count}"));
                }
            }
        };
        breakdown("Status", &s.decision_status_counts());
        breakdown("Category", &s.decision_category_counts());
    }

    let mut family = |label: &str, underline: &str, count: usize, valid: usize, invalid_label: &str, invalid: &[&crate::stats::ValidityStat]| {
        lines.push(String::new());
        lines.push(bold(label));
        lines.push(underline.to_string());
        lines.push(String::new());
        lines.push(format!("Total: {count}"));
        lines.push(format!("Valid: {valid}"));
        if !invalid.is_empty() {
            lines.push(String::new());
            lines.push(bold(&format!("{invalid_label} ({})", invalid.len())));
            for r in invalid {
                lines.push(invalid_reason_line(&r.path, &r.error_codes));
            }
        }
    };

    if !s.roadmaps.is_empty() {
        family("Roadmaps", "========", s.roadmap_count(), s.valid_roadmaps(), "Invalid Roadmaps", &s.invalid_roadmaps());
    }
    if !s.prompts.is_empty() {
        family("Prompts", "=======", s.prompt_count(), s.valid_prompts(), "Invalid Prompts", &s.invalid_prompts());
    }
    if !s.designs.is_empty() {
        family("Designs", "=======", s.design_count(), s.valid_designs(), "Invalid Designs", &s.invalid_designs());
    }

    if !s.unrecognized.is_empty() {
        let count = s.unrecognized_count();
        let noun = if count == 1 { "document" } else { "documents" };
        lines.push(String::new());
        lines.push(bold("Unrecognized"));
        lines.push("============".to_string());
        lines.push(String::new());
        lines.push(format!(
            "{count} {noun} matched no known artifact schema (not errors — see ADR-010):"
        ));
        for u in &s.unrecognized {
            lines.push(format!("  {}", u.path));
        }
    }

    if !s.relationship_counts.is_empty() {
        lines.push(String::new());
        lines.push(bold("Relationships"));
        lines.push("=============".to_string());
        lines.push(String::new());
        for (section, count) in &s.relationship_counts {
            lines.push(format!("Artifacts with {}: {count}", py_title(section)));
        }
    }

    if s.is_empty() {
        lines.push(String::new());
        lines.push(EMPTY_CORPUS_HINT.to_string());
    }

    lines.join("\n")
}

// --- portfolio ---------------------------------------------------------------

/// Human `rac portfolio` output (`render_portfolio_human`).
pub fn render_portfolio_human(s: &PortfolioSummary) -> String {
    let mut lines: Vec<String> = vec![
        bold("Repository Summary"),
        "==================".to_string(),
        String::new(),
        format!("Directory:  {}", s.directory),
        format!("Artifacts:  {}", s.total_artifacts()),
        String::new(),
        bold("By Type"),
        "-------".to_string(),
        String::new(),
    ];
    for (type_name, count) in &s.by_type {
        if *count > 0 {
            lines.push(format!("  {:<14} {count}", py_title(type_name)));
        }
    }

    lines.extend([
        String::new(),
        bold("Validation"),
        "----------".to_string(),
        String::new(),
        format!("  Valid:    {}", s.valid_artifacts),
        format!("  Invalid:  {}", s.invalid_artifacts),
        String::new(),
        bold("Completeness"),
        "------------".to_string(),
        String::new(),
        format!(
            "  {} ({} / {} recommended slots filled)",
            py_format_percent0(s.completeness()),
            s.filled_slots,
            s.recommended_slots
        ),
        String::new(),
        bold("Relationships"),
        "-------------".to_string(),
        String::new(),
        format!("  Total:    {}", s.relationships.total),
        format!("  Valid:    {}", s.relationships.valid),
        format!("  Broken:   {}", s.relationships.broken),
        format!("  Orphaned: {}", s.relationships.orphaned),
        format!("  Coverage: {}", py_format_percent0(s.relationships.coverage)),
    ]);

    if !s.attention.is_empty() {
        lines.extend([
            String::new(),
            bold(&format!("Attention ({} items)", s.attention.len())),
            "----------".to_string(),
            String::new(),
        ]);
        for item in &s.attention {
            let icon = if item.severity == "error" {
                red("\u{2717}")
            } else {
                yellow("!")
            };
            lines.push(format!("  {icon} {}", item.identifier));
            lines.push(format!("      {}", item.message));
        }
    } else {
        lines.push(String::new());
        lines.push(green("\u{2713} No attention items."));
    }

    let score = s.health_score();
    let colored = if score >= 80 {
        green(&score.to_string())
    } else if score >= 60 {
        yellow(&score.to_string())
    } else {
        red(&score.to_string())
    };
    lines.extend([
        String::new(),
        bold("Health Score"),
        "------------".to_string(),
        String::new(),
        format!("  {colored} / 100"),
    ]);

    if s.total_artifacts() == 0 {
        lines.push(String::new());
        lines.push(EMPTY_CORPUS_HINT.to_string());
    }

    lines.join("\n")
}

/// JSON `rac portfolio` output — `PortfolioSummary.to_dict()` (ADR-007).
pub fn render_portfolio_json(s: &PortfolioSummary) -> String {
    let mut payload = Map::new();
    payload.insert("schema_version".into(), json!("1"));
    payload.insert("directory".into(), json!(s.directory));
    payload.insert("recursive".into(), json!(s.recursive));
    payload.insert("empty".into(), json!(s.total_artifacts() == 0));

    let mut by_type = Map::new();
    for (t, c) in &s.by_type {
        by_type.insert(t.clone(), json!(c));
    }
    let mut artifacts = Map::new();
    artifacts.insert("total".into(), json!(s.total_artifacts()));
    artifacts.insert("by_type".into(), Value::Object(by_type));
    artifacts.insert("unknown_paths".into(), json!(s.unknown_paths));
    payload.insert("artifacts".into(), Value::Object(artifacts));

    let mut validation = Map::new();
    validation.insert("valid".into(), json!(s.valid_artifacts));
    validation.insert("invalid".into(), json!(s.invalid_artifacts));
    payload.insert("validation".into(), Value::Object(validation));

    let mut completeness = Map::new();
    completeness.insert("recommended_slots".into(), json!(s.recommended_slots));
    completeness.insert("filled".into(), json!(s.filled_slots));
    completeness.insert("ratio".into(), py_float(s.completeness()));
    payload.insert("completeness".into(), Value::Object(completeness));

    let mut relationships = Map::new();
    relationships.insert("total".into(), json!(s.relationships.total));
    relationships.insert("valid".into(), json!(s.relationships.valid));
    relationships.insert("broken".into(), json!(s.relationships.broken));
    relationships.insert("orphaned".into(), json!(s.relationships.orphaned));
    relationships.insert("coverage".into(), py_float(s.relationships.coverage));
    payload.insert("relationships".into(), Value::Object(relationships));

    let attention: Vec<Value> = s
        .attention
        .iter()
        .map(|item| {
            let mut m = Map::new();
            m.insert("path".into(), json!(item.path));
            m.insert("identifier".into(), json!(item.identifier));
            m.insert("severity".into(), json!(item.severity));
            m.insert("code".into(), json!(item.code));
            m.insert("message".into(), json!(item.message));
            Value::Object(m)
        })
        .collect();
    payload.insert("attention".into(), Value::Array(attention));

    let mut health = Map::new();
    health.insert("score".into(), json!(s.health_score()));
    payload.insert("health".into(), Value::Object(health));

    let mut validation_status = Map::new();
    validation_status.insert("artifacts_ok".into(), json!(s.invalid_artifacts == 0));
    validation_status.insert("relationships_ok".into(), json!(s.relationships_ok));
    validation_status.insert(
        "ok".into(),
        json!(s.invalid_artifacts == 0 && s.relationships_ok),
    );
    payload.insert("validation_status".into(), Value::Object(validation_status));

    dumps_indent2(&Value::Object(payload))
}

// --- coverage ----------------------------------------------------------------

/// Human `rac coverage` output (`render_coverage_human`).
pub fn render_coverage_human(report: &CoverageReport) -> String {
    let (unscheduled, unapplied, unscoped) = report.counts();
    let mut lines: Vec<String> = vec![
        format!("Traceability coverage \u{2014} {}", report.directory),
        String::new(),
    ];
    if report.gaps.is_empty() {
        lines.push(
            "\u{2713} No coverage gaps \u{2014} every artifact has its expected traceability edge."
                .to_string(),
        );
        return lines.join("\n");
    }
    let headings = [
        (
            GAP_UNSCHEDULED,
            "Unscheduled requirements (no roadmap schedules them)",
        ),
        (
            GAP_UNAPPLIED,
            "Unapplied decisions (no requirement or roadmap applies them)",
        ),
        (GAP_UNSCOPED, "Unscoped roadmaps (reference no requirement)"),
    ];
    for (gap_class, heading) in headings {
        let members: Vec<_> = report.gaps.iter().filter(|g| g.gap == gap_class).collect();
        if members.is_empty() {
            continue;
        }
        lines.push(format!("{heading}: {}", members.len()));
        for gap in members {
            lines.push(format!("  {}  {}", gap.id, gap.path));
        }
        lines.push(String::new());
    }
    let total = report.gaps.len();
    lines.push(format!(
        "{total} coverage gap{} ({unscheduled} unscheduled, {unapplied} unapplied, \
{unscoped} unscoped) \u{2014} advisory, not a build failure.",
        if total != 1 { "s" } else { "" }
    ));
    lines.join("\n")
}

/// JSON `rac coverage` output — `json.dumps(report.to_dict(), indent=2,
/// ensure_ascii=False)`.
pub fn render_coverage_json(report: &CoverageReport) -> String {
    let (unscheduled, unapplied, unscoped) = report.counts();
    let mut payload = Map::new();
    payload.insert("schema_version".into(), json!("1"));
    payload.insert("directory".into(), json!(report.directory));
    let gaps: Vec<Value> = report
        .gaps
        .iter()
        .map(|g| {
            let mut m = Map::new();
            m.insert("path".into(), json!(g.path));
            m.insert("id".into(), json!(g.id));
            m.insert("type".into(), json!(g.artifact_type));
            m.insert("gap".into(), json!(g.gap));
            m.insert("missing".into(), json!(g.missing));
            Value::Object(m)
        })
        .collect();
    payload.insert("gaps".into(), Value::Array(gaps));
    let mut summary = Map::new();
    summary.insert("unscheduled".into(), json!(unscheduled));
    summary.insert("unapplied".into(), json!(unapplied));
    summary.insert("unscoped".into(), json!(unscoped));
    summary.insert("total".into(), json!(report.gaps.len()));
    payload.insert("summary".into(), Value::Object(summary));
    dumps_indent2_no_ascii(&Value::Object(payload))
}

// --- decisions-for -----------------------------------------------------------

/// Human `rac decisions-for` output: aligned `id  status  title` rows with the
/// matching declared `## Applies To` entry under each, or a valid empty result.
pub fn render_decisions_for_human(result: &ScopeLookupResult) -> String {
    if result.decisions.is_empty() {
        if !result.in_repository {
            return format!(
                "{} is outside the repository \u{2014} no governing decisions.",
                py_repr_str(&result.query)
            );
        }
        return format!(
            "No decisions declare scope over {}.",
            py_repr_str(&result.query)
        );
    }
    let dash = "\u{2014}";
    let id_w = result
        .decisions
        .iter()
        .map(|d| d.id.chars().count())
        .max()
        .unwrap_or(0);
    let status_w = result
        .decisions
        .iter()
        .map(|d| {
            if d.status.is_empty() {
                dash.chars().count()
            } else {
                d.status.chars().count()
            }
        })
        .max()
        .unwrap_or(0);
    let indent = format!("{}  {}  ", " ".repeat(id_w), " ".repeat(status_w));
    let mut lines: Vec<String> = Vec::new();
    for d in &result.decisions {
        let status = if d.status.is_empty() { dash } else { &d.status };
        let title = if d.title.is_empty() { dash } else { &d.title };
        lines.push(format!(
            "{}  {}  {title}",
            ljust(&d.id, id_w),
            ljust(status, status_w)
        ));
        lines.push(format!("{indent}\u{21b3} applies to: {}", d.matching_entry));
    }
    lines.push(String::new());
    lines.push(format!(
        "{} decision(s) govern {}.",
        result.decisions.len(),
        py_repr_str(&result.query)
    ));
    lines.join("\n")
}

/// JSON `rac decisions-for` output — the same `ScopeLookupResult` payload the
/// MCP `find_decisions` path argument serializes (ADR-031).
pub fn render_decisions_for_json(result: &ScopeLookupResult) -> String {
    dumps_indent2(&scope_lookup_value(result))
}

// --- review ------------------------------------------------------------------

fn priority_label(priority: i64) -> &'static str {
    match priority {
        1 => "Invalid artifacts",
        2 => "Broken relationships",
        3 => "Unrecognized artifacts",
        4 => "Missing recommended information",
        5 => "Write cadence",
        6 => "Possible drift (review recommended)",
        _ => "",
    }
}

fn review_issue_value(i: &ReviewIssue) -> Value {
    let mut m = Map::new();
    m.insert("priority".into(), json!(i.priority));
    m.insert("severity".into(), json!(i.severity));
    m.insert("path".into(), json!(i.path));
    m.insert("identifier".into(), json!(i.identifier));
    m.insert("code".into(), json!(i.code));
    m.insert("message".into(), json!(i.message));
    m.insert("action".into(), json!(i.action));
    m.insert("impact".into(), json!(i.impact));
    Value::Object(m)
}

pub fn render_review_json(r: &ReviewReport) -> String {
    let p = &r.portfolio;
    let mut payload = Map::new();
    payload.insert("schema_version".into(), json!("1"));
    payload.insert("directory".into(), json!(r.directory));
    payload.insert("recursive".into(), json!(r.recursive));
    payload.insert("ok".into(), json!(r.ok()));
    payload.insert("empty".into(), json!(p.total_artifacts() == 0));

    let mut by_type = Map::new();
    for (t, c) in &p.by_type {
        by_type.insert(t.clone(), json!(c));
    }
    let mut artifacts = Map::new();
    artifacts.insert("total".into(), json!(p.total_artifacts()));
    artifacts.insert("by_type".into(), Value::Object(by_type));
    artifacts.insert("unknown_paths".into(), json!(p.unknown_paths));
    payload.insert("artifacts".into(), Value::Object(artifacts));

    let mut validation = Map::new();
    validation.insert("valid".into(), json!(p.valid_artifacts));
    validation.insert("invalid".into(), json!(p.invalid_artifacts));
    payload.insert("validation".into(), Value::Object(validation));

    let mut relationships = Map::new();
    relationships.insert("total".into(), json!(p.relationships.total));
    relationships.insert("valid".into(), json!(p.relationships.valid));
    relationships.insert("broken".into(), json!(p.relationships.broken));
    relationships.insert("orphaned".into(), json!(p.relationships.orphaned));
    relationships.insert("coverage".into(), py_float(p.relationships.coverage));
    payload.insert("relationships".into(), Value::Object(relationships));

    let mut health = Map::new();
    health.insert("score".into(), json!(p.health_score()));
    payload.insert("health".into(), Value::Object(health));

    payload.insert(
        "issues".into(),
        Value::Array(r.issues.iter().map(review_issue_value).collect()),
    );
    payload.insert("actions".into(), json!(r.actions()));
    dumps_indent2(&Value::Object(payload))
}

pub fn render_review_human(r: &ReviewReport) -> String {
    let p = &r.portfolio;
    let mut lines: Vec<String> = vec![
        bold("Repository Review"),
        "=================".to_string(),
        String::new(),
        format!("Directory:  {}", r.directory),
        format!("Artifacts:  {}", p.total_artifacts()),
        String::new(),
    ];
    for (type_name, count) in &p.by_type {
        if *count > 0 {
            lines.push(format!("  {:<14} {count}", py_title(type_name)));
        }
    }

    lines.extend([
        String::new(),
        bold("Validation"),
        "----------".to_string(),
        String::new(),
        format!("  Valid:    {}", p.valid_artifacts),
        format!("  Invalid:  {}", p.invalid_artifacts),
        String::new(),
        bold("Relationships"),
        "-------------".to_string(),
        String::new(),
        format!("  Total:    {}", p.relationships.total),
        format!("  Valid:    {}", p.relationships.valid),
        format!("  Broken:   {}", p.relationships.broken),
    ]);

    if !r.issues.is_empty() {
        lines.extend([
            String::new(),
            bold(&format!("Issues ({})", r.issues.len())),
            "------".to_string(),
        ]);
        for priority in 1..=6 {
            let group: Vec<&ReviewIssue> =
                r.issues.iter().filter(|i| i.priority == priority).collect();
            if group.is_empty() {
                continue;
            }
            lines.push(String::new());
            lines.push(format!(
                "  Priority {priority} \u{2014} {}:",
                priority_label(priority)
            ));
            for issue in group {
                let icon = match issue.severity.as_str() {
                    "error" => red("\u{2717}"),
                    "warning" => yellow("!"),
                    _ => "\u{00b7}".to_string(),
                };
                lines.push(format!("    {icon} {}", issue.identifier));
                lines.push(format!("        {}", issue.message));
            }
        }
        lines.extend([
            String::new(),
            bold("Suggested Actions"),
            "-----------------".to_string(),
            String::new(),
        ]);
        for (n, action) in r.actions().iter().enumerate() {
            lines.push(format!("  {}. {action}", n + 1));
        }
    } else {
        lines.push(String::new());
        lines.push(green("\u{2713} Nothing needs attention."));
    }

    let score = p.health_score();
    let colored = if score >= 80 {
        green(&score.to_string())
    } else if score >= 60 {
        yellow(&score.to_string())
    } else {
        red(&score.to_string())
    };
    lines.extend([
        String::new(),
        bold("Health Score"),
        "------------".to_string(),
        String::new(),
        format!("  {colored} / 100"),
    ]);
    if p.total_artifacts() == 0 {
        lines.push(String::new());
        lines.push(EMPTY_CORPUS_HINT.to_string());
    }
    lines.join("\n")
}

pub fn render_review_sarif(r: &ReviewReport) -> String {
    let results: Vec<SarifResult> = r
        .issues
        .iter()
        .map(|issue| SarifResult {
            rule_id: issue.code.clone(),
            level: sarif_level(&issue.severity),
            message: if issue.action.is_empty() {
                issue.message.clone()
            } else {
                format!("{} \u{2014} {}", issue.message, issue.action)
            },
            uri: quote_uri(&issue.path),
            line: None,
        })
        .collect();
    sarif_document(results)
}

// --- export ------------------------------------------------------------------

pub fn render_export_json(export: &CorpusExport) -> String {
    let mut corpus = Map::new();
    corpus.insert("name".into(), json!(export.corpus_name));
    corpus.insert("rac_version".into(), json!(export.rac_version));
    corpus.insert("artifact_count".into(), json!(export.artifact_count()));

    let artifacts: Vec<Value> = export
        .artifacts
        .iter()
        .map(|a| {
            let mut m = Map::new();
            m.insert("id".into(), json!(a.id));
            m.insert("aliases".into(), json!(a.aliases));
            m.insert("type".into(), json!(a.artifact_type));
            m.insert("status".into(), json!(a.status));
            m.insert("title".into(), json!(a.title));
            m.insert("path".into(), json!(a.path));
            m.insert("body_html".into(), json!(a.body_html));
            Value::Object(m)
        })
        .collect();

    let relationships: Vec<Value> = export
        .relationships
        .iter()
        .map(|e| {
            let mut m = Map::new();
            m.insert("from".into(), json!(e.from));
            m.insert("to".into(), json!(e.to));
            m.insert("type".into(), json!(e.edge_type));
            Value::Object(m)
        })
        .collect();

    let mut payload = Map::new();
    payload.insert("schema_version".into(), json!("1"));
    payload.insert("corpus".into(), Value::Object(corpus));
    payload.insert("artifacts".into(), Value::Array(artifacts));
    payload.insert("relationships".into(), Value::Array(relationships));
    dumps_indent2(&Value::Object(payload))
}

pub fn render_documents_jsonl(export: &DocumentsExport) -> String {
    export
        .documents
        .iter()
        .map(|d| {
            let mut meta = Map::new();
            meta.insert("path".into(), json!(d.path));
            meta.insert("aliases".into(), json!(d.aliases));
            meta.insert("tags".into(), json!(d.tags));
            meta.insert("source".into(), json!(export.corpus_name));
            let mut m = Map::new();
            m.insert("schema_version".into(), json!("1"));
            m.insert("id".into(), json!(d.id));
            m.insert("type".into(), json!(d.artifact_type));
            m.insert("status".into(), json!(d.status));
            m.insert("title".into(), json!(d.title));
            m.insert("text".into(), json!(d.text));
            m.insert("metadata".into(), Value::Object(meta));
            dumps_compact(&Value::Object(m))
        })
        .collect::<Vec<_>>()
        .join("\n")
}

pub fn render_graph_json(export: &GraphExport) -> String {
    let nodes: Vec<Value> = export
        .nodes
        .iter()
        .map(|n| {
            let mut m = Map::new();
            m.insert("id".into(), json!(n.id));
            m.insert("type".into(), json!(n.artifact_type));
            m.insert("status".into(), json!(n.status));
            m.insert("title".into(), json!(n.title));
            Value::Object(m)
        })
        .collect();
    let edges: Vec<Value> = export
        .edges
        .iter()
        .map(|e| {
            let mut m = Map::new();
            m.insert("source".into(), json!(e.source));
            m.insert("target".into(), json!(e.target));
            m.insert("type".into(), json!(e.edge_type));
            m.insert("directed".into(), json!(e.directed));
            m.insert("resolved".into(), json!(e.resolved));
            m.insert("external".into(), json!(e.external));
            m.insert("provider".into(), json!(e.provider));
            Value::Object(m)
        })
        .collect();
    let mut payload = Map::new();
    payload.insert("schema_version".into(), json!("1"));
    payload.insert("source".into(), json!(export.corpus_name));
    payload.insert("nodes".into(), Value::Array(nodes));
    payload.insert("edges".into(), Value::Array(edges));
    dumps_indent2(&Value::Object(payload))
}

// --- resolve / find (PORT-CONTRACT.d/06 §3.1, §11–13) -------------------------

/// `render_resolve_human`: the resolved-artifact card. Missing title renders
/// `—` (U+2014); the id is bold only on a tty.
pub fn render_resolve_human(artifact: &ResolvedArtifact) -> String {
    format!(
        "{}\n\nType: {}\nTitle: {}\nPath: {}",
        bold(&artifact.id),
        artifact.artifact_type,
        artifact.title.as_deref().filter(|t| !t.is_empty()).unwrap_or("\u{2014}"),
        artifact.path
    )
}

/// `ResolutionResult.to_dict()` for the failure outcomes — the `rac resolve
/// --json` error body, also served as the MCP structured lookup error
/// (`errors.from_resolution`, ADR-034).
pub fn resolution_error_value(result: &ResolutionResult) -> Value {
    let mut m = Map::new();
    m.insert("schema_version".into(), json!("1"));
    m.insert("error".into(), json!(result.outcome));
    m.insert("id".into(), json!(result.artifact_id)); // as given, unstripped
    if !result.duplicate_paths.is_empty() {
        m.insert("paths".into(), json!(result.duplicate_paths));
    }
    Value::Object(m)
}

/// `render_resolve_json` — `ResolutionResult.to_dict()` with `indent=2`.
pub fn render_resolve_json(result: &ResolutionResult) -> String {
    if result.outcome != OUTCOME_RESOLVED {
        return dumps_indent2(&resolution_error_value(result));
    }
    let artifact = result.artifact.as_ref().expect("resolved implies artifact");
    let mut m = Map::new();
    m.insert("schema_version".into(), json!("1"));
    m.insert("id".into(), json!(artifact.id));
    m.insert("type".into(), json!(artifact.artifact_type));
    m.insert("title".into(), json!(artifact.title));
    m.insert("path".into(), json!(artifact.path));
    // section/snippet/evidence/recency/tags are never set on the
    // resolution path — the keys stay absent.
    dumps_indent2(&Value::Object(m))
}

/// The match `recency` dict: `{last_committed, age_days, stale}`, all three
/// keys always present, each null when unknown.
pub fn recency_value(recency: &Recency) -> Value {
    let mut m = Map::new();
    m.insert("last_committed".into(), json!(recency.last_committed));
    m.insert("age_days".into(), json!(recency.age_days));
    m.insert("stale".into(), json!(recency.stale));
    Value::Object(m)
}

/// The search-match `evidence` dict exactly as `rac find --json --explain`
/// serializes it: `{field, terms, tier, score, components:{bm25,
/// lexical_rank, graph_rank, inbound}}`.
pub fn evidence_value(e: &Evidence) -> Value {
    let mut ev = Map::new();
    ev.insert("field".into(), json!(e.field));
    ev.insert("terms".into(), json!(e.terms));
    ev.insert("tier".into(), json!(e.tier));
    ev.insert("score".into(), py_float(e.score));
    let mut components = Map::new();
    components.insert("bm25".into(), py_float(e.bm25));
    components.insert("lexical_rank".into(), json!(e.lexical_rank));
    components.insert("graph_rank".into(), json!(e.graph_rank));
    components.insert("inbound".into(), json!(e.inbound));
    ev.insert("components".into(), Value::Object(components));
    Value::Object(ev)
}

/// `ResolvedArtifact.to_dict(include_evidence=…)` — the search-match /
/// resolved-artifact dict in pinned key order (`id, type, title, path,
/// [section], [snippet], [evidence], [recency], [tags]`); conditional keys
/// are absent, never null (except `title`). Shared by the CLI `rac find`
/// renderers and the MCP tool payloads.
pub fn find_match_value(m: &ResolvedArtifact, include_evidence: bool) -> Value {
    let mut obj = Map::new();
    obj.insert("id".into(), json!(m.id));
    obj.insert("type".into(), json!(m.artifact_type));
    obj.insert("title".into(), json!(m.title));
    obj.insert("path".into(), json!(m.path));
    if let Some(section) = &m.section {
        obj.insert("section".into(), json!(section));
    }
    if let Some(snippet) = &m.snippet {
        obj.insert("snippet".into(), json!(snippet));
    }
    if include_evidence {
        if let Some(e) = &m.evidence {
            obj.insert("evidence".into(), evidence_value(e));
        }
    }
    if let Some(recency) = &m.recency {
        obj.insert("recency".into(), recency_value(recency));
    }
    if !m.tags.is_empty() {
        obj.insert("tags".into(), json!(m.tags));
    }
    Value::Object(obj)
}

/// `render_retrieve_human(payload)` — the human `rac retrieve` block
/// (ADR-113), rendered from the budget-shaped payload (post-truncation), so
/// the human view reflects exactly what the JSON face carries.
pub fn render_retrieve_human(payload: &Value) -> String {
    let empty: Vec<Value> = Vec::new();
    let items = payload
        .get("items")
        .and_then(Value::as_array)
        .unwrap_or(&empty);
    let task = payload.get("task").and_then(Value::as_str).unwrap_or("");
    if items.is_empty() {
        return format!("No grounding for {}.", py_repr_str(task));
    }
    // `i.get("status") or "—"` / `i.get("title") or "—"` — falsy ⇒ em dash.
    let disp = |item: &Value, key: &str| -> String {
        match item.get(key).and_then(Value::as_str) {
            Some(s) if !s.is_empty() => s.to_string(),
            _ => "\u{2014}".to_string(),
        }
    };
    let id_of = |item: &Value| item["id"].as_str().unwrap_or("").to_string();
    let id_w = items
        .iter()
        .map(|i| id_of(i).chars().count())
        .max()
        .unwrap_or(0);
    let status_w = items
        .iter()
        .map(|i| disp(i, "status").chars().count())
        .max()
        .unwrap_or(0);
    let indent = format!("{}  {}  ", " ".repeat(id_w), " ".repeat(status_w));
    let mut lines: Vec<String> = Vec::new();
    for item in items {
        lines.push(format!(
            "{}  {}  {}",
            ljust(&id_of(item), id_w),
            ljust(&disp(item, "status"), status_w),
            disp(item, "title"),
        ));
        let empty_map = Map::new();
        let provenance = item
            .get("provenance")
            .and_then(Value::as_object)
            .unwrap_or(&empty_map);
        let via = provenance
            .get("channels")
            .and_then(Value::as_array)
            .map(|cs| {
                cs.iter()
                    .filter_map(Value::as_str)
                    .collect::<Vec<_>>()
                    .join("+")
            })
            .unwrap_or_default();
        let detail = if let Some(entry) = provenance.get("matching_entry") {
            format!(" [applies to: {}]", entry.as_str().unwrap_or(""))
        } else if let Some(evidence) = provenance.get("evidence") {
            let field = evidence["field"].as_str().unwrap_or("");
            let terms = evidence["terms"]
                .as_array()
                .map(|ts| {
                    ts.iter()
                        .filter_map(Value::as_str)
                        .collect::<Vec<_>>()
                        .join(",")
                })
                .unwrap_or_default();
            format!(" [field={field} terms={terms}]")
        } else {
            String::new()
        };
        lines.push(format!("{indent}\u{21b3} via: {via}{detail}"));
        if let Some(replaced) = provenance.get("superseded").and_then(Value::as_array) {
            for r in replaced {
                lines.push(format!("{indent}  replaces: {}", r.as_str().unwrap_or("")));
            }
        }
    }
    lines.push(String::new());
    let mut summary = format!("{} item(s) for {}.", items.len(), py_repr_str(task));
    if payload
        .get("truncated")
        .and_then(Value::as_bool)
        .unwrap_or(false)
    {
        let omitted = payload.get("omitted").and_then(Value::as_i64).unwrap_or(0);
        summary.push_str(&format!(" (truncated; {omitted} item(s) omitted)"));
    }
    lines.push(summary);
    lines.join("\n")
}

/// `SearchResult.to_dict(include_evidence=…)` — `{schema_version, query,
/// type, match_count, matches}`. Shared by `render_find_json` (which wraps
/// it in `indent=2` dumps) and the MCP search payloads (budget serializer).
pub fn search_result_value(result: &SearchResult, include_evidence: bool) -> Value {
    let mut m = Map::new();
    m.insert("schema_version".into(), json!("1"));
    m.insert("query".into(), json!(result.query));
    m.insert("type".into(), json!(result.artifact_type));
    m.insert("match_count".into(), json!(result.matches.len()));
    m.insert(
        "matches".into(),
        Value::Array(
            result
                .matches
                .iter()
                .map(|mm| find_match_value(mm, include_evidence))
                .collect(),
        ),
    );
    Value::Object(m)
}

/// `render_find_json` — `SearchResult.to_dict(include_evidence=explain)`.
pub fn render_find_json(result: &SearchResult, explain: bool) -> String {
    dumps_indent2(&search_result_value(result, explain))
}

/// `render_find_human` — aligned match rows, or a valid empty result
/// (PORT-CONTRACT.d/06 §13). `{query!r}` is Python string repr.
pub fn render_find_human(result: &SearchResult, explain: bool) -> String {
    if result.matches.is_empty() {
        return format!("No artifacts match {}.", py_repr_str(&result.query));
    }
    let id_w = result
        .matches
        .iter()
        .map(|m| m.id.chars().count())
        .max()
        .unwrap_or(0);
    let type_w = result
        .matches
        .iter()
        .map(|m| m.artifact_type.chars().count())
        .max()
        .unwrap_or(0);
    let indent = format!("{}  {}  ", " ".repeat(id_w), " ".repeat(type_w));
    let mut lines: Vec<String> = Vec::new();
    for m in &result.matches {
        let mut row = format!(
            "{}  {}  {}",
            ljust(&m.id, id_w),
            ljust(&m.artifact_type, type_w),
            m.title.as_deref().filter(|t| !t.is_empty()).unwrap_or("\u{2014}")
        );
        if let Some(recency) = &m.recency {
            if recency.stale == Some(true) {
                let marker = match recency.age_days {
                    Some(age) => format!("  \u{26a0} stale ({age}d)"),
                    None => "  \u{26a0} stale".to_string(),
                };
                row.push_str(&yellow(&marker));
            }
        }
        lines.push(row);
        if let Some(snippet) = &m.snippet {
            let section = match m.section.as_deref() {
                Some(s) if !s.is_empty() => format!("{s}: "),
                _ => String::new(),
            };
            lines.push(format!("{indent}\u{21b3} {section}{snippet}"));
        }
        if explain {
            if let Some(e) = &m.evidence {
                let mut attribution =
                    format!("field={} terms={}", e.field, e.terms.join(","));
                if let Some(snippet) = &m.snippet {
                    let where_ = match m.section.as_deref() {
                        Some(s) if !s.is_empty() => format!("{s}: "),
                        _ => String::new(),
                    };
                    attribution.push_str(&format!(" [{where_}{snippet}]"));
                }
                lines.push(format!("{indent}\u{2022} {attribution}"));
                lines.push(format!(
                    "{indent}  score={} bm25={} lexical_rank={} graph_rank={} inbound={}",
                    py_float_repr(e.score),
                    py_float_repr(e.bm25),
                    e.lexical_rank,
                    e.graph_rank,
                    e.inbound
                ));
            }
        }
    }
    lines.push(String::new());
    lines.push(format!(
        "{} match(es) for {}.",
        result.matches.len(),
        py_repr_str(&result.query)
    ));
    lines.join("\n")
}
