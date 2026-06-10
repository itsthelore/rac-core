"""External editor integration (v0.8.4, DESIGN-editor-integration).

Explorer is not an editor (ADR-024): it locates an artifact and hands it to the
user's own editor. The editor command is resolved from the standard `$VISUAL`
then `$EDITOR` environment variables; when neither is set, Explorer offers
guidance rather than guessing. Launch is fire-and-forget through a module-level
runner seam, so tests inject a spy and no real editor starts.

A persisted editor preference and first-run editor selection arrive with v0.8.6
preferences; terminal editors that need the TUI suspended are a later
enhancement. This module never imports Textual.
"""

from __future__ import annotations

import os
import shlex
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass

# Runner seam: launch a command, return nothing. Tests monkeypatch this; the
# default starts the editor detached so the TUI keeps running (GUI editors).
Runner = Callable[[Sequence[str]], None]


def _default_runner(command: Sequence[str]) -> None:  # pragma: no cover - spawns a process
    subprocess.Popen(command)


_RUNNER: Runner = _default_runner

UNCONFIGURED_GUIDANCE = (
    "No editor configured. Set $VISUAL or $EDITOR (e.g. export EDITOR=code) and try again."
)


@dataclass(frozen=True)
class EditorOutcome:
    """The result of an Open In Editor attempt — always a recoverable state."""

    launched: bool
    message: str


def resolve_editor() -> str | None:
    """The configured editor command, from ``$VISUAL`` then ``$EDITOR``."""
    for var in ("VISUAL", "EDITOR"):
        value = os.environ.get(var, "").strip()
        if value:
            return value
    return None


def open_in_editor(path: str) -> EditorOutcome:
    """Launch the configured editor on ``path`` (fire-and-forget).

    Returns guidance instead of raising when no editor is configured or the
    launch fails, so the interface never crashes (Initiative 5).
    """
    editor = resolve_editor()
    if editor is None:
        return EditorOutcome(launched=False, message=UNCONFIGURED_GUIDANCE)
    command = [*shlex.split(editor), path]
    try:
        _RUNNER(command)
    except OSError as exc:
        return EditorOutcome(launched=False, message=f"Could not launch editor '{editor}': {exc}")
    return EditorOutcome(launched=True, message=f"Opened {path} in {editor}")
