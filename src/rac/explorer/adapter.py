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
from rac.services.repository import Repository, load_repository

from .state import LoadErrorState, LoadProgressState, RepositorySummaryState

# Presentation labels for the analysis phases that follow the scan.
_PHASE_LABELS = {
    "index": "Indexing artifacts",
    "validate": "Validating artifacts",
    "relationships": "Analyzing relationships",
    "portfolio": "Calculating portfolio",
}

ProgressHandler = Callable[[LoadProgressState], None]


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
        return RepositorySummaryState(
            directory=repository.directory,
            artifact_total=portfolio.total_artifacts,
            by_type=tuple((name, count) for name, count in portfolio.by_type.items() if count),
            relationship_total=portfolio.relationships.total,
            broken_relationships=portfolio.relationships.broken,
            error_count=severities.count("error"),
            warning_count=severities.count("warning"),
            health_score=repository.health_score,
        )
