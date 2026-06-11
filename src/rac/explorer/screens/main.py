"""The main screen — one persistent workspace frame (v0.8.7).

App bar, navigation sidebar, context panel, command bar, status line: the
frame composes once and never rebuilds; views swap inside the context region
via ``ContentSwitcher`` with an internal history backing Esc
(DESIGN-visual-system). The screen stack survives only for the confirm-write
modal (ADR-024). Loading runs in a thread worker (Core is synchronous);
command routing answers everything through the adapter (ADR-015).
"""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.events import DescendantFocus, Resize
from textual.screen import Screen
from textual.widget import Widget
from textual.widgets import ContentSwitcher, Tree
from textual.widgets.option_list import Option
from textual.worker import Worker, WorkerState, get_current_worker

from rac.explorer import commands, mascot
from rac.explorer.adapter import ExplorerAdapter
from rac.explorer.state import (
    LoadErrorState,
    LoadProgressState,
    LookupState,
    RepositorySummaryState,
)
from rac.explorer.widgets.appbar import AppBar
from rac.explorer.widgets.palette import CommandPalette
from rac.explorer.widgets.sidebar import NavigationSidebar
from rac.explorer.widgets.statusline import StatusLine
from rac.explorer.widgets.views import (
    BrowseRequested,
    ContextView,
    HealthView,
    HomeView,
    ImportView,
    OpenArtifact,
    RecommendationsView,
    ResultsView,
    SettingsChanged,
    SettingsView,
    ShowRecommendations,
    launch_editor,
)

# The sidebar hides below this width so the context panel keeps room to read.
_SIDEBAR_MIN_WIDTH = 80

# How often the live watcher compares the corpus files on disk (v0.8.9).
_WATCH_INTERVAL = 2.0

# View id → the status-line hint set and the panel title when no artifact is open.
_VIEW_REGIONS = {
    "view-home": ("home", "Home"),
    "view-context": ("context", "Artifact"),
    "view-health": ("health", "Health"),
    "view-recommendations": ("recommendations", "Recommendations"),
    "view-import": ("import", "Import"),
    "view-results": ("results", "Results"),
    "view-settings": ("settings", "Settings"),
}


class _WorkerCancelToken:
    """Bridges Textual's worker cancellation into the Core CancelToken protocol."""

    def __init__(self, worker: Worker[object]) -> None:
        self._worker = worker

    @property
    def cancelled(self) -> bool:
        return self._worker.is_cancelled


class MainScreen(Screen[None]):
    """The workspace frame; every view swap happens inside the context region."""

    BINDINGS = [
        Binding("r", "reload", "Reload"),
        Binding("h", "health", "Health"),
        Binding("full_stop", "resume", "Resume last"),
        Binding("escape", "back", "Back"),
        Binding("question_mark", "help", "Help", show=False),
    ]

    def __init__(self, adapter: ExplorerAdapter) -> None:
        super().__init__()
        self.adapter = adapter
        self._history: list[tuple[str, str | None]] = []
        self._last_focus: Widget | None = None
        # Live reload (v0.8.9): the corpus snapshot the last load saw. None
        # means "do not watch" — before the first successful load, after a
        # load error, or while the application is suspended for an editor.
        self._watch_baseline: tuple[tuple[str, int], ...] | None = None
        self._watch_paused = False

    # --- frame ----------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield AppBar(self.adapter.directory)
        with Horizontal(id="workspace"):
            yield NavigationSidebar()
            with Vertical(id="context-region"), ContentSwitcher(initial="view-home", id="views"):
                yield HomeView(self.adapter)
                yield ContextView(self.adapter)
                yield HealthView()
                yield RecommendationsView(self.adapter)
                yield ImportView(self.adapter)
                yield ResultsView()
                yield SettingsView(self.adapter)
        yield StatusLine()
        # Floats over the context region on its own layer; hidden when idle.
        yield CommandPalette(self.adapter)

    def on_mount(self) -> None:
        self._set_region_title("view-home")
        self.query_one(StatusLine).show_hints("home")
        self.query_one(NavigationSidebar).display = self.app.size.width >= _SIDEBAR_MIN_WIDTH
        self.query_one(HomeView).focus()
        self.set_interval(_WATCH_INTERVAL, self._watch_tick)
        self.action_reload()

    def on_resize(self, event: Resize) -> None:
        self.query_one(NavigationSidebar).display = event.size.width >= _SIDEBAR_MIN_WIDTH

    @property
    def current_view(self) -> str:
        return self.query_one(ContentSwitcher).current or "view-home"

    def _snapshot(self) -> tuple[str, str | None]:
        """The current view as a history entry: (view id, open artifact path)."""
        current = self.current_view
        if current == "view-context":
            context = self.query_one(ContextView).context
            return (current, context.path if context is not None else None)
        return (current, None)

    def show_view(self, view_id: str, *, focus: bool = True, record: bool | None = None) -> None:
        """Swap the context region to ``view_id``, recording history for Esc.

        ``record`` defaults to "when the view changes"; artifact-to-artifact
        traversal stays on the context view but still records, so Esc can
        unwind across the graph.
        """
        switcher = self.query_one(ContentSwitcher)
        if record is None:
            record = switcher.current != view_id
        if record and switcher.current is not None:
            self._history.append(self._snapshot())
        switcher.current = view_id
        self._set_region_title(view_id)
        self.query_one(StatusLine).show_hints(_VIEW_REGIONS[view_id][0])
        if view_id in ("view-health", "view-recommendations", "view-context"):
            # Workspace continuity (v0.8.8): resume restores the view too.
            self.adapter.record_view(view_id)
        if focus:
            self._focus_view(view_id)

    def _focus_view(self, view_id: str) -> None:
        view = self.query_one(f"#{view_id}")
        take_focus = getattr(view, "take_focus", None)
        if take_focus is not None:
            take_focus()
        else:
            view.focus()

    def _set_region_title(self, view_id: str) -> None:
        region = self.query_one("#context-region")
        if view_id == "view-context":
            context = self.query_one(ContextView).context
            if context is not None:
                title = context.title or ""
                region.border_title = f"{context.id} — {title}" if title else context.id
                return
        region.border_title = _VIEW_REGIONS[view_id][1]

    # --- focus routing ----------------------------------------------------------

    def _region_of(self, widget: Widget) -> str:
        node: Widget | None = widget
        while node is not None and node is not self:
            if isinstance(node, CommandPalette):
                return "command"
            if isinstance(node, NavigationSidebar):
                return "sidebar"
            node_id = node.id or ""
            if node_id in _VIEW_REGIONS:
                return _VIEW_REGIONS[node_id][0]
            node = node.parent if isinstance(node.parent, Widget) else None
        return _VIEW_REGIONS[self.current_view][0]

    def on_descendant_focus(self, event: DescendantFocus) -> None:
        region = self._region_of(event.widget)
        self.query_one(StatusLine).show_hints(region)
        if region != "command":
            # Remembered so Esc in the palette can hand focus straight back.
            self._last_focus = event.widget

    def action_back(self) -> None:
        if not self._history:
            # Never a dead-end: with nothing to unwind, Esc returns home.
            if self.current_view != "view-home":
                self.show_view("view-home", record=False)
            return
        view_id, path = self._history.pop()
        if view_id == "view-context" and path is not None:
            self.open_artifact(path, record=False)
            return
        self.show_view(view_id, record=False)

    def action_help(self) -> None:
        self.route_command("help")

    # --- loading (moved from the v0.8.0 repository screen) ----------------------

    def action_reload(self) -> None:
        self.query_one(HomeView).show_progress(
            LoadProgressState(phase="scan", completed=0, total=None, label="Scanning artifacts")
        )
        self._load_repository()

    @work(thread=True, exclusive=True, group="repository-load")
    def _load_repository(self) -> RepositorySummaryState | LoadErrorState | None:
        worker = get_current_worker()
        token = _WorkerCancelToken(worker)

        def relay(progress: LoadProgressState) -> None:
            if not worker.is_cancelled:
                self.app.call_from_thread(self.query_one(HomeView).show_progress, progress)

        # Snapshot before loading: a save that lands mid-load differs from
        # this baseline, so the next watch tick reloads again and converges.
        baseline = self.adapter.fingerprint()
        result = self.adapter.load(on_progress=relay, cancel=token)
        self._watch_baseline = baseline if isinstance(result, RepositorySummaryState) else None
        return result

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        if event.worker.group == "watch-scan":
            if event.state == WorkerState.SUCCESS:
                self._on_scan_result(event.worker.result)
            return
        if event.worker.group != "repository-load":
            return
        home = self.query_one(HomeView)
        if event.state == WorkerState.SUCCESS:
            result = event.worker.result
            if isinstance(result, RepositorySummaryState):
                home.show_result(result)
                self.query_one(NavigationSidebar).show_repository(self.adapter.browser_state())
                self.query_one(StatusLine).show_summary(result)
                self._refresh_current_view()
            elif isinstance(result, LoadErrorState):
                home.show_error(result)
            # None — the load was cancelled; a fresh worker is taking over.
        elif event.state == WorkerState.ERROR:
            # The adapter is the recoverable boundary, so this is unexpected —
            # but the interface must still never crash (Initiative 6).
            self._watch_baseline = None
            home.show_error(
                LoadErrorState(
                    title="Unexpected failure",
                    detail=str(event.worker.error),
                    can_retry=True,
                )
            )

    # --- live reload (v0.8.9) ----------------------------------------------------

    def pause_watching(self) -> None:
        """Hold the watcher while the application is suspended for an editor."""
        self._watch_paused = True

    def resume_watching(self) -> None:
        """Resume watching and scan immediately — the edit loop closes itself."""
        self._watch_paused = False
        self._watch_tick()

    def _watch_tick(self) -> None:
        if self._watch_paused or self._watch_baseline is None:
            return
        if any(w.group == "repository-load" and w.is_running for w in self.workers):
            return
        self._scan_corpus()

    @work(thread=True, exclusive=True, group="watch-scan")
    def _scan_corpus(self) -> tuple[tuple[str, int], ...] | None:
        return self.adapter.fingerprint()

    def _on_scan_result(self, snapshot: tuple[tuple[str, int], ...] | None) -> None:
        # None is "could not list" — no signal. A load error since the scan
        # started clears the baseline, which also stops the comparison.
        if snapshot is None or self._watch_baseline is None:
            return
        if snapshot != self._watch_baseline:
            self.action_reload()

    def _refresh_current_view(self) -> None:
        """Re-render whatever the user is looking at from the fresh load.

        Reload (manual or watched) refreshes the open artifact, health, or
        recommendations in place; an artifact that disappeared from the
        repository falls back home rather than showing stale content.
        """
        current = self.current_view
        if current == "view-context":
            view = self.query_one(ContextView)
            context = view.context
            if context is None:
                return
            if self.adapter.context_state(context.path) is None:
                self.show_view("view-home", record=False)
                return
            focused = self.app.focused
            keep_focus = focused is not None and self._region_of(focused) == "context"
            scroll_y = view.content_scroll_y
            self.open_artifact(
                context.path,
                tab=view.active_tab,
                reveal=False,
                record=False,
                focus=keep_focus,
            )
            view.restore_scroll(scroll_y)
        elif current == "view-health":
            health = self.adapter.health_state()
            if health is not None:
                self.query_one(HealthView).show_health(health)
        elif current == "view-recommendations":
            recommendations = self.adapter.recommendations_state()
            if recommendations is not None:
                self.query_one(RecommendationsView).show_recommendations(recommendations)

    # --- navigation ---------------------------------------------------------------

    def open_artifact(
        self,
        path: str,
        *,
        tab: str | None = None,
        reveal: bool = True,
        record: bool = True,
        focus: bool = True,
    ) -> None:
        context = self.adapter.context_state(path)
        if context is None:
            return
        previous = self.query_one(ContextView).context
        same = (
            self.current_view == "view-context" and previous is not None and previous.path == path
        )
        # Workspace continuity (v0.8.6): this is now the last artifact opened.
        self.adapter.record_artifact(path)
        markdown = self.adapter.artifact_markdown(path) or ""
        relationships = self.adapter.relationships_view(path)
        recommendations = self.adapter.recommendations_state()
        findings = tuple(
            row
            for _, rows in (recommendations.groups if recommendations else ())
            for row in rows
            if row.path == path
        )
        # Improvement suggestions (v0.8.9) join the review findings — fetched
        # on open, never during the repository load.
        findings += self.adapter.improvement_rows(path)
        # Snapshot before the context view is overwritten, so Esc can unwind
        # artifact-to-artifact traversal across the graph.
        if record and not same:
            self._history.append(self._snapshot())
        self.query_one(ContextView).show_artifact(
            context, markdown, relationships, findings, tab=tab
        )
        self.show_view("view-context", record=False, focus=focus)
        sidebar = self.query_one(NavigationSidebar)
        if reveal:
            sidebar.reveal(path)
        sidebar.show_status(context.status_label)

    def on_open_artifact(self, message: OpenArtifact) -> None:
        message.stop()
        self.open_artifact(message.path, tab=message.tab)

    def on_browse_requested(self, message: BrowseRequested) -> None:
        message.stop()
        self.query_one(NavigationSidebar).focus()

    def on_show_recommendations(self, message: ShowRecommendations) -> None:
        message.stop()
        self._show_recommendations()

    def on_settings_changed(self, message: SettingsChanged) -> None:
        message.stop()
        if message.key == "artifact_grouping":
            # The sidebar mirrors the grouping preference immediately.
            self.query_one(NavigationSidebar).show_repository(self.adapter.browser_state())

    def on_tree_node_selected(self, event: Tree.NodeSelected[str]) -> None:
        path = event.node.data
        if path is not None and not path.startswith("group:"):
            self.open_artifact(path, reveal=False)

    def action_health(self) -> None:
        if self.query_one(HomeView).onboarding_active:
            return  # finish onboarding (Enter) before leaving home
        health = self.adapter.health_state()
        if health is not None:
            self.query_one(HealthView).show_health(health)
            self.show_view("view-health")

    def _show_recommendations(self) -> bool:
        recommendations = self.adapter.recommendations_state()
        if recommendations is None:
            return False
        self.query_one(RecommendationsView).show_recommendations(recommendations)
        self.show_view("view-recommendations")
        return True

    def action_resume(self) -> None:
        # Workspace continuity (v0.8.6, view restore v0.8.8): reopen the last
        # view — health and recommendations included — on request.
        if self.query_one(HomeView).onboarding_active:
            return
        view = self.adapter.resume_view()
        if view == "view-health":
            self.action_health()
            return
        if view == "view-recommendations":
            self._show_recommendations()
            return
        path = self.adapter.resume_path()
        if path is not None:
            self.open_artifact(path)

    def on_navigation_sidebar_edit_requested(
        self, message: NavigationSidebar.EditRequested
    ) -> None:
        message.stop()
        outcome = launch_editor(self, self.adapter, message.path)
        self.app.notify(outcome.message)

    # --- command routing (the summoned `/` palette) --------------------------------

    def _show_results(
        self,
        options: list[Option | None],
        *,
        focus: bool = False,
        count: int | None = None,
    ) -> None:
        self.query_one(ResultsView).show_options(options, focus_first=focus)
        self.show_view("view-results", focus=focus)
        # The panel says what it holds: a count when results are countable.
        region = self.query_one("#context-region")
        region.border_title = "Results" if count is None else f"Results · {count}"

    def _show_message(self, message: str) -> None:
        self._show_results([Option(message, disabled=True)])

    def _show_examples(self) -> None:
        options: list[Option | None] = [Option("Start typing…  Try:", disabled=True)]
        options.extend(Option(f"  {example}", disabled=True) for example in commands.EXAMPLES)
        self._show_results(options)

    def _show_lookup(self, lookup: LookupState) -> None:
        if lookup.rows:
            # Artifact rows render through the filterable path (v0.8.9).
            self.query_one(ResultsView).show_lookup(lookup.rows, lookup.message)
            self.show_view("view-results", focus=True)
            self.query_one("#context-region").border_title = f"Results · {len(lookup.rows)}"
            return
        options: list[Option | None] = []
        # The mascot's empty state keeps zero-result moments calm
        # (text label included, so `mascot = false` loses nothing).
        if self.adapter.preferences.mascot:
            figure = mascot.figure(mascot.EMPTY, animations=self.adapter.preferences.animations)
            options.append(Option(figure, disabled=True))
        if lookup.message:
            options.append(Option(lookup.message, disabled=True))
        self._show_results(options, count=0)

    def summon_palette(self) -> None:
        self.query_one(CommandPalette).show()

    def on_command_palette_dismissed(self, message: CommandPalette.Dismissed) -> None:
        message.stop()
        if self._last_focus is not None and self._last_focus.is_attached:
            self._last_focus.focus()
        else:
            self._focus_view(self.current_view)

    def on_command_palette_artifact_chosen(self, message: CommandPalette.ArtifactChosen) -> None:
        message.stop()
        self.open_artifact(message.path)

    def on_command_palette_routed(self, message: CommandPalette.Routed) -> None:
        message.stop()
        self.route_command(message.text)

    def route_command(self, text: str) -> None:
        invocation = commands.parse(text)
        if not invocation.args and invocation.command == commands.SEARCH:
            self._show_examples()
            return

        if invocation.command == "quit":
            self.app.exit()
        elif invocation.command == "help":
            self._show_results(
                [
                    Option(f"/{spec.usage:<22} {spec.summary}", disabled=True)
                    for spec in commands.REGISTRY
                ]
            )
        elif invocation.command == "home":
            self.show_view("view-home")
        elif invocation.command == "health":
            health = self.adapter.health_state()
            if health is None:
                self._show_message("Repository not loaded yet")
                return
            self.query_one(HealthView).show_health(health)
            self.show_view("view-health")
        elif invocation.command == "recommendations":
            if not self._show_recommendations():
                self._show_message("Repository not loaded yet")
        elif invocation.command == "schema":
            if not invocation.args:
                self._show_results(
                    [
                        Option(f"{name:<14} {summary}", disabled=True)
                        for name, summary in self.adapter.schema_overview()
                    ]
                )
                return
            detail = self.adapter.schema_detail(invocation.args)
            if detail is None:
                self._show_message(f"Unknown artifact type: {invocation.args} — try /schema")
                return
            self._show_results([Option(detail, disabled=True)])
        elif invocation.command == "settings":
            self.query_one(SettingsView).show_settings()
            self.show_view("view-settings")
        elif invocation.command == "resume":
            path = self.adapter.resume_path()
            if path is None:
                self._show_message("No previous artifact to resume")
                return
            self.open_artifact(path)
        elif invocation.command == "relationships":
            lookup = self.adapter.open_ref(invocation.args)
            if len(lookup.rows) != 1 or lookup.message is not None:
                self._show_lookup(lookup)
                return
            self.open_artifact(lookup.rows[0].path, tab="tab-links")
        elif invocation.command == "import":
            parts = invocation.args.split()
            if not parts:
                self._show_message("Usage: /import <source> [target]")
                return
            target = parts[1] if len(parts) > 1 else None
            self.query_one(ImportView).start(parts[0], target)
            self.show_view("view-import")
        elif invocation.command == "browse":
            artifact_type = invocation.args.casefold() or None
            if not self.query_one(NavigationSidebar).focus_group(artifact_type):
                self._show_message(f"Nothing to browse: {invocation.args}")
        elif invocation.command == "open":
            lookup = self.adapter.open_ref(invocation.args)
            if len(lookup.rows) == 1 and lookup.message is None:
                self.open_artifact(lookup.rows[0].path)
            else:
                self._show_lookup(lookup)
        else:  # search — explicit /find or bare input
            self._show_lookup(self.adapter.search_rows(invocation.args))
