"""Filesystem helpers shared across RAC commands.

Kept separate so that consumers (``stats``, ``inspect``) depend on a small,
neutral module rather than on each other — avoiding import cycles as more
commands need to walk a tree of Markdown files.
"""

from __future__ import annotations

from pathlib import Path


def find_markdown_files(directory: str, recursive: bool = True) -> list[Path]:
    """Find `*.md` files, skipping dotted dirs (.git, .venv, ...).

    Recursive by default (used by `stats` and `inspect`); pass ``recursive=False``
    to look only at files directly inside ``directory``.
    """
    root = Path(directory)
    glob = root.rglob if recursive else root.glob
    found = [
        p
        for p in glob("*.md")
        if not any(part.startswith(".") for part in p.relative_to(root).parts)
    ]
    return sorted(found)
