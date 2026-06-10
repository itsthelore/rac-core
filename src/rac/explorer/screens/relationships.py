"""Relationship screen — traverse the knowledge graph (v0.8.5).

Renders an artifact's outgoing relationships, its impact (what depends on it),
and its lineage, all from the loaded repository model (ADR-016). Connected
artifacts are selectable: opening one shows its context view, from which `g`
reopens this screen — traversal continues across the graph, Esc unwinds.
Terminal-readable text only; no canvas (Initiative 5).
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, Header, OptionList, Static
from textual.widgets.option_list import Option

from rac.explorer.adapter import ExplorerAdapter
from rac.explorer.state import RelationshipsView


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


class RelationshipScreen(Screen[None]):
    """Connected artifacts are selectable; `g`/Enter continues the traversal."""

    BINDINGS = [Binding("escape", "back", "Back")]

    def __init__(self, adapter: ExplorerAdapter, view: RelationshipsView) -> None:
        super().__init__()
        self.adapter = adapter
        self.view = view
        # Navigable connected artifacts (outgoing resolved + impact sources),
        # keyed by option index so duplicate paths stay unique.
        self._paths: list[str] = []

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(render_sections(self.view), id="relationship-panel")
        options: list[Option] = []
        for link in (*self.view.outgoing, *self.view.impact):
            if link.navigable:
                options.append(Option(f"{link.kind}: {link.label}", id=str(len(self._paths))))
                self._paths.append(link.target_path)
        if not options:
            options.append(Option("No connected artifacts to open", id=None, disabled=True))
        connected = OptionList(*options, id="connected-list")
        connected.border_title = "Open connected artifact"
        yield connected
        yield Footer()

    def on_mount(self) -> None:
        if self._paths:
            self.query_one(OptionList).focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_id is None:
            return
        context = self.adapter.context_state(self._paths[int(event.option_id)])
        if context is not None:
            from .context import ContextScreen

            self.app.push_screen(ContextScreen(self.adapter, context))

    def action_back(self) -> None:
        self.app.pop_screen()
