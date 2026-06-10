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

from rac.explorer import commands
from rac.explorer.adapter import ExplorerAdapter
from rac.explorer.state import LoadErrorState, LoadProgressState, RepositorySummaryState
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
)

# The sidebar hides below this width so the context panel keeps room to read.
_SIDEBAR_MIN_WIDTH = 80

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
    ]

    def __init__(self, adapter: ExplorerAdapter) -> None:
        super().__init__()
        self.adapter = adapter
        self._history: list[str] = []
        self._last_focus: Widget | None = None

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
            return
        view_id, path = self._history.pop()
        if view_id == "view-context" and path is not None:
            self.open_artifact(path, record=False)
            return
        self.show_view(view_id, record=False)

    # --- loading (moved from the v0.8.0 repository screen) ----------------------

    def action_reload(self) -> None:
        self.query_one(HomeView).panel.show_progress(
            LoadProgressState(phase="scan", completed=0, total=None, label="Scanning artifacts")
        )
        self._load_repository()

    @work(thread=True, exclusive=True, group="repository-load")
    def _load_repository(self) -> RepositorySummaryState | LoadErrorState | None:
        worker = get_current_worker()
        token = _WorkerCancelToken(worker)

        def relay(progress: LoadProgressState) -> None:
            if not worker.is_cancelled:
                self.app.call_from_thread(self.query_one(HomeView).panel.show_progress, progress)

        return self.adapter.load(on_progress=relay, cancel=token)

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        if event.worker.group != "repository-load":
            return
        home = self.query_one(HomeView)
        if event.state == WorkerState.SUCCESS:
            result = event.worker.result
            if isinstance(result, RepositorySummaryState):
                home.show_result(result)
                self.query_one(NavigationSidebar).show_repository(self.adapter.browser_state())
                self.query_one(StatusLine).show_summary(result)
            elif isinstance(result, LoadErrorState):
                home.panel.show_error(result)
            # None — the load was cancelled; a fresh worker is taking over.
        elif event.state == WorkerState.ERROR:
            # The adapter is the recoverable boundary, so this is unexpected —
            # but the interface must still never crash (Initiative 6).
            home.panel.show_error(
                LoadErrorState(
                    title="Unexpected failure",
                    detail=str(event.worker.error),
                    can_retry=True,
                )
            )

    # --- navigation ---------------------------------------------------------------

    def open_artifact(
        self, path: str, *, tab: str | None = None, reveal: bool = True, record: bool = True
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
        # Snapshot before the context view is overwritten, so Esc can unwind
        # artifact-to-artifact traversal across the graph.
        if record and not same:
            self._history.append(self._snapshot())
        self.query_one(ContextView).show_artifact(
            context, markdown, relationships, findings, tab=tab
        )
        self.show_view("view-context", record=False)
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
        # Workspace continuity (v0.8.6): reopen the last artifact, on request.
        if self.query_one(HomeView).onboarding_active:
            return
        path = self.adapter.resume_path()
        if path is not None:
            self.open_artifact(path)

    # --- command routing (the summoned `/` palette) --------------------------------

    def _show_results(self, options: list[Option | None], *, focus: bool = False) -> None:
        self.query_one(ResultsView).show_options(options, focus_first=focus)
        self.show_view("view-results", focus=focus)

    def _show_message(self, message: str) -> None:
        self._show_results([Option(message, disabled=True)])

    def _show_examples(self) -> None:
        options: list[Option | None] = [Option("Start typing…  Try:", disabled=True)]
        options.extend(Option(f"  {example}", disabled=True) for example in commands.EXAMPLES)
        self._show_results(options)

    def _show_lookup(self, lookup) -> None:
        options: list[Option | None] = []
        if lookup.message:
            options.append(Option(lookup.message, disabled=True))
        options.extend(
            Option(f"{row.status_label}  {row.title or row.id}  ({row.type})", id=row.path)
            for row in lookup.rows
        )
        self._show_results(options, focus=bool(lookup.rows))

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
