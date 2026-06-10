"""The `/` command surface — one entry point for search and commands (v0.8.1).

A modal over the current screen: type, Enter routes (registry command or
search), ↑↓ pick a result, Enter opens it, Esc closes. Routing lives in
:mod:`rac.explorer.commands`; every answer comes from the adapter (ADR-015).
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, OptionList
from textual.widgets.option_list import Option

from rac.explorer import commands
from rac.explorer.adapter import ExplorerAdapter
from rac.explorer.state import LookupState

from .context import ContextScreen


class CommandScreen(ModalScreen[None]):
    """The universal `/` surface (DESIGN-command-surface)."""

    BINDINGS = [Binding("escape", "dismiss_surface", "Close")]

    def __init__(self, adapter: ExplorerAdapter) -> None:
        super().__init__()
        self.adapter = adapter

    def compose(self) -> ComposeResult:
        with Vertical(id="command-surface"):
            yield Input(placeholder="Type a command or search…", id="command-input")
            yield OptionList(id="command-results")

    def on_mount(self) -> None:
        self.query_one(Input).focus()
        self._show_examples()

    # --- result list helpers -------------------------------------------------

    def _set_options(self, options: list[Option | None]) -> None:
        result_list = self.query_one(OptionList)
        result_list.clear_options()
        result_list.add_options(options)

    def _show_examples(self) -> None:
        options: list[Option | None] = [Option("Start typing…  Try:", disabled=True)]
        options.extend(Option(f"  {example}", disabled=True) for example in commands.EXAMPLES)
        self._set_options(options)

    def _show_help(self) -> None:
        self._set_options(
            [
                Option(f"/{spec.usage:<22} {spec.summary}", disabled=True)
                for spec in commands.REGISTRY
            ]
        )

    def _show_lookup(self, lookup: LookupState) -> None:
        options: list[Option | None] = []
        if lookup.message:
            options.append(Option(lookup.message, disabled=True))
        options.extend(
            Option(f"{row.status_label}  {row.title or row.id}  ({row.type})", id=row.path)
            for row in lookup.rows
        )
        self._set_options(options)
        if lookup.rows:
            result_list = self.query_one(OptionList)
            result_list.focus()
            result_list.highlighted = 1 if lookup.message else 0

    # --- routing --------------------------------------------------------------

    def on_input_changed(self, event: Input.Changed) -> None:
        text = event.value
        if not text.strip().lstrip("/").strip():
            self._show_examples()
            return
        matched = commands.suggestions(text)
        if matched:
            self._set_options(
                [Option(f"/{spec.usage:<22} {spec.summary}", disabled=True) for spec in matched]
            )
        else:
            hint = Option(f"Press Enter to search for '{text.strip()}'", disabled=True)
            self._set_options([hint])

    def on_input_submitted(self, event: Input.Submitted) -> None:
        invocation = commands.parse(event.value)
        if not invocation.args and invocation.command == commands.SEARCH:
            self._show_examples()
            return

        if invocation.command == "quit":
            self.app.exit()
        elif invocation.command == "help":
            self._show_help()
        elif invocation.command == "home":
            self._pop_to_home()
        elif invocation.command == "health":
            health = self.adapter.health_state()
            if health is None:
                self._set_options([Option("Repository not loaded yet", disabled=True)])
                return
            from .health import HealthScreen

            self.app.pop_screen()
            self.app.push_screen(HealthScreen(self.adapter, health))
        elif invocation.command == "recommendations":
            recommendations = self.adapter.recommendations_state()
            if recommendations is None:
                self._set_options([Option("Repository not loaded yet", disabled=True)])
                return
            from .recommendations import RecommendationsScreen

            self.app.pop_screen()
            self.app.push_screen(RecommendationsScreen(self.adapter, recommendations))
        elif invocation.command == "import":
            parts = invocation.args.split()
            if not parts:
                self._set_options([Option("Usage: /import <source> [target]", disabled=True)])
                return
            source = parts[0]
            target = parts[1] if len(parts) > 1 else None
            from .import_ import ImportScreen

            self.app.pop_screen()
            self.app.push_screen(ImportScreen(self.adapter, source, target))
        elif invocation.command == "browse":
            artifact_type = invocation.args.casefold() or None
            browser = self.adapter.browser_state(artifact_type)
            if browser is None or not browser.groups:
                self._set_options([Option(f"Nothing to browse: {invocation.args}", disabled=True)])
                return
            from .browser import BrowserScreen

            self.app.pop_screen()
            self.app.push_screen(BrowserScreen(self.adapter, browser))
        elif invocation.command == "open":
            lookup = self.adapter.open_ref(invocation.args)
            if len(lookup.rows) == 1 and lookup.message is None:
                self._open_path(lookup.rows[0].path)
            else:
                self._show_lookup(lookup)
        else:  # search — explicit /find or bare input
            self._show_lookup(self.adapter.search_rows(invocation.args))

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_id is not None:
            self._open_path(event.option_id)

    # --- navigation -----------------------------------------------------------

    def _open_path(self, path: str) -> None:
        context = self.adapter.context_state(path)
        if context is not None:
            self.app.pop_screen()
            self.app.push_screen(ContextScreen(self.adapter, context))

    def _pop_to_home(self) -> None:
        from .repository import RepositoryScreen

        self.app.pop_screen()  # the surface itself
        while not isinstance(self.app.screen, RepositoryScreen) and len(self.app.screen_stack) > 1:
            self.app.pop_screen()

    def action_dismiss_surface(self) -> None:
        self.app.pop_screen()
