"""Health screen — repository health at a glance (v0.8.2).

Renders Core's score, the four health areas, and a prioritized attention list
(DESIGN-health-model). Explorer calculates nothing here; selecting an
attention item opens the affected artifact's context view, and Esc backs out.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, Header, OptionList, Static
from textual.widgets.option_list import Option

from rac.explorer.adapter import ExplorerAdapter
from rac.explorer.state import HealthState

from .context import ContextScreen


def render_overview(health: HealthState) -> str:
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


class HealthScreen(Screen[None]):
    """Score + areas + a selectable attention list; Esc backs out."""

    BINDINGS = [
        Binding("escape", "back", "Back"),
        Binding("r", "recommendations", "Recommendations"),
    ]

    def __init__(self, adapter: ExplorerAdapter, health: HealthState) -> None:
        super().__init__()
        self.adapter = adapter
        self.health = health

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(render_overview(self.health), id="health-overview")
        # Options are keyed by list index, not artifact path: several findings
        # may concern the same artifact, and OptionList ids must be unique.
        options: list[Option] = []
        if self.health.attention:
            for i, row in enumerate(self.health.attention):
                options.append(
                    Option(f"{row.severity_label}  {row.identifier}  {row.message}", id=str(i))
                )
        else:
            options.append(Option("✓ Nothing needs attention", disabled=True))
        attention = OptionList(*options, id="attention-list")
        attention.border_title = "Attention"
        yield attention
        yield Footer()

    def on_mount(self) -> None:
        if self.health.attention:
            self.query_one(OptionList).focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_id is None:
            return
        row = self.health.attention[int(event.option_id)]
        context = self.adapter.context_state(row.path)
        if context is not None:
            self.app.push_screen(ContextScreen(self.adapter, context))

    def action_recommendations(self) -> None:
        recommendations = self.adapter.recommendations_state()
        if recommendations is not None:
            from .recommendations import RecommendationsScreen

            self.app.push_screen(RecommendationsScreen(self.adapter, recommendations))

    def action_back(self) -> None:
        self.app.pop_screen()
