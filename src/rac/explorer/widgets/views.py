"""Context-region views — the widgets the main screen swaps (v0.8.7).

One stable frame, many views: home, artifact context (tabbed), health,
recommendations, import, and command results all render inside the context
panel via ``ContentSwitcher`` — the layout never jumps
(DESIGN-visual-system). Views render UI state and own no intelligence
(ADR-015); navigation requests bubble to the screen as messages.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from textual import events, work
from textual.app import ComposeResult, SuspendNotSupported
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Input, Markdown, OptionList, Static, TabbedContent, TabPane, Tabs
from textual.widgets.option_list import Option
from textual.worker import Worker, WorkerState, get_current_worker

from rac.explorer import editor as editor_mod
from rac.explorer import firstrun, mascot
from rac.explorer.adapter import ExplorerAdapter
from rac.explorer.preferences import GROUPINGS, preferences_path
from rac.explorer.state import (
    ArtifactRow,
    ContextState,
    HealthState,
    ImportPreview,
    LoadErrorState,
    LoadProgressState,
    RecommendationRow,
    RecommendationsState,
    RelationshipsView,
    RepositorySummaryState,
    StatsState,
)
from rac.explorer.widgets import RepositoryPanel

_PREVIEW_LINES = 20


class OpenArtifact(Message):
    """A view asks the screen to open an artifact's context view."""

    def __init__(self, path: str, tab: str | None = None) -> None:
        super().__init__()
        self.path = path
        self.tab = tab


class BrowseRequested(Message):
    """The home view asks the screen to move focus into the sidebar."""


class ShowRecommendations(Message):
    """The health view asks the screen to show repository recommendations."""


class SettingsChanged(Message):
    """A preference changed; the screen may refresh dependent widgets."""

    def __init__(self, key: str) -> None:
        super().__init__()
        self.key = key


def launch_editor(widget: Widget, adapter: ExplorerAdapter, path: str) -> editor_mod.EditorOutcome:
    """Open ``path`` in the configured editor from any widget (ADR-024).

    Terminal editors run with the application suspended and resumed;
    sessions that cannot suspend get guidance instead of a blind launch.
    """
    editor = adapter.resolved_editor()
    if editor is not None and editor_mod.is_terminal_editor(editor):
        # The live watcher (v0.8.9) holds while the editor owns the terminal
        # and rescans the moment it returns, so the saved edit shows at once.
        # Duck-typed: importing MainScreen here would be circular.
        screen = widget.screen
        pause = getattr(screen, "pause_watching", lambda: None)
        resume = getattr(screen, "resume_watching", lambda: None)
        try:
            pause()
            with widget.app.suspend():
                return adapter.open_in_editor(path, blocking=True)
        except SuspendNotSupported:
            return editor_mod.EditorOutcome(
                launched=False,
                message=(
                    f"'{editor}' needs the terminal, and this session cannot "
                    "suspend. Configure a GUI editor in /settings."
                ),
            )
        finally:
            resume()
    return adapter.open_in_editor(path)


def _highlight_first(listing: OptionList) -> None:
    """Highlight the first selectable option after a dynamic rebuild.

    Rebuilt OptionLists start with no highlight, so Enter would be a no-op
    until the user moves the cursor.
    """
    for index in range(listing.option_count):
        if not listing.get_option_at_index(index).disabled:
            listing.highlighted = index
            return


# --- rendering helpers (carried over from the v0.8.1–v0.8.5 screens) --------


def render_context(context: ContextState) -> str:
    """The inspection tab as terminal-readable text (icons + labels, ADR-028)."""
    lines = [
        context.title or context.id,
        "",
        f"ID          {context.id}",
        f"Type        {context.type}",
        f"Path        {context.path}",
        f"Status      {context.status_label}",
    ]
    aliases = [a for a in context.aliases if a != context.id]
    if aliases:
        lines.append(f"Aliases     {', '.join(aliases)}")

    lines.append("")
    if context.missing_recommended:
        names = ", ".join(s.title() for s in context.missing_recommended)
        lines.append(f"Completeness  ! missing recommended: {names}")
    else:
        lines.append("Completeness  ✓ all recommended sections present")

    lines.extend(["", "Relationships"])
    if context.outgoing or context.incoming:
        lines.extend(f"  {line}" for line in context.outgoing)
        lines.extend(f"  {line}" for line in context.incoming)
    else:
        lines.append("  none declared or inbound")

    lines.extend(["", "Diagnostics"])
    if context.diagnostics:
        lines.extend(f"  {line}" for line in context.diagnostics)
    else:
        lines.append("  ✓ none")
    return "\n".join(lines)


def render_sections(view: RelationshipsView) -> str:
    """Outgoing / Impact / Lineage as terminal-readable text."""
    lines = [view.title or view.id, "", "Relationships"]
    if view.outgoing:
        lines.extend(f"  {link.kind} → {link.label}" for link in view.outgoing)
    else:
        lines.append("  none declared")

    lines.extend(["", "Impact (what depends on this)"])
    if view.impact:
        lines.extend(f"  ← {link.label} ({link.kind})" for link in view.impact)
    else:
        lines.append("  nothing depends on this artifact")

    lines.extend(["", "Lineage"])
    if view.lineage:
        lines.extend(f"  {line}" for line in view.lineage)
    else:
        lines.append("  no recorded supersession")
    return "\n".join(lines)


def render_health(health: HealthState) -> str:
    """The score and the four areas as terminal-readable text."""
    lines = [
        f"Repository Health  {health.directory}",
        "",
        f"Score   {health.score} / 100   {health.score_label}",
        "",
        "Areas",
    ]
    for area in health.areas:
        lines.append(f"  {area.status_label:<18} {area.name:<14} {area.detail}")
    return "\n".join(lines)


def render_recommendation(row: RecommendationRow) -> str:
    """One recommendation as a multi-line block: finding → impact → action."""
    return (
        f"{row.severity_label}  ·  {row.category}\n"
        f"  {row.identifier}  {row.finding}\n"
        f"  Impact: {row.impact}\n"
        f"  Action: {row.action}"
    )


def render_preview(preview: ImportPreview) -> str:
    """A converted document and its target, awaiting confirmation.

    Carries no key hints of its own: the status line covers the import view
    and the confirm modal renders its own chips (DESIGN-visual-system).
    """
    body = preview.markdown.splitlines()
    shown = body[:_PREVIEW_LINES]
    more = len(body) - len(shown)
    lines = [
        f"Source     {preview.source}",
        f"Converter  {preview.converter}",
        f"Target     {preview.target}",
        "",
        "Preview (converted Markdown)",
        "─" * 40,
        *shown,
    ]
    if more > 0:
        lines.append(f"… {more} more line(s)")
    lines.append("─" * 40)
    return "\n".join(lines)


# --- views -------------------------------------------------------------------


class HomeView(Vertical):
    """The repository summary: loading → summary/onboarding → error.

    Owns the mascot (v0.8.8): a frame sequence cycled on a slow timer, only
    while visible and while animations are enabled (DESIGN-mascot-animations).
    The searching state plays during a load; welcome and empty states keep
    theirs; everything else hides the mascot.
    """

    can_focus = True
    BINDINGS = [Binding("enter", "continue", "Browse")]

    def __init__(self, adapter: ExplorerAdapter) -> None:
        super().__init__(id="view-home")
        self.adapter = adapter
        # The summary held back while first-run onboarding is on screen;
        # Enter dismisses onboarding and reveals it (no forced setup).
        self._onboarding_summary: RepositorySummaryState | None = None
        # The optional editor step between welcome and summary (v0.8.11).
        self._prompting_editor = False
        self._mascot_state: str | None = None
        self._mascot_frame = 0

    def compose(self) -> ComposeResult:
        art = Static(id="mascot")
        art.display = False
        yield art
        yield RepositoryPanel(id="repository-panel")
        editor_input = Input(
            placeholder="Editor command, e.g. code or vim — empty keeps $VISUAL/$EDITOR",
            id="firstrun-editor",
        )
        editor_input.display = False
        yield editor_input

    def on_mount(self) -> None:
        self.set_interval(0.6, self._tick_mascot)

    @property
    def onboarding_active(self) -> bool:
        return self._onboarding_summary is not None

    @property
    def panel(self) -> RepositoryPanel:
        return self.query_one(RepositoryPanel)

    # --- the mascot -----------------------------------------------------------

    def show_mascot(self, state: str) -> None:
        if not self.adapter.preferences.mascot:
            return
        self._mascot_state = state
        self._mascot_frame = 0
        art = self.query_one("#mascot", Static)
        art.display = True
        art.update(mascot.figure(state, 0, animations=self.adapter.preferences.animations))

    def hide_mascot(self) -> None:
        self._mascot_state = None
        self.query_one("#mascot", Static).display = False

    def _tick_mascot(self) -> None:
        if self._mascot_state is None or not self.adapter.preferences.animations:
            return
        self._mascot_frame += 1
        self.query_one("#mascot", Static).update(
            mascot.figure(self._mascot_state, self._mascot_frame)
        )

    # --- load states ------------------------------------------------------------

    def show_progress(self, progress: LoadProgressState) -> None:
        # Loading and welcome compose centred ("welcome"); the summary reads
        # top-left like every other view.
        self.add_class("welcome")
        self.panel.show_progress(progress)
        if self._mascot_state != mascot.SEARCHING:
            self.show_mascot(mascot.SEARCHING)

    def show_result(self, summary: RepositorySummaryState) -> None:
        if firstrun.is_first_run():
            self._onboarding_summary = summary
            self.add_class("welcome")
            self.panel.show_onboarding(summary, header=self._welcome_header(summary))
            self.show_mascot(mascot.EMPTY if summary.artifact_total == 0 else mascot.DISCOVERY)
            return
        self.remove_class("welcome")
        self.panel.show_summary(summary)
        self._mascot_for_summary(summary)

    def show_error(self, error: LoadErrorState) -> None:
        self.remove_class("welcome")
        self.panel.show_error(error)
        self.hide_mascot()

    def _mascot_for_summary(self, summary: RepositorySummaryState) -> None:
        # The mascot lives in the welcome and empty states only (DESIGN-mascot).
        if summary.artifact_total == 0:
            self.show_mascot(mascot.EMPTY)
        else:
            self.hide_mascot()

    def _welcome_header(self, summary: RepositorySummaryState) -> str:
        """Recent repositories and a resume hint for the welcome state."""
        lines: list[str] = []
        resume = self.adapter.resume_path()
        if resume is not None:
            lines.append(f"Resume last artifact: press .  ({resume})")
        recent = [d for d in self.adapter.workspace.recent if d != self.adapter.directory]
        if recent:
            lines.append("Recent repositories: " + ", ".join(recent[:3]))
        return "\n".join(lines)

    def action_continue(self) -> None:
        if self._onboarding_summary is not None:
            if not self._prompting_editor:
                # The optional editor step (v0.8.11): one prefilled,
                # skippable line between the welcome and the summary.
                self._prompting_editor = True
                self.panel.show_editor_prompt(editor_mod.resolve_editor(""))
                field = self.query_one("#firstrun-editor", Input)
                field.display = True
                field.focus()
            return
        self.post_message(BrowseRequested())

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        # Enter accepts: an empty value stores "" — the $VISUAL/$EDITOR
        # fallback — matching /settings semantics (ADR-024: explorer.json only).
        self.adapter.save_preferences(replace(self.adapter.preferences, editor=event.value.strip()))
        self._finish_onboarding()

    def on_key(self, event: events.Key) -> None:
        # Esc skips the editor step without writing anything; today's
        # behavior exactly. Only intercepted while the prompt is up.
        if event.key == "escape" and self._prompting_editor:
            event.stop()
            self._finish_onboarding()

    def _finish_onboarding(self) -> None:
        summary, self._onboarding_summary = self._onboarding_summary, None
        self._prompting_editor = False
        self.query_one("#firstrun-editor", Input).display = False
        firstrun.mark_onboarded()
        self.remove_class("welcome")
        self.focus()
        if summary is not None:
            self.panel.show_summary(summary)
            self._mascot_for_summary(summary)


class ContextView(Vertical):
    """One artifact in full: Content │ Inspection │ Links │ Findings.

    Content (the default tab) renders the document's Markdown read-only
    (ADR-024) and takes the keyboard on open: the pane scrolls with
    `j`/`k`/PgUp/PgDn, `←`/`→` switch tabs from anywhere in the view, and
    artifact references inside the document navigate in place (v0.8.8).
    """

    BINDINGS = [
        Binding("e", "open_in_editor", "Open in editor"),
        Binding("g", "links", "Links"),
        Binding("j", "scroll_content(1)", "Scroll", show=False),
        Binding("k", "scroll_content(-1)", "Scroll", show=False),
        Binding("left", "switch_tab(-1)", "Tab", show=False),
        Binding("right", "switch_tab(1)", "Tab", show=False),
    ]

    def __init__(self, adapter: ExplorerAdapter) -> None:
        super().__init__(id="view-context")
        self.adapter = adapter
        self.context: ContextState | None = None
        # Navigable connected artifacts (outgoing resolved + impact sources),
        # keyed by option index so duplicate paths stay unique.
        self._link_paths: list[str] = []

    def compose(self) -> ComposeResult:
        with TabbedContent(id="context-tabs"):
            with TabPane("Content", id="tab-content"), VerticalScroll(id="content-scroll"):
                yield Markdown("", id="artifact-markdown")
            with TabPane("Inspection", id="tab-inspection"):
                yield Static(id="context-panel")
                yield Static("", id="context-status")
            with TabPane("Links", id="tab-links"):
                yield Static(id="relationship-panel")
                yield OptionList(id="connected-list")
            with TabPane("Findings", id="tab-findings"):
                yield Static(id="findings-panel")

    def show_artifact(
        self,
        context: ContextState,
        markdown_text: str,
        relationships: RelationshipsView | None,
        findings: tuple[RecommendationRow, ...],
        tab: str | None = None,
    ) -> None:
        self.context = context
        self.query_one("#artifact-markdown", Markdown).update(markdown_text)
        self.query_one("#context-panel", Static).update(render_context(context))
        self.query_one("#context-status", Static).update("")

        self._link_paths = []
        connected = self.query_one("#connected-list", OptionList)
        connected.clear_options()
        if relationships is not None:
            self.query_one("#relationship-panel", Static).update(render_sections(relationships))
            for link in (*relationships.outgoing, *relationships.impact):
                if link.navigable:
                    connected.add_option(
                        Option(f"{link.kind}: {link.label}", id=str(len(self._link_paths)))
                    )
                    self._link_paths.append(link.target_path)
        if not self._link_paths:
            connected.add_option(Option("No connected artifacts to open", disabled=True))
        _highlight_first(connected)

        if findings:
            blocks = "\n\n".join(render_recommendation(row) for row in findings)
        else:
            blocks = "✓ No findings for this artifact"
        self.query_one("#findings-panel", Static).update(blocks)

        # Count badges: whether a tab is worth visiting, before visiting it.
        tabs = self.query_one(TabbedContent)
        diagnostics_count = len(context.diagnostics)
        tabs.get_tab("tab-inspection").label = (
            f"Inspection ({diagnostics_count})" if diagnostics_count else "Inspection"
        )
        links_count = len(self._link_paths)
        tabs.get_tab("tab-links").label = f"Links ({links_count})" if links_count else "Links"
        tabs.get_tab("tab-findings").label = (
            f"Findings ({len(findings)})" if findings else "Findings"
        )

        tabs.active = tab or "tab-content"
        # A fresh document starts at the top.
        self.query_one("#content-scroll", VerticalScroll).scroll_home(animate=False)

    def take_focus(self) -> None:
        # The document is the point: the content pane takes the keyboard on
        # open; other tabs hand focus to the tab strip.
        if self.query_one(TabbedContent).active == "tab-content":
            self.query_one("#content-scroll", VerticalScroll).focus()
        else:
            self.query_one(Tabs).focus()

    @property
    def active_tab(self) -> str:
        return self.query_one(TabbedContent).active

    @property
    def content_scroll_y(self) -> float:
        return self.query_one("#content-scroll", VerticalScroll).scroll_y

    def restore_scroll(self, y: float) -> None:
        """Put the document back where it was after an in-place refresh."""
        pane = self.query_one("#content-scroll", VerticalScroll)
        # After the Markdown re-renders: the target offset only exists once
        # the new content has a height.
        self.call_after_refresh(lambda: pane.scroll_to(y=y, animate=False))

    def action_scroll_content(self, direction: int) -> None:
        self.query_one("#content-scroll", VerticalScroll).scroll_relative(
            y=direction * 3, animate=False
        )

    def action_switch_tab(self, direction: int) -> None:
        tabs = self.query_one(Tabs)
        if direction > 0:
            tabs.action_next_tab()
        else:
            tabs.action_previous_tab()

    def on_markdown_link_clicked(self, event: Markdown.LinkClicked) -> None:
        # References inside the document are walkable hypertext: resolve
        # through the adapter and navigate with the same history as any open.
        event.stop()
        if self.context is None:
            return
        target = self.adapter.resolve_link(event.href, self.context.path)
        if target is not None:
            self.post_message(OpenArtifact(target))
        else:
            self.app.notify(f"Cannot resolve link: {event.href}", severity="warning")

    def action_open_in_editor(self) -> None:
        # ADR-024: Explorer hands the file to an external editor; it never edits.
        if self.context is None:
            return
        outcome = launch_editor(self, self.adapter, self.context.path)
        self.query_one("#context-status", Static).update(outcome.message)
        self.query_one(TabbedContent).active = "tab-inspection"

    def action_links(self) -> None:
        self.query_one(TabbedContent).active = "tab-links"
        self.query_one("#connected-list", OptionList).focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_id is not None:
            self.post_message(OpenArtifact(self._link_paths[int(event.option_id)]))


class HealthView(Vertical):
    """Score + areas + a selectable attention list (v0.8.2 renderers)."""

    BINDINGS = [Binding("r", "recommendations", "Recommendations")]

    def __init__(self) -> None:
        super().__init__(id="view-health")
        self.health: HealthState | None = None

    def compose(self) -> ComposeResult:
        yield Static(id="health-overview")
        yield OptionList(id="attention-list")

    def show_health(self, health: HealthState) -> None:
        self.health = health
        # A plain section line, not another border: the region border already
        # frames this view (v0.8.8 de-dup).
        self.query_one("#health-overview", Static).update(render_health(health) + "\n\nAttention")
        # Options are keyed by list index, not artifact path: several findings
        # may concern the same artifact, and OptionList ids must be unique.
        attention = self.query_one(OptionList)
        attention.clear_options()
        if health.attention:
            for i, row in enumerate(health.attention):
                attention.add_option(
                    Option(f"{row.severity_label}  {row.identifier}  {row.message}", id=str(i))
                )
        else:
            attention.add_option(Option("✓ Nothing needs attention", disabled=True))
        _highlight_first(attention)

    def take_focus(self) -> None:
        self.query_one(OptionList).focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_id is None or self.health is None:
            return
        # Drill-down (v0.8.9): an attention item lands on the tab that
        # explains it — the Inspection diagnostics — not on the document.
        path = self.health.attention[int(event.option_id)].path
        self.post_message(OpenArtifact(path, tab="tab-inspection"))

    def action_recommendations(self) -> None:
        self.post_message(ShowRecommendations())


class RecommendationsView(Vertical):
    """Category-grouped recommendations; Enter opens the artifact (v0.8.3)."""

    BINDINGS = [Binding("x", "export", "Export")]

    def __init__(self, adapter: ExplorerAdapter) -> None:
        super().__init__(id="view-recommendations")
        self.adapter = adapter
        # Selection maps an option index → the affected artifact path; several
        # recommendations may concern one artifact, so ids must stay unique.
        self._paths: list[str] = []

    def compose(self) -> ComposeResult:
        yield Static(id="recommendations-summary")
        yield OptionList(id="recommendations-list")

    def show_recommendations(self, recommendations: RecommendationsState) -> None:
        listing = self.query_one(OptionList)
        listing.clear_options()
        # A plain count line — the region border already says where we are.
        self.query_one("#recommendations-summary", Static).update(
            f"{recommendations.total} recommendation(s)"
        )
        self._paths = []
        options: list[Option | None] = []
        if recommendations.groups:
            for category, rows in recommendations.groups:
                if options:
                    options.append(None)
                options.append(Option(f"{category} ({len(rows)})", id=None, disabled=True))
                for row in rows:
                    options.append(Option(render_recommendation(row), id=str(len(self._paths))))
                    self._paths.append(row.path)
        else:
            options.append(Option("✓ No recommendations", id=None, disabled=True))
        listing.add_options(options)
        _highlight_first(listing)

    def take_focus(self) -> None:
        self.query_one(OptionList).focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_id is not None:
            # Drill-down (v0.8.9): a recommendation opens the artifact on its
            # own Findings tab, where this finding is shown in context.
            self.post_message(OpenArtifact(self._paths[int(event.option_id)], tab="tab-findings"))

    def action_export(self) -> None:
        result = self.adapter.export_recommendations()
        if isinstance(result, str):
            return  # nothing to export
        from rac.explorer.screens.confirm import ConfirmWriteScreen

        self.app.push_screen(ConfirmWriteScreen(self.adapter, result))


class ArtifactCreated(Message):
    """A `/new` write succeeded — the screen reloads and opens the artifact."""

    def __init__(self, path: str) -> None:
        super().__init__()
        self.path = path


class ImportView(Vertical):
    """The guided write workflow: preview (y confirms) → result (v0.8.4).

    One confirm path for both writers: document import (conversion runs off
    the UI thread) and `/new` template creation (v0.8.10, rendered
    instantly). Nothing is written until the user confirms, and writes never
    overwrite (Initiative 4, ADR-024).
    """

    can_focus = True
    BINDINGS = [Binding("y", "confirm", "Confirm write")]

    def __init__(self, adapter: ExplorerAdapter) -> None:
        super().__init__(id="view-import")
        self.adapter = adapter
        self.source = ""
        self.target: str | None = None
        self.preview: ImportPreview | None = None
        # The pending write for the confirmed preview; set with the preview
        # so `y` runs the right Core writer (import vs create).
        self._writer: Callable[[], str] | None = None
        self._done = False

    def compose(self) -> ComposeResult:
        yield Static(id="import-panel")

    def start(self, source: str, target: str | None) -> None:
        self.source = source
        self.target = target
        self.preview = None
        self._writer = None
        self._done = False
        self.query_one("#import-panel", Static).update(f"Converting {source}…")
        self._convert()

    def start_creation(self, artifact_type: str, target: str) -> None:
        """Preview a `/new` template; the confirmed write goes through Core's
        create service, which mints the ID (v0.8.10)."""
        self.preview = None
        self._writer = None
        self._done = False
        result = self.adapter.new_preview(artifact_type, target)
        panel = self.query_one("#import-panel", Static)
        if isinstance(result, ImportPreview):
            self.preview = result
            self._writer = lambda: self.adapter.write_new(artifact_type, target)
            panel.update(render_preview(result))
        else:
            self._done = True
            panel.update(f"✗ Cannot create\n\n{result}\n\nPress Esc to go back.")

    @work(thread=True, exclusive=True, group="import-convert")
    def _convert(self) -> ImportPreview | str:
        worker = get_current_worker()
        if worker.is_cancelled:  # pragma: no cover - defensive
            return "Cancelled"
        return self.adapter.import_preview(self.source, self.target)

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        if event.worker.group != "import-convert" or event.state != WorkerState.SUCCESS:
            return
        result = event.worker.result
        panel = self.query_one("#import-panel", Static)
        if isinstance(result, ImportPreview):
            self.preview = result
            preview = result
            self._writer = lambda: self.adapter.write_import(preview)
            panel.update(render_preview(result))
        else:  # an error message — recoverable, no write happened
            self._done = True
            panel.update(f"✗ Import failed\n\n{result}\n\nPress Esc to go back.")

    def action_confirm(self) -> None:
        if self.preview is None or self._writer is None or self._done:
            return
        target = self.preview.target
        message = self._writer()
        self._done = True
        self.query_one("#import-panel", Static).update(f"{message}\n\nPress Esc to go back.")
        if message.startswith("Created "):
            # The new artifact joins the workspace: reload, then open it.
            self.post_message(ArtifactCreated(target))


class StatsView(Vertical):
    """The portfolio statistics dashboard (v0.8.10).

    Collection re-walks the corpus, so it runs in a worker on request —
    never during the repository load. The dashboard scrolls under the
    keyboard like the content tab.
    """

    BINDINGS = [
        Binding("j", "scroll_stats(1)", "Scroll", show=False),
        Binding("k", "scroll_stats(-1)", "Scroll", show=False),
    ]

    def __init__(self, adapter: ExplorerAdapter) -> None:
        super().__init__(id="view-stats")
        self.adapter = adapter

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="stats-scroll", can_focus=True):
            yield Static(id="stats-panel")

    def show_stats(self) -> None:
        self.query_one("#stats-panel", Static).update("Collecting portfolio statistics…")
        self._collect()

    @work(thread=True, exclusive=True, group="stats-collect")
    def _collect(self) -> StatsState:
        return self.adapter.stats_state()

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        if event.worker.group != "stats-collect" or event.state != WorkerState.SUCCESS:
            return
        stats = event.worker.result
        if isinstance(stats, StatsState):
            blocks = [f"Portfolio Statistics  {stats.directory}"]
            for title, lines in stats.sections:
                blocks.append("")
                blocks.append(title)
                blocks.extend(f"  {line}" for line in lines)
            self.query_one("#stats-panel", Static).update("\n".join(blocks))

    def take_focus(self) -> None:
        self.query_one("#stats-scroll", VerticalScroll).focus()

    def action_scroll_stats(self, direction: int) -> None:
        self.query_one("#stats-scroll", VerticalScroll).scroll_relative(
            y=direction * 3, animate=False
        )


class SettingsView(Vertical):
    """Interactive settings — Explorer edits its own config only (ADR-024).

    Enter changes the highlighted setting: enumerations cycle (the theme
    live-previews), booleans toggle, and the editor row takes typed input.
    Every change persists immediately through the adapter (v0.8.8).
    """

    def __init__(self, adapter: ExplorerAdapter) -> None:
        super().__init__(id="view-settings")
        self.adapter = adapter

    def compose(self) -> ComposeResult:
        yield OptionList(id="settings-list")
        editor_input = Input(
            placeholder="Editor command, e.g. code or vim — empty uses $VISUAL/$EDITOR",
            id="settings-editor-input",
        )
        editor_input.display = False
        yield editor_input
        yield Static(id="settings-footer")

    def show_settings(self, *, highlight: str | None = None) -> None:
        prefs = self.adapter.preferences
        rows = (
            ("theme", prefs.theme),
            ("mascot", "on" if prefs.mascot else "off"),
            ("animations", "on" if prefs.animations else "off"),
            ("artifact_grouping", prefs.artifact_grouping),
            ("editor", prefs.editor or "(from $VISUAL / $EDITOR)"),
        )
        listing = self.query_one("#settings-list", OptionList)
        listing.clear_options()
        listing.add_options([Option(f"{key:<19} {value}", id=key) for key, value in rows])
        keys = [key for key, _ in rows]
        listing.highlighted = keys.index(highlight) if highlight in keys else 0
        self.query_one("#settings-footer", Static).update(
            f"Enter changes a setting · stored in {preferences_path()}"
        )

    def take_focus(self) -> None:
        self.query_one("#settings-list", OptionList).focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        key = event.option_id
        prefs = self.adapter.preferences
        if key == "theme":
            themes = sorted(self.app.available_themes)
            current = themes.index(prefs.theme) if prefs.theme in themes else -1
            chosen = themes[(current + 1) % len(themes)]
            self.app.theme = chosen  # live preview before anything else
            updated = replace(prefs, theme=chosen)
        elif key == "mascot":
            updated = replace(prefs, mascot=not prefs.mascot)
        elif key == "animations":
            updated = replace(prefs, animations=not prefs.animations)
        elif key == "artifact_grouping":
            # folders → type → flat → folders (the canonical order, v0.8.10).
            current = GROUPINGS.index(prefs.artifact_grouping)
            updated = replace(prefs, artifact_grouping=GROUPINGS[(current + 1) % len(GROUPINGS)])
        else:  # editor — reveal the inline input instead of cycling
            field = self.query_one("#settings-editor-input", Input)
            field.display = True
            field.value = prefs.editor
            field.focus()
            return
        self.adapter.save_preferences(updated)
        self.show_settings(highlight=key)
        if key is not None:
            self.post_message(SettingsChanged(key))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        self.adapter.save_preferences(replace(self.adapter.preferences, editor=event.value.strip()))
        self._dismiss_editor_input()
        self.post_message(SettingsChanged("editor"))

    def on_key(self, event: events.Key) -> None:
        # Esc while typing the editor command cancels the edit only; from the
        # list it bubbles to the screen's view history as usual.
        field = self.query_one("#settings-editor-input", Input)
        if event.key == "escape" and field.display:
            event.stop()
            self._dismiss_editor_input()

    def _dismiss_editor_input(self) -> None:
        self.query_one("#settings-editor-input", Input).display = False
        self.show_settings(highlight="editor")
        self.take_focus()


class ResultsView(Vertical):
    """Search results, lookups, and help — in the context region.

    Results render here rather than in a modal, so the layout never jumps
    (DESIGN-command-surface). Artifact results can be narrowed by type from
    the keyboard: `f` cycles all → each type present → all (v0.8.9). The
    filter is presentation state only — it re-filters rows the search
    already returned.
    """

    BINDINGS = [Binding("f", "cycle_filter", "Filter")]

    def __init__(self) -> None:
        super().__init__(id="view-results")
        self.border_title = "Results"
        self._rows: tuple[ArtifactRow, ...] = ()
        self._message: str | None = None
        self._filter: str | None = None

    def compose(self) -> ComposeResult:
        filter_line = Static(id="results-filter")
        filter_line.display = False
        yield filter_line
        yield OptionList(id="command-results")

    def show_options(self, options: list[Option | None], *, focus_first: bool = False) -> None:
        """Informational listings (help, examples, schema) — not filterable."""
        self._rows = ()
        self._message = None
        self._filter = None
        self.query_one("#results-filter", Static).display = False
        listing = self.query_one(OptionList)
        listing.clear_options()
        listing.add_options(options)
        if focus_first:
            _highlight_first(listing)

    def show_lookup(self, rows: tuple[ArtifactRow, ...], message: str | None = None) -> None:
        """Artifact results; `f` narrows them by type."""
        self._rows = rows
        self._message = message
        self._filter = None
        self._render_rows()

    def _types(self) -> list[str]:
        seen: list[str] = []
        for row in self._rows:
            if row.type not in seen:
                seen.append(row.type)
        return seen

    def action_cycle_filter(self) -> None:
        types = self._types()
        if len(types) < 2:
            return
        order: list[str | None] = [None, *types]
        self._filter = order[(order.index(self._filter) + 1) % len(order)]
        self._render_rows()

    def _render_rows(self) -> None:
        shown = [row for row in self._rows if self._filter in (None, row.type)]
        options: list[Option] = []
        if self._message:
            options.append(Option(self._message, disabled=True))
        options.extend(
            Option(f"{row.status_label}  {row.title or row.id}  ({row.type})", id=row.path)
            for row in shown
        )
        listing = self.query_one(OptionList)
        listing.clear_options()
        listing.add_options(options)
        _highlight_first(listing)
        filter_line = self.query_one("#results-filter", Static)
        if len(self._types()) > 1:
            filter_line.display = True
            filter_line.update(
                f"Filter: {self._filter or 'all'} · {len(shown)} of {len(self._rows)}"
                " · f cycles types"
            )
        else:
            filter_line.display = False

    def take_focus(self) -> None:
        self.query_one(OptionList).focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_id is not None:
            self.post_message(OpenArtifact(event.option_id))
