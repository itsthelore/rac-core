"""First-run marker — the only state Explorer persists in v0.8.1.

Returning users skip onboarding (DESIGN-first-run-experience); everything
else — last repository, views, preferences — is deliberately not stored
until v0.8.6 workspace persistence. The marker lives under the XDG state
directory and persistence failures are silently tolerated: onboarding
showing twice is better than a crash on a read-only home.
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
