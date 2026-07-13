//! Store-served search (ADR-104) — `rac find` answered from the memory-
//! mapped base, byte-identical to the fresh walk (INDEX-PLAN B3).
//!
//! The candidate set comes from the term-major postings and only candidates
//! are reconstructed; the corpus-global statistics the scorer needs — n and
//! the per-field Σ from the header, document frequency from the prefix
//! ranges — carry the non-matching corpus's contribution without touching
//! its rows. Matching, snippets, and ranking run through the one shared
//! `rank_and_build` tail, so warm bytes equal cold bytes by construction.
//!
//! Deliberate divergence from the oracle's warm path (PORT-CONTRACT.d/10
//! §0a): a query term listed twice contributes its document frequency once
//! per OCCURRENCE here, exactly as the fresh walk counts it. The oracle's
//! store path dedups (an ADR-112 violation recorded as an oracle defect);
//! the native engine keeps warm == cold instead.

use crate::index_store::MmapIndexReader;
use crate::resolve::{
    entry_has_tags, entry_is_retired, match_entry, rank_and_build, tokenize, tokenize_entry,
    CorpusStats, SearchResult,
};

/// `rac find` served from the store — reproduces `search_index_filtered`.
pub fn store_search(
    reader: &MmapIndexReader,
    query: &str,
    artifact_type: Option<&str>,
    tags: &[String],
    live_only: bool,
) -> SearchResult {
    let terms = tokenize(query);
    let empty = || SearchResult {
        query: query.to_string(),
        artifact_type: artifact_type.map(str::to_string),
        matches: Vec::new(),
    };
    if terms.is_empty() {
        return empty();
    }
    let tag_filter: Vec<String> = tags.iter().map(|t| crate::pycompat::py_casefold(t)).collect();

    // Candidate docids: the union of each term's prefix-range postings —
    // ascending, so the matched set keeps walk (docid) order.
    let mut candidates: std::collections::BTreeSet<u32> = std::collections::BTreeSet::new();
    for term in &terms {
        match reader.prefix_docids(term) {
            Ok(docids) => candidates.extend(docids),
            Err(_) => return empty(), // corrupt row mid-read: valid empty, never a crash
        }
    }

    let mut matched = Vec::new();
    for docid in candidates {
        let Ok(entry) = reader.full_entry(docid) else {
            continue;
        };
        if let Some(t) = artifact_type {
            if entry.artifact_type != t {
                continue;
            }
        }
        if !tag_filter.is_empty() && !entry_has_tags(&entry, &tag_filter) {
            continue;
        }
        let entry_tokens = tokenize_entry(&entry);
        if let Some(m) = match_entry(&entry_tokens, &terms) {
            matched.push((entry, entry_tokens, m));
        }
    }
    if live_only && !matched.is_empty() {
        matched.retain(|(entry, _, _)| !entry_is_retired(entry));
    }
    if matched.is_empty() {
        return empty();
    }

    // Corpus-global statistics from the store's integer accumulators: the
    // same values the walk derives, without materialising unmatched rows.
    let n = i64::from(reader.doc_count);
    let mut avglen = [0.0f64; 6];
    for (i, sum) in reader.field_length_sums.iter().enumerate() {
        avglen[i] = if n != 0 { *sum as f64 / n as f64 } else { 0.0 };
    }
    let mut df: std::collections::HashMap<String, i64> = std::collections::HashMap::new();
    let mut occurrences: std::collections::HashMap<&str, i64> = std::collections::HashMap::new();
    for term in &terms {
        *occurrences.entry(term.as_str()).or_insert(0) += 1;
    }
    for (term, occ) in occurrences {
        let doc_count = reader
            .prefix_docids(term)
            .map(|d| d.len() as i64)
            .unwrap_or(0);
        // Per-OCCURRENCE df, the fresh walk's accounting (see module doc).
        df.insert(term.to_string(), occ * doc_count);
    }
    let stats = CorpusStats { n, df, avglen };

    let scored: Vec<_> = matched
        .iter()
        .map(|(entry, tokens, m)| (entry, &tokens.fields, m.clone()))
        .collect();
    rank_and_build(query, artifact_type, scored, &terms, &stats)
}

/// Live-decision topic search served from the store (ADR-067): the
/// decision-typed search, then the liveness filter over the precomputed
/// live-decision paths — `ReadModelView.find_decisions`.
pub fn store_find_decisions(reader: &MmapIndexReader, topic: &str) -> SearchResult {
    let mut result = store_search(reader, topic, Some("decision"), &[], false);
    let live: std::collections::HashSet<String> =
        reader.live_decision_paths().unwrap_or_default().into_iter().collect();
    result.matches.retain(|m| live.contains(&m.path));
    result
}

/// `find_decisions_in` over already-derived structures — the fresh-build
/// arm of the cache seam (`_find_from_store`'s `else` branch).
pub fn find_decisions_in(
    entries: &[crate::resolve::IndexEntry],
    live_paths: &[String],
    topic: &str,
) -> SearchResult {
    let mut result = crate::resolve::search_index(entries, topic, Some("decision"), &[]);
    let live: std::collections::HashSet<&str> = live_paths.iter().map(String::as_str).collect();
    result.matches.retain(|m| live.contains(m.path.as_str()));
    result
}
