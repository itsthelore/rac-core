"""The persistent command bar — the universal `/` surface (v0.8.7).

Always visible at the bottom of the frame, never modal
(DESIGN-command-surface). The bar is an Input that binds Esc itself
(Textual's Input does not consume it) and announces dismissal; routing of
submitted text lives on the main screen.
"""

from __future__ import annotations

from textual.binding import Binding
from textual.message import Message
from textual.widgets import Input


class CommandBar(Input):
    """Type a command or search; Enter routes, Esc returns focus."""

    BINDINGS = [Binding("escape", "dismiss_bar", "Back", show=False)]

    class Dismissed(Message):
        """The user pressed Esc — focus should return to the previous region."""

    def __init__(self) -> None:
        super().__init__(placeholder="Type a command or search…", id="command-input")
        self.border_title = "/"

    def action_dismiss_bar(self) -> None:
        self.post_message(self.Dismissed())
