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
    RelationshipIssue, RelationshipValidation, ISSUE_DUPLICATE_IDENTIFIER, ISSUE_EDGE_UNSUPPORTED,
    ISSUE_RELATIONSHIP_CYCLE, ISSUE_SCOPE_TARGET_NOT_FOUND, ISSUE_SELF_REFERENCE,
    ISSUE_TARGET_AMBIGUOUS, ISSUE_TARGET_NOT_FOUND, ISSUE_TARGET_SUPERSEDED,
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
