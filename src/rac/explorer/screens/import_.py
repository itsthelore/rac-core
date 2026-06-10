"""Guided import screen — convert, preview, confirm, write (v0.8.4).

Wraps the Core ingest service (DESIGN-import-workflow): conversion runs off the
UI thread with operation feedback, the converted Markdown is previewed with its
target path, and nothing is written until the user confirms (Initiative 4).
Explorer owns the workflow; RAC Core owns the conversion (ADR-015).
"""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, Header, Static
from textual.worker import Worker, WorkerState, get_current_worker

from rac.explorer.adapter import ExplorerAdapter
from rac.explorer.state import ImportPreview

_PREVIEW_LINES = 20


class ImportScreen(Screen[None]):
    """Converting → Preview (y confirms) → Result. Esc cancels at any point."""

    BINDINGS = [
        Binding("y", "confirm", "Confirm import"),
        Binding("escape", "back", "Cancel"),
    ]

    def __init__(self, adapter: ExplorerAdapter, source: str, target: str | None) -> None:
        super().__init__()
        self.adapter = adapter
        self.source = source
        self.target = target
        self.preview: ImportPreview | None = None
        self._done = False

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(f"Converting {self.source}…", id="import-panel")
        yield Footer()

    def on_mount(self) -> None:
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
            panel.update(self._render_preview(result))
        else:  # an error message — recoverable, no write happened
            self._done = True
            panel.update(f"✗ Import failed\n\n{result}\n\nPress Esc to go back.")

    @staticmethod
    def _render_preview(preview: ImportPreview) -> str:
        body = preview.markdown.splitlines()
        shown = body[:_PREVIEW_LINES]
        more = len(body) - len(shown)
        lines = [
            "Import Knowledge",
            "",
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
        lines.extend(["─" * 40, "", "Press y to write this file · Esc to cancel"])
        return "\n".join(lines)

    def action_confirm(self) -> None:
        if self.preview is None or self._done:
            return
        message = self.adapter.write_import(self.preview)
        self._done = True
        self.query_one("#import-panel", Static).update(f"{message}\n\nPress Esc to go back.")

    def action_back(self) -> None:
        self.app.pop_screen()
