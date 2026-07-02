"""Artifact lookup and search — the engine behind `rac resolve` / `rac find`.

Everything here reads from the repository index; nothing walks the filesystem,
extracts identity, or classifies on its own. The CLI, Explorer, Watchkeeper, the
MCP server, and IDE integrations all consume these functions, so lookup
semantics cannot fork per consumer (ADR-015, ADR-026).

Two capabilities live side by side:

* **Exact resolution** answers "which artifact is this identifier?" with exactly
  one of three outcomes — resolved, not found, duplicate. A duplicate is never
  silently collapsed to one file by path order; it is reported with every path.

* **Search** (ADR-037/ADR-038) is deterministic token-boundary matching over a
  five-tier ladder (id, title, path, heading, body). A query term matches a
  token by casefolded equality or prefix; a multi-term query is an AND. The
  matched set is then ordered by a reproducible relevance score (ADR-078) that
  fuses a field-weighted BM25 lexical signal with a bounded inbound-edge graph
  signal — no embeddings, no learned model, no network.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from rac.core.corpus import walk_corpus
from rac.core.models import SearchSection
from rac.services.index import build_repository_index, index_from_corpus

OUTCOME_RESOLVED = "resolved"
OUTCOME_NOT_FOUND = "not-found"
OUTCOME_DUPLICATE = "duplicate"


class SearchableArtifact(Protocol):
    """The structural shape resolution and search consume.

    Defined as a Protocol (not a concrete class) so a caller already holding a
    loaded repository model can feed its artifacts straight in and reuse the
    exact `rac resolve` / `rac find` semantics without a second directory walk
    (ADR-026). Index entries and repository artifacts both satisfy it.
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


# --- Tokenization (ADR-037) --------------------------------------------------
#
# A token is a maximal run that is neither a non-alphanumeric boundary nor a
# camelCase seam. We split on both so `soft-delete` and `camelCaseWord` become
# separate searchable tokens and a query term matches on token boundaries rather
# than as a raw substring.

_NON_ALNUM_RE = re.compile(r"[^0-9A-Za-z]+")
_CAMEL_RE = re.compile(r"(?<=[a-z])(?=[A-Z])")


def tokenize(text: str) -> list[str]:
    """Split ``text`` into casefolded match tokens (ADR-037).

    Non-alphanumeric runs and lowercase-to-uppercase transitions both break
    tokens: ``soft-delete`` -> ``[soft, delete]``, ``camelCaseWord`` ->
    ``[camel, case, word]``, ``adr-002-legacy.md`` -> ``[adr, 002, legacy,
    md]``. Empty pieces are dropped, so an all-punctuation string yields ``[]``.
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


# --- Result shapes (stable JSON contract, ADR-007) ---------------------------


@dataclass
class ResolvedArtifact:
    """The identity answer for one resolution or search hit.

    ``section``/``snippet`` carry the matched heading and line for a heading or
    body *search* hit; they stay None for resolution and for id/title/path hits,
    and are then absent (not null) from ``to_dict`` — so the metadata-match shape
    is byte-identical to the pre-body-tier contract. ``evidence`` is the additive
    ``{field, terms, tier, score, components}`` object a search hit carries; it
    too is absent from ``to_dict`` when None or when evidence is suppressed, so
    the default `rac find` JSON stays byte-stable (ADR-007).
    """

    id: str
    type: str
    title: str | None
    path: str
    section: str | None = None
    snippet: str | None = None
    evidence: dict | None = None

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
    """Outcome of one exact-ID lookup."""

    artifact_id: str  # the query as given
    outcome: str  # OUTCOME_RESOLVED | OUTCOME_NOT_FOUND | OUTCOME_DUPLICATE
    artifact: ResolvedArtifact | None = None
    duplicate_paths: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        if self.outcome == OUTCOME_RESOLVED:
            assert self.artifact is not None  # a resolved outcome always carries the artifact
            return {"schema_version": "1", **self.artifact.to_dict()}
        payload: dict[str, Any] = {
            "schema_version": "1",
            "error": self.outcome,
            "id": self.artifact_id,
        }
        if self.duplicate_paths:
            payload["paths"] = self.duplicate_paths
        return payload


@dataclass
class SearchResult:
    """Outcome of one repository search."""

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


# --- Exact resolution --------------------------------------------------------


def resolve_artifact(directory: str, artifact_id: str, recursive: bool = True) -> ResolutionResult:
    """Resolve ``artifact_id`` to exactly one artifact under ``directory``.

    Matching is case-insensitive against every identifier an artifact answers to
    — its canonical ID and any legacy aliases — the same identity set
    relationship resolution uses. Two distinct files answering to the ID is a
    duplicate, reported with both paths and never resolved by order.
    """
    entries = build_repository_index(directory, recursive=recursive).artifacts
    return resolve_in_index(entries, artifact_id)


def resolve_in_index(entries: Sequence[SearchableArtifact], artifact_id: str) -> ResolutionResult:
    """Resolve ``artifact_id`` against an already-discovered index.

    The seam behind :func:`resolve_artifact`: identical outcomes, but a caller
    with a loaded model answers lookups without re-walking the directory.
    """
    wanted = artifact_id.strip().casefold()
    matches = [
        entry for entry in entries if any(alias.casefold() == wanted for alias in entry.aliases)
    ]
    if not matches:
        return ResolutionResult(artifact_id=artifact_id, outcome=OUTCOME_NOT_FOUND)
    if len(matches) > 1:
        return ResolutionResult(
            artifact_id=artifact_id,
            outcome=OUTCOME_DUPLICATE,
            duplicate_paths=sorted(entry.path for entry in matches),
        )
    return ResolutionResult(
        artifact_id=artifact_id,
        outcome=OUTCOME_RESOLVED,
        artifact=ResolvedArtifact.from_entry(matches[0]),
    )


# --- Match tiers and evidence (ADR-037/ADR-038) ------------------------------
#
# Field priority for a match, best (lowest) first: the ladder ADR-037/ADR-038
# pins. The winning tier is surfaced verbatim as match evidence — no second
# heuristic, no relevance score enters here (ADR-034).

_RANK_ID = 0
_RANK_TITLE = 1
_RANK_PATH = 2
_RANK_HEADING = 3
_RANK_BODY = 4

_RANK_NAMES: dict[int, str] = {
    _RANK_ID: "id",
    _RANK_TITLE: "title",
    _RANK_PATH: "path",
    _RANK_HEADING: "heading",
    _RANK_BODY: "body",
}


@dataclass
class _Match:
    """One artifact's best search hit: winning tier, snippet, matched terms.

    ``terms`` are the matched query terms in query order — the evidence the
    matcher already has in hand, kept rather than recomputed downstream.
    """

    rank: int
    section: str | None = None
    snippet: str | None = None
    terms: list[str] = field(default_factory=list)


def _evidence(match: _Match) -> dict:
    """The ``{field, terms, tier}`` evidence for a search hit (ADR-037)."""
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
    """Match evidence extended with the additive relevance components (ADR-078).

    Adds the fused score and its per-signal contributions so ``--explain`` (and
    the MCP payload) can show why one hit outranks another. The tier keys are
    untouched; ``schema_version`` is unchanged (ADR-007).
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
    """Every alias tokenized into one flat id-tier token list."""
    tokens: list[str] = []
    for alias in entry.aliases:
        tokens.extend(tokenize(alias))
    return tokens


def _match_entry(entry: SearchableArtifact, terms: Sequence[str]) -> _Match | None:
    """The best tiered match for an AND query, or None if any term misses.

    Every term must hit *somewhere* across the matchable fields (AND); the
    artifact then ranks by the best tier *any single* term reached. For a
    heading or body win, the snippet is the first matching line in document order
    — the heading text itself for a heading hit, the body line for a body hit —
    so snippets are deterministic (ADR-038).
    """
    id_tokens = _id_tokens(entry)
    title_tokens = tokenize(entry.title or "")
    path_tokens = tokenize(entry.path)

    matched_terms: set[str] = set()
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

    # Heading and body hits both need the source text (for the snippet), so they
    # are captured while scanning sections in document order — first hit wins.
    heading_hit: tuple[str, str] | None = None  # (section heading, snippet line)
    body_hit: tuple[str, str] | None = None
    for section in entry.search_sections:
        heading_tokens = tokenize(section.heading)
        for term in terms:
            if _term_hits_tokens(term, heading_tokens):
                matched_terms.add(term)
                if heading_hit is None:
                    heading_hit = (section.heading, section.heading)
        for line in section.lines:
            line_tokens = tokenize(line)
            for term in terms:
                if _term_hits_tokens(term, line_tokens):
                    matched_terms.add(term)
                    if body_hit is None:
                        body_hit = (section.heading, line)

    if heading_hit is not None and (best_rank is None or _RANK_HEADING < best_rank):
        best_rank = _RANK_HEADING
    if body_hit is not None and (best_rank is None or _RANK_BODY < best_rank):
        best_rank = _RANK_BODY

    # AND semantics: every query term must have matched at least one field.
    if best_rank is None or any(term not in matched_terms for term in terms):
        return None

    # Distinct query terms in query order — AND makes this every term, deduped.
    ordered_terms = [term for term in dict.fromkeys(terms) if term in matched_terms]

    if best_rank == _RANK_HEADING and heading_hit is not None:
        return _Match(
            rank=best_rank, section=heading_hit[0], snippet=heading_hit[1], terms=ordered_terms
        )
    if best_rank == _RANK_BODY and body_hit is not None:
        return _Match(rank=best_rank, section=body_hit[0], snippet=body_hit[1], terms=ordered_terms)
    return _Match(rank=best_rank, terms=ordered_terms)


# --- Search entry points -----------------------------------------------------


def find_artifacts(
    directory: str,
    query: str,
    artifact_type: str | None = None,
    recursive: bool = True,
) -> SearchResult:
    """Search artifacts under ``directory`` by id, title, path, heading, or body.

    Token-boundary matching (ADR-037), the five-tier ladder with body text
    (ADR-038), ordered by the deterministic relevance score (ADR-078). An empty
    result is a valid outcome, not an error.
    """
    entries = build_repository_index(directory, recursive=recursive).artifacts
    return search_index(entries, query, artifact_type=artifact_type)


# The single artifact type the live-decision query answers over. Named locally so
# the dependency on the agent-rules projection stays legible.
_DECISION_TYPE = "decision"


def find_decisions(directory: str, topic: str, recursive: bool = True) -> SearchResult:
    """Search *live* decisions under ``directory`` for ``topic`` (ADR-067).

    Two deterministic filters compose over the existing tiered search: restrict
    to decisions, then to the *live* ones — the same Accepted, non-retired
    predicate the agent-rules projection uses, so the definition never forks.
    Superseded or deprecated decisions are dropped even when their text matches.

    This is structural retrieval, not a verdict: it returns the decisions that
    bind the topic and leaves any contradiction judgement to the consuming agent
    (ADR-067). No semantic score is computed here or downstream. An empty result
    is a valid answer.
    """
    # Reuse the liveness predicate rather than re-deriving "Accepted and not
    # retired"; the rule behind the committed rules block must stay single-source.
    from rac.services.agent_rules import is_live_decision

    entries = list(walk_corpus(directory, recursive=recursive))
    live_paths = {
        str(entry.path)
        for entry in entries
        if entry.artifact_type == _DECISION_TYPE and is_live_decision(entry.product)
    }
    index = index_from_corpus(directory, entries, recursive=recursive).artifacts
    result = search_index(index, topic, artifact_type=_DECISION_TYPE)
    # Preserve ranking/order; only drop the non-live decisions.
    result.matches = [m for m in result.matches if m.path in live_paths]
    return result


# --- Deterministic relevance ranking: BM25F + graph, fused by RRF (ADR-078) --
#
# The matched set is ordered by a fused relevance score, not by tier then path.
# Two deterministic signals combine via Reciprocal Rank Fusion: a field-weighted
# BM25 lexical score and a bounded inbound-edge graph boost. No embeddings, no
# semantic scoring (ADR-038, ADR-066); the matched set and its {field, terms,
# tier} evidence are unchanged, and the score components are additive.
#
# These tunables are byte-pinned through the golden output — changing any of them
# (or the arithmetic below) shifts the sixth decimal and breaks the contract.

_RRF_K = 60  # the conventional RRF constant, the one recorded tunable.
_GRAPH_WEIGHT = 0.5  # graph boost weighted below lexical: it breaks near-ties, never dominates.
_BM25_K1 = 1.2  # term-frequency saturation.
_BM25_B = 0.75  # field-length normalisation strength.
# Field boosts mirror the tier order (id/title heaviest, body lightest), turning
# the old hard tier cutoff into a graded BM25F contribution. Insertion order is
# load-bearing: it fixes the summation order of the float score.
_FIELD_BOOSTS: dict[str, float] = {
    "id": 4.0,
    "title": 3.0,
    "path": 2.0,
    "heading": 1.5,
    "body": 1.0,
}


def _field_tokens(entry: SearchableArtifact) -> dict[str, list[str]]:
    """Match tokens per scorable field, via the same tokeniser matching uses."""
    headings: list[str] = []
    body: list[str] = []
    for section in entry.search_sections:
        headings.extend(tokenize(section.heading))
        for line in section.lines:
            body.extend(tokenize(line))
    return {
        "id": _id_tokens(entry),
        "title": tokenize(entry.title or ""),
        "path": tokenize(entry.path),
        "heading": headings,
        "body": body,
    }


def _tf(term: str, tokens: Sequence[str]) -> int:
    """Term frequency under ADR-037 matching (equality or prefix), not substring."""
    return sum(1 for token in tokens if token == term or token.startswith(term))


def _corpus_stats(
    entries: Sequence[SearchableArtifact], terms: Sequence[str]
) -> tuple[int, dict[str, int], dict[str, float], dict[str, dict[str, list[str]]]]:
    """Document count, per-term document frequency, mean field length, field tokens.

    Computed over the *whole* corpus so IDF and length normalisation are global
    (standard BM25), and the per-entry field tokens are cached here for the
    scorer to reuse rather than re-tokenize.
    """
    field_tokens_by_path: dict[str, dict[str, list[str]]] = {}
    length_sums: dict[str, int] = dict.fromkeys(_FIELD_BOOSTS, 0)
    df: dict[str, int] = dict.fromkeys(terms, 0)
    n = 0
    for entry in entries:
        n += 1
        fields = _field_tokens(entry)
        field_tokens_by_path[entry.path] = fields
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
    """1-based competition ranks (higher score is better), ties sharing a rank.

    Ordered by ``(-score, path)``; equal scores get the same rank so a signal
    never leaks path order onto candidates it does not actually distinguish
    (e.g. artifacts with equal inbound counts).
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
) -> SearchResult:
    """Search an already-discovered index with `rac find` semantics.

    Matching is the AND token-boundary ladder (ADR-037/ADR-038) and each hit
    carries its ``{field, terms, tier}`` evidence. Ordering is the deterministic
    relevance score (ADR-078): field-weighted BM25 and a bounded inbound-edge
    graph signal, fused by RRF and tie-broken by sorted path. The seam lets a
    loaded model serve searches without another directory walk.
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

    # Global BM25 statistics (IDF and mean field length over the whole corpus).
    n, df, avglen, field_tokens_by_path = _corpus_stats(entries, terms)
    bm25 = {e.path: _bm25f(field_tokens_by_path[e.path], terms, n, df, avglen) for e, _ in matched}
    inbound = {e.path: float(getattr(e, "inbound_count", 0)) for e, _ in matched}
    lexical_rank = _competition_ranks(bm25)
    graph_rank = _competition_ranks(inbound)
    fused = {
        path: 1.0 / (_RRF_K + lexical_rank[path]) + _GRAPH_WEIGHT / (_RRF_K + graph_rank[path])
        for path in bm25
    }

    # Fused score descending, sorted path as the tiebreak: total and byte-stable.
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
