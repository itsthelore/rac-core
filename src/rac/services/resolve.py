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
requires every term to match somewhere in the artifact (AND). The matched set is
ordered by a deterministic relevance score (ADR-078): a field-weighted BM25F
lexical signal and a bounded inbound-reference graph signal, fused by Reciprocal
Rank Fusion, with the fused score rounded to 12 places and the artifact path as
the final tiebreak — the sort key is ``(-round(fused, 12), path)``. Heading and
body matches carry snippet fields (the matched heading and the matching line, as
stored).
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from rac.core.artifacts import spec_for
from rac.core.corpus import CorpusEntry, walk_corpus
from rac.core.identity import artifact_identifier, artifact_identifiers
from rac.core.models import SearchSection
from rac.services.index import IndexEntry, build_repository_index, index_from_corpus

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
    @property
    def tags(self) -> Sequence[str]: ...


# Match-field priority for search ordering (lower ranks first); the ladder pinned
# by ADR-037/ADR-038 and extended by ADR-109 with a tags tier between title and
# path: id, title, tags, path, heading, body. A curated tag outranks an
# incidental path token but not the artifact's own title.
_RANK_ID = 0
_RANK_TITLE = 1
_RANK_TAGS = 2
_RANK_PATH = 3
_RANK_HEADING = 4
_RANK_BODY = 5

# Tier number -> field name, the projection ADR-037's ladder exposes as match
# evidence (WS2 explainable retrieval): the winning rank named, no new compute.
_RANK_NAMES: dict[int, str] = {
    _RANK_ID: "id",
    _RANK_TITLE: "title",
    _RANK_TAGS: "tags",
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
    # Frontmatter tags (ADR-109, additive): surfaced on a *search* hit so a caller
    # sees why it matched and what else the artifact carries. Emitted from
    # ``to_dict`` only when non-empty, so an untagged hit is byte-identical to the
    # pre-tags shape (ADR-007); the identity-only ``rac index`` manifest is
    # unchanged.
    tags: list[str] = field(default_factory=list)

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
        if self.tags:
            payload["tags"] = self.tags
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
            tags=list(getattr(entry, "tags", ())),
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
    entries = _identity_index(directory, recursive=recursive)
    return resolve_in_index(entries, artifact_id)


def _identity_index(directory: str, recursive: bool) -> list[IndexEntry]:
    """Identity-only inventory for exact resolution (aliases + path).

    Resolution reads only an entry's aliases and path (and, for the resolved
    answer, its id/type/title). It never reads the inbound-edge graph signal or
    the searchable sections, so this walk skips both — no relationship
    resolution (``inbound_counts_from_corpus``) and no ``SearchSection``
    construction — the work the full :func:`build_repository_index` does for the
    *search* path but that a one-ID lookup wastes. The id/type/title/path/aliases
    it produces are byte-identical to :func:`index_from_corpus`; only the unused
    graph and section fields are left at their empty defaults.
    """
    entries: list[IndexEntry] = []
    for entry in walk_corpus(directory, recursive=recursive):
        path = str(entry.path)
        product = entry.product
        spec = spec_for(entry.artifact_type)  # None for Unknown
        entries.append(
            IndexEntry(
                id=artifact_identifier(product, spec, path),
                type=entry.artifact_type,
                title=product.title,
                path=path,
                aliases=artifact_identifiers(product, spec, path),
            )
        )
    return entries


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


@dataclass
class _SectionTokens:
    """One section tokenised once: heading plus each body line and its tokens.

    Retains the section/line structure (in document order) the matcher needs to
    pick a snippet — the first matching line in document order — which the flat
    BM25 field vectors alone cannot reproduce.
    """

    heading: str
    heading_tokens: list[str]
    lines: list[tuple[str, list[str]]]


@dataclass
class _EntryTokens:
    """An entry tokenised once per search call.

    Carries both the flat per-field token vectors the BM25F scorer consumes
    (``{id, title, path, heading, body}``) and the section structure the matcher
    needs for snippet selection — both derived from a single tokenisation pass,
    so a search tokenises each entry once rather than once to match and again to
    score.
    """

    fields: dict[str, list[str]]
    sections: list[_SectionTokens]


def _tokenize_entry(entry: SearchableArtifact) -> _EntryTokens:
    """Tokenise every scorable field of ``entry`` exactly once (ADR-037).

    The flat ``heading``/``body`` vectors are the concatenation of the per-section
    heading tokens and per-line body tokens in document order — byte-identical to
    the previous separate :func:`_field_tokens` pass — while the section list
    preserves the per-line structure the snippet rule depends on.
    """
    sections: list[_SectionTokens] = []
    heading_tokens: list[str] = []
    body_tokens: list[str] = []
    for sec in entry.search_sections:
        sec_heading_tokens = tokenize(sec.heading)
        heading_tokens.extend(sec_heading_tokens)
        sec_lines: list[tuple[str, list[str]]] = []
        for line in sec.lines:
            line_tokens = tokenize(line)
            body_tokens.extend(line_tokens)
            sec_lines.append((line, line_tokens))
        sections.append(_SectionTokens(sec.heading, sec_heading_tokens, sec_lines))
    fields = {
        "id": _id_tokens(entry),
        "title": tokenize(entry.title or ""),
        # Tags tokenise by the same ADR-037 rule as every field: a multi-word tag
        # like ``data-model`` yields ``data``/``model``, so a query term matches a
        # tag uniformly (ADR-109). The facet (``_entry_has_tags``) matches the raw
        # whole tag instead — a deliberately different mechanism.
        "tags": [token for tag in getattr(entry, "tags", ()) for token in tokenize(tag)],
        "path": tokenize(entry.path),
        "heading": heading_tokens,
        "body": body_tokens,
    }
    return _EntryTokens(fields=fields, sections=sections)


# A tier matcher inspects one field family of an entry against the query terms
# and returns ``(matched_terms, snippet)``: the set of terms that hit this tier
# (whose non-emptiness makes the tier a candidate for ``best_rank``), and, for
# the snippet-bearing tiers, the ``(section_heading, snippet_line)`` captured at
# the first match in document order (``None`` for metadata tiers, which carry no
# snippet — ADR-038). The set is order-independent; ``best_rank`` and the query
# order of surfaced terms are recovered by :func:`_match_entry`, so a tier
# matcher never needs to know the tier ladder it sits in.
_TierMatcher = Callable[["_EntryTokens", Sequence[str]], tuple[set[str], tuple[str, str] | None]]


def _match_field(field: str) -> _TierMatcher:
    """A metadata tier matcher over one flat field vector (id/title/path).

    Metadata matches carry no snippet (ADR-038): the returned snippet is always
    ``None``; only the set of terms hitting the field is reported.
    """

    def matcher(entry_tokens: _EntryTokens, terms: Sequence[str]) -> tuple[set[str], None]:
        tokens = entry_tokens.fields[field]
        return {term for term in terms if _term_hits_tokens(term, tokens)}, None

    return matcher


def _match_headings(
    entry_tokens: _EntryTokens, terms: Sequence[str]
) -> tuple[set[str], tuple[str, str] | None]:
    """The heading tier: terms hitting any section heading, snippet = the first
    matching heading in document order (its own text — ADR-038)."""
    matched: set[str] = set()
    snippet: tuple[str, str] | None = None
    for sec in entry_tokens.sections:
        hits = {term for term in terms if _term_hits_tokens(term, sec.heading_tokens)}
        if hits:
            matched |= hits
            if snippet is None:
                snippet = (sec.heading, sec.heading)
    return matched, snippet


def _match_body(
    entry_tokens: _EntryTokens, terms: Sequence[str]
) -> tuple[set[str], tuple[str, str] | None]:
    """The body tier: terms hitting any body line, snippet = the first matching
    line in document order, sectioned under its heading (ADR-038)."""
    matched: set[str] = set()
    snippet: tuple[str, str] | None = None
    for sec in entry_tokens.sections:
        for line, line_tokens in sec.lines:
            hits = {term for term in terms if _term_hits_tokens(term, line_tokens)}
            if hits:
                matched |= hits
                if snippet is None:
                    snippet = (sec.heading, line)
    return matched, snippet


# The tier ladder as data, not control flow (ADR-037/ADR-038): an ordered list of
# ``(rank, matcher)`` from best to worst — id, title, path, heading, body. A
# lower rank wins; :func:`_match_entry` iterates this in order, so the precedence
# lives in the sequence, and each tier is independently testable.
_TIERS: tuple[tuple[int, _TierMatcher], ...] = (
    (_RANK_ID, _match_field("id")),
    (_RANK_TITLE, _match_field("title")),
    (_RANK_TAGS, _match_field("tags")),
    (_RANK_PATH, _match_field("path")),
    (_RANK_HEADING, _match_headings),
    (_RANK_BODY, _match_body),
)


def _match_entry(entry_tokens: _EntryTokens, terms: Sequence[str]) -> _Match | None:
    """Best tiered match for an AND query, or None when a term matches nothing.

    Every term of ``terms`` must match somewhere in the artifact's matchable
    fields (id, title, path, headings, body); the artifact then ranks by the
    best (lowest) tier *any* term hit (ADR-037). For a heading/body win, the
    snippet is the first matching line in document order — the heading itself
    for a heading hit, the body line for a body hit (ADR-038, deterministic). A
    metadata win carries no snippet even when a lower tier also matched.

    Runs the :data:`_TIERS` ladder in order over an :class:`_EntryTokens`
    tokenised once by :func:`_tokenize_entry`, so the same tokens feed matching
    and scoring without a second pass.
    """
    matched_terms: set[str] = set()
    best_rank: int | None = None
    snippets: dict[int, tuple[str, str]] = {}
    for rank, matcher in _TIERS:
        hits, snippet = matcher(entry_tokens, terms)
        if not hits:
            continue
        matched_terms |= hits
        if best_rank is None:  # _TIERS is ascending, so the first hit is the best rank.
            best_rank = rank
        if snippet is not None:
            snippets[rank] = snippet

    # AND semantics: every term must have matched at least one field. (With no
    # terms, or none matched, ``best_rank`` stays None — an empty query matches
    # nothing.)
    if not set(terms) <= matched_terms or best_rank is None:
        return None

    # Matched terms in query order (deduped) — the evidence the matcher already
    # has (WS2). AND semantics make this every distinct query term.
    ordered_terms = [term for term in dict.fromkeys(terms) if term in matched_terms]

    # Only the winning tier's snippet is surfaced: metadata tiers store none, so a
    # metadata win yields ``section``/``snippet`` None even if heading/body matched.
    snippet = snippets.get(best_rank)
    if snippet is not None:
        return _Match(rank=best_rank, section=snippet[0], snippet=snippet[1], terms=ordered_terms)
    return _Match(rank=best_rank, terms=ordered_terms)


def find_artifacts(
    directory: str,
    query: str,
    artifact_type: str | None = None,
    recursive: bool = True,
    *,
    tags: Sequence[str] | None = None,
) -> SearchResult:
    """Search artifacts under ``directory`` by id, title, tags, path, heading, or body.

    Deterministic and explainable (no ranking heuristics): token-boundary
    matching (ADR-037), the tiered ladder with a tags tier and body text
    (ADR-038/ADR-109), results ordered by match-field priority then sorted path.
    ``tags`` narrows the matched set to artifacts carrying every requested tag
    (the ``--tag`` facet). An empty result is a valid outcome, not an error.
    """
    entries = build_repository_index(directory, recursive=recursive).artifacts
    return search_index(entries, query, artifact_type=artifact_type, tags=tags)


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
# turning the hard tier cutoff into a graded BM25F contribution. ``tags`` is
# appended LAST, not at its tier position (rank 2), so the original five fields
# keep their exact float-summation order — the parity-critical one the store
# depends on (ADR-109); an untagged artifact adds a ``+0.0`` tags term, leaving
# its score byte-identical. The boost value (2.5, above path, below title), not
# the dict position, is the BM25F ranking lever.
_FIELD_BOOSTS: dict[str, float] = {
    "id": 4.0,
    "title": 3.0,
    "path": 2.0,
    "heading": 1.5,
    "body": 1.0,
    "tags": 2.5,
}


def _field_tokens(entry: SearchableArtifact) -> dict[str, list[str]]:
    """Match tokens per scorable field, using the same tokeniser as matching.

    A thin projection of :func:`_tokenize_entry` to the flat BM25 field vectors,
    so the cache-persistence path and the search path share one tokeniser.
    """
    return _tokenize_entry(entry).fields


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
    return _bm25f_scored(
        terms,
        n,
        df,
        avglen,
        tf_of=lambda term, name: _tf(term, fields.get(name, [])),
        len_of=lambda name: len(fields.get(name, [])),
    )


def _bm25f_scored(
    terms: Sequence[str],
    n: int,
    df: dict[str, int],
    avglen: dict[str, float],
    *,
    tf_of: Callable[[str, str], int],
    len_of: Callable[[str], int],
) -> float:
    """BM25F over supplied per-field tf and length lookups — the scoring seam (ADR-104).

    The arithmetic and its summation order (outer over query terms, inner over
    ``_FIELD_BOOSTS`` insertion order) are the single source of truth every scoring
    path reuses. :func:`_bm25f` supplies token-list lookups; the persistent index
    store supplies prefix-range/accumulator lookups. Because tf, df, n, and length
    are integers, identical integers yield byte-identical floats however obtained,
    so this factoring is behaviour-preserving for the token-list path.
    """
    score = 0.0
    for term in terms:
        d = df.get(term, 0)
        if d == 0:
            continue
        idf = math.log(1 + (n - d + 0.5) / (d + 0.5))
        weighted_tf = 0.0
        for name, boost in _FIELD_BOOSTS.items():
            tf = tf_of(term, name)
            if tf == 0:
                continue
            length = len_of(name)
            mean = avglen.get(name, 0.0)
            denom = 1.0 - _BM25_B + _BM25_B * (length / mean) if mean > 0 else 1.0
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


def _entry_has_tags(entry: SearchableArtifact, wanted: frozenset[str]) -> bool:
    """Whether ``entry`` carries every tag in ``wanted`` (the ``--tag`` facet).

    Exact whole-tag match, casefolded (tags are case-insensitive labels, ADR-109):
    ``--tag data-model`` matches only that tag, never the token ``model``. AND
    across the requested set — a narrowing filter, like the query's term AND.
    """
    return wanted <= {tag.casefold() for tag in getattr(entry, "tags", ())}


def search_index(
    entries: Sequence[SearchableArtifact],
    query: str,
    artifact_type: str | None = None,
    *,
    field_tokens_by_path: dict[str, dict[str, list[str]]] | None = None,
    tags: Sequence[str] | None = None,
) -> SearchResult:
    """Search already-discovered entries with `rac find` semantics (v0.8.1).

    Matching is unchanged (ADR-037/038): a multi-term query requires every term
    to hit somewhere, and the result carries the same `{field, terms, tier}`
    evidence. Ordering is the deterministic relevance score (ADR-078): a
    field-weighted BM25 lexical signal and a bounded inbound-reference graph
    signal, fused by RRF, with the fused score rounded to 12 places and the
    artifact path as the final tiebreak — the sort key is
    ``(-round(fused, 12), path)``. The seam lets a loaded repository model serve
    searches without another directory walk.

    ``field_tokens_by_path`` may be supplied precomputed (the derived-index cache,
    ADR-099): it must cover exactly ``entries``, and the result is byte-identical
    to computing it fresh — only the per-call re-tokenisation is skipped.
    """
    terms = tokenize(query)
    # The tag facet is a pre-scoring constraint applied alongside the type filter,
    # so surviving results rank among themselves while corpus-wide BM25 stats stay
    # corpus-global (IDF unchanged, ADR-109). Empty/None means no facet.
    tag_filter = frozenset(t.casefold() for t in tags) if tags else frozenset()
    matched: list[tuple[SearchableArtifact, _Match]] = []
    # Field vectors of the entries the matcher tokenised this call, reused below
    # for the corpus statistics so each entry is tokenised at most once.
    matched_field_tokens: dict[str, dict[str, list[str]]] = {}
    if terms:  # an all-punctuation query tokenizes to nothing: no matches.
        for entry in entries:
            if artifact_type is not None and entry.type != artifact_type:
                continue
            if tag_filter and not _entry_has_tags(entry, tag_filter):
                continue
            entry_tokens = _tokenize_entry(entry)
            matched_field_tokens[entry.path] = entry_tokens.fields
            match = _match_entry(entry_tokens, terms)
            if match is not None:
                matched.append((entry, match))
    if not matched:
        return SearchResult(query=query, artifact_type=artifact_type, matches=[])

    # Corpus-wide BM25 statistics (global IDF and mean field length, ADR-078).
    # On the fresh path, reuse the field vectors already tokenised during matching
    # and only tokenise the entries the matcher skipped (a different ``--type``),
    # so no entry is tokenised twice. A supplied cache replaces all of this.
    if field_tokens_by_path is None:
        field_tokens_by_path = {}
        for entry in entries:
            cached = matched_field_tokens.get(entry.path)
            field_tokens_by_path[entry.path] = (
                cached if cached is not None else _field_tokens(entry)
            )
    n, df, avglen, field_tokens_by_path = _corpus_stats(entries, terms, field_tokens_by_path)
    return _rank_and_build(
        query, artifact_type, matched, terms, n, df, avglen, field_tokens_by_path
    )


def _rank_and_build(
    query: str,
    artifact_type: str | None,
    matched: list[tuple[SearchableArtifact, _Match]],
    terms: Sequence[str],
    n: int,
    df: dict[str, int],
    avglen: dict[str, float],
    field_tokens_by_path: dict[str, dict[str, list[str]]],
) -> SearchResult:
    """Fuse, rank, and shape the matched set into a :class:`SearchResult` (ADR-078).

    The single owner of the scoring tail every search path shares: the BM25F
    lexical score (via :func:`_bm25f` over ``field_tokens_by_path``, which must
    cover every matched path), the bounded inbound graph signal, their RRF fusion,
    the ``(-round(fused, 12), path)`` sort, and the match evidence. The global
    stats — ``n``, ``df``, ``avglen`` — are supplied by the caller: the fresh walk
    computes them over the whole corpus, the persistent store from its integer
    accumulators and prefix-range postings. Because those inputs are integers and
    the arithmetic and its summation order are fixed, the two paths emit
    byte-identical bytes.
    """
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
                    inbound=getattr(e, "inbound_count", 0),
                ),
            )
            for e, m in matched
        ],
    )
