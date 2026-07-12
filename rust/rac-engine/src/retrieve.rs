//! Compound deterministic grounding retrieval (`rac retrieve`, ADR-113) — a
//! port of `src/rac/services/retrieve.py`, `src/rac/services/scope.py` /
//! `scope_paths.py` (the scope-binding channel), and the retrieve arm of
//! `src/rac/mcp/budget.py` from the `grounding-retrieval-surface` branch
//! (oracle `0.1.dev55+gf2091befd`).
//!
//! Landmines reproduced here:
//! - The budget unit is CHARACTERS of the serialized JSON
//!   (`json.dumps(payload, ensure_ascii=False)` — `pyjson::dumps_compact`),
//!   never bytes.
//! - Excerpts are Python character slices (`content[:share]`), over the file's
//!   text read with universal newlines (`\r\n`/`\r` → `\n`); an unreadable or
//!   non-UTF-8 file contributes an empty excerpt.
//! - Payload/provenance key ORDER is Python dict insertion order: items are
//!   `id, type, title, status, path, excerpt, provenance`; provenance keys in
//!   first-set order (`channels` first, then whichever of `matching_entry`,
//!   `superseded`, `evidence` was set first).
//! - Scope binding matches `scope._entry_covers`: segment-aware globs compiled
//!   exactly like `_glob_to_regex` (`*`/`?` within a segment, `**` across,
//!   `**/` zero-or-more whole segments, `[...]` classes, `.`-collapse and
//!   `..`-rejection in path normalisation).
//! - Truncation is excerpt-first (binary search for the largest fitting
//!   prefix), whole-item drop only when an emptied excerpt still misses.

use std::collections::HashMap;
use std::path::{Path, PathBuf};

use serde_json::{json, Map, Value};

use crate::identity::artifact_identifier;
use crate::pycompat::{py_casefold, py_strip};
use crate::pyjson::dumps_compact;
use crate::relationships::{
    corpus_items, extract_relationships_full, relationships_from_corpus, CorpusItem, Relationship,
};
use crate::resolve::{
    artifact_status, index_from_items, is_live_decision, is_retired_status, search_index,
    IndexEntry,
};

// Defaults pinned by the grounding-retrieval-surface design.
pub const DEFAULT_TOP_K: i64 = 5;
pub const DEFAULT_BUDGET: i64 = 10_000;

const SUPERSEDES: &str = "supersedes";
const DECISION_TYPE: &str = "decision";

// Discovery channel names on the wire (pinned by the design).
const CHANNEL_KEYWORD: &str = "keyword";
const CHANNEL_SCOPE: &str = "scope";
const CHANNEL_SUPERSEDES: &str = "supersedes";

// Pinned marker fields + retrieve hint (`rac.mcp.budget`).
const MARKER_TRUNCATED: &str = "truncated";
const MARKER_OMITTED: &str = "omitted";
const MARKER_HINT: &str = "hint";
const HINT_RETRIEVE: &str = "Lower top_k, raise the budget, or narrow the task.";

// ---------------------------------------------------------------------------
// Python character-slice helpers
// ---------------------------------------------------------------------------

/// `len(text)` in Python — code points, not bytes.
fn char_len(s: &str) -> i64 {
    s.chars().count() as i64
}

/// `text[:stop]` with Python slice semantics (negative stop trims the tail).
fn py_slice_to(s: &str, stop: i64) -> String {
    let n = char_len(s);
    let stop = if stop < 0 { (n + stop).max(0) } else { stop.min(n) };
    s.chars().take(stop as usize).collect()
}

/// `Path(path).read_text(encoding="utf-8")` — strict UTF-8 with universal
/// newlines; OSError/UnicodeDecodeError callers substitute "".
fn read_text_universal(path: &str) -> Option<String> {
    let bytes = std::fs::read(path).ok()?;
    let text = String::from_utf8(bytes).ok()?;
    Some(text.replace("\r\n", "\n").replace('\r', "\n"))
}

// ---------------------------------------------------------------------------
// scope_paths.py — entry classification, path normalisation, repository root
// ---------------------------------------------------------------------------

/// `classify_scope_entry(entry)`: `glob` | `path` | `component`.
fn classify_scope_entry(entry: &str) -> &'static str {
    if entry.contains(['*', '?', '[']) {
        return "glob";
    }
    if entry.contains('/') {
        return "path";
    }
    "component"
}

/// `PurePosixPath(text).parts` minus any root marker: empty and `.` segments
/// collapse; the root marker (when the text is absolute) is returned apart.
fn pure_posix_parts(text: &str) -> (Option<&'static str>, Vec<String>) {
    let root = if text.starts_with('/') {
        // POSIX: exactly two leading slashes are the special `//` root;
        // one or three-plus collapse to `/`.
        if text.starts_with("//") && !text.starts_with("///") {
            Some("//")
        } else {
            Some("/")
        }
    } else {
        None
    };
    let parts = text
        .split('/')
        .filter(|p| !p.is_empty() && *p != ".")
        .map(str::to_string)
        .collect();
    (root, parts)
}

/// `normalized_scope_path(entry)`.
fn normalized_scope_path(entry: &str) -> Option<String> {
    let text = py_strip(entry);
    if text.is_empty() || text.starts_with('/') {
        return None;
    }
    let (_, raw_parts) = pure_posix_parts(text);
    let mut parts: Vec<String> = Vec::new();
    for part in raw_parts {
        if part == ".." {
            return None;
        }
        parts.push(part);
    }
    if parts.is_empty() {
        None
    } else {
        Some(parts.join("/"))
    }
}

/// `repository_root(directory)` — nearest ancestor holding `.rac/config.yaml`,
/// else the resolved directory itself.
fn repository_root(directory: &str) -> PathBuf {
    let resolved = Path::new(directory).canonicalize().unwrap_or_else(|_| {
        // Python resolve() is non-strict; absolutize against the cwd.
        std::env::current_dir()
            .map(|c| c.join(directory))
            .unwrap_or_else(|_| PathBuf::from(directory))
    });
    for candidate in resolved.ancestors() {
        if candidate.join(".rac").join("config.yaml").is_file() {
            return candidate.to_path_buf();
        }
    }
    resolved
}

// ---------------------------------------------------------------------------
// scope.py — the `_glob_to_regex` glob matcher (compiled, not regex-backed)
// ---------------------------------------------------------------------------

#[derive(Debug, Clone)]
enum ClassItem {
    Ch(char),
    Range(char, char),
    Digit,
    NonDigit,
    Word,
    NonWord,
    Space,
    NonSpace,
}

#[derive(Debug, Clone)]
enum GlobTok {
    Lit(char),
    /// `[^/]*`
    Star,
    /// `[^/]`
    Q,
    /// `(?:[^/]+/)*`
    SegStar,
    /// `.*` (any char except `\n`)
    DotStar,
    Class {
        negated: bool,
        items: Vec<ClassItem>,
    },
}

/// Compile the pattern exactly as `_glob_to_regex` builds its regex.
fn compile_glob(pattern: &str) -> Vec<GlobTok> {
    let chars: Vec<char> = pattern.chars().collect();
    let n = chars.len();
    let mut out: Vec<GlobTok> = Vec::new();
    let mut i = 0usize;
    while i < n {
        let c = chars[i];
        if c == '*' {
            if i + 1 < n && chars[i + 1] == '*' {
                i += 2;
                if i < n && chars[i] == '/' {
                    i += 1;
                    out.push(GlobTok::SegStar);
                } else {
                    out.push(GlobTok::DotStar);
                }
                continue;
            }
            out.push(GlobTok::Star);
        } else if c == '?' {
            out.push(GlobTok::Q);
        } else if c == '[' {
            let mut j = i + 1;
            if j < n && (chars[j] == '!' || chars[j] == '^') {
                j += 1;
            }
            if j < n && chars[j] == ']' {
                j += 1;
            }
            while j < n && chars[j] != ']' {
                j += 1;
            }
            if j >= n {
                out.push(GlobTok::Lit('[')); // unterminated class → literal '['
            } else {
                let inner: Vec<char> = chars[i + 1..j].to_vec();
                let (negated, body) = match inner.first() {
                    Some('!') | Some('^') => (true, &inner[1..]),
                    _ => (false, &inner[..]),
                };
                out.push(GlobTok::Class {
                    negated,
                    items: parse_class_items(body),
                });
                i = j + 1;
                continue;
            }
        } else {
            out.push(GlobTok::Lit(c));
        }
        i += 1;
    }
    out
}

/// Parse a regex character-class body (`a-z`, escapes, shorthands).
fn parse_class_items(body: &[char]) -> Vec<ClassItem> {
    let mut items: Vec<ClassItem> = Vec::new();
    let mut k = 0usize;
    let n = body.len();
    while k < n {
        // Resolve one class atom (an escaped char/shorthand or a literal).
        let (atom, used, shorthand) = if body[k] == '\\' && k + 1 < n {
            let e = body[k + 1];
            let sh = match e {
                'd' => Some(ClassItem::Digit),
                'D' => Some(ClassItem::NonDigit),
                'w' => Some(ClassItem::Word),
                'W' => Some(ClassItem::NonWord),
                's' => Some(ClassItem::Space),
                'S' => Some(ClassItem::NonSpace),
                _ => None,
            };
            (e, 2usize, sh)
        } else {
            (body[k], 1usize, None)
        };
        if let Some(sh) = shorthand {
            items.push(sh);
            k += used;
            continue;
        }
        // Range: atom '-' atom (the '-' not last in the class body).
        if k + used < n && body[k + used] == '-' && k + used + 1 < n {
            let mut m = k + used + 1;
            let hi = if body[m] == '\\' && m + 1 < n {
                m += 1;
                body[m]
            } else {
                body[m]
            };
            items.push(ClassItem::Range(atom, hi));
            k = m + 1;
            continue;
        }
        items.push(ClassItem::Ch(atom));
        k += used;
    }
    items
}

fn class_matches(negated: bool, items: &[ClassItem], c: char) -> bool {
    let hit = items.iter().any(|item| match item {
        ClassItem::Ch(x) => c == *x,
        ClassItem::Range(lo, hi) => (*lo..=*hi).contains(&c),
        ClassItem::Digit => crate::pycompat::is_re_digit(c),
        ClassItem::NonDigit => !crate::pycompat::is_re_digit(c),
        ClassItem::Word => crate::pycompat::is_re_word(c),
        ClassItem::NonWord => !crate::pycompat::is_re_word(c),
        ClassItem::Space => py_re_space(c),
        ClassItem::NonSpace => !py_re_space(c),
    });
    hit != negated
}

/// Python `re` `\s` over str patterns.
fn py_re_space(c: char) -> bool {
    matches!(c, ' ' | '\t' | '\n' | '\r' | '\x0b' | '\x0c' | '\u{1c}'..='\u{1f}' | '\u{85}')
        || crate::pycompat::py_is_space(c)
}

/// Backtracking matcher — boolean-equivalent to `re.match(regex + r"\Z", s)`.
fn glob_match_at(toks: &[GlobTok], s: &[char]) -> bool {
    let Some(tok) = toks.first() else {
        return s.is_empty();
    };
    let rest = &toks[1..];
    match tok {
        GlobTok::Lit(c) => s.first() == Some(c) && glob_match_at(rest, &s[1..]),
        GlobTok::Q => s.first().is_some_and(|&c| c != '/') && glob_match_at(rest, &s[1..]),
        GlobTok::Star => {
            let limit = s.iter().take_while(|&&c| c != '/').count();
            (0..=limit).any(|k| glob_match_at(rest, &s[k..]))
        }
        GlobTok::DotStar => {
            let limit = s.iter().take_while(|&&c| c != '\n').count();
            (0..=limit).any(|k| glob_match_at(rest, &s[k..]))
        }
        GlobTok::SegStar => {
            // zero segments:
            if glob_match_at(rest, s) {
                return true;
            }
            // one whole segment `[^/]+/`, then this token again:
            let mut i = 0usize;
            while i < s.len() && s[i] != '/' {
                i += 1;
            }
            i > 0 && i < s.len() && glob_match_at(toks, &s[i + 1..])
        }
        GlobTok::Class { negated, items } => s
            .first()
            .is_some_and(|&c| class_matches(*negated, items, c))
            && glob_match_at(rest, &s[1..]),
    }
}

/// `_entry_covers(entry, query)`.
fn entry_covers(entry: &str, query: &str) -> bool {
    match classify_scope_entry(entry) {
        "component" => false,
        "glob" => {
            let toks = compile_glob(py_strip(entry));
            let q: Vec<char> = query.chars().collect();
            glob_match_at(&toks, &q)
        }
        _ => match normalized_scope_path(entry) {
            None => false,
            Some(normalized) => {
                query == normalized || query.starts_with(&format!("{normalized}/"))
            }
        },
    }
}

/// `_normalize_query(path, root)` — POSIX repo-relative form, or None.
fn normalize_query(path: &str, root: &Path) -> Option<String> {
    let text = py_strip(path);
    if text.is_empty() {
        return None;
    }
    let (cand_root, mut cand_parts) = pure_posix_parts(text);
    if cand_root.is_some() {
        // PurePosixPath.relative_to(root.as_posix()) — parts-prefix check;
        // a ValueError (differing root marker, or not nested) → None.
        let root_posix = root.to_string_lossy().replace('\\', "/");
        let (root_marker, root_parts) = pure_posix_parts(&root_posix);
        if cand_root != root_marker
            || cand_parts.len() < root_parts.len()
            || cand_parts[..root_parts.len()] != root_parts[..]
        {
            return None; // outside the repository
        }
        cand_parts = cand_parts[root_parts.len()..].to_vec();
    }
    let mut parts: Vec<String> = Vec::new();
    for part in cand_parts {
        if part == ".." {
            return None;
        }
        parts.push(part);
    }
    if parts.is_empty() {
        None
    } else {
        Some(parts.join("/"))
    }
}

// ---------------------------------------------------------------------------
// derived_cache.py — scope rows + governing_decisions
// ---------------------------------------------------------------------------

/// One live decision's declared `## Applies To` scope (`ScopeRow`).
struct ScopeRow {
    id: String,
    title: String,
    status: String,
    path: String,
    scope_entries: Vec<String>,
}

/// `_scope_rows_from_corpus(entries)` — live decisions with declared scope.
fn scope_rows_from_items(items: &[CorpusItem]) -> Vec<ScopeRow> {
    let mut rows = Vec::new();
    for item in items {
        let Some(spec) = item.spec else { continue };
        if spec.name != DECISION_TYPE || !is_live_decision(&item.artifact) {
            continue;
        }
        // SCOPE_SECTIONS = ("applies to",) → snake key "applies_to".
        let declared: Vec<String> = extract_relationships_full(&item.artifact, spec)
            .into_iter()
            .filter(|(section, _)| section == "applies_to")
            .flat_map(|(_, refs)| refs)
            .collect();
        if declared.is_empty() {
            continue;
        }
        rows.push(ScopeRow {
            id: artifact_identifier(&item.artifact, Some(spec), &item.path),
            title: item.artifact.product.title.clone().unwrap_or_default(),
            status: artifact_status(&item.artifact),
            path: item.path.clone(),
            scope_entries: declared,
        });
    }
    rows
}

/// One governing decision (the fields retrieve reads).
struct Governing {
    id: String,
    title: String,
    status: String,
    path: String,
    matching_entry: String,
}

/// `governing_decisions(scope_rows, directory, path).decisions`.
fn governing_decisions(rows: &[ScopeRow], directory: &str, path: &str) -> Vec<Governing> {
    let root = repository_root(directory);
    let Some(query) = normalize_query(path, &root) else {
        return Vec::new();
    };
    let mut matches: Vec<Governing> = Vec::new();
    for row in rows {
        for declared in &row.scope_entries {
            if entry_covers(declared, &query) {
                matches.push(Governing {
                    id: row.id.clone(),
                    title: row.title.clone(),
                    status: row.status.clone(),
                    path: row.path.clone(),
                    matching_entry: declared.clone(),
                });
                break;
            }
        }
    }
    matches.sort_by(|a, b| {
        (py_casefold(&a.id), &a.path).cmp(&(py_casefold(&b.id), &b.path))
    });
    matches
}

/// `find_decisions` path mode (MCP surface): the `ScopeLookupResult.to_dict()`
/// payload — `{schema_version, query, in_repository, decisions}` — for the live
/// decisions whose declared `## Applies To` scope governs `path`. Additive
/// wrapper over the same scope internals `retrieve_grounding` uses
/// (`scope_rows_from_items` / `normalize_query` / `entry_covers`), byte-identical
/// to `rac.services.derived_cache.governing_decisions(...).to_dict()`.
pub fn find_decisions_path_payload(directory: &str, path: &str) -> Value {
    let root = repository_root(directory);
    let mut payload = Map::new();
    payload.insert("schema_version".to_string(), json!("1"));
    match normalize_query(path, &root) {
        None => {
            payload.insert("query".to_string(), json!(py_strip(path)));
            payload.insert("in_repository".to_string(), json!(false));
            payload.insert("decisions".to_string(), json!([]));
        }
        Some(query) => {
            let items = corpus_items(directory, true);
            let rows = scope_rows_from_items(&items);
            let mut matches: Vec<Governing> = Vec::new();
            for row in &rows {
                for declared in &row.scope_entries {
                    if entry_covers(declared, &query) {
                        matches.push(Governing {
                            id: row.id.clone(),
                            title: row.title.clone(),
                            status: row.status.clone(),
                            path: row.path.clone(),
                            matching_entry: declared.clone(),
                        });
                        break;
                    }
                }
            }
            matches.sort_by(|a, b| {
                (py_casefold(&a.id), &a.path).cmp(&(py_casefold(&b.id), &b.path))
            });
            let decisions: Vec<Value> = matches
                .into_iter()
                .map(|d| {
                    let mut m = Map::new();
                    m.insert("id".to_string(), json!(d.id));
                    m.insert("title".to_string(), json!(d.title));
                    m.insert("status".to_string(), json!(d.status));
                    m.insert("path".to_string(), json!(d.path));
                    m.insert("matching_entry".to_string(), json!(d.matching_entry));
                    m
                })
                .map(Value::Object)
                .collect();
            payload.insert("query".to_string(), json!(query));
            payload.insert("in_repository".to_string(), json!(true));
            payload.insert("decisions".to_string(), Value::Array(decisions));
        }
    }
    Value::Object(payload)
}

// ---------------------------------------------------------------------------
// retrieve.py — the compound grounding payload
// ---------------------------------------------------------------------------

/// `_successor_map(relationships)` — retired target path → sorted superseding
/// source paths (resolved `supersedes` edges only).
fn successor_map(relationships: &[Relationship]) -> HashMap<String, Vec<String>> {
    let mut by_target: HashMap<String, Vec<String>> = HashMap::new();
    for rel in relationships {
        if rel.relationship == SUPERSEDES {
            if let Some(target) = &rel.resolved_path {
                by_target
                    .entry(target.clone())
                    .or_default()
                    .push(rel.source_path.clone());
            }
        }
    }
    for sources in by_target.values_mut() {
        sources.sort();
        sources.dedup();
    }
    by_target
}

/// `_live_successors(path, by_target, is_retired, visited)`.
fn live_successors(
    path: &str,
    by_target: &HashMap<String, Vec<String>>,
    is_retired: &dyn Fn(&str) -> bool,
    visited: &mut std::collections::HashSet<String>,
) -> Vec<String> {
    let mut out: Vec<String> = Vec::new();
    let Some(sources) = by_target.get(path) else {
        return out;
    };
    for source in sources {
        if visited.contains(source) {
            continue;
        }
        visited.insert(source.clone());
        if is_retired(source) {
            out.extend(live_successors(source, by_target, is_retired, visited));
        } else {
            out.push(source.clone());
        }
    }
    out
}

/// One in-progress item (Python's per-path dict + its provenance dict).
struct ItemBuilder {
    id: String,
    item_type: String,
    title: Option<String>,
    status: String,
    path: String,
    /// Provenance keys in insertion order.
    provenance: Map<String, Value>,
}

#[allow(clippy::too_many_arguments)]
fn add_item(
    items: &mut Vec<ItemBuilder>,
    index_of: &mut HashMap<String, usize>,
    path: &str,
    channel: &str,
    item_id: &str,
    item_type: &str,
    title: Option<&str>,
    status: &str,
    matching_entry: Option<&str>,
    superseded: Option<&str>,
    evidence: Option<Value>,
) {
    let idx = match index_of.get(path) {
        Some(&i) => i,
        None => {
            let mut provenance = Map::new();
            provenance.insert("channels".to_string(), json!([]));
            items.push(ItemBuilder {
                id: item_id.to_string(),
                item_type: item_type.to_string(),
                title: title.map(str::to_string),
                status: status.to_string(),
                path: path.to_string(),
                provenance,
            });
            index_of.insert(path.to_string(), items.len() - 1);
            items.len() - 1
        }
    };
    let provenance = &mut items[idx].provenance;
    {
        let channels = provenance
            .get_mut("channels")
            .and_then(Value::as_array_mut)
            .expect("channels array");
        if !channels.iter().any(|c| c.as_str() == Some(channel)) {
            channels.push(json!(channel));
        }
    }
    if let Some(entry) = matching_entry {
        if !provenance.contains_key("matching_entry") {
            provenance.insert("matching_entry".to_string(), json!(entry));
        }
    }
    if let Some(replaced_id) = superseded {
        if !provenance.contains_key("superseded") {
            provenance.insert("superseded".to_string(), json!([]));
        }
        let replaced = provenance
            .get_mut("superseded")
            .and_then(Value::as_array_mut)
            .expect("superseded array");
        if !replaced.iter().any(|r| r.as_str() == Some(replaced_id)) {
            replaced.push(json!(replaced_id));
        }
    }
    if let Some(ev) = evidence {
        if !provenance.contains_key("evidence") {
            provenance.insert("evidence".to_string(), ev);
        }
    }
}

/// The search-match `evidence` dict exactly as `rac find --json --explain`
/// serializes it: `{field, terms, tier, score, components:{bm25,
/// lexical_rank, graph_rank, inbound}}`.
fn evidence_value(e: &crate::resolve::Evidence) -> Value {
    let mut ev = Map::new();
    ev.insert("field".to_string(), json!(e.field));
    ev.insert("terms".to_string(), json!(e.terms));
    ev.insert("tier".to_string(), json!(e.tier));
    ev.insert("score".to_string(), crate::pyjson::py_float(e.score));
    let mut components = Map::new();
    components.insert("bm25".to_string(), crate::pyjson::py_float(e.bm25));
    components.insert("lexical_rank".to_string(), json!(e.lexical_rank));
    components.insert("graph_rank".to_string(), json!(e.graph_rank));
    components.insert("inbound".to_string(), json!(e.inbound));
    ev.insert("components".to_string(), Value::Object(components));
    Value::Object(ev)
}

/// `retrieve_grounding(directory, task, scope, top_k, budget, live_only)` —
/// the contract-shaped payload, pre-serialization (`serialize` caps it).
pub fn retrieve_grounding(
    directory: &str,
    task: &str,
    scope: Option<&str>,
    top_k: i64,
    budget: i64,
    live_only: bool,
) -> Value {
    let top_k = top_k.max(1);
    let corpus = corpus_items(directory, true);
    let entries: Vec<IndexEntry> = index_from_items(&corpus);
    let entry_by_path: HashMap<&str, &IndexEntry> =
        entries.iter().map(|e| (e.path.as_str(), e)).collect();
    // Memoised per-call status reader: every queried path is a corpus path, so
    // re-parsing its bytes yields exactly the already-parsed artifact.
    let status_by_path: HashMap<&str, String> = corpus
        .iter()
        .map(|item| (item.path.as_str(), artifact_status(&item.artifact)))
        .collect();
    let status_of = |path: &str| -> String {
        match status_by_path.get(path) {
            Some(s) => s.clone(),
            // Not part of the walked corpus: parse fresh, "" when unreadable.
            None => {
                if Path::new(path).is_file() {
                    artifact_status(&crate::parse::parse_file(path))
                } else {
                    String::new()
                }
            }
        }
    };
    let is_retired = |path: &str| -> bool {
        let artifact_type = entry_by_path
            .get(path)
            .map(|e| e.artifact_type.as_str())
            .unwrap_or(DECISION_TYPE);
        is_retired_status(artifact_type, &status_of(path))
    };

    let mut items: Vec<ItemBuilder> = Vec::new();
    let mut index_of: HashMap<String, usize> = HashMap::new();

    // Scope stratum: declared `## Applies To` coverage binds regardless of
    // keyword match; the rows are live by construction.
    let scope = scope.filter(|s| !s.is_empty()); // Python `if scope:` truthiness
    if let Some(scope_path) = scope {
        let rows = scope_rows_from_items(&corpus);
        for governing in governing_decisions(&rows, directory, scope_path) {
            add_item(
                &mut items,
                &mut index_of,
                &governing.path,
                CHANNEL_SCOPE,
                &governing.id,
                DECISION_TYPE,
                if governing.title.is_empty() {
                    None
                } else {
                    Some(&governing.title)
                },
                &governing.status,
                Some(&governing.matching_entry),
                None,
                None,
            );
        }
    }

    // Keyword stratum: the existing tiered match and fused ranking, unchanged.
    let keyword = search_index(&entries, task, None, &[]);
    let by_target = if live_only {
        successor_map(&relationships_from_corpus(&corpus))
    } else {
        HashMap::new()
    };
    for m in &keyword.matches {
        if live_only && is_retired(&m.path) {
            let mut visited: std::collections::HashSet<String> =
                std::collections::HashSet::new();
            visited.insert(m.path.clone());
            for successor_path in live_successors(&m.path, &by_target, &is_retired, &mut visited)
            {
                let Some(successor) = entry_by_path.get(successor_path.as_str()) else {
                    continue;
                };
                add_item(
                    &mut items,
                    &mut index_of,
                    &successor_path,
                    CHANNEL_SUPERSEDES,
                    &successor.id,
                    &successor.artifact_type,
                    successor.title.as_deref(),
                    &status_of(&successor_path),
                    None,
                    Some(&m.id),
                    None,
                );
            }
            continue;
        }
        add_item(
            &mut items,
            &mut index_of,
            &m.path,
            CHANNEL_KEYWORD,
            &m.id,
            &m.artifact_type,
            m.title.as_deref(),
            &status_of(&m.path),
            None,
            None,
            m.evidence.as_ref().map(evidence_value),
        );
    }

    let selected: Vec<ItemBuilder> = {
        let keep = (top_k.max(0) as usize).min(items.len());
        items.truncate(keep);
        items
    };
    // Even excerpt shaping: each item's excerpt is the head of the artifact's
    // stored text capped at the budget's per-item share.
    let share = if selected.is_empty() {
        0
    } else {
        budget.div_euclid((top_k.min(selected.len() as i64)).max(1))
    };
    let mut shaped: Vec<Value> = Vec::new();
    for item in selected {
        let content = read_text_universal(&item.path).unwrap_or_default();
        let mut obj = Map::new();
        obj.insert("id".to_string(), json!(item.id));
        obj.insert("type".to_string(), json!(item.item_type));
        obj.insert(
            "title".to_string(),
            item.title.map(|t| json!(t)).unwrap_or(Value::Null),
        );
        obj.insert("status".to_string(), json!(item.status));
        obj.insert("path".to_string(), json!(item.path));
        obj.insert("excerpt".to_string(), json!(py_slice_to(&content, share)));
        obj.insert("provenance".to_string(), Value::Object(item.provenance));
        shaped.push(Value::Object(obj));
    }

    let mut payload = Map::new();
    payload.insert("schema_version".to_string(), json!("1"));
    payload.insert("task".to_string(), json!(task));
    if let Some(scope_path) = scope {
        payload.insert("scope".to_string(), json!(scope_path));
    }
    payload.insert("live_only".to_string(), json!(live_only));
    payload.insert("items".to_string(), Value::Array(shaped));
    Value::Object(payload)
}

// ---------------------------------------------------------------------------
// mcp/budget.py — serialize + the `items` truncation rule
// ---------------------------------------------------------------------------

/// `budget.serialize(payload, budget)` — Python-shaped JSON within `budget`
/// characters, truncating the retrieve `items` shape when needed.
pub fn serialize(payload: &Value, budget: i64) -> String {
    let text = dumps_compact(payload);
    if char_len(&text) <= budget {
        return text;
    }
    dumps_compact(&truncate_items(payload, budget))
}

fn with_marker(payload: &Value, kept: Vec<Value>, omitted: i64) -> Value {
    let mut marked = payload.as_object().expect("object payload").clone();
    marked.insert("items".to_string(), Value::Array(kept)); // keeps position
    marked.insert(MARKER_TRUNCATED.to_string(), json!(true));
    marked.insert(MARKER_OMITTED.to_string(), json!(omitted));
    marked.insert(MARKER_HINT.to_string(), json!(HINT_RETRIEVE));
    Value::Object(marked)
}

fn fits(candidate: &Value, budget: i64) -> bool {
    char_len(&dumps_compact(candidate)) <= budget
}

/// `_truncate_items(payload, budget)` — excerpt-first, then whole-item.
fn truncate_items(payload: &Value, budget: i64) -> Value {
    let items: Vec<Value> = payload["items"].as_array().cloned().unwrap_or_default();
    let total = items.len() as i64;
    let mut kept = items;
    while !kept.is_empty() {
        let omitted = total - kept.len() as i64;
        let candidate = with_marker(payload, kept.clone(), omitted);
        if fits(&candidate, budget) {
            return candidate;
        }
        // Trim the last kept item's excerpt before dropping it entirely.
        let mut last = kept
            .last()
            .and_then(Value::as_object)
            .expect("item object")
            .clone();
        let excerpt: String = last
            .get("excerpt")
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_string();
        let (mut lo, mut hi) = (0i64, char_len(&excerpt));
        let mut best: Option<i64> = None;
        while lo <= hi {
            let mid = (lo + hi).div_euclid(2);
            last.insert("excerpt".to_string(), json!(py_slice_to(&excerpt, mid)));
            let mut trial_items: Vec<Value> = kept[..kept.len() - 1].to_vec();
            trial_items.push(Value::Object(last.clone()));
            let trial = with_marker(payload, trial_items, omitted);
            if fits(&trial, budget) {
                best = Some(mid);
                lo = mid + 1;
            } else {
                hi = mid - 1;
            }
        }
        if let Some(best) = best {
            last.insert("excerpt".to_string(), json!(py_slice_to(&excerpt, best)));
            let mut final_items: Vec<Value> = kept[..kept.len() - 1].to_vec();
            final_items.push(Value::Object(last));
            return with_marker(payload, final_items, omitted);
        }
        kept.pop();
    }
    // Even an empty list does not fit: marked empty-list payload.
    with_marker(payload, Vec::new(), total)
}
