"""Explorer adapter — the boundary between RAC services and the TUI (v0.8.0).

The adapter invokes RAC services, translates Core models into UI state, and
owns no repository intelligence (ADR-015). It is the single place the
Explorer touches ``rac.services`` / ``rac.core``; widgets depend on
:mod:`rac.explorer.state` only. This module never imports Textual, so it is
testable without a terminal.
"""

from __future__ import annotations

from collections.abc import Callable

from rac.core.operations import CancelToken, OperationCancelled, Progress
from rac.services.repository import Artifact, Repository, load_repository

from .state import (
    ArtifactRow,
    BrowserState,
    ContextState,
    LoadErrorState,
    LoadProgressState,
    RepositorySummaryState,
)

# Presentation labels for the analysis phases that follow the scan.
_PHASE_LABELS = {
    "index": "Indexing artifacts",
    "validate": "Validating artifacts",
    "relationships": "Analyzing relationships",
    "portfolio": "Calculating portfolio",
}

# Validation status → text-bearing label (never colour or symbol alone).
_STATUS_LABELS = {
    "valid": "✓ valid",
    "invalid": "✗ invalid",
    "skipped": "– unknown",
}

ProgressHandler = Callable[[LoadProgressState], None]


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" + ("" if count == 1 else "s")


def _status_label(status: str) -> str:
    return _STATUS_LABELS.get(status, status)


def _row(artifact: Artifact) -> ArtifactRow:
    return ArtifactRow(
        path=artifact.path,
        id=artifact.id,
        type=artifact.type,
        title=artifact.title,
        status_label=_status_label(artifact.status),
    )


def _progress_state(progress: Progress) -> LoadProgressState:
    if progress.phase == "scan":
        counter = f" ({progress.completed}/{progress.total})" if progress.total else ""
        label = f"Scanning artifacts{counter}"
    else:
        label = _PHASE_LABELS.get(progress.phase, progress.phase.title())
    return LoadProgressState(
        phase=progress.phase,
        completed=progress.completed,
        total=progress.total,
        label=label,
    )


class ExplorerAdapter:
    """Loads a repository through Core services and yields UI state.

    Failures surface as :class:`LoadErrorState` (Initiative 6 — recoverable,
    never a crash); a cancelled load returns ``None`` so workers can discard
    it without handling Core exception types. The last successful
    :class:`Repository` is kept for navigation milestones (v0.8.1+).
    """

    def __init__(self, directory: str, recursive: bool = True) -> None:
        self.directory = directory
        self.recursive = recursive
        self.repository: Repository | None = None

    def load(
        self,
        *,
        on_progress: ProgressHandler | None = None,
        cancel: CancelToken | None = None,
    ) -> RepositorySummaryState | LoadErrorState | None:
        def relay(progress: Progress) -> None:
            if on_progress is not None:
                on_progress(_progress_state(progress))

        try:
            repository = load_repository(
                self.directory,
                recursive=self.recursive,
                on_progress=relay,
                cancel=cancel,
            )
        except OperationCancelled:
            return None  # discarded by the caller; not an error
        except Exception as exc:  # noqa: BLE001 — the recoverable boundary (Initiative 6)
            return LoadErrorState(
                title="Could not load repository",
                detail=f"{type(exc).__name__}: {exc}",
                can_retry=True,
            )

        self.repository = repository
        return self._summary(repository)

    @staticmethod
    def _summary(repository: Repository) -> RepositorySummaryState:
        portfolio = repository.portfolio
        severities = [d.severity for d in repository.diagnostics]
        incomplete = sum(1 for a in repository.artifacts if a.missing_recommended)
        attention = tuple(
            line
            for count, noun in (
                (portfolio.invalid_artifacts, "invalid artifact"),
                (portfolio.relationships.broken, "broken relationship"),
                (incomplete, "incomplete artifact"),
            )
            if count
            for line in (_plural(count, noun),)
        )
        return RepositorySummaryState(
            directory=repository.directory,
            artifact_total=portfolio.total_artifacts,
            by_type=tuple((name, count) for name, count in portfolio.by_type.items() if count),
            relationship_total=portfolio.relationships.total,
            broken_relationships=portfolio.relationships.broken,
            error_count=severities.count("error"),
            warning_count=severities.count("warning"),
            health_score=repository.health_score,
            attention=attention,
        )

    # --- navigation state (v0.8.1) — requires a loaded repository -----------

    def browser_state(self) -> BrowserState | None:
        """Artifacts grouped by type for the browser, or None before a load."""
        if self.repository is None:
            return None
        repository = self.repository
        groups = tuple(
            (artifact_type, tuple(_row(a) for a in repository.artifacts_of_type(artifact_type)))
            for artifact_type, count in repository.portfolio.by_type.items()
            if count
        )
        return BrowserState(
            directory=self.repository.directory,
            groups=groups,
            total=self.repository.portfolio.total_artifacts,
        )

    def context_state(self, path: str) -> ContextState | None:
        """The context view for the artifact at ``path``, or None if unknown."""
        repository = self.repository
        if repository is None:
            return None
        artifact = next((a for a in repository.artifacts if a.path == path), None)
        if artifact is None:
            return None

        titles = {a.path: a.title or a.id for a in repository.artifacts}
        outgoing: list[str] = []
        incoming: list[str] = []
        for rel in repository.relationships_for(path):
            label = rel.relationship.replace("_", " ").title()
            if rel.source_path == path:
                if rel.resolved_path is not None:
                    outgoing.append(f"{label} → {rel.target} ({titles[rel.resolved_path]})")
                else:
                    phrase = (rel.issue or "unresolved").replace("-", " ")
                    outgoing.append(f"{label} → {rel.target} (✗ {phrase})")
            else:
                incoming.append(f"← {titles.get(rel.source_path, rel.source_path)} ({label})")

        diagnostics = tuple(
            f"{'✗' if d.severity == 'error' else '!'} {d.severity}: {d.message}"
            for d in repository.diagnostics_for(path)
        )
        return ContextState(
            id=artifact.id,
            type=artifact.type,
            title=artifact.title,
            path=artifact.path,
            aliases=artifact.aliases,
            status_label=_status_label(artifact.status),
            missing_recommended=artifact.missing_recommended,
            outgoing=tuple(outgoing),
            incoming=tuple(incoming),
            diagnostics=diagnostics,
        )
