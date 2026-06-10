"""Context screen — one artifact in full (v0.8.1).

Identity, validation state, completeness, relationships, and diagnostics,
rendered from the loaded repository model. Esc returns to the browser.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from rac.explorer.state import ContextState


def render_context(context: ContextState) -> str:
    """The context view as terminal-readable text (icons + labels, ADR-028)."""
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


class ContextScreen(Screen[None]):
    """Read-only artifact context; editing belongs to external tools (ADR-024)."""

    BINDINGS = [Binding("escape", "back", "Back")]

    def __init__(self, context: ContextState) -> None:
        super().__init__()
        self.context = context

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(render_context(self.context), id="context-panel")
        yield Footer()

    def action_back(self) -> None:
        self.app.pop_screen()
