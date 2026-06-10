"""External editor integration (v0.8.4, DESIGN-editor-integration).

Explorer is not an editor (ADR-024): it locates an artifact and hands it to
the user's own editor. The command is resolved from the `editor` preference
(v0.8.8, `/settings`), then the standard `$VISUAL` and `$EDITOR` variables;
when nothing is set, Explorer offers guidance rather than guessing.

GUI editors launch fire-and-forget through a module-level runner seam, so
the TUI keeps running and tests inject a spy. Terminal editors (vi, vim, …)
need the terminal itself: callers detect them with :func:`is_terminal_editor`
and run the blocking launch under a suspended application. This module never
imports Textual.
"""

from __future__ import annotations

import os
import shlex
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import PurePath

# Runner seams: tests monkeypatch these; the defaults start the editor
# detached (GUI) or in the foreground (terminal editors, app suspended).
Runner = Callable[[Sequence[str]], None]


def _default_runner(command: Sequence[str]) -> None:  # pragma: no cover - spawns a process
    subprocess.Popen(command)


def _default_blocking_runner(command: Sequence[str]) -> None:  # pragma: no cover - spawns
    subprocess.run(command, check=False)


_RUNNER: Runner = _default_runner
_BLOCKING_RUNNER: Runner = _default_blocking_runner

UNCONFIGURED_GUIDANCE = (
    "No editor configured. Set one in /settings, or export $VISUAL/$EDITOR "
    "(e.g. export EDITOR=code) and try again."
)

# Editors that own the terminal while they run (DESIGN-editor-integration).
_TERMINAL_EDITORS = frozenset(
    {"vi", "vim", "nvim", "emacs", "nano", "helix", "hx", "micro", "kak", "pico"}
)


@dataclass(frozen=True)
class EditorOutcome:
    """The result of an Open In Editor attempt — always a recoverable state."""

    launched: bool
    message: str


def resolve_editor(preference: str = "") -> str | None:
    """The configured editor: the preference, then ``$VISUAL``, then ``$EDITOR``."""
    if preference.strip():
        return preference.strip()
    for var in ("VISUAL", "EDITOR"):
        value = os.environ.get(var, "").strip()
        if value:
            return value
    return None


def is_terminal_editor(editor: str) -> bool:
    """True when ``editor`` needs the terminal (run it with the TUI suspended)."""
    parts = shlex.split(editor)
    if not parts:
        return False
    return PurePath(parts[0]).name in _TERMINAL_EDITORS


def open_in_editor(path: str, preference: str = "", *, blocking: bool = False) -> EditorOutcome:
    """Launch the configured editor on ``path``.

    ``blocking`` selects the foreground runner — callers use it for terminal
    editors after suspending the application. Returns guidance instead of
    raising when no editor is configured or the launch fails, so the
    interface never crashes (Initiative 5).
    """
    editor = resolve_editor(preference)
    if editor is None:
        return EditorOutcome(launched=False, message=UNCONFIGURED_GUIDANCE)
    command = [*shlex.split(editor), path]
    runner = _BLOCKING_RUNNER if blocking else _RUNNER
    try:
        runner(command)
    except OSError as exc:
        return EditorOutcome(launched=False, message=f"Could not launch editor '{editor}': {exc}")
    return EditorOutcome(launched=True, message=f"Opened {path} in {editor}")
