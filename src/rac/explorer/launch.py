"""Explorer entry point — `rac explorer` lands here (v0.8.0).

Textual ships in the optional ``explorer`` extra, so the Textual application
is imported lazily: the base install keeps working, and a missing extra
becomes :class:`ExplorerUnavailable` with an install hint instead of an
ImportError traceback. This module itself never imports Textual.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rac.errors import RACError

if TYPE_CHECKING:  # pragma: no cover — typing only, never at runtime
    from rac.explorer.app import ExplorerApp

MISSING_EXTRA_HINT = (
    "explorer needs the explorer extra: pip install 'requirements-as-code[explorer]'"
)


class ExplorerUnavailable(RACError):
    """The Explorer cannot start because the ``explorer`` extra is missing."""


def _import_app() -> type[ExplorerApp]:
    # Module-level seam: tests monkeypatch this to exercise the missing-extra
    # path without uninstalling Textual.
    from rac.explorer.app import ExplorerApp

    return ExplorerApp


def run_explorer(directory: str, recursive: bool = True) -> int:
    """Launch the Explorer over ``directory``; returns the exit code (0)."""
    try:
        app_cls = _import_app()
    except ModuleNotFoundError as exc:
        if (exc.name or "").partition(".")[0] != "textual":
            raise  # a genuine import bug, not a missing extra
        raise ExplorerUnavailable(MISSING_EXTRA_HINT) from exc
    app_cls(directory, recursive=recursive).run()
    return 0
