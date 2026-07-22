"""Filesystem-scope path helpers (decision-to-code-proximity, Initiative 1).

``## Applies To`` entries are code paths/components a decision governs. They ride
the relationship machinery (extracted, graphed, surfaced via get_related) but are
resolved against the *file tree*, not the identifier index: a literal path or
directory entry is existence-checked relative to the repository root. Declared,
never inferred (ADR-065/066); a pure function of the declared entry and the tree
(ADR-066). Glob patterns (matched at lookup, #275) and component-name labels
(no registry this cycle) are recorded without existence-checking.

This module owns the pure entry-classification, path-normalisation, and
repository-root discovery that both relationship validation
(:func:`asdecided.services.relationships._scope_validation_issues`) and the
path-to-decisions lookup (:mod:`asdecided.services.scope`) share — a single home so
neither reaches across a module boundary for the other's internals.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath

# Glob metacharacters that mark an entry as a declared *pattern* rather than a
# literal path — stdlib ``fnmatch``/``glob`` semantics, pinned for the lookup.
_GLOB_METACHARS: tuple[str, ...] = ("*", "?", "[")

# Config anchor for repository-root discovery (ADR-018), mirroring
# ``asdecided.services.init.find_config_file`` without importing the services layer so
# this module stays core-only in its dependencies.
_CONFIG_DIR = ".decided"
_CONFIG_FILE = "config.yaml"


def classify_scope_entry(entry: str) -> str:
    """Classify one ``## Applies To`` entry as ``glob``, ``path``, or ``component``.

    Deterministic (slash-or-glob rule): an entry containing a glob metacharacter
    (``*``/``?``/``[``) is a declared ``glob`` pattern; otherwise an entry
    containing a path separator ``/`` is a literal ``path`` (a file or directory);
    otherwise it is a ``component`` label. Only ``path`` entries are existence-
    checked — an author writes ``src/`` (not bare ``src``) to mean the directory.
    """
    if any(ch in entry for ch in _GLOB_METACHARS):
        return "glob"
    if "/" in entry:
        return "path"
    return "component"


def normalized_scope_path(entry: str) -> str | None:
    """A literal path entry as a POSIX repo-relative string, or None if invalid.

    Strips a leading ``./`` and trailing ``/`` and collapses ``.`` segments.
    Returns None when the entry is absolute or escapes the repository root (a
    ``..`` segment) — such an entry cannot name an in-repository scope, so it is
    treated as not-found rather than followed outside the tree (ADR-065).
    """
    text = entry.strip()
    if not text or text.startswith("/"):
        return None
    parts: list[str] = []
    for part in PurePosixPath(text).parts:
        if part == ".":
            continue
        if part == "..":
            return None
        parts.append(part)
    return "/".join(parts) if parts else None


def repository_root(directory: str) -> Path:
    """The repository root anchoring ``## Applies To`` paths (ADR-018).

    The nearest directory at or above ``directory`` that holds ``.decided/config.yaml``
    (the same discovery ``asdecided.services.init`` uses for identity and overrides).
    Falls back to the resolved ``directory`` when no config is found, so the check
    is deterministic even in an un-initialized tree.
    """
    resolved = Path(directory).resolve()
    for candidate in (resolved, *resolved.parents):
        if (candidate / _CONFIG_DIR / _CONFIG_FILE).is_file():
            return candidate
    return resolved
