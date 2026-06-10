"""Artifact lookup and resolution — `rac resolve` / `rac find` (v0.7.12).

Built strictly on the repository index (the dependency direction pinned by the
roadmap): no independent file discovery, identity extraction, or
classification happens here. Explorer, Watchkeeper, CI, and IDE integrations
consume these same functions, so lookup behavior cannot fork per consumer
(ADR-015, ADR-026).

Exact resolution has exactly three outcomes — resolved, not found, duplicate —
and a duplicate is never silently resolved by path order. Search is
deterministic: case-insensitive substring matching over identifiers, title,
and path, ordered by match-field priority (id, then title, then filename/path)
with sorted path as the tiebreak.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from rac.services.index import IndexEntry, build_repository_index

OUTCOME_RESOLVED = "resolved"
OUTCOME_NOT_FOUND = "not-found"
OUTCOME_DUPLICATE = "duplicate"

# Match-field priority for search ordering (lower ranks first).
_RANK_ID = 0
_RANK_TITLE = 1
_RANK_PATH = 2


@dataclass
class ResolvedArtifact:
    """The canonical answer to "what artifact is this ID?" (ADR-026)."""

    id: str
    type: str
    title: str | None
    path: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "title": self.title,
            "path": self.path,
        }

    @classmethod
    def from_entry(cls, entry: IndexEntry) -> ResolvedArtifact:
        return cls(id=entry.id, type=entry.type, title=entry.title, path=entry.path)


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
    wanted = artifact_id.strip().casefold()
    matches: list[IndexEntry] = []
    for entry in build_repository_index(directory, recursive=recursive).artifacts:
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


def _match_rank(entry: IndexEntry, needle: str) -> int | None:
    """Best match-field rank for ``needle`` in ``entry``, or None for no match."""
    if any(needle in alias.casefold() for alias in entry.aliases):
        return _RANK_ID
    if entry.title and needle in entry.title.casefold():
        return _RANK_TITLE
    if needle in entry.path.casefold():
        return _RANK_PATH
    return None


def find_artifacts(
    directory: str,
    query: str,
    artifact_type: str | None = None,
    recursive: bool = True,
) -> SearchResult:
    """Search artifacts under ``directory`` by id, title, filename, or path.

    Deterministic and explainable (no ranking heuristics): case-insensitive
    substring match, results ordered by match-field priority then sorted
    path. An empty result is a valid outcome, not an error.
    """
    needle = query.strip().casefold()
    ranked: list[tuple[int, str, IndexEntry]] = []
    for entry in build_repository_index(directory, recursive=recursive).artifacts:
        if artifact_type is not None and entry.type != artifact_type:
            continue
        rank = _match_rank(entry, needle)
        if rank is not None:
            ranked.append((rank, entry.path, entry))
    ranked.sort(key=lambda r: (r[0], r[1]))
    return SearchResult(
        query=query,
        artifact_type=artifact_type,
        matches=[ResolvedArtifact.from_entry(e) for _, _, e in ranked],
    )
