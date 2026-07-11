//! Command orchestration (`rac.cli.cmd_validate` / `cmd_relationships` and
//! the `rac.services.validate` composition layer): walk -> parse -> classify
//! -> validate -> render. Sequential; output is order-deterministic.

use std::path::Path;

use crate::classify::classify;
use crate::output;
use crate::parse::{parse_file, parse_text, Artifact, Issue};
use crate::relationships::{
    corpus_items, validate_document_against_corpus, validate_relationships,
    validate_relationships_file, RelationshipIssue,
};
use crate::validate::{
    apply_overrides, check_okf_conformance, has_errors, load_overrides, load_ticketing_provider,
    validate, validate_product, OkfConformanceReport, OkfEntry,
};
use crate::walk::normalize_root;

pub const EXIT_OK: i32 = 0;
pub const EXIT_VALIDATION_FAILED: i32 = 1;
pub const EXIT_USAGE: i32 = 2;

// Stable per-file statuses (JSON contract).
pub const STATUS_VALID: &str = "valid";
pub const STATUS_INVALID: &str = "invalid";
pub const STATUS_SKIPPED: &str = "skipped";

fn usage_error(message: &str) -> i32 {
    eprintln!("rac: {message}");
    EXIT_USAGE
}

fn emit(text: String) {
    use std::io::Write;
    let mut stdout = std::io::stdout().lock();
    let _ = stdout.write_all(text.as_bytes());
    let _ = stdout.write_all(b"\n");
    let _ = stdout.flush();
}

// ---------------------------------------------------------------------------
// Service results (rac.services.validate)
// ---------------------------------------------------------------------------

pub struct FileValidation {
    pub path: String,
    pub artifact_type: String,
    pub status: &'static str,
    pub issues: Vec<Issue>,
}

pub struct DirectoryValidation {
    pub directory: String,
    pub recursive: bool,
    pub files: Vec<FileValidation>,
    pub okf: Option<OkfConformanceReport>,
}

impl DirectoryValidation {
    pub fn checked(&self) -> usize {
        self.files.iter().filter(|f| f.status != STATUS_SKIPPED).count()
    }

    pub fn valid(&self) -> usize {
        self.files.iter().filter(|f| f.status == STATUS_VALID).count()
    }

    pub fn invalid(&self) -> usize {
        self.files.iter().filter(|f| f.status == STATUS_INVALID).count()
    }

    pub fn skipped(&self) -> usize {
        self.files.iter().filter(|f| f.status == STATUS_SKIPPED).count()
    }

    pub fn ok(&self) -> bool {
        self.invalid() == 0 && self.okf.as_ref().map(|o| o.ok()).unwrap_or(true)
    }
}

pub struct StdinCorpusValidation {
    pub source_path: String,
    pub structural_issues: Vec<Issue>,
    pub relationship_issues: Vec<RelationshipIssue>,
}

impl StdinCorpusValidation {
    pub fn ok(&self) -> bool {
        !has_errors(&self.structural_issues) && self.relationship_issues.is_empty()
    }
}

/// `validate_directory(directory, recursive)` — the uncached walk (the cache
/// path is contractually byte-identical, PORT-CONTRACT.d/01 §6).
pub fn validate_directory(directory: &str, recursive: bool) -> DirectoryValidation {
    let entries = corpus_items(directory, recursive);
    let overrides = load_overrides(directory);
    let provider = load_ticketing_provider(directory);
    let mut files: Vec<FileValidation> = Vec::new();
    for item in &entries {
        let artifact_type = item
            .spec
            .map(|s| s.name.clone())
            .unwrap_or_else(|| "unknown".to_string());
        if item.spec.is_none() {
            files.push(FileValidation {
                path: item.path.clone(),
                artifact_type,
                status: STATUS_SKIPPED,
                issues: Vec::new(),
            });
            continue;
        }
        let issues = apply_overrides(
            validate(&item.artifact, provider.as_deref(), Some(&artifact_type)),
            &artifact_type,
            &overrides,
        );
        let status = if has_errors(&issues) {
            STATUS_INVALID
        } else {
            STATUS_VALID
        };
        files.push(FileValidation {
            path: item.path.clone(),
            artifact_type,
            status,
            issues,
        });
    }
    let okf_entries: Vec<OkfEntry> = entries
        .iter()
        .map(|item| OkfEntry {
            path: &item.path,
            artifact_type: item
                .spec
                .map(|s| s.name.as_str())
                .unwrap_or("unknown"),
            file_name: item.path.rsplit('/').next().unwrap_or(&item.path),
        })
        .collect();
    let okf = check_okf_conformance(&okf_entries, &overrides);
    DirectoryValidation {
        directory: directory.to_string(),
        recursive,
        files,
        okf: Some(okf),
    }
}

/// `validate_stdin_against_corpus(product, corpus_dir, source_path)`.
pub fn validate_stdin_against_corpus(
    artifact: &Artifact,
    corpus_dir: &str,
    source_path: &str,
    recursive: bool,
) -> StdinCorpusValidation {
    let structural = validate_product(artifact, corpus_dir);
    let relationships =
        validate_document_against_corpus(artifact, source_path, corpus_dir, recursive);
    StdinCorpusValidation {
        source_path: source_path.to_string(),
        structural_issues: structural,
        relationship_issues: relationships.issues,
    }
}

// ---------------------------------------------------------------------------
// cmd_validate
// ---------------------------------------------------------------------------

pub struct ValidateArgs {
    pub file: String,
    pub json: bool,
    pub sarif: bool,
    pub top_level: bool,
    pub corpus: Option<String>,
}

/// `str(Path(p))` — PurePosixPath normalization of a CLI path argument.
fn py_path_str(p: &str) -> String {
    normalize_root(p)
}

/// `str(Path(p).parent)`.
fn py_path_parent(p: &str) -> String {
    let normalized = py_path_str(p);
    if normalized == "/" || normalized == "." {
        return normalized;
    }
    match normalized.rfind('/') {
        Some(0) => "/".to_string(),
        Some(i) => normalized[..i].to_string(),
        None => ".".to_string(),
    }
}

/// `_read(path)` — a directly named file that is missing or unreadable is a
/// usage error. Returns Err(exit_code) on usage failure.
fn read_named_file(path: &str) -> Result<Artifact, i32> {
    if !Path::new(path).is_file() {
        return Err(usage_error(&format!("file not found: {path}")));
    }
    let artifact = parse_file(path);
    if artifact
        .parse_issues
        .iter()
        .any(|i| i.code == "unreadable-artifact")
    {
        return Err(usage_error(&format!("cannot read {path}")));
    }
    Ok(artifact)
}

fn read_validate_input(target: &str) -> Result<Artifact, i32> {
    if target == "-" {
        use std::io::Read;
        let mut buf = Vec::new();
        let _ = std::io::stdin().lock().read_to_end(&mut buf);
        let text = String::from_utf8_lossy(&buf).into_owned();
        return Ok(parse_text(&text, "-"));
    }
    read_named_file(target)
}

pub fn cmd_validate(args: &ValidateArgs) -> i32 {
    // Directory? Validate every recognized artifact beneath it.
    if args.file != "-" && Path::new(&args.file).is_dir() {
        if args.corpus.is_some() {
            return usage_error("--corpus applies to stdin ('-') or a single file");
        }
        let result = validate_directory(&args.file, !args.top_level);
        if args.sarif {
            emit(output::render_validate_sarif(&result));
        } else if args.json {
            emit(output::render_validate_dir_json(&result));
        } else {
            emit(output::render_validate_dir_human(&result));
        }
        return if result.ok() {
            EXIT_OK
        } else {
            EXIT_VALIDATION_FAILED
        };
    }

    if args.sarif {
        return usage_error("--sarif applies to directory validation");
    }

    let artifact = match read_validate_input(&args.file) {
        Ok(a) => a,
        Err(code) => return code,
    };

    if let Some(corpus) = &args.corpus {
        if !Path::new(corpus).is_dir() {
            return usage_error(&format!("--corpus is not a directory: {corpus}"));
        }
        let source_path = if args.file == "-" {
            "-".to_string()
        } else {
            py_path_str(&args.file)
        };
        let result = validate_stdin_against_corpus(&artifact, corpus, &source_path, true);
        if args.json {
            emit(output::render_stdin_corpus_json(&result));
        } else {
            emit(output::render_stdin_corpus_human(&result));
        }
        return if result.ok() {
            EXIT_OK
        } else {
            EXIT_VALIDATION_FAILED
        };
    }

    let start = if args.file == "-" {
        ".".to_string()
    } else {
        py_path_parent(&args.file)
    };
    let issues = validate_product(&artifact, &start);
    if args.json {
        emit(output::render_validation_json(
            &artifact.product.source_path,
            &issues,
        ));
    } else {
        emit(output::render_validation_human(
            &artifact.product.source_path,
            &issues,
        ));
    }
    if has_errors(&issues) {
        EXIT_VALIDATION_FAILED
    } else {
        EXIT_OK
    }
}

// ---------------------------------------------------------------------------
// cmd_relationships (--validate arm; inspection arm is out of this phase)
// ---------------------------------------------------------------------------

pub struct RelationshipsArgs {
    pub path: String,
    pub validate: bool,
    pub sarif: bool,
    pub json: bool,
    pub top_level: bool,
}

pub fn cmd_relationships(args: &RelationshipsArgs) -> i32 {
    if args.sarif && !args.validate {
        return usage_error("relationships --sarif requires --validate");
    }
    let path = Path::new(&args.path);
    let is_dir = if path.is_dir() {
        true
    } else if path.is_file() {
        let suffix = args
            .path
            .rsplit('/')
            .next()
            .and_then(|name| name.rfind('.').map(|i| name[i..].to_lowercase()))
            .unwrap_or_default();
        if suffix != ".md" && suffix != ".markdown" {
            return usage_error(&format!(
                "relationships expects a Markdown file or directory; \
                 convert it first with: rac ingest {}",
                args.path
            ));
        }
        false
    } else {
        return usage_error(&format!("path not found: {}", args.path));
    };

    if args.validate {
        let report = if is_dir {
            validate_relationships(&args.path, !args.top_level)
        } else {
            validate_relationships_file(&args.path)
        };
        if args.sarif {
            emit(output::render_relationships_sarif(&report));
        } else if args.json {
            emit(output::render_relationship_validation_json(&report));
        } else {
            emit(output::render_relationship_validation_human(&report));
        }
        return if report.ok() {
            EXIT_OK
        } else {
            EXIT_VALIDATION_FAILED
        };
    }

    // UNIMPLEMENTED STUB (this phase wires validate + --version only; the
    // relationships inspection arm has no parity case in the current filters).
    eprintln!("rac-rs: 'relationships' without --validate is not yet implemented");
    EXIT_USAGE
}

// ---------------------------------------------------------------------------
// Helpers reused by cli.rs
// ---------------------------------------------------------------------------

/// Classify a parsed artifact's type name (used by cli-level flows needing it).
pub fn classified_type(artifact: &Artifact) -> String {
    classify(artifact).artifact_type
}
