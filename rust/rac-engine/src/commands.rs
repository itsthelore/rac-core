//! Command orchestration: walk -> parse -> classify -> validate -> render.
//! Output is order-deterministic.

use std::path::Path;

use crate::output;
use crate::parse::{parse_file, parse_text, Artifact, Issue};
use crate::relationships::{
    build_relationship_report, build_relationship_report_file, corpus_items,
    validate_document_against_corpus, validate_relationships, validate_relationships_file,
    RelationshipIssue,
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
    // stdin surrogateescape sentinels re-materialize as their raw bytes on
    // stdout (the oracle's stdout encoder uses surrogateescape). No-op —
    // a borrowed passthrough — unless stdin decoding produced sentinels.
    let payload = crate::pycompat::encode_stdout_surrogateescape(&text);
    let mut stdout = std::io::stdout().lock();
    let _ = stdout.write_all(&payload);
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
    // Per-file validation in parallel over the sorted corpus (PORT-CONTRACT
    // decision 5): an indexed rayon iterator, so `collect` preserves the
    // sorted order and the worker count is invisible in the output. The
    // shared inputs (overrides, provider) are read-only.
    use rayon::prelude::*;
    let files: Vec<FileValidation> = entries
        .par_iter()
        .map(|item| {
            let artifact_type = item
                .spec
                .map(|s| s.name.clone())
                .unwrap_or_else(|| "unknown".to_string());
            if item.spec.is_none() {
                return FileValidation {
                    path: item.path.clone(),
                    artifact_type,
                    status: STATUS_SKIPPED,
                    issues: Vec::new(),
                };
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
            FileValidation {
                path: item.path.clone(),
                artifact_type,
                status,
                issues,
            }
        })
        .collect();
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
        // The oracle reads stdin as TEXT with errors="surrogateescape" —
        // NOT the errors="replace" lossy decode used for files.
        let text = crate::pycompat::decode_stdin_surrogateescape(&buf);
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
// cmd_diff
// ---------------------------------------------------------------------------

pub struct DiffArgs {
    pub old: String,
    pub new: String,
    pub json: bool,
}

pub fn cmd_diff(args: &DiffArgs) -> i32 {
    // `old` is `_read()` before `new`, so a bad old path wins the error.
    let old = match read_named_file(&args.old) {
        Ok(a) => a,
        Err(code) => return code,
    };
    let new = match read_named_file(&args.new) {
        Ok(a) => a,
        Err(code) => return code,
    };
    let result = crate::diff::diff(&old, &new);
    if args.json {
        emit(output::render_diff_json(&result, &args.old, &args.new));
    } else {
        emit(output::render_diff_human(&result));
    }
    EXIT_OK
}

// ---------------------------------------------------------------------------
// cmd_inspect / cmd_improve
// ---------------------------------------------------------------------------

/// `Path(target).suffix.lower()` — the final `.`-suffix of the last path
/// component, empty for dotless names, leading-dot names, and trailing dots.
fn py_suffix_lower(target: &str) -> String {
    let name = target.rsplit('/').next().unwrap_or(target);
    match name.rfind('.') {
        Some(i) if i > 0 && i < name.len() - 1 => name[i..].to_lowercase(),
        _ => String::new(),
    }
}

/// `_read_markdown_input(target, command)` — a Markdown file or stdin (`-`).
fn read_markdown_input(target: &str, command: &str) -> Result<String, i32> {
    if target == "-" {
        use std::io::Read;
        let mut buf = Vec::new();
        let _ = std::io::stdin().lock().read_to_end(&mut buf);
        // `sys.stdin.read()` under the harness locale decodes UTF-8 with
        // errors="surrogateescape" — same seam as `validate -`.
        return Ok(crate::pycompat::decode_stdin_surrogateescape(&buf));
    }
    if !Path::new(target).is_file() {
        return Err(usage_error(&format!("file not found: {target}")));
    }
    let suffix = py_suffix_lower(target);
    if suffix != ".md" && suffix != ".markdown" {
        return Err(usage_error(&format!(
            "{command} expects a Markdown file; convert it first with: rac ingest {target}"
        )));
    }
    match std::fs::read(target) {
        Ok(bytes) => match String::from_utf8(bytes) {
            Ok(text) => Ok(text),
            // The oracle's `path.read_text(encoding="utf-8")` decodes
            // strictly: invalid UTF-8 raises UnicodeDecodeError, which no
            // handler catches — an unhandled traceback, exit 1, empty stdout.
            Err(e) => {
                eprintln!(
                    "UnicodeDecodeError: 'utf-8' codec can't decode input: {e}"
                );
                Err(EXIT_VALIDATION_FAILED)
            }
        },
        // OSError -> `rac: cannot read <t>: <err>`, exit 2.
        Err(e) => Err(usage_error(&format!("cannot read {target}: {e}"))),
    }
}

pub struct InspectArgs {
    pub file: String,
    pub verbose: bool,
    pub top_level: bool,
    pub json: bool,
}

pub fn cmd_inspect(args: &InspectArgs) -> i32 {
    // Directory? Aggregate per-file results into type counts. (The directory
    // check precedes the .md extension guard — and never applies to `-`.)
    if args.file != "-" && Path::new(&args.file).is_dir() {
        let result = crate::inspect::inspect_directory(&args.file, !args.top_level);
        if args.json {
            emit(output::render_dir_inspect_json(&result));
        } else {
            emit(output::render_dir_inspect_human(&result));
        }
        return EXIT_OK;
    }

    // Single file (or stdin).
    let text = match read_markdown_input(&args.file, "inspect") {
        Ok(t) => t,
        Err(code) => return code,
    };
    let artifact = parse_text(&text, "");
    let inspection = crate::inspect::build_inspection(&artifact);
    if args.verbose && !args.json {
        emit(output::render_inspect_verbose(
            &inspection,
            &crate::classify::score_artifacts(&artifact),
        ));
    } else if args.json {
        emit(output::render_inspect_json(&inspection));
    } else {
        emit(output::render_inspect_human(&inspection));
    }
    // A completed inspection always succeeds — Unknown is a valid outcome.
    EXIT_OK
}

pub struct ImproveArgs {
    pub file: String,
    pub json: bool,
    pub template: bool,
}

pub fn cmd_improve(args: &ImproveArgs) -> i32 {
    let text = match read_markdown_input(&args.file, "improve") {
        Ok(t) => t,
        Err(code) => return code,
    };
    let result = crate::improve::improve_product(&parse_text(&text, ""));
    if args.json {
        emit(output::render_improve_json(&result));
    } else if args.template {
        emit(output::render_improve_template(&result));
    } else {
        emit(output::render_improve_human(&result));
    }
    // Advisory: a completed analysis always succeeds.
    EXIT_OK
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

    // Inspection arm (non --validate): always exit 0.
    let report = if is_dir {
        build_relationship_report(&args.path, !args.top_level)
    } else {
        build_relationship_report_file(&args.path)
    };
    if args.json {
        emit(output::render_relationships_json(&report));
    } else {
        emit(output::render_relationships_human(&report));
    }
    EXIT_OK
}

// ---------------------------------------------------------------------------
// cmd_stats
// ---------------------------------------------------------------------------

pub struct StatsArgs {
    pub directory: String,
    pub json: bool,
}

pub fn cmd_stats(args: &StatsArgs) -> i32 {
    if !Path::new(&args.directory).is_dir() {
        return usage_error(&format!("not a directory: {}", args.directory));
    }
    let stats = crate::stats::collect_stats(&args.directory);
    if args.json {
        emit(output::render_stats_json(&stats));
    } else {
        emit(output::render_stats_human(&stats));
    }
    if stats.has_meaningful_content() || stats.is_empty() {
        EXIT_OK
    } else {
        EXIT_VALIDATION_FAILED
    }
}

// ---------------------------------------------------------------------------
// cmd_review
// ---------------------------------------------------------------------------

pub struct ReviewArgs {
    pub directory: String,
    pub json: bool,
    pub sarif: bool,
    pub top_level: bool,
    /// `--stale-after`: None when absent; Some(days) when present (const 14).
    pub stale_after: Option<i64>,
}

pub fn cmd_review(args: &ReviewArgs) -> i32 {
    if !Path::new(&args.directory).is_dir() {
        return usage_error(&format!("not a directory: {}", args.directory));
    }
    if let Some(days) = args.stale_after {
        if days < 0 {
            return usage_error("--stale-after must be a non-negative number of days");
        }
    }
    let report = crate::review::build_review(&args.directory, !args.top_level, args.stale_after);
    if args.sarif {
        emit(output::render_review_sarif(&report));
    } else if args.json {
        emit(output::render_review_json(&report));
    } else {
        emit(output::render_review_human(&report));
    }
    if report.ok() {
        EXIT_OK
    } else {
        EXIT_VALIDATION_FAILED
    }
}

// ---------------------------------------------------------------------------
// cmd_export
// ---------------------------------------------------------------------------

pub struct ExportArgs {
    pub directory: String,
    pub json: bool,
    pub graph: bool,
    pub documents: bool,
    pub html: bool,
    pub okf: bool,
    pub agent_rules: bool,
    pub check: bool,
    pub client: Vec<String>,
    pub out: Option<String>,
}

pub fn cmd_export(args: &ExportArgs) -> i32 {
    if !Path::new(&args.directory).is_dir() {
        return usage_error(&format!("not a directory: {}", args.directory));
    }
    if args.agent_rules {
        eprintln!("rac-rs: export --agent-rules is not implemented in this stage");
        return EXIT_USAGE;
    }
    if args.check {
        return usage_error("--check requires --agent-rules");
    }
    if !args.client.is_empty() {
        return usage_error("--client requires --agent-rules");
    }
    if args.json && (args.html || args.okf) {
        return usage_error("--json cannot combine with --html or --okf");
    }
    if args.out.is_some() && !(args.html || args.okf) {
        return usage_error("--out requires --html or --okf (--json writes to stdout)");
    }
    if args.documents {
        emit(output::render_documents_jsonl(
            &crate::export::build_documents_export(&args.directory),
        ));
        return EXIT_OK;
    }
    if args.graph {
        emit(output::render_graph_json(&crate::export::build_graph_export(
            &args.directory,
        )));
        return EXIT_OK;
    }
    let export = crate::export::build_corpus_export(&args.directory, output::rac_version());
    if args.okf {
        eprintln!("rac-rs: export --okf is not implemented in this stage");
        return EXIT_USAGE;
    }
    if !args.html {
        emit(output::render_export_json(&export));
        return EXIT_OK;
    }
    eprintln!("rac-rs: export --html is not implemented in this stage");
    EXIT_USAGE
}

// ---------------------------------------------------------------------------
// cmd_schema / cmd_templates
// ---------------------------------------------------------------------------

pub struct SchemaArgs {
    pub schema: Option<String>,
    pub list: bool,
    pub json: bool,
    pub template: bool,
}

pub fn cmd_schema(args: &SchemaArgs) -> i32 {
    let names = crate::spec::available_schemas();
    if args.list {
        if args.template {
            return usage_error("--template cannot be used with --list");
        }
        if args.schema.is_some() {
            return usage_error("schema name cannot be used with --list");
        }
        if args.json {
            emit(output::render_schema_list_json(&names));
        } else {
            emit(output::render_schema_list_human(&names));
        }
        return EXIT_OK;
    }

    let Some(name) = &args.schema else {
        return usage_error("schema name required unless --list is passed");
    };

    let Some(spec) = crate::spec::spec_for(name) else {
        // Unknown schema: multi-line blob to stderr, exit 2 (no `rac:` prefix).
        eprintln!("{}", output::render_unknown_schema(name, &names));
        return EXIT_USAGE;
    };

    if args.json {
        emit(output::render_schema_json(spec));
    } else if args.template {
        emit(output::render_schema_template(spec));
    } else {
        emit(output::render_schema_human(spec));
    }
    EXIT_OK
}

pub struct TemplatesArgs {
    pub json: bool,
}

pub fn cmd_templates(args: &TemplatesArgs) -> i32 {
    let names = crate::spec::available_schemas();
    if args.json {
        emit(output::render_templates_json(&names));
    } else {
        emit(output::render_templates_human(&names));
    }
    EXIT_OK
}

// ---------------------------------------------------------------------------
// cmd_resolve / cmd_find (PORT-CONTRACT.d/06)
// ---------------------------------------------------------------------------

pub struct ResolveArgs {
    pub id: String,
    pub directory: String,
    pub json: bool,
    pub top_level: bool,
}

pub fn cmd_resolve(args: &ResolveArgs) -> i32 {
    if !Path::new(&args.directory).is_dir() {
        return usage_error(&format!("not a directory: {}", args.directory));
    }
    let result = crate::resolve::resolve_artifact(&args.directory, &args.id, !args.top_level);
    if args.json {
        emit(output::render_resolve_json(&result));
    } else if result.outcome == crate::resolve::OUTCOME_RESOLVED {
        emit(output::render_resolve_human(
            result.artifact.as_ref().expect("resolved implies artifact"),
        ));
    } else if result.outcome == crate::resolve::OUTCOME_DUPLICATE {
        let found: Vec<String> = result
            .duplicate_paths
            .iter()
            .map(|p| format!("- {p}"))
            .collect();
        eprintln!(
            "rac: duplicate artifact ID: {}\n\nFound in:\n{}",
            args.id,
            found.join("\n")
        );
    } else {
        eprintln!("rac: artifact not found: {}", args.id);
    }
    // Not-found and duplicate identity are both repository findings (exit 1).
    if result.outcome == crate::resolve::OUTCOME_RESOLVED {
        EXIT_OK
    } else {
        EXIT_VALIDATION_FAILED
    }
}

pub struct FindArgs {
    pub query: String,
    pub directory: String,
    pub artifact_type: Option<String>,
    pub decisions: bool,
    pub tags: Vec<String>,
    pub json: bool,
    pub explain: bool,
    pub top_level: bool,
    /// The live-only facet (ADR-113): drop retired matches of every type.
    pub live: bool,
}

/// `annotate_search_recency(matches, directory)` — the read-surface join
/// (ADR-045): git-derived staleness per match, computed AFTER ranking so the
/// matched set and order are unchanged. All-null outside a git repository.
/// Shared by `cmd_find` and the MCP `search_artifacts` tool (both surfaces
/// are byte-identical on this join).
pub fn annotate_search_recency(matches: &mut [crate::resolve::ResolvedArtifact], directory: &str) {
    use crate::gitinfo;
    if matches.is_empty() {
        return;
    }
    let threshold = crate::validate::load_freshness_threshold(directory);
    let reference = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs() as i64)
        .unwrap_or(0);
    let repo_root = gitinfo::repository_root(Path::new(directory));
    for m in matches.iter_mut() {
        let last = repo_root
            .as_ref()
            .and_then(|root| gitinfo::last_committed(root, Path::new(&m.path)));
        let st = gitinfo::staleness(last.as_deref(), threshold, reference);
        m.recency = Some(crate::resolve::Recency {
            last_committed: st.last_committed.as_deref().map(gitinfo::isoformat_roundtrip),
            age_days: st.age_days,
            stale: st.stale,
        });
    }
}

pub fn cmd_find(args: &FindArgs) -> i32 {
    if !Path::new(&args.directory).is_dir() {
        return usage_error(&format!("not a directory: {}", args.directory));
    }
    let mut result = if args.decisions {
        // The live decision query (ADR-067): decision type filter + the
        // Accepted/non-retired liveness filter; `--tag` is silently ignored.
        crate::resolve::find_decisions(&args.directory, &args.query, !args.top_level)
    } else {
        crate::resolve::find_artifacts(
            &args.directory,
            &args.query,
            args.artifact_type.as_deref(),
            !args.top_level,
            &args.tags,
            args.live,
        )
    };
    annotate_search_recency(&mut result.matches, &args.directory);
    if args.json {
        emit(output::render_find_json(&result, args.explain));
    } else {
        emit(output::render_find_human(&result, args.explain));
    }
    // An empty result is a valid outcome, not an error.
    EXIT_OK
}

pub struct RetrieveArgs {
    pub task: String,
    pub directory: String,
    pub scope: Option<String>,
    pub top_k: i64,
    pub budget: i64,
    pub all: bool,
    pub json: bool,
}

/// `cmd_retrieve` — one-call compound grounding retrieval (ADR-113). The
/// `--json` face emits the budget-capped serialization; the human face renders
/// the same truncated payload. An empty `items` list is a valid answer.
pub fn cmd_retrieve(args: &RetrieveArgs) -> i32 {
    if !Path::new(&args.directory).is_dir() {
        return usage_error(&format!("not a directory: {}", args.directory));
    }
    if args.top_k < 1 {
        return usage_error(&format!("--top-k must be at least 1, got {}", args.top_k));
    }
    if args.budget < 1 {
        return usage_error(&format!("--budget must be at least 1, got {}", args.budget));
    }
    let payload = crate::retrieve::retrieve_grounding(
        &args.directory,
        &args.task,
        args.scope.as_deref(),
        args.top_k,
        args.budget,
        !args.all,
    );
    let serialized = crate::budget::serialize(&payload, args.budget);
    if args.json {
        emit(serialized);
    } else {
        // The oracle renders from json.loads(serialized) — the truncated shape.
        let truncated: serde_json::Value =
            serde_json::from_str(&serialized).expect("serialized payload is valid JSON");
        emit(output::render_retrieve_human(&truncated));
    }
    EXIT_OK
}
