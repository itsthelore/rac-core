"""The command palette — summoned by `/`, dismissed by Esc (v0.8.8).

A titled floating panel over the context region: an input line on top and a
live, navigable suggestion menu directly below it (DESIGN-command-surface).
Empty input teaches the registry; a command prefix filters it; any other
text quick-opens matching artifacts. The idle frame carries no input chrome.
Routing of submitted text stays on the main screen — the palette only
decides between completing, running, and opening.
"""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import Input, OptionList
from textual.widgets.option_list import Option

from rac.explorer import commands
from rac.explorer.adapter import ExplorerAdapter
from rac.explorer.state import ArtifactRow
from rac.explorer.widgets.sidebar import type_tag

# Quick-open shows at most this many artifact matches; full result sets
# belong to the results view in the context region.
_MATCH_LIMIT = 8


def _takes_args(spec: commands.CommandSpec) -> bool:
    return "<" in spec.usage or "[" in spec.usage


def _command_option(spec: commands.CommandSpec) -> Option:
    label = Text()
    label.append(f"/{spec.usage:<24}", style="bold")
    label.append(spec.summary, style="dim")
    return Option(label, id=f"cmd:{spec.name}")


def _artifact_option(row: ArtifactRow, *, dark: bool = True) -> Option:
    tag, colour = type_tag(row.type, dark=dark)
    label = Text()
    label.append(tag, style=f"bold {colour}")
    label.append(f" {row.title or row.id}")
    label.append(f"  {row.status_label}", style="dim")
    return Option(label, id=f"path:{row.path}")


class CommandPalette(Vertical):
    """Input on top, menu below; `↑ ↓` drive the menu while typing continues."""

    BINDINGS = [
        Binding("escape", "dismiss_palette", "Close", show=False),
        Binding("up", "menu_up", "Choose", show=False),
        Binding("down", "menu_down", "Choose", show=False),
    ]

    class Dismissed(Message):
        """Esc — the screen should restore the previous focus."""

    class Routed(Message):
        """Submitted text for the screen's command routing."""

        def __init__(self, text: str) -> None:
            super().__init__()
            self.text = text

    class ArtifactChosen(Message):
        """A quick-open match was selected."""

        def __init__(self, path: str) -> None:
            super().__init__()
            self.path = path

    def __init__(self, adapter: ExplorerAdapter) -> None:
        super().__init__(id="command-palette")
        self.adapter = adapter
        self.border_title = "/"
        self.display = False

    def compose(self) -> ComposeResult:
        yield Input(placeholder="Type a command or search…", id="command-input")
        yield OptionList(id="palette-menu")

    # --- lifecycle -------------------------------------------------------------

    def show(self) -> None:
        self.display = True
        field = self.query_one(Input)
        field.value = ""
        self._refresh_menu("")
        field.focus()

    def hide(self, *, restore_focus: bool) -> None:
        self.display = False
        if restore_focus:
            self.post_message(self.Dismissed())

    def action_dismiss_palette(self) -> None:
        self.hide(restore_focus=True)

    # --- the live menu ----------------------------------------------------------

    def _menu(self) -> OptionList:
        return self.query_one(OptionList)

    def _tag_dark(self) -> bool:
        """Whether the active theme is dark, for theme-aware tag hues (v0.26.1)."""
        try:
            return bool(self.app.current_theme.dark)
        except Exception:  # noqa: BLE001 - no app/theme yet: assume the dark default
            return True

    def _refresh_menu(self, text: str) -> None:
        menu = self._menu()
        menu.clear_options()
        stripped = text.strip().lstrip("/").strip()
        # Theme-aware tag hues (v0.26.1); the menu rebuilds on every keystroke,
        # so reading the active theme here keeps the palette tags current.
        dark = self._tag_dark()
        options: list[Option] = []
        if not stripped:
            # The artifacts the user actually works in come first (v0.8.9);
            # Enter reopens one. The registry follows, labelled, in full.
            recents = self.adapter.recent_rows()
            if recents:
                options.append(Option(Text("Recent", style="dim"), disabled=True))
                options.extend(_artifact_option(row, dark=dark) for row in recents)
                options.append(Option(Text("Commands", style="dim"), disabled=True))
            options.extend(_command_option(spec) for spec in commands.REGISTRY)
        else:
            matched = commands.suggestions(stripped)
            if matched:
                options = [_command_option(spec) for spec in matched]
            else:
                lookup = self.adapter.search_rows(stripped)
                options.extend(
                    _artifact_option(row, dark=dark) for row in lookup.rows[:_MATCH_LIMIT]
                )
                options.append(Option(f"Search all results for '{stripped}'", id="route:search"))
        menu.add_options(options)
        for index in range(menu.option_count):
            if not menu.get_option_at_index(index).disabled:
                menu.highlighted = index
                break

    def on_input_changed(self, event: Input.Changed) -> None:
        event.stop()
        self._refresh_menu(event.value)

    def action_menu_up(self) -> None:
        self._menu().action_cursor_up()

    def action_menu_down(self) -> None:
        self._menu().action_cursor_down()

    # --- selection ---------------------------------------------------------------

    def _highlighted_id(self) -> str | None:
        menu = self._menu()
        if menu.highlighted is None or not menu.option_count:
            return None
        option = menu.get_option_at_index(menu.highlighted)
        return None if option.disabled else option.id

    def _choose(self, option_id: str, raw_text: str) -> None:
        """Complete, run, or open the selected menu row."""
        kind, _, value = option_id.partition(":")
        if kind == "path":
            self.hide(restore_focus=False)
            self.post_message(self.ArtifactChosen(value))
            return
        if kind == "route":
            # "Search all results" — hand the raw text to the screen's routing.
            self.hide(restore_focus=False)
            self.post_message(self.Routed(raw_text))
            return
        spec = next(s for s in commands.REGISTRY if s.name == value)
        head = raw_text.strip().lstrip("/").strip().partition(" ")[0].casefold()
        if head == spec.name:
            # The command is fully typed — run it with whatever follows.
            self.hide(restore_focus=False)
            self.post_message(self.Routed(raw_text))
        elif _takes_args(spec):
            # Complete into the input, Claude Code style, and keep typing.
            field = self.query_one(Input)
            field.value = f"{spec.name} "
            field.cursor_position = len(field.value)
            field.focus()
        else:
            self.hide(restore_focus=False)
            self.post_message(self.Routed(spec.name))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        option_id = self._highlighted_id()
        if option_id is not None:
            self._choose(option_id, event.value)
        else:
            self.hide(restore_focus=False)
            self.post_message(self.Routed(event.value))

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        if event.option_id is not None:
            self._choose(event.option_id, self.query_one(Input).value)
