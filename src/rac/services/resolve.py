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

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

from rac.core.corpus import walk_corpus
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


# Match-field priority for search ordering (lower ranks first); the ladder
# pinned by ADR-037/ADR-038: id, then title, then path, then heading, then body.
_RANK_ID = 0
_RANK_TITLE = 1
_RANK_PATH = 2
_RANK_HEADING = 3
_RANK_BODY = 4

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

    def to_dict(self) -> dict:
        payload = {
            "id": self.id,
            "type": self.type,
            "title": self.title,
            "path": self.path,
        }
        if self.section is not None:
            payload["section"] = self.section
        if self.snippet is not None:
            payload["snippet"] = self.snippet
        return payload

    @classmethod
    def from_entry(
        cls,
        entry: SearchableArtifact,
        *,
        section: str | None = None,
        snippet: str | None = None,
    ) -> ResolvedArtifact:
        return cls(
            id=entry.id,
            type=entry.type,
            title=entry.title,
            path=entry.path,
            section=section,
            snippet=snippet,
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

    def to_dict(self) -> dict:
        return {
            "schema_version": "1",
            "query": self.query,
            "type": self.artifact_type,
            "match_count": self.match_count,
            "matches": [m.to_dict() for m in self.matches],
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
    """A search hit: the winning tier plus snippet text for heading/body tiers."""

    rank: int
    section: str | None = None
    snippet: str | None = None


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

    if best_rank == _RANK_HEADING and heading_hit is not None:
        return _Match(rank=best_rank, section=heading_hit[0], snippet=heading_hit[1])
    if best_rank == _RANK_BODY and body_hit is not None:
        return _Match(rank=best_rank, section=body_hit[0], snippet=body_hit[1])
    return _Match(rank=best_rank)


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
    # Reuse the liveness predicate from the agent-rules projection rather than
    # re-deriving "Accepted and not retired" — the definition must not fork
    # (the same rule the committed rules block is built from).
    from rac.services.agent_rules import is_live_decision

    entries = list(walk_corpus(directory, recursive=recursive))
    live_paths = {
        str(entry.path)
        for entry in entries
        if entry.artifact_type == _DECISION_TYPE and is_live_decision(entry.product)
    }
    index = index_from_corpus(directory, entries, recursive=recursive).artifacts
    result = search_index(index, topic, artifact_type=_DECISION_TYPE)
    # Drop matches that are decisions but not live; ranking/order is preserved.
    result.matches = [m for m in result.matches if m.path in live_paths]
    return result


def search_index(
    entries: Sequence[SearchableArtifact],
    query: str,
    artifact_type: str | None = None,
) -> SearchResult:
    """Search already-discovered entries with `rac find` semantics (v0.8.1).

    Identical matching and ordering to :func:`find_artifacts`; the seam lets
    a loaded repository model serve searches without another directory walk.
    """
    terms = tokenize(query)
    ranked: list[tuple[int, str, SearchableArtifact, _Match]] = []
    if terms:  # an all-punctuation query tokenizes to nothing: no matches.
        for entry in entries:
            if artifact_type is not None and entry.type != artifact_type:
                continue
            match = _match_entry(entry, terms)
            if match is not None:
                ranked.append((match.rank, entry.path, entry, match))
    ranked.sort(key=lambda r: (r[0], r[1]))
    return SearchResult(
        query=query,
        artifact_type=artifact_type,
        matches=[
            ResolvedArtifact.from_entry(e, section=m.section, snippet=m.snippet)
            for _, _, e, m in ranked
        ],
    )
