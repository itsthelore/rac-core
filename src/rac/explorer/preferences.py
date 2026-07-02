"""Explorer preferences — optional, file-based, never blocking.

Preferences live as JSON under ``$XDG_CONFIG_HOME/rac/explorer.json`` and are
edited there by hand (Explorer authors nothing, ADR-024). Loading tolerates a
missing or corrupt file by returning defaults, so preferences never gate
onboarding and need no login, cloud, or sync. This module never imports
Textual.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

# Sidebar groupings, in settings-cycle order. ``folders`` — the repository's
# real directory structure — is the default.
GROUPING_FOLDERS = "folders"
GROUPING_TYPE = "type"
GROUPING_FLAT = "flat"
GROUPINGS = (GROUPING_FOLDERS, GROUPING_TYPE, GROUPING_FLAT)
_GROUPINGS = GROUPINGS

# Workspace layouts, in settings-cycle order. ``frame`` is the tree plus a
# swapping context region; ``split`` is master-detail — the portfolio list
# driving a persistent reading pane.
LAYOUT_FRAME = "frame"
LAYOUT_SPLIT = "split"
LAYOUTS = (LAYOUT_FRAME, LAYOUT_SPLIT)


@dataclass(frozen=True)
class Preferences:
    """User preferences with safe defaults; unknown values fall back.

    Field order and defaults are contract: the ``/settings`` view renders one
    row per field in declaration order.
    """

    theme: str = "rac-lantern"
    mascot: bool = True
    animations: bool = True
    # Selecting the mascot returns a small response; kept independent of
    # ``mascot`` and ``animations`` so any combination can be disabled.
    mascot_interaction: bool = True
    artifact_grouping: str = GROUPING_FOLDERS
    # Preferred Markdown editor command; empty falls back to $VISUAL / $EDITOR.
    editor: str = ""
    # Workspace layout: ``frame`` (default) or ``split`` master-detail.
    layout: str = LAYOUT_FRAME


def preferences_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "rac" / "explorer.json"


def _one_of(value: object, allowed: tuple[str, ...], default: str) -> str:
    """``value`` if it is one of ``allowed`` (an enum-like field), else ``default``."""
    if isinstance(value, str) and value in allowed:
        return value
    return default


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
    return Preferences(
        theme=str(data.get("theme", defaults.theme)),
        mascot=bool(data.get("mascot", defaults.mascot)),
        animations=bool(data.get("animations", defaults.animations)),
        mascot_interaction=bool(data.get("mascot_interaction", defaults.mascot_interaction)),
        artifact_grouping=_one_of(
            data.get("artifact_grouping", defaults.artifact_grouping),
            _GROUPINGS,
            defaults.artifact_grouping,
        ),
        editor=str(data.get("editor", defaults.editor)),
        layout=_one_of(data.get("layout", defaults.layout), LAYOUTS, defaults.layout),
    )


def save_preferences(preferences: Preferences) -> None:
    """Persist preferences; tolerates filesystem trouble silently."""
    path = preferences_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(preferences), indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass
