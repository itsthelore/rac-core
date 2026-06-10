"""Recommendations screen — findings with impact and a suggested action (v0.8.3).

Presents RAC Core's review findings grouped by category, explaining each before
suggesting an action (DESIGN-recommendations). Explorer applies nothing;
selecting a recommendation opens the affected artifact's context view.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, Header, OptionList
from textual.widgets.option_list import Option

from rac.explorer.adapter import ExplorerAdapter
from rac.explorer.state import RecommendationRow, RecommendationsState

from .context import ContextScreen


def _prompt(row: RecommendationRow) -> str:
    """One recommendation as a multi-line block: finding → impact → action."""
    return (
        f"{row.severity_label}  ·  {row.category}\n"
        f"  {row.identifier}  {row.finding}\n"
        f"  Impact: {row.impact}\n"
        f"  Action: {row.action}"
    )


class RecommendationsScreen(Screen[None]):
    """Category-grouped recommendations; Enter opens the artifact, Esc backs."""

    BINDINGS = [Binding("escape", "back", "Back")]

    def __init__(self, adapter: ExplorerAdapter, recommendations: RecommendationsState) -> None:
        super().__init__()
        self.adapter = adapter
        self.recommendations = recommendations
        # Selection maps an option index → the affected artifact path; several
        # recommendations may concern one artifact, so ids must stay unique.
        self._paths: list[str] = []

    def compose(self) -> ComposeResult:
        yield Header()
        options: list[Option | None] = []
        if self.recommendations.groups:
            for category, rows in self.recommendations.groups:
                if options:
                    options.append(None)
                options.append(Option(f"{category} ({len(rows)})", id=None, disabled=True))
                for row in rows:
                    options.append(Option(_prompt(row), id=str(len(self._paths))))
                    self._paths.append(row.path)
        else:
            options.append(Option("✓ No recommendations", id=None, disabled=True))
        option_list = OptionList(*options, id="recommendations-list")
        option_list.border_title = f"Recommendations ({self.recommendations.total})"
        yield option_list
        yield Footer()

    def on_mount(self) -> None:
        if self.recommendations.total:
            self.query_one(OptionList).focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_id is None:
            return
        context = self.adapter.context_state(self._paths[int(event.option_id)])
        if context is not None:
            self.app.push_screen(ContextScreen(self.adapter, context))

    def action_back(self) -> None:
        self.app.pop_screen()
