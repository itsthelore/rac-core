"""Explorer UI state — what the widgets render (v0.8.0).

Frozen, presentation-ready snapshots translated from Core models by the
adapter (ADR-015). Widgets and screens consume these types only; they never
import Core models, and this module never imports Textual.
"""

from __future__ import annotations

from dataclasses import dataclass


def health_label(score: int) -> str:
    """The overall health band label for ``score`` (text beside the symbol).

    Shared by the home summary and the health screen so they never disagree
    (ADR-028: meaning never depends on colour alone).
    """
    if score >= 80:
        return "✓ Healthy"
    if score >= 50:
        return "! Needs Attention"
    return "✗ Unhealthy"


@dataclass(frozen=True)
class LoadProgressState:
    """One progress update while the repository loads."""

    phase: str
    completed: int
    total: int | None
    label: str  # presentation-ready, e.g. "Scanning artifacts (12/95)"


@dataclass(frozen=True)
class RepositorySummaryState:
    """The repository summary the home screen renders."""

    directory: str
    artifact_total: int
    by_type: tuple[tuple[str, int], ...]  # (type, count), zero counts omitted
    relationship_total: int
    broken_relationships: int
    error_count: int
    warning_count: int
    health_score: int
    # Attention lines (v0.8.1): aggregated counts such as "2 broken
    # relationships"; empty when the repository needs none.
    attention: tuple[str, ...] = ()


@dataclass(frozen=True)
class ArtifactRow:
    """One artifact line in the browser or in search results."""

    path: str  # navigation key (opens the context view)
    id: str
    type: str
    title: str | None
    status_label: str  # e.g. "✓ valid" — text alongside any symbol


@dataclass(frozen=True)
class BrowserState:
    """The artifact browser: artifacts grouped by type, walk order."""

    directory: str
    groups: tuple[tuple[str, tuple[ArtifactRow, ...]], ...]  # (type, rows)
    total: int


@dataclass(frozen=True)
class LookupState:
    """The outcome of an /open or /find: rows to pick from, or a message.

    One row means an unambiguous answer (open it directly); several rows let
    the user choose; a message explains an empty or ambiguous outcome.
    """

    rows: tuple[ArtifactRow, ...]
    message: str | None = None


@dataclass(frozen=True)
class ContextState:
    """Everything the context view shows for one artifact."""

    id: str
    type: str
    title: str | None
    path: str
    aliases: tuple[str, ...]
    status_label: str
    missing_recommended: tuple[str, ...]
    outgoing: tuple[str, ...]  # rendered relationship lines declared here
    incoming: tuple[str, ...]  # rendered lines for references resolving here
    diagnostics: tuple[str, ...]  # rendered finding lines


@dataclass(frozen=True)
class HealthAreaState:
    """One health area (Completeness, Relationships, Validation, Coverage)."""

    name: str
    status_label: str  # "✓ Healthy" | "! Needs Attention" | "✗ Error"
    detail: str  # Core facts, e.g. "92% (110/120 recommended sections)"


@dataclass(frozen=True)
class AttentionRow:
    """One prioritized attention item, linked to the artifact it concerns."""

    path: str  # navigation key (opens the context view)
    identifier: str
    severity_label: str  # "✗ error" | "! warning"
    message: str


@dataclass(frozen=True)
class HealthState:
    """The repository health screen, rendered entirely from Core results."""

    directory: str
    score: int
    score_label: str
    areas: tuple[HealthAreaState, ...]
    attention: tuple[AttentionRow, ...]


@dataclass(frozen=True)
class RecommendationRow:
    """One recommendation: a finding with impact, action, and a target."""

    path: str  # navigation key (opens the affected artifact's context view)
    identifier: str
    category: str  # Validation | Relationships | Repository Health | Quality
    severity_label: str  # "✗ Critical" | "! Warning" | "· Suggestion"
    finding: str
    impact: str
    action: str


@dataclass(frozen=True)
class RecommendationsState:
    """Recommendations grouped by category, rendered from Core review findings."""

    directory: str
    groups: tuple[tuple[str, tuple[RecommendationRow, ...]], ...]  # (category, rows)
    total: int


@dataclass(frozen=True)
class RelationshipLink:
    """One edge in the knowledge graph, rendered for the terminal."""

    kind: str  # e.g. "Related Decisions", "Supersedes"
    label: str  # the connected artifact's title/id, or the raw reference text
    target_path: str  # the artifact to navigate to ("" when unresolved)
    navigable: bool


@dataclass(frozen=True)
class RelationshipsView:
    """An artifact's relationships: outgoing edges, impact, and lineage."""

    id: str
    title: str | None
    path: str
    outgoing: tuple[RelationshipLink, ...]
    impact: tuple[RelationshipLink, ...]  # what depends on this artifact
    lineage: tuple[str, ...]  # Supersedes / Superseded By lines


@dataclass(frozen=True)
class ImportPreview:
    """A converted document awaiting confirmation before it is written."""

    source: str
    converter: str
    target: str
    markdown: str


@dataclass(frozen=True)
class LoadErrorState:
    """A recoverable failure: the shell shows it and offers retry."""

    title: str
    detail: str
    can_retry: bool
