"""Workspace continuity — recent repositories and the last artifact (v0.8.6).

Persists, under ``$XDG_STATE_HOME/rac/explorer-workspace.json``, the recently
opened repositories and, per repository, the last opened artifact, so returning
users can resume (Initiative 1). This is local state only — no login, cloud, or
sync — and every write tolerates filesystem trouble silently (resuming is a
convenience, never a requirement). This module never imports Textual.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

_RECENT_LIMIT = 10


@dataclass
class Workspace:
    """Recently opened repositories and the last artifact opened in each."""

    recent: list[str] = field(default_factory=list)
    last_artifact: dict[str, str] = field(default_factory=dict)

    def record_open(self, directory: str) -> None:
        """Move ``directory`` to the front of the recent list (deduped)."""
        self.recent = [directory, *(d for d in self.recent if d != directory)][:_RECENT_LIMIT]

    def record_artifact(self, directory: str, path: str) -> None:
        self.last_artifact[directory] = path

    def resume_artifact(self, directory: str) -> str | None:
        return self.last_artifact.get(directory)


def workspace_path() -> Path:
    base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(base) / "rac" / "explorer-workspace.json"


def load_workspace() -> Workspace:
    """Read the workspace, returning an empty one on any problem."""
    path = workspace_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Workspace()
    if not isinstance(data, dict):
        return Workspace()
    recent = [str(d) for d in data.get("recent", []) if isinstance(d, str)]
    last = {
        str(k): str(v)
        for k, v in (data.get("last_artifact", {}) or {}).items()
        if isinstance(k, str) and isinstance(v, str)
    }
    return Workspace(recent=recent[:_RECENT_LIMIT], last_artifact=last)


def save_workspace(workspace: Workspace) -> None:
    """Persist the workspace; tolerates filesystem trouble silently."""
    path = workspace_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"recent": workspace.recent, "last_artifact": workspace.last_artifact}
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass
