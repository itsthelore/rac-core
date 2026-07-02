"""Explorer entry point — where ``rac explorer`` lands.

Textual is an optional dependency (the ``explorer`` extra), so the Textual
application is only imported when the command actually runs. That keeps the
base install working and turns a missing extra into a friendly
:class:`ExplorerUnavailable` with an install hint rather than a raw
``ImportError`` traceback. Nothing in this module imports Textual directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rac.errors import RACError

if TYPE_CHECKING:  # pragma: no cover — import is for type checkers only
    from rac.explorer.app import ExplorerApp

MISSING_EXTRA_HINT = "explorer needs the explorer extra: pip install 'rac-core[explorer]'"


class ExplorerUnavailable(RACError):
    """Raised when the Explorer cannot start because the extra is missing.

    Subclasses :class:`rac.errors.RACError` so callers that already handle RAC
    errors surface it uniformly (pinned by ``tests/test_sdk_surface.py``).
    """


def _import_app() -> type[ExplorerApp]:
    # A module-level seam so tests can force the missing-extra path without
    # actually uninstalling Textual: they monkeypatch this function.
    from rac.explorer.app import ExplorerApp

    return ExplorerApp


def run_explorer(directory: str, recursive: bool = True) -> int:
    """Launch the Explorer over ``directory`` and return its exit code (0)."""
    try:
        app_cls = _import_app()
    except ModuleNotFoundError as exc:
        # Only a *missing Textual* becomes the friendly extra hint. Any other
        # missing module is a genuine import bug and must propagate unchanged.
        if (exc.name or "").partition(".")[0] != "textual":
            raise
        raise ExplorerUnavailable(MISSING_EXTRA_HINT) from exc
    app_cls(directory, recursive=recursive).run()
    return 0
