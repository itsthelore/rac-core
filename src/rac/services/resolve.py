"""Artifact lookup and resolution — `rac resolve` / `rac find` (v0.7.12).

Built strictly on the repository index (the dependency direction pinned by the
roadmap): no independent file discovery, identity extraction, or
classification happens here. Explorer, Watchkeeper, CI, and IDE integrations
consume these same functions, so lookup behavior cannot fork per consumer
(ADR-015, ADR-026).

Exact resolution has exactly three outcomes — resolved, not found, duplicate —
and a duplicate is never silently resolved by path order. Resolution stays
exact-match against an artifact's identifier set.

Search (v0.10.3, ADR-037/ADR-038) is deterministic, tiered, token-boundary
matching: identifiers, title, path, section headings, and body text are
tokenized on non-alphanumeric boundaries and camelCase transitions; a query
term matches a token by casefolded equality or prefix; a multi-term query
requires every term to match somewhere in the artifact (AND). Matches rank by
the best field any term hit — identifier, then title, then path, then heading,
then body — with sorted path as the tiebreak. Heading and body matches carry
snippet fields (the matched heading and the matching line, as stored).
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from rac.core.corpus import CorpusEntry, walk_corpus
from rac.core.models import SearchSection
from rac.services.index import build_repository_index, index_from_corpus

OUTCOME_RESOLVED = "resolved"
OUTCOME_NOT_FOUND = "not-found"
OUTCOME_DUPLICATE = "duplicate"


class SearchableArtifact(Protocol):
    """Anything resolvable/searchable: index entries, repository artifacts.

    Structural (v0.8.1) so consumers holding an already-loaded repository
    model can reuse the exact `rac resolve` / `rac find` semantics without
    re-walking the directory (ADR-026).
    """

    @property
    def id(self) -> str: ...
    @property
    def type(self) -> str: ...
    @property
    def title(self) -> str | None: ...
    @property
    def path(self) -> str: ...
    @property
    def aliases(self) -> Sequence[str]: ...
    @property
    def search_sections(self) -> Sequence[SearchSection]: ...
    @property
    def inbound_count(self) -> int: ...


# Match-field priority for search ordering (lower ranks first); the ladder
# pinned by ADR-037/ADR-038: id, then title, then path, then heading, then body.
_RANK_ID = 0
_RANK_TITLE = 1
_RANK_PATH = 2
_RANK_HEADING = 3
_RANK_BODY = 4

# Tier number -> field name, the projection ADR-037's ladder exposes as match
# evidence (WS2 explainable retrieval): the winning rank named, no new compute.
_RANK_NAMES: dict[int, str] = {
    _RANK_ID: "id",
    _RANK_TITLE: "title",
    _RANK_PATH: "path",
    _RANK_HEADING: "heading",
    _RANK_BODY: "body",
}

# A token is a maximal run that is neither a non-alphanumeric boundary nor a
# camelCase transition. We split on both: ``_TOKEN_SPLIT`` breaks on runs of
# non-alphanumerics, then ``_CAMEL_SPLIT`` breaks lowercase->uppercase seams.
_NON_ALNUM_RE = re.compile(r"[^0-9A-Za-z]+")
_CAMEL_RE = re.compile(r"(?<=[a-z])(?=[A-Z])")


def tokenize(text: str) -> list[str]:
    """Split ``text`` into casefolded match tokens (ADR-037).

    Tokens break on non-alphanumeric boundaries and on lowercase-to-uppercase
    (camelCase) transitions: ``soft-delete`` -> ``[soft, delete]``,
    ``relationships`` -> ``[relationships]``, ``Explorer`` -> ``[explorer]``,
    ``camelCase`` -> ``[camel, case]``. Empty pieces are dropped.
    """
    tokens: list[str] = []
    for piece in _NON_ALNUM_RE.split(text):
        if not piece:
            continue
        for sub in _CAMEL_RE.split(piece):
            if sub:
                tokens.append(sub.casefold())
    return tokens


def _term_hits_tokens(term: str, tokens: Sequence[str]) -> bool:
    """True when ``term`` equals or is a prefix of any token (ADR-037)."""
    return any(token == term or token.startswith(term) for token in tokens)


@dataclass
class ResolvedArtifact:
    """The canonical answer to "what artifact is this ID?" (ADR-026).

    ``section`` and ``snippet`` (v0.10.3, additive) carry the matched section
    heading and matching line for heading/body search matches; both stay None
    for resolution and for id/title/path search matches, and are absent (not
    null) from ``to_dict`` then — the metadata-match shape is byte-identical to
    pre-v0.10.3 (ADR-007).
    """

    id: str
    type: str
    title: str | None
    path: str
    section: str | None = None
    snippet: str | None = None
    # Match evidence (v0.23.0, WS2, additive): the winning field/tier and matched
    # terms for a *search* hit — ``{field, terms, tier}`` (ADR-037/ADR-038). None
    # for resolution and absent from ``to_dict`` then, so the exact-lookup shape
    # is unchanged. Always set for a search match; the gate it answers to is
    # ``include_evidence`` so the CLI's default ``rac find`` JSON stays byte-stable.
    evidence: dict | None = None
    # Git-derived staleness (freshness phase 1, additive): last-committed date
    # plus the staleness indicator, joined by the read surface *after* ranking so
    # matching and order are unchanged (ADR-045, ADR-078). None for resolution and
    # for search until a surface enriches it, and absent from ``to_dict`` then, so
    # the pre-freshness shape is byte-identical (ADR-007).
    recency: dict | None = None

    def to_dict(self, *, include_evidence: bool = True) -> dict:
        payload: dict[str, Any] = {
            "id": self.id,
            "type": self.type,
            "title": self.title,
            "path": self.path,
        }
        if self.section is not None:
            payload["section"] = self.section
        if self.snippet is not None:
            payload["snippet"] = self.snippet
        if include_evidence and self.evidence is not None:
            payload["evidence"] = self.evidence
        if self.recency is not None:
            payload["recency"] = self.recency
        return payload

    @classmethod
    def from_entry(
        cls,
        entry: SearchableArtifact,
        *,
        section: str | None = None,
        snippet: str | None = None,
        evidence: dict | None = None,
    ) -> ResolvedArtifact:
        return cls(
            id=entry.id,
            type=entry.type,
            title=entry.title,
            path=entry.path,
            section=section,
            snippet=snippet,
            evidence=evidence,
        )


@dataclass
class ResolutionResult:
    """Outcome of one exact-ID lookup (stable JSON contract, ADR-007)."""

    artifact_id: str  # the query as given
    outcome: str  # OUTCOME_RESOLVED | OUTCOME_NOT_FOUND | OUTCOME_DUPLICATE
    artifact: ResolvedArtifact | None = None
    duplicate_paths: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        if self.outcome == OUTCOME_RESOLVED:
            assert self.artifact is not None  # resolved outcome implies an artifact
            return {"schema_version": "1", **self.artifact.to_dict()}
        payload: dict = {
            "schema_version": "1",
            "error": self.outcome,
            "id": self.artifact_id,
        }
        if self.duplicate_paths:
            payload["paths"] = self.duplicate_paths
        return payload


@dataclass
class SearchResult:
    """Outcome of one repository search (stable JSON contract, ADR-007)."""

    query: str
    artifact_type: str | None
    matches: list[ResolvedArtifact] = field(default_factory=list)

    @property
    def match_count(self) -> int:
        return len(self.matches)

    def to_dict(self, *, include_evidence: bool = True) -> dict:
        return {
            "schema_version": "1",
            "query": self.query,
            "type": self.artifact_type,
            "match_count": self.match_count,
            "matches": [m.to_dict(include_evidence=include_evidence) for m in self.matches],
        }


def resolve_artifact(directory: str, artifact_id: str, recursive: bool = True) -> ResolutionResult:
    """Resolve ``artifact_id`` to exactly one artifact under ``directory``.

    Matching is case-insensitive against every identifier an artifact answers
    to — the canonical ID and its legacy aliases — the same identity set
    relationship resolution uses. Multiple *distinct files* matching is a
    duplicate, reported with every path and never resolved by order.
    """
    entries = build_repository_index(directory, recursive=recursive).artifacts
    return resolve_in_index(entries, artifact_id)


def resolve_in_index(entries: Sequence[SearchableArtifact], artifact_id: str) -> ResolutionResult:
    """Resolve ``artifact_id`` against already-discovered entries (v0.8.1).

    Same outcomes and semantics as :func:`resolve_artifact`; the seam lets a
    loaded repository model answer lookups without another directory walk.
    """
    wanted = artifact_id.strip().casefold()
    matches: list[SearchableArtifact] = []
    for entry in entries:
        if any(alias.casefold() == wanted for alias in entry.aliases):
            matches.append(entry)
    if not matches:
        return ResolutionResult(artifact_id=artifact_id, outcome=OUTCOME_NOT_FOUND)
    if len(matches) > 1:
        return ResolutionResult(
            artifact_id=artifact_id,
            outcome=OUTCOME_DUPLICATE,
            duplicate_paths=sorted(e.path for e in matches),
        )
    return ResolutionResult(
        artifact_id=artifact_id,
        outcome=OUTCOME_RESOLVED,
        artifact=ResolvedArtifact.from_entry(matches[0]),
    )


@dataclass
class _Match:
    """A search hit: the winning tier, snippet for heading/body, matched terms.

    ``terms`` is the matched-terms set the matcher already computes (WS2), kept
    in query order and surfaced as evidence rather than recomputed (ADR-037).
    """

    rank: int
    section: str | None = None
    snippet: str | None = None
    terms: list[str] = field(default_factory=list)


def _evidence(match: _Match) -> dict:
    """The additive match ``evidence`` object for a search hit (WS2, ADR-037).

    ``{field, terms, tier}``: the winning field name, the matched query terms in
    query order, and the numeric tier — read off the matcher's existing rank and
    matched-terms set, never a second heuristic or a relevance score (ADR-034).
    """
    return {"field": _RANK_NAMES[match.rank], "terms": list(match.terms), "tier": match.rank}


def _score_evidence(
    match: _Match,
    *,
    fused: float,
    bm25: float,
    lexical_rank: int,
    graph_rank: int,
    inbound: int,
) -> dict:
    """The match evidence plus the additive relevance-score components (ADR-078).

    Extends ``{field, terms, tier}`` with the fused score and its per-signal
    contributions, so ``--explain`` and the JSON show why one hit outranks
    another. ``schema_version`` is unchanged; the existing keys are untouched
    (ADR-007).
    """
    evidence = _evidence(match)
    evidence["score"] = round(fused, 6)
    evidence["components"] = {
        "bm25": round(bm25, 6),
        "lexical_rank": lexical_rank,
        "graph_rank": graph_rank,
        "inbound": inbound,
    }
    return evidence


def _id_tokens(entry: SearchableArtifact) -> list[str]:
    tokens: list[str] = []
    for alias in entry.aliases:
        tokens.extend(tokenize(alias))
    return tokens


def _match_entry(entry: SearchableArtifact, terms: Sequence[str]) -> _Match | None:
    """Best tiered match for an AND query, or None when a term matches nothing.

    Every term of ``terms`` must match somewhere in the artifact's matchable
    fields (id, title, path, headings, body); the artifact then ranks by the
    best (lowest) tier *any* term hit (ADR-037). For a heading/body win, the
    snippet is the first matching line in document order — the heading itself
    for a heading hit, the body line for a body hit (ADR-038, deterministic).
    """
    id_tokens = _id_tokens(entry)
    title_tokens = tokenize(entry.title or "")
    path_tokens = tokenize(entry.path)

    # Per term: does any term hit each metadata tier? (AND requires every term
    # match *somewhere*; ranking uses the best tier any *single* term reached.)
    matched_terms = set()
    best_rank: int | None = None

    def consider(rank: int, tokens: Sequence[str]) -> None:
        nonlocal best_rank
        for term in terms:
            if _term_hits_tokens(term, tokens):
                matched_terms.add(term)
                if best_rank is None or rank < best_rank:
                    best_rank = rank

    consider(_RANK_ID, id_tokens)
    consider(_RANK_TITLE, title_tokens)
    consider(_RANK_PATH, path_tokens)

    # Heading/body tiers, with the snippet captured at the first matching line
    # in document order. Headings rank above body; within each, document order.
    heading_hit: tuple[str, str] | None = None  # (section_heading, snippet_line)
    body_hit: tuple[str, str] | None = None
    for sec in entry.search_sections:
        heading_tokens = tokenize(sec.heading)
        for term in terms:
            if _term_hits_tokens(term, heading_tokens):
                matched_terms.add(term)
                if heading_hit is None:
                    heading_hit = (sec.heading, sec.heading)
        for line in sec.lines:
            line_tokens = tokenize(line)
            for term in terms:
                if _term_hits_tokens(term, line_tokens):
                    matched_terms.add(term)
                    if body_hit is None:
                        body_hit = (sec.heading, line)

    if heading_hit is not None and (best_rank is None or _RANK_HEADING < best_rank):
        best_rank = _RANK_HEADING
    if body_hit is not None and (best_rank is None or _RANK_BODY < best_rank):
        best_rank = _RANK_BODY

    # AND semantics: every term must have matched at least one field.
    if any(term not in matched_terms for term in terms):
        return None
    if best_rank is None:
        return None

    # Matched terms in query order (deduped) — the evidence the matcher already
    # has (WS2). AND semantics make this every distinct query term.
    ordered_terms = [term for term in dict.fromkeys(terms) if term in matched_terms]

    if best_rank == _RANK_HEADING and heading_hit is not None:
        return _Match(
            rank=best_rank, section=heading_hit[0], snippet=heading_hit[1], terms=ordered_terms
        )
    if best_rank == _RANK_BODY and body_hit is not None:
        return _Match(rank=best_rank, section=body_hit[0], snippet=body_hit[1], terms=ordered_terms)
    return _Match(rank=best_rank, terms=ordered_terms)


def find_artifacts(
    directory: str,
    query: str,
    artifact_type: str | None = None,
    recursive: bool = True,
) -> SearchResult:
    """Search artifacts under ``directory`` by id, title, path, heading, or body.

    Deterministic and explainable (no ranking heuristics): token-boundary
    matching (ADR-037), the five-tier ladder with body text (ADR-038), results
    ordered by match-field priority then sorted path. An empty result is a
    valid outcome, not an error.
    """
    entries = build_repository_index(directory, recursive=recursive).artifacts
    return search_index(entries, query, artifact_type=artifact_type)


# --- Live decision query (v0.21.16, ADR-067) ---------------------------------
#
# The deterministic "what did we decide about X / is X ruled out" retrieval. The
# engine asserts *which live decisions bind a topic* — structural search filtered
# to decisions, then to the live ones — and stops there. It never asserts that a
# change is *wrong*: semantic contradiction stays in the consuming agent, which
# reads the engine-supplied decisions and judges (ADR-067). No scoring enters the
# engine; ranking is the same explainable tiered ladder `rac find` already uses.

# Decisions are the artifact type the query answers over. The same constant the
# agent-rules projection scopes to, named locally so the dependency reads cleanly.
_DECISION_TYPE = "decision"


def find_decisions(directory: str, topic: str, recursive: bool = True) -> SearchResult:
    """Search *live* decisions under ``directory`` for ``topic`` (ADR-067).

    Two deterministic filters compose over the existing tiered search: the type
    filter restricts to decisions, and a liveness filter — the same Accepted,
    non-retired predicate the agent-rules projection uses (one source of truth,
    never duplicated) — drops superseded/deprecated decisions even when their
    text matches the topic. Ranking is the explainable id/title/path/heading/body
    ladder (ADR-037/ADR-038); an empty result is a valid answer (a query always
    succeeds), not an error.

    This is structural retrieval, not a verdict: it returns the decisions that
    bind the topic and lets the agent judge contradiction (ADR-067). No semantic
    score is computed here or anywhere downstream.
    """
    entries = list(walk_corpus(directory, recursive=recursive))
    live_paths = live_decision_paths(entries)
    index = index_from_corpus(directory, entries, recursive=recursive).artifacts
    return find_decisions_in(index, live_paths, topic)


def live_decision_paths(entries: Sequence[CorpusEntry]) -> list[str]:
    """The paths of the live (Accepted, non-retired) decisions in a snapshot.

    A pure function of the corpus, so the derived-index cache (ADR-099) can
    persist it alongside the index. Reuses the agent-rules liveness predicate
    rather than re-deriving "Accepted and not retired" — the definition must not
    fork (the same rule the committed rules block is built from).
    """
    from rac.services.agent_rules import is_live_decision

    return [
        str(entry.path)
        for entry in entries
        if entry.artifact_type == _DECISION_TYPE and is_live_decision(entry.product)
    ]


def find_decisions_in(
    index_entries: Sequence[SearchableArtifact],
    live_paths: Sequence[str],
    topic: str,
    *,
    field_tokens_by_path: dict[str, dict[str, list[str]]] | None = None,
) -> SearchResult:
    """Live-decision topic search over already-derived structures (ADR-067).

    The cache-friendly core of :func:`find_decisions`: given the repository index,
    the live-decision paths, and optionally the precomputed field tokens (all pure
    functions of the corpus the derived-index cache persists, ADR-099), it runs
    the same type-restricted tiered search and liveness filter, byte-identical to
    the fresh path. Ranking/order is preserved; an empty result is a valid answer.
    """
    result = search_index(
        index_entries,
        topic,
        artifact_type=_DECISION_TYPE,
        field_tokens_by_path=field_tokens_by_path,
    )
    live = set(live_paths)
    # Drop matches that are decisions but not live; ranking/order is preserved.
    result.matches = [m for m in result.matches if m.path in live]
    return result


# --- Deterministic relevance ranking (ADR-078): BM25 + RRF + graph boost -----
#
# Ordering replaces the old "best tier, then path" sort with a fused relevance
# score. Two deterministic signals — a field-weighted BM25 lexical score and a
# bounded graph boost (inbound resolved-edge count) — are combined with
# Reciprocal Rank Fusion. No embeddings, no semantic scoring (ADR-038, ADR-066);
# the matched set and the {field, terms, tier} evidence are unchanged, and the
# score components are additive under `--explain` (ADR-007).

_RRF_K = 60  # the conventional RRF constant, the one recorded tunable (ADR-078).
# The graph signal is bounded below lexical relevance (REQ-004: a connected
# artifact ranks higher only *at equal lexical relevance*), so its fused
# contribution is weighted down — it breaks near-ties, never overrides a clear
# lexical winner. This is the design's "capped, not dominant" graph boost.
_GRAPH_WEIGHT = 0.5
_BM25_K1 = 1.2  # term-frequency saturation.
_BM25_B = 0.75  # field-length normalisation strength.
# Field boosts mirror the old tier order (id/title heaviest, body lightest),
# turning the hard tier cutoff into a graded BM25F contribution.
_FIELD_BOOSTS: dict[str, float] = {
    "id": 4.0,
    "title": 3.0,
    "path": 2.0,
    "heading": 1.5,
    "body": 1.0,
}


def _field_tokens(entry: SearchableArtifact) -> dict[str, list[str]]:
    """Match tokens per scorable field, using the same tokeniser as matching."""
    headings: list[str] = []
    body: list[str] = []
    for sec in entry.search_sections:
        headings.extend(tokenize(sec.heading))
        for line in sec.lines:
            body.extend(tokenize(line))
    return {
        "id": _id_tokens(entry),
        "title": tokenize(entry.title or ""),
        "path": tokenize(entry.path),
        "heading": headings,
        "body": body,
    }


def field_tokens_for_entries(
    entries: Sequence[SearchableArtifact],
) -> dict[str, dict[str, list[str]]]:
    """The per-entry BM25 field tokens for a whole corpus — the tokenised field
    vectors the derived-index cache persists (ADR-099).

    Uses the same tokeniser (:func:`_field_tokens`) the scorer consumes, so cached
    tokens yield byte-identical search statistics and scores to the fresh path.
    """
    return {entry.path: _field_tokens(entry) for entry in entries}


def _tf(term: str, tokens: Sequence[str]) -> int:
    """Term frequency under ADR-037 matching (equality or prefix), not substring."""
    return sum(1 for token in tokens if token == term or token.startswith(term))


def _corpus_stats(
    entries: Sequence[SearchableArtifact],
    terms: Sequence[str],
    field_tokens_by_path: dict[str, dict[str, list[str]]] | None = None,
) -> tuple[int, dict[str, int], dict[str, float], dict[str, dict[str, list[str]]]]:
    """Document count, per-term document frequency, mean field length, field tokens.

    Computed once over the whole corpus so IDF and length normalisation are
    global (standard BM25), and the per-entry field tokens are cached for reuse
    by the scorer.

    ``field_tokens_by_path`` may be supplied precomputed — the derived-index cache
    (ADR-099) persists exactly this tokenisation, the expensive per-call work — in
    which case the re-tokenisation is skipped and only the cheap query-dependent
    document frequencies are recounted. The derived counts (``n``, ``avglen``,
    ``df``) are byte-identical either way: they are pure aggregates of the same
    tokens, independent of how the tokens were obtained.
    """
    if field_tokens_by_path is None:
        field_tokens_by_path = {entry.path: _field_tokens(entry) for entry in entries}
    length_sums: dict[str, int] = dict.fromkeys(_FIELD_BOOSTS, 0)
    df: dict[str, int] = dict.fromkeys(terms, 0)
    n = 0
    for fields in field_tokens_by_path.values():
        n += 1
        for name in _FIELD_BOOSTS:
            length_sums[name] += len(fields[name])
        for term in terms:
            if any(_tf(term, fields[name]) for name in _FIELD_BOOSTS):
                df[term] += 1
    avglen = {name: (length_sums[name] / n if n else 0.0) for name in _FIELD_BOOSTS}
    return n, df, avglen, field_tokens_by_path


def _bm25f(
    fields: dict[str, list[str]],
    terms: Sequence[str],
    n: int,
    df: dict[str, int],
    avglen: dict[str, float],
) -> float:
    """A field-weighted BM25 score for one artifact over the query terms."""
    score = 0.0
    for term in terms:
        d = df.get(term, 0)
        if d == 0:
            continue
        idf = math.log(1 + (n - d + 0.5) / (d + 0.5))
        weighted_tf = 0.0
        for name, boost in _FIELD_BOOSTS.items():
            tokens = fields.get(name, [])
            tf = _tf(term, tokens)
            if tf == 0:
                continue
            mean = avglen.get(name, 0.0)
            denom = 1.0 - _BM25_B + _BM25_B * (len(tokens) / mean) if mean > 0 else 1.0
            weighted_tf += boost * (tf / denom)
        if weighted_tf > 0:
            score += idf * (weighted_tf / (_BM25_K1 + weighted_tf))
    return score


def _competition_ranks(scores: dict[str, float]) -> dict[str, int]:
    """1-based ranks (higher score → better), ties sharing a rank, by path order.

    Equal scores get the same rank so a signal never leaks path order onto
    candidates it does not actually distinguish (e.g. equal inbound counts).
    """
    ordered = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    ranks: dict[str, int] = {}
    previous: float | None = None
    rank = 0
    for position, (path, score) in enumerate(ordered, start=1):
        if previous is None or score != previous:
            rank = position
            previous = score
        ranks[path] = rank
    return ranks


def search_index(
    entries: Sequence[SearchableArtifact],
    query: str,
    artifact_type: str | None = None,
    *,
    field_tokens_by_path: dict[str, dict[str, list[str]]] | None = None,
) -> SearchResult:
    """Search already-discovered entries with `rac find` semantics (v0.8.1).

    Matching is unchanged (ADR-037/038): a multi-term query requires every term
    to hit somewhere, and the result carries the same `{field, terms, tier}`
    evidence. Ordering is the deterministic relevance score (ADR-078): a
    field-weighted BM25 lexical signal and a bounded inbound-reference graph
    signal, fused by RRF, tie-broken by sorted path. The seam lets a loaded
    repository model serve searches without another directory walk.

    ``field_tokens_by_path`` may be supplied precomputed (the derived-index cache,
    ADR-099): it must cover exactly ``entries``, and the result is byte-identical
    to computing it fresh — only the per-call re-tokenisation is skipped.
    """
    terms = tokenize(query)
    matched: list[tuple[SearchableArtifact, _Match]] = []
    if terms:  # an all-punctuation query tokenizes to nothing: no matches.
        for entry in entries:
            if artifact_type is not None and entry.type != artifact_type:
                continue
            match = _match_entry(entry, terms)
            if match is not None:
                matched.append((entry, match))
    if not matched:
        return SearchResult(query=query, artifact_type=artifact_type, matches=[])

    # Corpus-wide BM25 statistics (global IDF and mean field length, ADR-078).
    n, df, avglen, field_tokens_by_path = _corpus_stats(entries, terms, field_tokens_by_path)
    bm25 = {e.path: _bm25f(field_tokens_by_path[e.path], terms, n, df, avglen) for e, _ in matched}
    inbound = {e.path: float(getattr(e, "inbound_count", 0)) for e, _ in matched}
    lexical_rank = _competition_ranks(bm25)
    graph_rank = _competition_ranks(inbound)
    fused = {
        path: 1.0 / (_RRF_K + lexical_rank[path]) + _GRAPH_WEIGHT / (_RRF_K + graph_rank[path])
        for path in bm25
    }

    # Fused score descending, ties broken by sorted path: total and byte-stable.
    matched.sort(key=lambda em: (-round(fused[em[0].path], 12), em[0].path))
    return SearchResult(
        query=query,
        artifact_type=artifact_type,
        matches=[
            ResolvedArtifact.from_entry(
                e,
                section=m.section,
                snippet=m.snippet,
                evidence=_score_evidence(
                    m,
                    fused=fused[e.path],
                    bm25=bm25[e.path],
                    lexical_rank=lexical_rank[e.path],
                    graph_rank=graph_rank[e.path],
                    inbound=int(inbound[e.path]),
                ),
            )
            for e, m in matched
        ],
    )
