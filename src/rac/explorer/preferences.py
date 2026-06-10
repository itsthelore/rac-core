"""Explorer preferences — optional, file-based, never blocking (v0.8.6).

Preferences live as JSON under ``$XDG_CONFIG_HOME/rac/explorer.json`` and are
edited in that file (Explorer authors nothing, ADR-024). Loading tolerates a
missing or corrupt file by returning defaults, so preferences never block
onboarding and need no login, cloud, or sync (DESIGN-first-run-experience).
This module never imports Textual.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

GROUPING_TYPE = "type"
GROUPING_FLAT = "flat"
_GROUPINGS = (GROUPING_TYPE, GROUPING_FLAT)


@dataclass(frozen=True)
class Preferences:
    """User preferences with safe defaults; unknown values fall back."""

    theme: str = "rac-lantern"
    mascot: bool = True
    animations: bool = True
    artifact_grouping: str = GROUPING_TYPE
    # The default Markdown editor command (v0.8.8); empty falls back to
    # $VISUAL / $EDITOR (DESIGN-editor-integration).
    editor: str = ""


def preferences_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "rac" / "explorer.json"


def load_preferences() -> Preferences:
    """Read preferences, returning defaults on any problem (never raises)."""
    path = preferences_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Preferences()
    if not isinstance(data, dict):
        return Preferences()
    defaults = Preferences()
    grouping = data.get("artifact_grouping", defaults.artifact_grouping)
    if grouping not in _GROUPINGS:
        grouping = defaults.artifact_grouping
    return Preferences(
        theme=str(data.get("theme", defaults.theme)),
        mascot=bool(data.get("mascot", defaults.mascot)),
        animations=bool(data.get("animations", defaults.animations)),
        artifact_grouping=grouping,
        editor=str(data.get("editor", defaults.editor)),
    )


def save_preferences(preferences: Preferences) -> None:
    """Persist preferences; tolerates filesystem trouble silently."""
    path = preferences_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(preferences), indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass
