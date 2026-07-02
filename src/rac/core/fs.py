"""Markdown-file discovery shared across RAC commands.

Several commands (``stats``, ``inspect``, and the corpus walk) need to enumerate
the Markdown files beneath a directory. Keeping that one operation in a small,
dependency-free module lets them share it without importing one another, which
would otherwise risk an import cycle as more commands walk the tree.
"""

from __future__ import annotations

from pathlib import Path


def find_markdown_files(directory: str, recursive: bool = True) -> list[Path]:
    """Return the ``*.md`` files under ``directory`` in sorted path order.

    A file is skipped when any path component *relative to* ``directory`` begins
    with a dot, which excludes ``.git``, ``.venv``, other dotted directories, and
    dotfiles while still descending a root that is itself dotted. Recursion is on
    by default; ``recursive=False`` looks only at the top level.

    The sort is ``Path``'s lexicographic ordering, and it is a determinism
    contract: ``walk_corpus`` yields entries in exactly this order, and downstream
    output depends on the match.
    """
    root = Path(directory)
    # rglob descends the whole tree; glob stays at the top level.
    walk = root.rglob if recursive else root.glob
    return sorted(
        path
        for path in walk("*.md")
        if not any(part.startswith(".") for part in path.relative_to(root).parts)
    )
