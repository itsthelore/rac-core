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
_RECENT_ARTIFACT_LIMIT = 8


@dataclass
class Workspace:
    """Recently opened repositories, plus the last artifact and view in each."""

    recent: list[str] = field(default_factory=list)
    last_artifact: dict[str, str] = field(default_factory=dict)
    last_view: dict[str, str] = field(default_factory=dict)
    # Per repository, the artifacts opened most recently, newest first
    # (v0.8.9) — the palette offers them before a character is typed.
    recent_artifacts: dict[str, list[str]] = field(default_factory=dict)

    def record_open(self, directory: str) -> None:
        """Move ``directory`` to the front of the recent list (deduped)."""
        self.recent = [directory, *(d for d in self.recent if d != directory)][:_RECENT_LIMIT]

    def record_artifact(self, directory: str, path: str) -> None:
        self.last_artifact[directory] = path
        previous = self.recent_artifacts.get(directory, [])
        self.recent_artifacts[directory] = [path, *(p for p in previous if p != path)][
            :_RECENT_ARTIFACT_LIMIT
        ]

    def recent_artifacts_for(self, directory: str) -> list[str]:
        return list(self.recent_artifacts.get(directory, []))

    def resume_artifact(self, directory: str) -> str | None:
        return self.last_artifact.get(directory)

    def record_view(self, directory: str, view: str) -> None:
        """Remember the active view so resume can restore it (v0.8.8)."""
        self.last_view[directory] = view

    def resume_view(self, directory: str) -> str | None:
        return self.last_view.get(directory)


def workspace_path() -> Path:
    base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(base) / "decided" / "explorer-workspace.json"


def load_workspace() -> Workspace:
    """Read the workspace, returning an empty one on any problem."""
    path = workspace_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Workspace()
    if not isinstance(data, dict):
        return Workspace()

    def _str_map(key: str) -> dict[str, str]:
        return {
            str(k): str(v)
            for k, v in (data.get(key, {}) or {}).items()
            if isinstance(k, str) and isinstance(v, str)
        }

    recent = [str(d) for d in data.get("recent", []) if isinstance(d, str)]
    # Additive (v0.8.9): state files written before recent_artifacts load as-is.
    recent_artifacts = {
        str(k): [str(p) for p in v if isinstance(p, str)][:_RECENT_ARTIFACT_LIMIT]
        for k, v in (data.get("recent_artifacts", {}) or {}).items()
        if isinstance(k, str) and isinstance(v, list)
    }
    return Workspace(
        recent=recent[:_RECENT_LIMIT],
        last_artifact=_str_map("last_artifact"),
        last_view=_str_map("last_view"),
        recent_artifacts=recent_artifacts,
    )


def save_workspace(workspace: Workspace) -> None:
    """Persist the workspace; tolerates filesystem trouble silently."""
    path = workspace_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "recent": workspace.recent,
            "last_artifact": workspace.last_artifact,
            "last_view": workspace.last_view,
            "recent_artifacts": workspace.recent_artifacts,
        }
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass
