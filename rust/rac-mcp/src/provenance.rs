//! Git-derived artifact provenance — a port of `artifact_provenance`,
//! `_commit_record` and `_status_history` in `src/rac/services/recency.py`
//! (WS5, ADR-045/ADR-065). Same narrow git touchpoint as
//! `rac_engine::gitinfo`: shell out to the real `git`, degrade every field to
//! `null` / `[]` when git cannot answer — no error crosses the boundary.

use rac_engine::pycompat::py_strip;
use rac_engine::resolve::artifact_status;
use serde_json::{json, Map, Value};
use std::path::{Path, PathBuf};
use std::process::Command;

/// Field separator in combined `git log --format` records (`\x1f`).
const FIELD_SEP: char = '\x1f';

fn run_git(args: &[&str], cwd: &Path) -> Option<String> {
    let output = Command::new("git").args(args).current_dir(cwd).output().ok()?;
    if !output.status.success() {
        return None;
    }
    // Python `text=True` decodes and applies universal newlines.
    let text = String::from_utf8_lossy(&output.stdout).into_owned();
    Some(text.replace("\r\n", "\n").replace('\r', "\n"))
}

fn repository_root(directory: &str) -> Option<PathBuf> {
    let out = run_git(&["rev-parse", "--show-toplevel"], Path::new(directory))?;
    let root = out.trim();
    if root.is_empty() {
        None
    } else {
        Some(PathBuf::from(root))
    }
}

/// `path` relative to `repo_root`, or absolute if outside the work tree.
fn pathspec(repo_root: &Path, path: &str) -> String {
    let p = Path::new(path);
    let abspath = p.canonicalize().unwrap_or_else(|_| p.to_path_buf());
    let root = repo_root
        .canonicalize()
        .unwrap_or_else(|_| repo_root.to_path_buf());
    match abspath.strip_prefix(&root) {
        Ok(rel) => rel.to_string_lossy().into_owned(),
        Err(_) => abspath.to_string_lossy().into_owned(),
    }
}

/// `datetime.fromisoformat(stamp).isoformat()` round trip on a git `%cI`
/// stamp (same normalization the search-recency join applies): space
/// separator → `T`, `Z` → `+00:00`, `±HHMM`/`±HH` → `±HH:MM`.
fn py_isoformat_roundtrip(stamp: &str) -> String {
    let mut s = stamp.to_string();
    if s.len() > 10 && s.as_bytes()[10] == b' ' {
        s.replace_range(10..11, "T");
    }
    if s.ends_with('Z') || s.ends_with('z') {
        s.truncate(s.len() - 1);
        s.push_str("+00:00");
        return s;
    }
    if let Some(pos) = s.rfind(['+', '-']) {
        if pos > 10 {
            let body = &s[pos + 1..];
            if body.len() == 4 && body.bytes().all(|b| b.is_ascii_digit()) {
                let fixed = format!("{}:{}", &body[..2], &body[2..]);
                s.replace_range(pos + 1.., &fixed);
            } else if body.len() == 2 && body.bytes().all(|b| b.is_ascii_digit()) {
                let fixed = format!("{body}:00");
                s.replace_range(pos + 1.., &fixed);
            }
        }
    }
    s
}

/// `_parse_stamp` → isoformat, or `None` for a blank/unparseable stamp.
fn parse_stamp(stamp: &str) -> Option<String> {
    let stamp = py_strip(stamp);
    if stamp.is_empty() {
        return None;
    }
    // The oracle treats a `fromisoformat` failure as unknown; git `%cI` is
    // always parseable, so validate lightly through the epoch parser.
    rac_engine::gitinfo::parse_iso8601_epoch(stamp)?;
    Some(py_isoformat_roundtrip(stamp))
}

/// `(committed isoformat | None, author | None)` for one boundary commit.
fn commit_record(repo_root: &Path, spec: &str, earliest: bool) -> (Option<String>, Option<String>) {
    let fmt = format!("--format=%cI{FIELD_SEP}%an <%ae>");
    let args: Vec<&str> = if earliest {
        vec!["log", "--reverse", &fmt, "--", spec]
    } else {
        vec!["log", "-1", &fmt, "--", spec]
    };
    let Some(out) = run_git(&args, repo_root) else {
        return (None, None);
    };
    for line in out.lines() {
        if line.trim().is_empty() {
            continue;
        }
        let (stamp, author) = match line.find(FIELD_SEP) {
            Some(i) => (&line[..i], &line[i + 1..]),
            None => (line, ""),
        };
        let author = py_strip(author);
        return (
            parse_stamp(stamp),
            if author.is_empty() {
                None
            } else {
                Some(author.to_string())
            },
        );
    }
    (None, None)
}

/// `_status_history(repo_root, path)` — one entry per parsed `## Status`
/// change, oldest first.
fn status_history(repo_root: &Path, spec: &str) -> Vec<Value> {
    let fmt = format!("--format=%H{FIELD_SEP}%cI{FIELD_SEP}%an <%ae>");
    let Some(walk) = run_git(&["log", "--reverse", &fmt, "--", spec], repo_root) else {
        return Vec::new();
    };
    let mut history: Vec<Value> = Vec::new();
    let mut last_status = String::new();
    for line in walk.lines() {
        if line.trim().is_empty() {
            continue;
        }
        let mut parts = line.splitn(3, FIELD_SEP);
        let sha = parts.next().unwrap_or("");
        let stamp = parts.next().unwrap_or("");
        let author = parts.next().unwrap_or("");
        let Some(shown) = run_git(&["show", &format!("{sha}:{spec}")], repo_root) else {
            continue;
        };
        let status = artifact_status(&rac_engine::parse::parse_text(&shown, spec));
        if !status.is_empty() && status != last_status {
            let author = py_strip(author);
            let mut change = Map::new();
            change.insert("status".to_string(), json!(status));
            change.insert(
                "committed".to_string(),
                match parse_stamp(stamp) {
                    Some(s) => json!(s),
                    None => Value::Null,
                },
            );
            change.insert(
                "author".to_string(),
                if author.is_empty() {
                    Value::Null
                } else {
                    json!(author)
                },
            );
            last_status = status;
            history.push(Value::Object(change));
        }
    }
    history
}

/// `artifact_provenance(directory, path).to_dict()` — the git-only fields
/// (the caller prepends the parsed `status`).
pub fn artifact_provenance(directory: &str, path: &str) -> Map<String, Value> {
    let mut m = Map::new();
    let opt = |v: Option<String>| v.map(|s| json!(s)).unwrap_or(Value::Null);
    match repository_root(directory) {
        None => {
            m.insert("last_committed".to_string(), Value::Null);
            m.insert("last_author".to_string(), Value::Null);
            m.insert("first_committed".to_string(), Value::Null);
            m.insert("first_author".to_string(), Value::Null);
            m.insert("status_history".to_string(), json!([]));
        }
        Some(root) => {
            let spec = pathspec(&root, path);
            let (last_committed, last_author) = commit_record(&root, &spec, false);
            let (first_committed, first_author) = commit_record(&root, &spec, true);
            m.insert("last_committed".to_string(), opt(last_committed));
            m.insert("last_author".to_string(), opt(last_author));
            m.insert("first_committed".to_string(), opt(first_committed));
            m.insert("first_author".to_string(), opt(first_author));
            m.insert(
                "status_history".to_string(),
                Value::Array(status_history(&root, &spec)),
            );
        }
    }
    m
}

/// `annotate_search_recency(matches, directory)` — the read-surface join
/// (ADR-045), byte-identical to the CLI `rac find` path.
pub fn annotate_search_recency(
    matches: &mut [rac_engine::resolve::ResolvedArtifact],
    directory: &str,
) {
    use rac_engine::gitinfo;
    if matches.is_empty() {
        return;
    }
    let threshold = rac_engine::validate::load_freshness_threshold(directory);
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
        m.recency = Some(rac_engine::resolve::Recency {
            last_committed: st.last_committed.as_deref().map(py_isoformat_roundtrip),
            age_days: st.age_days,
            stale: st.stale,
        });
    }
}
