"""Explorer UI state — what the widgets render (v0.8.0).

Frozen, presentation-ready snapshots translated from Core models by the
adapter (ADR-015). Widgets and screens consume these types only; they never
import Core models, and this module never imports Textual.
"""

from __future__ import annotations

from dataclasses import dataclass


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
class LoadErrorState:
    """A recoverable failure: the shell shows it and offers retry."""

    title: str
    detail: str
    can_retry: bool
