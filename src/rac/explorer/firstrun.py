"""First-run marker — a single onboarding flag under the XDG state directory.

Returning users skip onboarding (DESIGN-first-run-experience). Persistence
failures are deliberately swallowed: showing onboarding twice on a read-only
home is a far better outcome than crashing the Explorer. This module never
imports Textual.
"""

from __future__ import annotations

import os
from pathlib import Path

_MARKER_NAME = "explorer-first-run"


def _marker_path() -> Path:
    base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(base) / "rac" / _MARKER_NAME


def is_first_run() -> bool:
    """True until :func:`mark_onboarded` has recorded a completed first run."""
    return not _marker_path().exists()


def mark_onboarded() -> None:
    """Record that onboarding completed; never raises on filesystem trouble."""
    marker = _marker_path()
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("onboarded\n", encoding="utf-8")
    except OSError:
        pass
