"""Explorer UI state — what the widgets render (v0.8.0).

Frozen, presentation-ready snapshots translated from Core models by the
adapter (ADR-015). Widgets and screens consume these types only; they never
import Core models, and this module never imports Textual.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime


def relative_age(then: datetime, now: datetime | None = None) -> str:
    """A compact "time ago" label (today, 3d, 2w, 5mo, 1y) for the portfolio
    recency column (v0.26.2). Shared so display and any other caller agree.
    """
    now = now or datetime.now(UTC)
    days = (now - then).days
    if days <= 0:
        return "today"
    if days < 7:
        return f"{days}d"
    if days < 30:
        return f"{days // 7}w"
    if days < 365:
        return f"{days // 30}mo"
    return f"{days // 365}y"


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
class PortfolioRow:
    """One row in the portfolio list view (v0.26.2).

    Carries the browser fields plus a relationship ``link_count`` (degree in
    the loaded graph) and a ``recency_label`` filled later by the recency
    worker — git is too slow to run in the load path (ADR-045), so it arrives
    after the table is already on screen.
    """

    path: str
    id: str
    type: str
    title: str | None
    status_label: str
    link_count: int
    recency_label: str = ""  # "2d", "3w", … ; "" until the worker fills it


@dataclass(frozen=True)
class PortfolioState:
    """Every artifact as a portfolio row (v0.26.2)."""

    rows: tuple[PortfolioRow, ...]


@dataclass(frozen=True)
class DirectoryNode:
    """One directory in the repository tree (folders grouping, v0.8.10).

    ``path`` is the posix relpath from the repository root (the root node
    carries ``name="" path=""``); ``rows`` are the artifacts directly inside
    this directory, in repository order.
    """

    name: str
    path: str
    dirs: tuple[DirectoryNode, ...]  # sorted by name
    rows: tuple[ArtifactRow, ...]


@dataclass(frozen=True)
class BrowserState:
    """The artifact browser: artifacts grouped by type, walk order."""

    directory: str
    groups: tuple[tuple[str, tuple[ArtifactRow, ...]], ...]  # (type, rows)
    total: int
    # Folders grouping (v0.8.10): the repository directory tree mirroring
    # the structure on disk; None for type and flat grouping.
    tree: DirectoryNode | None = None


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
class StatsState:
    """The portfolio statistics dashboard (v0.8.10): (section title, lines).

    A summary surface, not per-artifact listings — the browser and results
    views already navigate individual artifacts.
    """

    directory: str
    sections: tuple[tuple[str, tuple[str, ...]], ...]


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
