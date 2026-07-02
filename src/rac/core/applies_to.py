"""Applies-to scope grammar and matcher (ADR-098).

A decision's ``## Applies To`` section declares the code it governs, one entry
per line. An entry is either a repo-root-relative POSIX **path glob** or a free
**component label**; the discrimination rule below is deterministic and total,
so interpretation never depends on the tree, the platform, or configuration
(ADR-002, ADR-066). Extraction stays verbatim (ADR-016) — this module owns the
*interpretation*: normalisation, classification, the format lint, and the
``governs`` matcher the path→decisions lookup uses.

Matching uses :func:`fnmatch.fnmatchcase` — never ``fnmatch.fnmatch``, whose
``normcase`` makes results platform-dependent — over ``/``-separated strings,
case-sensitive everywhere, matching git's view of paths. In this dialect ``*``
crosses ``/`` and ``**`` behaves as ``*``; the dialect is pinned by tests so a
standard-library change fails loudly rather than silently reordering matches.
"""

from __future__ import annotations

from fnmatch import fnmatchcase

# Glob metacharacters that mark a whitespace-free entry as a path scope.
_GLOB_CHARS = ("*", "?", "[")


def normalize_entry(entry: str) -> str:
    """Normalise a raw ``## Applies To`` line for classification and matching.

    Strips one surrounding backtick pair, a leading ``./`` (the explicit
    path-hood marker for repo-root files), and a trailing ``/`` (directory
    convention, not an error). The result is what the lint and matcher see.
    """
    text = entry.strip()
    if len(text) >= 2 and text.startswith("`") and text.endswith("`"):
        text = text[1:-1].strip()
    if text.startswith("./"):
        text = text[2:]
    return text.rstrip("/")


def is_path_scope(entry: str) -> bool:
    """Whether a normalised entry is a path glob rather than a component label.

    Whitespace always means a label ("RAC Core"); otherwise a separator or a
    glob metacharacter means a path; anything else is a label (``rac-core``).
    """
    if not entry or any(ch.isspace() for ch in entry):
        return False
    return "/" in entry or any(ch in entry for ch in _GLOB_CHARS)


def malformed_reason(entry: str) -> str | None:
    """Why a path-classified entry is malformed, or None when well-formed.

    Purely syntactic (no filesystem, no configuration): absolute paths,
    backslashes, ``.``/``..`` segments, empty segments, and unbalanced ``[``
    are rejected so every recorded scope is a portable repo-relative glob.
    """
    if not entry:
        return "empty after normalisation"
    if entry.startswith("/"):
        return "absolute path (scopes are repo-root-relative)"
    if "\\" in entry:
        return "backslash (use POSIX separators)"
    segments = entry.split("/")
    if any(not segment for segment in segments):
        return "empty path segment"
    if any(segment in (".", "..") for segment in segments):
        return "'.' or '..' segment"
    if entry.count("[") != entry.count("]"):
        return "unbalanced '['"
    return None


def governs(path: str, scope: str) -> bool:
    """Whether a declared path ``scope`` governs the queried ``path``.

    Both sides are repo-root-relative POSIX strings; ``scope`` is already
    normalised. A scope governs a path when the glob matches it exactly, or
    when the path lies anywhere under the scope (the ``scope + "/*"`` clause —
    fnmatch's ``*`` crosses ``/``, so one clause covers the whole subtree).
    """
    query = path.replace("\\", "/").strip()
    if query.startswith("./"):
        query = query[2:]
    query = query.rstrip("/")
    if not query or not scope:
        return False
    return fnmatchcase(query, scope) or fnmatchcase(query, scope + "/*")
