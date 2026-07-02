"""Explorer UI state — the frozen snapshots the widgets render (v0.8.0).

The adapter translates Core models into these presentation-ready shapes; the
widgets and screens consume *only* this module and never reach into Core
(ADR-015). Everything here is a plain dataclass plus two label helpers, so the
module stays Textual-free and the base install (no ``explorer`` extra) can
import it in headless tests.

Field names, order, and defaults are contract: the adapter constructs these by
keyword and the views index them positionally, so a reorder is a breaking
change even when the types are unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime


def relative_age(then: datetime, now: datetime | None = None) -> str:
    """Compact "time ago" label for the portfolio recency column (v0.26.2).

    The single source of the age vocabulary (``today``, ``3d``, ``2w``,
    ``5mo``, ``1y``) so every caller that both displays and sorts by recency
    agrees on the boundaries.
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
    """The overall health band for ``score`` (text that rides beside a symbol).

    Canonical bands, shared by the home summary, the health screen, and the
    status line so they never disagree — ADR-028 forbids meaning that depends
    on colour alone, so the words carry the signal.
    """
    if score >= 80:
        return "✓ Healthy"
    if score >= 50:
        return "! Needs Attention"
    return "✗ Unhealthy"


@dataclass(frozen=True)
class LoadProgressState:
    """One progress tick while the repository loads."""

    phase: str
    completed: int
    total: int | None
    label: str  # presentation-ready, e.g. "Scanning artifacts (12/95)"


@dataclass(frozen=True)
class RepositorySummaryState:
    """The at-a-glance repository summary the home screen renders."""

    directory: str
    artifact_total: int
    by_type: tuple[tuple[str, int], ...]  # (type, count); zero counts omitted
    relationship_total: int
    broken_relationships: int
    error_count: int
    warning_count: int
    health_score: int
    # Aggregated attention lines (e.g. "2 broken relationships"); empty when
    # the repository needs no attention.
    attention: tuple[str, ...] = ()


@dataclass(frozen=True)
class ArtifactRow:
    """One artifact line in the browser or in a results listing."""

    path: str  # navigation key — opens the context view
    id: str
    type: str
    title: str | None
    status_label: str  # text alongside any symbol, e.g. "✓ Valid"


@dataclass(frozen=True)
class PortfolioRow:
    """One row of the portfolio table (v0.26.2).

    Extends the browser fields with the artifact's ``link_count`` (its degree
    in the loaded graph) and a ``recency_label`` that the recency worker fills
    after the fact — git is too slow for the load path (ADR-045), so recency
    arrives once the table is already on screen.
    """

    path: str
    id: str
    type: str
    title: str | None
    status_label: str
    link_count: int
    recency_label: str = ""  # "2d", "3w", …; "" until the worker fills it


@dataclass(frozen=True)
class PortfolioState:
    """Every artifact rendered as a portfolio row (v0.26.2)."""

    rows: tuple[PortfolioRow, ...]


@dataclass(frozen=True)
class DirectoryNode:
    """One directory in the repository tree (folders grouping, v0.8.10).

    ``path`` is the posix relpath from the repository root — the root carries
    ``name="" path=""`` — and doubles as the sidebar's ``dir:`` expansion key,
    so it must stay stable across platforms. ``rows`` are the artifacts
    directly inside this directory, in repository order.
    """

    name: str
    path: str
    dirs: tuple[DirectoryNode, ...]  # sorted by name
    rows: tuple[ArtifactRow, ...]


@dataclass(frozen=True)
class BrowserState:
    """The artifact browser: artifacts grouped for display."""

    directory: str
    groups: tuple[tuple[str, tuple[ArtifactRow, ...]], ...]  # (group, rows)
    total: int
    # Only folders grouping carries a tree mirroring the on-disk structure;
    # type and flat grouping leave it None.
    tree: DirectoryNode | None = None


@dataclass(frozen=True)
class LookupState:
    """The outcome of an /open or /find: rows to pick from, or a message.

    One row is an unambiguous answer (open it directly); several rows let the
    user choose; a message explains an empty or ambiguous outcome.
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
    outgoing: tuple[str, ...]  # rendered lines for references declared here
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

    path: str  # navigation key — opens the context view
    identifier: str
    severity_label: str  # "✗ Error" | "! Warning"
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
    """One recommendation: a finding with its impact, action, and target."""

    path: str  # navigation key — opens the affected artifact's context view
    identifier: str
    category: str  # Validation | Relationships | Repository Health | Quality
    severity_label: str  # "✗ Critical" | "! Warning" | "· Suggestion"
    finding: str
    impact: str
    action: str


@dataclass(frozen=True)
class RecommendationsState:
    """Recommendations grouped by category, from Core's review findings."""

    directory: str
    groups: tuple[tuple[str, tuple[RecommendationRow, ...]], ...]  # (category, rows)
    total: int


@dataclass(frozen=True)
class RelationshipLink:
    """One edge of the knowledge graph, rendered for the terminal."""

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

    A summary surface rather than per-artifact listings — the browser and
    results views already navigate individual artifacts.
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
    """A recoverable failure: the shell shows it and offers a retry."""

    title: str
    detail: str
    can_retry: bool
