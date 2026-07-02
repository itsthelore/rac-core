"""Git-hook installation — `rac hook install` (v0.13.4).

:func:`install_hook` is the reusable capability behind the CLI adapter: it owns
resource loading, the git-directory check, the never-overwrite refusal, and the
result model. It writes one bundled script into ``<dir>/.git/hooks/<style>``
and marks it executable — note the installed name has no ``.sh`` suffix even
though the packaged resource does. Mirrors ``rac skill install`` (ADR-021
resource loading; never-overwrite posture).

Failure contract:

- unknown style          → :class:`~rac.core.hooks.HookNotFound` (usage error)
- no .git directory      → :class:`NotAGitWorkTree` (usage error, exit 2)
- hook file exists       → :class:`HookFileExists` (refused; exit 1; untouched)
- missing packaged hook  → :class:`~rac.core.hooks.HookResourceMissing`
  (operational; a broken installation)
"""

from __future__ import annotations

import stat
from dataclasses import dataclass
from pathlib import Path

from rac.core.hooks import DEFAULT_STYLE, HookNotFound, available_hooks, load_hook
from rac.errors import RACError

# The executable bits git requires on a hook script: rwxr-xr-x, applied on top
# of whatever mode the freshly written file already carries.
_EXECUTABLE_BITS = stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH


class NotAGitWorkTree(RACError):
    """The target directory has no ``.git`` directory (usage error)."""

    def __init__(self, directory: str):
        self.directory = directory
        super().__init__(
            f"no .git directory in {directory}; run `rac hook install` from a git repository root"
        )


class HookFileExists(RACError):
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
        # bytes_written is tracked for callers but deliberately absent from the
        # JSON shape (pinned by test_installation_json_contract).
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

    content = load_hook(style)  # cheap, and validates the packaged resource
    dest = git_dir / "hooks" / style
    if dest.exists():
        raise HookFileExists(str(dest))

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(content)
    dest.chmod(dest.stat().st_mode | _EXECUTABLE_BITS)
    return InstalledHook(style=style, path=str(dest), bytes_written=len(content))
