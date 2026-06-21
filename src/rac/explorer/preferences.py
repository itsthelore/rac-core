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

# Sidebar groupings, in settings-cycle order; folders — the repository's
# real directory structure — is the default (v0.8.10).
GROUPING_FOLDERS = "folders"
GROUPING_TYPE = "type"
GROUPING_FLAT = "flat"
GROUPINGS = (GROUPING_FOLDERS, GROUPING_TYPE, GROUPING_FLAT)
_GROUPINGS = GROUPINGS

# Workspace layouts, in settings-cycle order (v0.26.3). `frame` is the tree +
# swapping context region; `split` is master-detail — the portfolio list driving
# a persistent reading pane.
LAYOUT_FRAME = "frame"
LAYOUT_SPLIT = "split"
LAYOUTS = (LAYOUT_FRAME, LAYOUT_SPLIT)


@dataclass(frozen=True)
class Preferences:
    """User preferences with safe defaults; unknown values fall back."""

    theme: str = "rac-lantern"
    mascot: bool = True
    animations: bool = True
    # Selecting the mascot returns a small response (v0.8.12); independent of
    # `mascot` and `animations` so any combination can be disabled
    # (DESIGN-mascot-interaction).
    mascot_interaction: bool = True
    artifact_grouping: str = GROUPING_FOLDERS
    # The default Markdown editor command (v0.8.8); empty falls back to
    # $VISUAL / $EDITOR (DESIGN-editor-integration).
    editor: str = ""
    # Workspace layout (v0.26.3): `frame` (default) or `split` master-detail.
    layout: str = LAYOUT_FRAME


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
    layout = data.get("layout", defaults.layout)
    if layout not in LAYOUTS:
        layout = defaults.layout
    return Preferences(
        theme=str(data.get("theme", defaults.theme)),
        mascot=bool(data.get("mascot", defaults.mascot)),
        animations=bool(data.get("animations", defaults.animations)),
        mascot_interaction=bool(data.get("mascot_interaction", defaults.mascot_interaction)),
        artifact_grouping=grouping,
        editor=str(data.get("editor", defaults.editor)),
        layout=layout,
    )


def save_preferences(preferences: Preferences) -> None:
    """Persist preferences; tolerates filesystem trouble silently."""
    path = preferences_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(preferences), indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass
