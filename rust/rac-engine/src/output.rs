//! Output renderers (validate + relationships surfaces), per
//! PORT-CONTRACT.d/07: human text (code-point padding, TTY-gated ANSI),
//! `--json` via `pyjson::dumps_indent2`, and SARIF 2.1.0.

use std::io::IsTerminal;
use std::sync::OnceLock;

use serde_json::{json, Map, Value};

use crate::commands::{DirectoryValidation, StdinCorpusValidation, STATUS_INVALID};
use crate::parse::Issue;
use crate::pyjson::dumps_indent2;
use crate::relationships::{
    RelationshipIssue, RelationshipReport, RelationshipValidation, ISSUE_DUPLICATE_IDENTIFIER,
    ISSUE_EDGE_UNSUPPORTED, ISSUE_RELATIONSHIP_CYCLE, ISSUE_SCOPE_TARGET_NOT_FOUND,
    ISSUE_SELF_REFERENCE, ISSUE_TARGET_AMBIGUOUS, ISSUE_TARGET_NOT_FOUND, ISSUE_TARGET_SUPERSEDED,
    ISSUE_TARGET_TYPE_MISMATCH,
};
use crate::spec::spec_for;
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

// --- validate (single file) --------------------------------------------------

fn issue_value(i: &Issue) -> Value {
    let mut m = Map::new();
    m.insert("severity".into(), json!(i.severity));
    m.insert("code".into(), json!(i.code));
    m.insert("message".into(), json!(i.message));
    m.insert(
        "line".into(),
        match i.line {
            Some(l) => json!(l),
            None => Value::Null,
        },
    );
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
    if !errors.is_empty() {
        lines.push(red(&bold(&format!("FAIL  {file}"))));
    } else {
        lines.push(green(&bold(&format!("PASS  {file}"))));
    }

    for issue in &errors {
        lines.push(format!(
            "  {}   [{}] {}",
            red("error"),
            issue.code,
            loc(file, issue.line)
        ));
        lines.push(format!("          {}", issue.message));
    }
    for issue in &warnings {
        lines.push(format!(
            "  {} [{}] {}",
            yellow("warning"),
            issue.code,
            loc(file, issue.line)
        ));
        lines.push(format!("          {}", issue.message));
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
    if result.ok() {
        lines.push(green(&bold(&format!("PASS  {file}"))));
    } else {
        lines.push(red(&bold(&format!("FAIL  {file}"))));
    }

    for issue in &errors {
        lines.push(format!(
            "  {}   [{}] {}",
            red("error"),
            issue.code,
            loc(file, issue.line)
        ));
        lines.push(format!("          {}", issue.message));
    }
    for issue in &warnings {
        lines.push(format!(
            "  {} [{}] {}",
            yellow("warning"),
            issue.code,
            loc(file, issue.line)
        ));
        lines.push(format!("          {}", issue.message));
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
        lines.push(format!(
            "{}  ({display})",
            red(&bold(&format!("FAIL  {}", f.path)))
        ));
        for issue in &f.issues {
            if issue.severity != "error" {
                continue;
            }
            lines.push(format!(
                "  {}   [{}] {}",
                red("error"),
                issue.code,
                loc(&f.path, issue.line)
            ));
            lines.push(format!("          {}", issue.message));
        }
        lines.push(String::new());
    }

    if let Some(okf) = &result.okf {
        if !okf.findings.is_empty() {
            for finding in &okf.findings {
                lines.push(format!(
                    "{}  (OKF conformance)",
                    red(&bold(&format!("FAIL  {}", finding.path)))
                ));
                lines.push(format!(
                    "  {}   [{}] {}",
                    red("error"),
                    finding.code,
                    finding.path
                ));
                lines.push(format!("          {}", finding.message));
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
            out.push_str(&format!("%{b:02X}"));
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
    let opt = |v: &Option<String>| match v {
        Some(s) => json!(s),
        None => Value::Null,
    };
    if issue.code == ISSUE_DUPLICATE_IDENTIFIER {
        m.insert("identifier".into(), opt(&issue.identifier));
        m.insert(
            "paths".into(),
            match &issue.paths {
                Some(p) => json!(p),
                None => Value::Null,
            },
        );
        m.insert("code".into(), json!(issue.code));
    } else if issue.code == ISSUE_EDGE_UNSUPPORTED {
        m.insert("source_path".into(), opt(&issue.source_path));
        m.insert("relationship".into(), opt(&issue.relationship));
        m.insert("code".into(), json!(issue.code));
    } else if issue.code == ISSUE_RELATIONSHIP_CYCLE {
        m.insert("relationship".into(), opt(&issue.relationship));
        m.insert(
            "paths".into(),
            match &issue.paths {
                Some(p) => json!(p),
                None => Value::Null,
            },
        );
        m.insert("code".into(), json!(issue.code));
    } else {
        m.insert("source_path".into(), opt(&issue.source_path));
        m.insert("relationship".into(), opt(&issue.relationship));
        m.insert("target".into(), opt(&issue.target));
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

use crate::spec::{snake as spec_snake, ArtifactSpec};

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

use crate::pycompat::{py_format_1f, py_round};
use crate::stats::PortfolioStats;

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
            let pad = width.saturating_sub(f.name.chars().count());
            lines.push(format!("{}{}{}", f.name, " ".repeat(pad), f.requirements));
        }
    } else {
        lines.push("(none)".to_string());
    }

    let invalid = s.invalid();
    if !invalid.is_empty() {
        lines.push(String::new());
        lines.push(bold(&format!("Invalid Features ({})", invalid.len())));
        for f in &invalid {
            let reasons = if f.error_codes.is_empty() {
                "unknown".to_string()
            } else {
                f.error_codes.join(", ")
            };
            lines.push(format!("  {} \u{2014} {reasons}", red(&f.path)));
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
                let reasons = if r.error_codes.is_empty() {
                    "unknown".to_string()
                } else {
                    r.error_codes.join(", ")
                };
                lines.push(format!("  {} \u{2014} {reasons}", red(&r.path)));
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
