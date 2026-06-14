"""Git hook installation — `rac hook install` (v0.13.4).

``install_hook`` is the reusable installation capability: it owns resource
loading, the git-directory check, the never-overwrite check, and the result
model, so the CLI stays a thin adapter. It writes the bundled script for one
style into ``<dir>/.git/hooks/<style>`` and makes it executable, mirroring
``rac skill install`` (ADR-021 resource loading; never-overwrite posture).

Failure contract:

- unknown style          → :class:`~rac.core.hooks.HookNotFound` (usage error)
- no .git directory      → :class:`NotAGitWorkTree` (usage error, exit 2)
- hook file exists       → :class:`HookFileExists` (refused; exit 1; untouched)
- missing packaged hook  → :class:`~rac.core.hooks.HookResourceMissing`
  (operational; broken installation)
"""

from __future__ import annotations

import stat
from dataclasses import dataclass
from pathlib import Path

from rac.core.hooks import DEFAULT_STYLE, HookNotFound, available_hooks, load_hook


class NotAGitWorkTree(Exception):
    """The target directory has no ``.git`` directory (usage error)."""

    def __init__(self, directory: str):
        self.directory = directory
        super().__init__(
            f"no .git directory in {directory}; run `rac hook install` from a git repository root"
        )


class HookFileExists(Exception):
    """A target hook file already exists; RAC never overwrites it."""

    def __init__(self, path: str):
        self.path = path
        super().__init__(f"{path} already exists; rac hook install never overwrites")


@dataclass
class InstalledHook:
    """Result of a `rac hook install` run (stable JSON contract, ADR-007)."""

    style: str
    path: str
    bytes_written: int

    def to_dict(self) -> dict:
        return {
            "schema_version": "1",
            "installed": True,
            "hook": {"style": self.style, "path": self.path},
        }


def install_hook(target_dir: str, style: str = DEFAULT_STYLE) -> InstalledHook:
    """Write the bundled ``style`` hook into ``target_dir``'s ``.git/hooks``.

    Raises :class:`~rac.core.hooks.HookNotFound` for an unknown style,
    :class:`NotAGitWorkTree` when there is no ``.git`` directory,
    :class:`HookFileExists` when the target hook already exists (left
    untouched), and :class:`~rac.core.hooks.HookResourceMissing` when the
    packaged resource is absent.
    """
    if style not in available_hooks():
        raise HookNotFound(style)

    git_dir = Path(target_dir) / ".git"
    if not git_dir.is_dir():
        raise NotAGitWorkTree(target_dir)

    content = load_hook(style)  # validates the installation (cheap)
    hooks_dir = git_dir / "hooks"
    dest = hooks_dir / style
    if dest.exists():
        raise HookFileExists(str(dest))

    hooks_dir.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(content)
    # Make the hook executable (rwxr-xr-x), as git requires.
    dest.chmod(dest.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return InstalledHook(style=style, path=str(dest), bytes_written=len(content))
