//! Resolve & search (`rac resolve`, `rac find`) — a port of
//! `src/rac/services/resolve.py` (+ the index construction in
//! `src/rac/services/index.py`), per PORT-CONTRACT.d/06.
//!
//! Landmines reproduced here (contract §15):
//! - ASCII-only tokenizer (§1) vs full-Unicode casefold/strip in exact
//!   resolution (§3) and the `--tag` facet (§5.2).
//! - Corpus statistics are corpus-global (all types, unknowns included) even
//!   under `--type`/`--tag`; ranks are over the matched set only (§6).
//! - Duplicate query tokens are NOT deduped: `df` increments per occurrence
//!   and the per-term score adds per occurrence (§7.1).
//! - BM25F float operation ORDER is normative (§7): weighted_tf accumulates
//!   in `id, title, path, heading, body, tags` field order with zero-tf
//!   fields skipped; score accumulates in query-token order;
//!   `idf = ln(1 + (n - d + 0.5)/(d + 0.5))` via plain f64 ops (not ln_1p).
//! - Competition ranks share on EXACT f64 equality (§8).
//! - Sort key is `(-py_round(fused, 12), path)`; the stored fused value stays
//!   unrounded; evidence carries `py_round(., 6)` (§9–10).

use std::collections::{HashMap, HashSet};

use crate::identity::{artifact_identifier, artifact_identifiers};
use crate::markdown::SearchSection;
use crate::parse::Artifact;
use crate::pycompat::{first_nonempty_line, py_casefold, py_round, py_strip};
use crate::relationships::{
    corpus_items, edge_spec, resolution_index_from_rows, validation_row, CorpusItem,
};
use crate::spec::spec_for;

pub const OUTCOME_RESOLVED: &str = "resolved";
pub const OUTCOME_NOT_FOUND: &str = "not-found";
pub const OUTCOME_DUPLICATE: &str = "duplicate";

// Match-field tier ladder (ADR-037/038/109): id, title, tags, path, heading,
// body — lower rank wins.
const RANK_ID: i64 = 0;
const RANK_TITLE: i64 = 1;
const RANK_TAGS: i64 = 2;
const RANK_PATH: i64 = 3;
const RANK_HEADING: i64 = 4;
const RANK_BODY: i64 = 5;

fn rank_name(rank: i64) -> &'static str {
    match rank {
        RANK_ID => "id",
        RANK_TITLE => "title",
        RANK_TAGS => "tags",
        RANK_PATH => "path",
        RANK_HEADING => "heading",
        _ => "body",
    }
}

// BM25F constants (ADR-078).
const RRF_K: i64 = 60;
const GRAPH_WEIGHT: f64 = 0.5;
const BM25_K1: f64 = 1.2;
const BM25_B: f64 = 0.75;

/// `_FIELD_BOOSTS` in insertion order — `tags` is LAST, not at its tier
/// position (deliberate: preserves the pre-ADR-109 float summation order).
const FIELD_BOOSTS: [(&str, f64); 6] = [
    ("id", 4.0),
    ("title", 3.0),
    ("path", 2.0),
    ("heading", 1.5),
    ("body", 1.0),
    ("tags", 2.5),
];

// ---------------------------------------------------------------------------
// Tokenization (ADR-037) — ASCII-only splitter + ASCII camel seams
// ---------------------------------------------------------------------------

/// `tokenize(text)`: split on runs of non-`[0-9A-Za-z]` (every non-ASCII char
/// is a separator), split each piece at ASCII lowercase→uppercase seams, then
/// casefold (pure-ASCII pieces: exactly `A-Z -> a-z`).
pub fn tokenize(text: &str) -> Vec<String> {
    let mut tokens: Vec<String> = Vec::new();
    for piece in text.split(|c: char| !c.is_ascii_alphanumeric()) {
        if piece.is_empty() {
            continue;
        }
        let bytes = piece.as_bytes();
        let mut start = 0usize;
        for i in 1..bytes.len() {
            if bytes[i - 1].is_ascii_lowercase() && bytes[i].is_ascii_uppercase() {
                tokens.push(piece[start..i].to_ascii_lowercase());
                start = i;
            }
        }
        tokens.push(piece[start..].to_ascii_lowercase());
    }
    tokens
}

/// `_term_hits_tokens`: term equals or is a prefix of any token.
fn term_hits_tokens(term: &str, tokens: &[String]) -> bool {
    tokens.iter().any(|t| t.starts_with(term))
}

/// `_tf(term, tokens)`: count of tokens the term equals or prefixes.
fn tf(term: &str, tokens: &[String]) -> i64 {
    tokens.iter().filter(|t| t.starts_with(term)).count() as i64
}

// ---------------------------------------------------------------------------
// Index entries (rac.services.index.IndexEntry)
// ---------------------------------------------------------------------------

/// One searchable row of the repository index.
#[derive(Debug, Clone)]
pub struct IndexEntry {
    pub id: String,
    pub artifact_type: String,
    pub title: Option<String>,
    pub path: String,
    /// Canonical ID first, then legacy aliases (case-insensitively deduped).
    pub aliases: Vec<String>,
    pub search_sections: Vec<SearchSection>,
    /// Count of resolved inbound relationship edges (the graph signal).
    pub inbound_count: i64,
    /// Frontmatter tags, in frontmatter order.
    pub tags: Vec<String>,
}

/// The identity-only projection of an entry (the oracle's `_identity_index`):
/// `_identity_index` never reads tags/sections/graph, so those stay at their
/// empty defaults — the resolved artifact matches the oracle's shape exactly
/// and the discarded clones never happen.
fn identity_entry_from_item(item: &CorpusItem) -> IndexEntry {
    let artifact_type = item
        .spec
        .map(|s| s.name.clone())
        .unwrap_or_else(|| "unknown".to_string());
    IndexEntry {
        id: artifact_identifier(&item.artifact, item.spec, &item.path),
        artifact_type,
        title: item.artifact.product.title.clone(),
        path: item.path.clone(),
        aliases: artifact_identifiers(&item.artifact, item.spec, &item.path),
        search_sections: Vec::new(),
        inbound_count: 0,
        tags: Vec::new(),
    }
}

fn entry_from_item(item: &CorpusItem, inbound: i64) -> IndexEntry {
    IndexEntry {
        search_sections: item.artifact.product.search_sections.clone(),
        inbound_count: inbound,
        tags: item
            .artifact
            .metadata
            .as_ref()
            .map(|m| m.tags.clone())
            .unwrap_or_default(),
        ..identity_entry_from_item(item)
    }
}

/// `inbound_counts_from_corpus`: `{path -> count of resolved edges pointing
/// at it}` — resolved, unique, non-self edges only; external edges (ADR-087)
/// never resolve.
fn inbound_counts(items: &[CorpusItem]) -> HashMap<String, i64> {
    let rows: Vec<_> = items
        .iter()
        .map(|item| validation_row(&item.path, &item.artifact, item.spec))
        .collect();
    let index = resolution_index_from_rows(&rows);
    let mut counts: HashMap<String, i64> = HashMap::new();
    for row in &rows {
        for (section, refs) in &row.edges {
            let external = edge_spec(section).map(|e| e.external).unwrap_or(false);
            if external {
                continue;
            }
            for r in refs {
                let targets = index.get(&py_casefold(r));
                if targets.len() == 1 && targets[0].0 != row.path {
                    *counts.entry(targets[0].0.clone()).or_insert(0) += 1;
                }
            }
        }
    }
    counts
}

/// `build_repository_index(directory, recursive).artifacts` — the searchable
/// index in corpus-walk (sorted-path) order, inbound counts included.
pub fn build_index(directory: &str, recursive: bool) -> Vec<IndexEntry> {
    index_from_items(&corpus_items(directory, recursive))
}

pub fn index_from_items(items: &[CorpusItem]) -> Vec<IndexEntry> {
    let inbound = inbound_counts(items);
    items
        .iter()
        .map(|item| entry_from_item(item, *inbound.get(&item.path).unwrap_or(&0)))
        .collect()
}

// ---------------------------------------------------------------------------
// Exact resolution (contract §3)
// ---------------------------------------------------------------------------

/// One resolved artifact / search match (`ResolvedArtifact`).
#[derive(Debug, Clone)]
pub struct ResolvedArtifact {
    pub id: String,
    pub artifact_type: String,
    pub title: Option<String>,
    pub path: String,
    pub section: Option<String>,
    pub snippet: Option<String>,
    pub evidence: Option<Evidence>,
    pub recency: Option<Recency>,
    pub tags: Vec<String>,
}

/// The `--explain` evidence object plus the unrounded score components
/// (`bm25_raw`/`fused_raw` are not serialized; they exist so conformance
/// tests can assert exact f64 bit equality against the oracle).
#[derive(Debug, Clone)]
pub struct Evidence {
    pub field: &'static str,
    /// Distinct casefolded query tokens, in query order.
    pub terms: Vec<String>,
    pub tier: i64,
    /// `py_round(fused, 6)`.
    pub score: f64,
    /// `py_round(bm25, 6)`.
    pub bm25: f64,
    pub lexical_rank: i64,
    pub graph_rank: i64,
    pub inbound: i64,
    /// The unrounded BM25F score (test-only surface).
    pub bm25_raw: f64,
    /// The unrounded fused RRF score (test-only surface).
    pub fused_raw: f64,
}

/// The git-derived recency join (`Staleness.to_dict()` shape).
#[derive(Debug, Clone)]
pub struct Recency {
    pub last_committed: Option<String>,
    pub age_days: Option<i64>,
    pub stale: Option<bool>,
}

/// Outcome of one exact-ID lookup (`ResolutionResult`).
#[derive(Debug, Clone)]
pub struct ResolutionResult {
    /// The query as given (unstripped).
    pub artifact_id: String,
    pub outcome: &'static str,
    pub artifact: Option<ResolvedArtifact>,
    pub duplicate_paths: Vec<String>,
}

fn resolved_from_entry(entry: &IndexEntry) -> ResolvedArtifact {
    ResolvedArtifact {
        id: entry.id.clone(),
        artifact_type: entry.artifact_type.clone(),
        title: entry.title.clone(),
        path: entry.path.clone(),
        section: None,
        snippet: None,
        evidence: None,
        recency: None,
        tags: entry.tags.clone(),
    }
}

/// `resolve_in_index(entries, artifact_id)`: full-Unicode strip + casefold on
/// the query, casefolded exact equality against every alias.
pub fn resolve_in_index(entries: &[IndexEntry], artifact_id: &str) -> ResolutionResult {
    let wanted = py_casefold(py_strip(artifact_id));
    let matches: Vec<&IndexEntry> = entries
        .iter()
        .filter(|e| e.aliases.iter().any(|a| py_casefold(a) == wanted))
        .collect();
    if matches.is_empty() {
        return ResolutionResult {
            artifact_id: artifact_id.to_string(),
            outcome: OUTCOME_NOT_FOUND,
            artifact: None,
            duplicate_paths: Vec::new(),
        };
    }
    if matches.len() > 1 {
        let mut paths: Vec<String> = matches.iter().map(|e| e.path.clone()).collect();
        paths.sort(); // Python str sort = code-point order = UTF-8 byte order
        return ResolutionResult {
            artifact_id: artifact_id.to_string(),
            outcome: OUTCOME_DUPLICATE,
            artifact: None,
            duplicate_paths: paths,
        };
    }
    ResolutionResult {
        artifact_id: artifact_id.to_string(),
        outcome: OUTCOME_RESOLVED,
        artifact: Some(resolved_from_entry(matches[0])),
        duplicate_paths: Vec::new(),
    }
}

/// `resolve_artifact(directory, artifact_id, recursive)`. The oracle's
/// identity-only walk (`_identity_index`) leaves sections/graph/tags at their
/// empty defaults; resolve output reads only id/type/title/path, so those
/// fields never surface (resolve JSON never gains a "tags" key).
pub fn resolve_artifact(directory: &str, artifact_id: &str, recursive: bool) -> ResolutionResult {
    let items = corpus_items(directory, recursive);
    let entries: Vec<IndexEntry> = items.iter().map(identity_entry_from_item).collect();
    resolve_in_index(&entries, artifact_id)
}

// ---------------------------------------------------------------------------
// Tokenised entries (contract §4)
// ---------------------------------------------------------------------------

/// Flat per-field token vectors, one per scorable field.
#[derive(Debug, Clone, Default)]
pub struct FieldTokens {
    pub id: Vec<String>,
    pub title: Vec<String>,
    pub tags: Vec<String>,
    pub path: Vec<String>,
    pub heading: Vec<String>,
    pub body: Vec<String>,
}

impl FieldTokens {
    fn get(&self, name: &str) -> &Vec<String> {
        match name {
            "id" => &self.id,
            "title" => &self.title,
            "tags" => &self.tags,
            "path" => &self.path,
            "heading" => &self.heading,
            _ => &self.body,
        }
    }
}

struct SectionTokens {
    heading: String,
    heading_tokens: Vec<String>,
    lines: Vec<(String, Vec<String>)>,
}

struct EntryTokens {
    fields: FieldTokens,
    sections: Vec<SectionTokens>,
}

fn tokenize_entry(entry: &IndexEntry) -> EntryTokens {
    let mut sections: Vec<SectionTokens> = Vec::new();
    let mut heading_tokens: Vec<String> = Vec::new();
    let mut body_tokens: Vec<String> = Vec::new();
    for sec in &entry.search_sections {
        let sec_heading_tokens = tokenize(&sec.heading);
        heading_tokens.extend(sec_heading_tokens.iter().cloned());
        let mut sec_lines: Vec<(String, Vec<String>)> = Vec::new();
        for line in &sec.lines {
            let line_tokens = tokenize(line);
            body_tokens.extend(line_tokens.iter().cloned());
            sec_lines.push((line.clone(), line_tokens));
        }
        sections.push(SectionTokens {
            heading: sec.heading.clone(),
            heading_tokens: sec_heading_tokens,
            lines: sec_lines,
        });
    }
    let mut id_tokens: Vec<String> = Vec::new();
    for alias in &entry.aliases {
        id_tokens.extend(tokenize(alias));
    }
    let mut tag_tokens: Vec<String> = Vec::new();
    for tag in &entry.tags {
        tag_tokens.extend(tokenize(tag));
    }
    EntryTokens {
        fields: FieldTokens {
            id: id_tokens,
            title: tokenize(entry.title.as_deref().unwrap_or("")),
            tags: tag_tokens,
            path: tokenize(&entry.path),
            heading: heading_tokens,
            body: body_tokens,
        },
        sections,
    }
}

// ---------------------------------------------------------------------------
// Tier matching (contract §4)
// ---------------------------------------------------------------------------

struct TierMatch {
    rank: i64,
    section: Option<String>,
    snippet: Option<String>,
    /// Distinct matched terms, in query-token order.
    terms: Vec<String>,
}

fn match_entry(entry_tokens: &EntryTokens, terms: &[String]) -> Option<TierMatch> {
    let mut matched_terms: HashSet<&str> = HashSet::new();
    let mut best_rank: Option<i64> = None;
    let mut heading_snippet: Option<(String, String)> = None;
    let mut body_snippet: Option<(String, String)> = None;

    // Metadata tiers: id, title, tags, path — flat vectors, no snippet.
    for (rank, field) in [
        (RANK_ID, "id"),
        (RANK_TITLE, "title"),
        (RANK_TAGS, "tags"),
        (RANK_PATH, "path"),
    ] {
        let tokens = entry_tokens.fields.get(field);
        let mut any = false;
        for term in terms {
            if term_hits_tokens(term, tokens) {
                matched_terms.insert(term.as_str());
                any = true;
            }
        }
        if any && best_rank.is_none() {
            best_rank = Some(rank);
        }
    }

    // Heading tier: first matching heading in document order.
    {
        let mut any = false;
        for sec in &entry_tokens.sections {
            let mut hit = false;
            for term in terms {
                if term_hits_tokens(term, &sec.heading_tokens) {
                    matched_terms.insert(term.as_str());
                    hit = true;
                }
            }
            if hit {
                any = true;
                if heading_snippet.is_none() {
                    heading_snippet = Some((sec.heading.clone(), sec.heading.clone()));
                }
            }
        }
        if any && best_rank.is_none() {
            best_rank = Some(RANK_HEADING);
        }
    }

    // Body tier: first matching line in document order.
    {
        let mut any = false;
        for sec in &entry_tokens.sections {
            for (line, line_tokens) in &sec.lines {
                let mut hit = false;
                for term in terms {
                    if term_hits_tokens(term, line_tokens) {
                        matched_terms.insert(term.as_str());
                        hit = true;
                    }
                }
                if hit {
                    any = true;
                    if body_snippet.is_none() {
                        body_snippet = Some((sec.heading.clone(), line.clone()));
                    }
                }
            }
        }
        if any && best_rank.is_none() {
            best_rank = Some(RANK_BODY);
        }
    }

    // AND semantics: every distinct term must have matched somewhere.
    let distinct: HashSet<&str> = terms.iter().map(|t| t.as_str()).collect();
    if !distinct.is_subset(&matched_terms) {
        return None;
    }
    let best_rank = best_rank?;

    // Matched terms in query order, deduped (dict.fromkeys semantics).
    let mut seen: HashSet<&str> = HashSet::new();
    let mut ordered: Vec<String> = Vec::new();
    for term in terms {
        if seen.insert(term.as_str()) && matched_terms.contains(term.as_str()) {
            ordered.push(term.clone());
        }
    }

    // Only the winning tier's snippet is surfaced; metadata wins carry none.
    let snippet = match best_rank {
        RANK_HEADING => heading_snippet,
        RANK_BODY => body_snippet,
        _ => None,
    };
    let (section, snippet) = match snippet {
        Some((section, line)) => (Some(section), Some(line)),
        None => (None, None),
    };
    Some(TierMatch {
        rank: best_rank,
        section,
        snippet,
        terms: ordered,
    })
}

// ---------------------------------------------------------------------------
// Corpus statistics + BM25F (contract §6–7)
// ---------------------------------------------------------------------------

/// Corpus-global BM25 statistics (all entries, unknowns included).
pub struct CorpusStats {
    pub n: i64,
    /// Per-term document frequency; duplicate query terms double-count.
    pub df: HashMap<String, i64>,
    /// Mean field length in `FIELD_BOOSTS` order.
    pub avglen: [f64; 6],
}

fn corpus_stats(field_tokens: &[FieldTokens], terms: &[String]) -> CorpusStats {
    let n = field_tokens.len() as i64;
    let mut length_sums = [0i64; 6];
    let mut df: HashMap<String, i64> = HashMap::new();
    for term in terms {
        df.entry(term.clone()).or_insert(0);
    }
    for fields in field_tokens {
        for (i, (name, _)) in FIELD_BOOSTS.iter().enumerate() {
            length_sums[i] += fields.get(name).len() as i64;
        }
        // Duplicates iterate: a term appearing twice increments its df twice.
        for term in terms {
            if FIELD_BOOSTS
                .iter()
                .any(|(name, _)| tf(term, fields.get(name)) != 0)
            {
                *df.get_mut(term.as_str()).expect("df pre-seeded") += 1;
            }
        }
    }
    let mut avglen = [0.0f64; 6];
    for (i, sum) in length_sums.iter().enumerate() {
        avglen[i] = if n != 0 { *sum as f64 / n as f64 } else { 0.0 };
    }
    CorpusStats { n, df, avglen }
}

/// Corpus-global statistics for one query over `entries` — the conformance
/// vector surface (`gen_vectors_resolve.py` pins `n`/`df`/`avglen`).
pub fn stats_for(entries: &[IndexEntry], query: &str) -> CorpusStats {
    let terms = tokenize(query);
    let field_tokens: Vec<FieldTokens> = entries
        .iter()
        .map(|e| tokenize_entry(e).fields)
        .collect();
    corpus_stats(&field_tokens, &terms)
}

/// `_bm25f` — the EXACT f64 operation sequence (contract §7).
fn bm25f(fields: &FieldTokens, terms: &[String], stats: &CorpusStats) -> f64 {
    let mut score = 0.0f64;
    for term in terms {
        // QUERY-TOKEN ORDER, DUPLICATES INCLUDED
        let d = *stats.df.get(term.as_str()).unwrap_or(&0);
        if d == 0 {
            continue;
        }
        // arg = 1 + (n - d + 0.5)/(d + 0.5) — plain add, then ln (not ln_1p).
        let num = (stats.n - d) as f64 + 0.5;
        let den = d as f64 + 0.5;
        let idf = (1.0 + num / den).ln();
        let mut weighted_tf = 0.0f64;
        for (i, (name, boost)) in FIELD_BOOSTS.iter().enumerate() {
            let tokens = fields.get(name);
            let tfv = tf(term, tokens);
            if tfv == 0 {
                continue; // zero-tf fields are SKIPPED (no +0.0 term)
            }
            let length = tokens.len() as i64;
            let mean = stats.avglen[i];
            let denom = if mean > 0.0 {
                1.0 - BM25_B + BM25_B * (length as f64 / mean)
            } else {
                1.0
            };
            weighted_tf += boost * (tfv as f64 / denom);
        }
        if weighted_tf > 0.0 {
            score += idf * (weighted_tf / (BM25_K1 + weighted_tf));
        }
    }
    score
}

/// `_competition_ranks`: 1-based, ties (EXACT f64 equality) share a rank,
/// ordered by `(-score, path)`.
fn competition_ranks(scores: &[(String, f64)]) -> HashMap<String, i64> {
    let mut ordered: Vec<&(String, f64)> = scores.iter().collect();
    ordered.sort_by(|a, b| {
        b.1.partial_cmp(&a.1)
            .expect("finite score")
            .then_with(|| a.0.cmp(&b.0))
    });
    let mut ranks: HashMap<String, i64> = HashMap::new();
    let mut previous: Option<f64> = None;
    let mut rank = 0i64;
    for (position, (path, score)) in ordered.iter().enumerate() {
        let position = position as i64 + 1;
        if Some(*score) != previous {
            rank = position;
            previous = Some(*score);
        }
        ranks.insert(path.clone(), rank);
    }
    ranks
}

// ---------------------------------------------------------------------------
// Search (contract §4–10)
// ---------------------------------------------------------------------------

/// Outcome of one repository search (`SearchResult`).
#[derive(Debug, Clone)]
pub struct SearchResult {
    pub query: String,
    /// The `--type` value; `"decision"` under `--decisions`; else None.
    pub artifact_type: Option<String>,
    pub matches: Vec<ResolvedArtifact>,
}

/// `_entry_has_tags`: exact whole-tag comparison, full Unicode casefold.
fn entry_has_tags(entry: &IndexEntry, wanted: &[String]) -> bool {
    let have: HashSet<String> = entry.tags.iter().map(|t| py_casefold(t)).collect();
    wanted.iter().all(|w| have.contains(w))
}

/// `search_index(entries, query, artifact_type, tags)` — matching, corpus
/// stats, BM25F + RRF ranking, and the `(-round(fused,12), path)` sort.
pub fn search_index(
    entries: &[IndexEntry],
    query: &str,
    artifact_type: Option<&str>,
    tags: &[String],
) -> SearchResult {
    search_index_filtered(entries, query, artifact_type, tags, false)
}

/// `entry_is_retired(entry)` — the `live_only` facet (ADR-113): re-read the
/// entry's `## Status` from its file and test it against the type's
/// `retired_status` set (`is_retired_status`). Unreadable/unknown ⇒ live.
pub fn entry_is_retired(entry: &IndexEntry) -> bool {
    let status = artifact_status(&crate::parse::parse_file(&entry.path));
    is_retired_status(&entry.artifact_type, &status)
}

/// `agent_rules.is_retired_status(artifact_type, status)` (ADR-113):
/// spec-driven retirement for every typed artifact. An unknown type retires
/// nothing; an empty status is never retired.
pub fn is_retired_status(artifact_type: &str, status: &str) -> bool {
    let Some(spec) = spec_for(artifact_type) else {
        return false;
    };
    let wanted = py_casefold(status);
    spec.retired_status.iter().any(|s| py_casefold(s) == wanted)
}

/// `search_index(..., live_only=...)` (ADR-113, additive): with `live_only`,
/// retired artifacts of every type are dropped from the matched set BEFORE
/// scoring, so competition ranks are computed among the live survivors. With
/// `live_only=false` the result is byte-identical to `search_index`.
pub fn search_index_filtered(
    entries: &[IndexEntry],
    query: &str,
    artifact_type: Option<&str>,
    tags: &[String],
    live_only: bool,
) -> SearchResult {
    let terms = tokenize(query);
    let tag_filter: Vec<String> = tags.iter().map(|t| py_casefold(t)).collect();
    let mut matched: Vec<(usize, TierMatch)> = Vec::new();
    let mut tokenized: Vec<Option<EntryTokens>> = Vec::with_capacity(entries.len());
    tokenized.resize_with(entries.len(), || None);
    if !terms.is_empty() {
        for (i, entry) in entries.iter().enumerate() {
            if let Some(t) = artifact_type {
                if entry.artifact_type != t {
                    continue;
                }
            }
            if !tag_filter.is_empty() && !entry_has_tags(entry, &tag_filter) {
                continue;
            }
            let entry_tokens = tokenize_entry(entry);
            let m = match_entry(&entry_tokens, &terms);
            tokenized[i] = Some(entry_tokens);
            if let Some(m) = m {
                matched.push((i, m));
            }
        }
    }
    // The live-only facet filters the matched set before scoring (ADR-113), so
    // competition ranks are computed among the live survivors — only matched
    // files are re-read, never the whole corpus.
    if live_only && !matched.is_empty() {
        matched.retain(|(i, _)| !entry_is_retired(&entries[*i]));
    }
    if matched.is_empty() {
        return SearchResult {
            query: query.to_string(),
            artifact_type: artifact_type.map(str::to_string),
            matches: Vec::new(),
        };
    }

    // Corpus-wide statistics over EVERY entry (type/tag-excluded included).
    let field_tokens: Vec<FieldTokens> = entries
        .iter()
        .enumerate()
        .map(|(i, entry)| match tokenized[i].take() {
            Some(t) => t.fields,
            None => tokenize_entry(entry).fields,
        })
        .collect();
    let stats = corpus_stats(&field_tokens, &terms);

    // Score the matched set only.
    let bm25_scores: Vec<(String, f64)> = matched
        .iter()
        .map(|(i, _)| {
            (
                entries[*i].path.clone(),
                bm25f(&field_tokens[*i], &terms, &stats),
            )
        })
        .collect();
    let inbound_scores: Vec<(String, f64)> = matched
        .iter()
        .map(|(i, _)| (entries[*i].path.clone(), entries[*i].inbound_count as f64))
        .collect();
    let lexical_rank = competition_ranks(&bm25_scores);
    let graph_rank = competition_ranks(&inbound_scores);
    let bm25_by_path: HashMap<&str, f64> =
        bm25_scores.iter().map(|(p, s)| (p.as_str(), *s)).collect();
    let fused: HashMap<String, f64> = bm25_scores
        .iter()
        .map(|(path, _)| {
            let f = 1.0 / ((RRF_K + lexical_rank[path]) as f64)
                + GRAPH_WEIGHT / ((RRF_K + graph_rank[path]) as f64);
            (path.clone(), f)
        })
        .collect();

    // Fused score descending (rounded to 12 places inside the key only),
    // ties broken by path: total and byte-stable.
    matched.sort_by(|a, b| {
        let fa = py_round(fused[&entries[a.0].path], 12);
        let fb = py_round(fused[&entries[b.0].path], 12);
        fb.partial_cmp(&fa)
            .expect("finite fused")
            .then_with(|| entries[a.0].path.cmp(&entries[b.0].path))
    });

    let matches: Vec<ResolvedArtifact> = matched
        .into_iter()
        .map(|(i, m)| {
            let entry = &entries[i];
            let path = entry.path.as_str();
            let fused_raw = fused[path];
            let bm25_raw = bm25_by_path[path];
            ResolvedArtifact {
                id: entry.id.clone(),
                artifact_type: entry.artifact_type.clone(),
                title: entry.title.clone(),
                path: entry.path.clone(),
                section: m.section,
                snippet: m.snippet,
                evidence: Some(Evidence {
                    field: rank_name(m.rank),
                    terms: m.terms,
                    tier: m.rank,
                    score: py_round(fused_raw, 6),
                    bm25: py_round(bm25_raw, 6),
                    lexical_rank: lexical_rank[path],
                    graph_rank: graph_rank[path],
                    inbound: entry.inbound_count,
                    bm25_raw,
                    fused_raw,
                }),
                recency: None,
                tags: entry.tags.clone(),
            }
        })
        .collect();

    SearchResult {
        query: query.to_string(),
        artifact_type: artifact_type.map(str::to_string),
        matches,
    }
}

/// `find_artifacts(directory, query, artifact_type, recursive, tags, live_only)`.
pub fn find_artifacts(
    directory: &str,
    query: &str,
    artifact_type: Option<&str>,
    recursive: bool,
    tags: &[String],
    live_only: bool,
) -> SearchResult {
    let entries = build_index(directory, recursive);
    search_index_filtered(&entries, query, artifact_type, tags, live_only)
}

// ---------------------------------------------------------------------------
// Live decision query (`--decisions`, ADR-067)
// ---------------------------------------------------------------------------

/// `agent_rules.artifact_status`: first non-empty stripped line of `## Status`.
pub fn artifact_status(artifact: &Artifact) -> String {
    artifact
        .section("status")
        .map(first_nonempty_line)
        .unwrap_or("")
        .to_string()
}

/// `agent_rules.is_live_decision`: Accepted and not retired.
pub(crate) fn is_live_decision(artifact: &Artifact) -> bool {
    let status = py_casefold(&artifact_status(artifact));
    if status != "accepted" {
        return false;
    }
    let retired: Vec<String> = spec_for("decision")
        .map(|s| s.retired_status.iter().map(|r| py_casefold(r)).collect())
        .unwrap_or_default();
    !retired.contains(&status)
}

/// `find_decisions(directory, topic, recursive)`: the type-restricted tiered
/// search, post-filtered to live decisions (ranks keep their gaps — evidence
/// is computed over all matched decisions including non-live ones).
pub fn find_decisions(directory: &str, topic: &str, recursive: bool) -> SearchResult {
    let items = corpus_items(directory, recursive);
    let live: HashSet<String> = items
        .iter()
        .filter(|item| {
            item.spec.map(|s| s.name.as_str()) == Some("decision")
                && is_live_decision(&item.artifact)
        })
        .map(|item| item.path.clone())
        .collect();
    let entries = index_from_items(&items);
    let mut result = search_index(&entries, topic, Some("decision"), &[]);
    result.matches.retain(|m| live.contains(&m.path));
    result
}

#[cfg(test)]
mod tests {
    use super::*;

    fn toks(s: &str) -> Vec<String> {
        tokenize(s)
    }

    #[test]
    fn tokenize_contract_examples() {
        assert_eq!(toks("soft-delete"), vec!["soft", "delete"]);
        assert_eq!(toks("camelCase"), vec!["camel", "case"]);
        assert_eq!(toks("HTTPServer"), vec!["httpserver"]);
        assert_eq!(
            toks("MiXeD-Case_fooBAR"),
            vec!["mi", "xe", "d", "case", "foo", "bar"]
        );
        assert_eq!(toks("v0.22.0"), vec!["v0", "22", "0"]);
        assert_eq!(toks("ADR-037"), vec!["adr", "037"]);
        assert_eq!(toks("foo_barBaz2Qux"), vec!["foo", "bar", "baz2qux"]);
        assert_eq!(toks("caf\u{e9}"), vec!["caf"]);
        assert_eq!(toks("e\u{301}clair"), vec!["e", "clair"]);
        assert_eq!(toks("\u{130}stanbul"), vec!["stanbul"]);
        assert_eq!(toks("Stra\u{df}e"), vec!["stra", "e"]);
        assert_eq!(toks("..."), Vec::<String>::new());
        assert_eq!(toks(""), Vec::<String>::new());
    }

    #[test]
    fn prefix_matching_is_one_directional() {
        let tokens = vec!["searching".to_string()];
        assert!(term_hits_tokens("sear", &tokens));
        assert!(term_hits_tokens("searching", &tokens));
        assert!(!term_hits_tokens("searchingx", &tokens));
        assert_eq!(tf("sear", &tokens), 1);
    }

    #[test]
    fn competition_ranks_share_on_exact_equality() {
        let scores = vec![
            ("a".to_string(), 2.0),
            ("b".to_string(), 2.0),
            ("c".to_string(), 1.0),
        ];
        let ranks = competition_ranks(&scores);
        assert_eq!(ranks["a"], 1);
        assert_eq!(ranks["b"], 1);
        assert_eq!(ranks["c"], 3);
    }
}
