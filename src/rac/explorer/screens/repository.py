"""Repository screen — the v0.8.0 application shell (loading → summary → error).

The screen never executes Core operations in UI handlers (Initiative 5):
loading runs in a thread worker (Core is synchronous), progress is marshalled
back with ``call_from_thread``, and ``r`` cancels any in-flight load before
starting a fresh one (``exclusive=True``). Failures arrive as
``LoadErrorState`` and render as a recoverable view (Initiative 6).
"""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, Header
from textual.worker import Worker, WorkerState, get_current_worker

from rac.explorer import firstrun
from rac.explorer.adapter import ExplorerAdapter
from rac.explorer.state import LoadErrorState, LoadProgressState, RepositorySummaryState
from rac.explorer.widgets import RepositoryPanel

from .browser import BrowserScreen
from .health import HealthScreen


class _WorkerCancelToken:
    """Bridges Textual's worker cancellation into the Core CancelToken protocol."""

    def __init__(self, worker: Worker[object]) -> None:
        self._worker = worker

    @property
    def cancelled(self) -> bool:
        return self._worker.is_cancelled


class RepositoryScreen(Screen[None]):
    """The home screen: loads off the UI thread, renders summary + attention."""

    BINDINGS = [
        Binding("r", "reload", "Reload"),
        Binding("enter", "browse", "Browse"),
        Binding("h", "health", "Health"),
    ]

    def __init__(self, adapter: ExplorerAdapter) -> None:
        super().__init__()
        self.adapter = adapter
        # The summary held back while first-run onboarding is on screen;
        # Enter dismisses onboarding and reveals it (no forced setup).
        self._onboarding_summary: RepositorySummaryState | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield RepositoryPanel(id="repository-panel")
        yield Footer()

    def on_mount(self) -> None:
        self.action_reload()

    def action_reload(self) -> None:
        self.query_one(RepositoryPanel).show_progress(
            LoadProgressState(phase="scan", completed=0, total=None, label="Scanning artifacts")
        )
        self._load_repository()

    def action_browse(self) -> None:
        if self._onboarding_summary is not None:
            summary, self._onboarding_summary = self._onboarding_summary, None
            firstrun.mark_onboarded()
            self.query_one(RepositoryPanel).show_summary(summary)
            return
        browser = self.adapter.browser_state()
        if browser is not None:
            self.app.push_screen(BrowserScreen(self.adapter, browser))

    def action_health(self) -> None:
        if self._onboarding_summary is not None:
            return  # finish onboarding (Enter) before opening sub-screens
        health = self.adapter.health_state()
        if health is not None:
            self.app.push_screen(HealthScreen(self.adapter, health))

    @work(thread=True, exclusive=True, group="repository-load")
    def _load_repository(self) -> RepositorySummaryState | LoadErrorState | None:
        worker = get_current_worker()
        token = _WorkerCancelToken(worker)

        def relay(progress: LoadProgressState) -> None:
            if not worker.is_cancelled:
                self.app.call_from_thread(self.query_one(RepositoryPanel).show_progress, progress)

        return self.adapter.load(on_progress=relay, cancel=token)

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        if event.worker.group != "repository-load":
            return
        panel = self.query_one(RepositoryPanel)
        if event.state == WorkerState.SUCCESS:
            result = event.worker.result
            if isinstance(result, RepositorySummaryState):
                if firstrun.is_first_run():
                    self._onboarding_summary = result
                    panel.show_onboarding(result)
                else:
                    panel.show_summary(result)
            elif isinstance(result, LoadErrorState):
                panel.show_error(result)
            # None — the load was cancelled; a fresh worker is taking over.
        elif event.state == WorkerState.ERROR:
            # The adapter is the recoverable boundary, so this is unexpected —
            # but the interface must still never crash (Initiative 6).
            panel.show_error(
                LoadErrorState(
                    title="Unexpected failure",
                    detail=str(event.worker.error),
                    can_retry=True,
                )
            )
