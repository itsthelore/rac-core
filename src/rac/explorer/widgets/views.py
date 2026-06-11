"""Context-region views — the widgets the main screen swaps (v0.8.7).

One stable frame, many views: home, artifact context (tabbed), health,
recommendations, import, and command results all render inside the context
panel via ``ContentSwitcher`` — the layout never jumps
(DESIGN-visual-system). Views render UI state and own no intelligence
(ADR-015); navigation requests bubble to the screen as messages.
"""

from __future__ import annotations

from dataclasses import replace

from textual import events, work
from textual.app import ComposeResult, SuspendNotSupported
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.message import Message
from textual.widgets import Input, Markdown, OptionList, Static, TabbedContent, TabPane, Tabs
from textual.widgets.option_list import Option
from textual.worker import Worker, WorkerState, get_current_worker

from rac.explorer import editor as editor_mod
from rac.explorer import firstrun, mascot
from rac.explorer.adapter import ExplorerAdapter
from rac.explorer.preferences import GROUPING_FLAT, GROUPING_TYPE, preferences_path
from rac.explorer.state import (
    ContextState,
    HealthState,
    ImportPreview,
    LoadErrorState,
    LoadProgressState,
    RecommendationRow,
    RecommendationsState,
    RelationshipsView,
    RepositorySummaryState,
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
        self._mascot_state: str | None = None
        self._mascot_frame = 0

    def compose(self) -> ComposeResult:
        art = Static(id="mascot")
        art.display = False
        yield art
        yield RepositoryPanel(id="repository-panel")

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
        self.panel.show_progress(progress)
        if self._mascot_state != mascot.SEARCHING:
            self.show_mascot(mascot.SEARCHING)

    def show_result(self, summary: RepositorySummaryState) -> None:
        if firstrun.is_first_run():
            self._onboarding_summary = summary
            self.panel.show_onboarding(summary, header=self._welcome_header(summary))
            self.show_mascot(mascot.EMPTY if summary.artifact_total == 0 else mascot.DISCOVERY)
            return
        self.panel.show_summary(summary)
        self._mascot_for_summary(summary)

    def show_error(self, error: LoadErrorState) -> None:
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
            summary, self._onboarding_summary = self._onboarding_summary, None
            firstrun.mark_onboarded()
            self.panel.show_summary(summary)
            self._mascot_for_summary(summary)
            return
        self.post_message(BrowseRequested())


class ContextView(Vertical):
    """One artifact in full: Content │ Inspection │ Links │ Findings.

    Content (the default tab) renders the document's Markdown read-only —
    editing belongs to external tools (ADR-024).
    """

    BINDINGS = [
        Binding("e", "open_in_editor", "Open in editor"),
        Binding("g", "links", "Links"),
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

        self.query_one(TabbedContent).active = tab or "tab-content"

    def take_focus(self) -> None:
        # TabbedContent is a container; its Tabs strip takes the focus.
        self.query_one(Tabs).focus()

    def action_open_in_editor(self) -> None:
        # ADR-024: Explorer hands the file to an external editor; it never edits.
        if self.context is None:
            return
        editor = self.adapter.resolved_editor()
        if editor is not None and editor_mod.is_terminal_editor(editor):
            # Terminal editors own the terminal: suspend, run, resume.
            try:
                with self.app.suspend():
                    outcome = self.adapter.open_in_editor(self.context.path, blocking=True)
            except SuspendNotSupported:
                outcome = editor_mod.EditorOutcome(
                    launched=False,
                    message=(
                        f"'{editor}' needs the terminal, and this session cannot "
                        "suspend. Configure a GUI editor in /settings."
                    ),
                )
        else:
            outcome = self.adapter.open_in_editor(self.context.path)
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
        attention = OptionList(id="attention-list")
        attention.border_title = "Attention"
        yield attention

    def show_health(self, health: HealthState) -> None:
        self.health = health
        self.query_one("#health-overview", Static).update(render_health(health))
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
        self.post_message(OpenArtifact(self.health.attention[int(event.option_id)].path))

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
        yield OptionList(id="recommendations-list")

    def show_recommendations(self, recommendations: RecommendationsState) -> None:
        listing = self.query_one(OptionList)
        listing.clear_options()
        listing.border_title = f"Recommendations ({recommendations.total})"
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
            self.post_message(OpenArtifact(self._paths[int(event.option_id)]))

    def action_export(self) -> None:
        result = self.adapter.export_recommendations()
        if isinstance(result, str):
            return  # nothing to export
        from rac.explorer.screens.confirm import ConfirmWriteScreen

        self.app.push_screen(ConfirmWriteScreen(self.adapter, result))


class ImportView(Vertical):
    """Guided import: converting → preview (y confirms) → result (v0.8.4).

    Conversion runs off the UI thread; nothing is written until the user
    confirms, and writes never overwrite (Initiative 4, ADR-024).
    """

    can_focus = True
    BINDINGS = [Binding("y", "confirm", "Confirm import")]

    def __init__(self, adapter: ExplorerAdapter) -> None:
        super().__init__(id="view-import")
        self.adapter = adapter
        self.source = ""
        self.target: str | None = None
        self.preview: ImportPreview | None = None
        self._done = False

    def compose(self) -> ComposeResult:
        yield Static(id="import-panel")

    def start(self, source: str, target: str | None) -> None:
        self.source = source
        self.target = target
        self.preview = None
        self._done = False
        self.query_one("#import-panel", Static).update(f"Converting {source}…")
        self._convert()

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
            panel.update(render_preview(result))
        else:  # an error message — recoverable, no write happened
            self._done = True
            panel.update(f"✗ Import failed\n\n{result}\n\nPress Esc to go back.")

    def action_confirm(self) -> None:
        if self.preview is None or self._done:
            return
        message = self.adapter.write_import(self.preview)
        self._done = True
        self.query_one("#import-panel", Static).update(f"{message}\n\nPress Esc to go back.")


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
            grouping = GROUPING_FLAT if prefs.artifact_grouping == GROUPING_TYPE else GROUPING_TYPE
            updated = replace(prefs, artifact_grouping=grouping)
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
    (DESIGN-command-surface).
    """

    def __init__(self) -> None:
        super().__init__(id="view-results")
        self.border_title = "Results"

    def compose(self) -> ComposeResult:
        yield OptionList(id="command-results")

    def show_options(self, options: list[Option | None], *, focus_first: bool = False) -> None:
        listing = self.query_one(OptionList)
        listing.clear_options()
        listing.add_options(options)
        if focus_first:
            _highlight_first(listing)

    def take_focus(self) -> None:
        self.query_one(OptionList).focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_id is not None:
            self.post_message(OpenArtifact(event.option_id))
