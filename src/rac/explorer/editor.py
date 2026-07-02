"""External editor integration (DESIGN-editor-integration).

Explorer is not an editor (ADR-024): it finds an artifact and hands the file
to whatever editor the user already trusts. The command is resolved from the
``editor`` preference (set in ``/settings``), then the conventional
``$VISUAL`` / ``$EDITOR`` variables; when nothing is configured, Explorer
offers guidance instead of guessing.

GUI editors are launched fire-and-forget through a module-level runner seam so
the TUI keeps running (and tests can inject a spy). Terminal editors need the
terminal itself, so callers detect them with :func:`is_terminal_editor` and
run the blocking launch under a suspended application. Nothing here imports
Textual.
"""

from __future__ import annotations

import os
import shlex
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import PurePath

Runner = Callable[[Sequence[str]], None]


def _default_runner(command: Sequence[str]) -> None:  # pragma: no cover — spawns a process
    subprocess.Popen(command)


def _default_blocking_runner(command: Sequence[str]) -> None:  # pragma: no cover — spawns
    subprocess.run(command, check=False)


# Runner seams. Tests monkeypatch these module globals; :func:`open_in_editor`
# reads them at call time (never captures them at def time) so a patch applied
# after import still takes effect.
_RUNNER: Runner = _default_runner
_BLOCKING_RUNNER: Runner = _default_blocking_runner

UNCONFIGURED_GUIDANCE = (
    "No editor configured. Set one in /settings, or export $VISUAL/$EDITOR "
    "(e.g. export EDITOR=code) and try again."
)

# Editors that take over the terminal while running: they must be launched with
# the application suspended, not detached.
_TERMINAL_EDITORS = frozenset(
    {"vi", "vim", "nvim", "emacs", "nano", "helix", "hx", "micro", "kak", "pico"}
)


@dataclass(frozen=True)
class EditorOutcome:
    """The result of an Open-In-Editor attempt — always a recoverable state."""

    launched: bool
    message: str


def resolve_editor(preference: str = "") -> str | None:
    """Resolve the editor command: the preference, then ``$VISUAL``, then ``$EDITOR``.

    A blank (or whitespace-only) preference falls through to the environment.
    Returns ``None`` when nothing is configured.
    """
    if preference.strip():
        return preference.strip()
    for var in ("VISUAL", "EDITOR"):
        value = os.environ.get(var, "").strip()
        if value:
            return value
    return None


def is_terminal_editor(editor: str) -> bool:
    """True when ``editor`` needs the terminal (run it with the TUI suspended).

    The check is on the program name only, so absolute paths and trailing
    arguments (``/usr/bin/nvim -u NONE``) still resolve. Empty input is False.
    """
    parts = shlex.split(editor)
    if not parts:
        return False
    return PurePath(parts[0]).name in _TERMINAL_EDITORS


def open_in_editor(path: str, preference: str = "", *, blocking: bool = False) -> EditorOutcome:
    """Launch the configured editor on ``path``.

    ``blocking`` selects the foreground runner, which callers use for terminal
    editors after suspending the application. Returns guidance instead of
    raising when no editor is configured or the launch fails, so the interface
    never crashes on an editor problem (Initiative 5).
    """
    editor = resolve_editor(preference)
    if editor is None:
        return EditorOutcome(launched=False, message=UNCONFIGURED_GUIDANCE)
    command = [*shlex.split(editor), path]
    # Read the seam globals at call time so monkeypatched runners are honoured.
    runner = _BLOCKING_RUNNER if blocking else _RUNNER
    try:
        runner(command)
    except OSError as exc:
        return EditorOutcome(launched=False, message=f"Could not launch editor '{editor}': {exc}")
    return EditorOutcome(launched=True, message=f"Opened {path} in {editor}")
