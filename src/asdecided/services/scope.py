"""Path-to-decisions lookup — the decisions governing a code path.

Initiative 2 of the ``decision-to-code-proximity`` roadmap (``rac-path-decisions-lookup``).
Given a file or directory path, return every *live* decision whose declared
``## Applies To`` scope (Initiative 1) covers it. This is the read side of the
code-scope vocabulary: Initiative 1 authors and validates the scope; this module
queries it.

The answer is a pure function of the declared references and the query path
(ADR-066): no code parsing, no similarity, no persisted index (ADR-002/080). It
reports which decisions bind and their status — never a compliance judgement
(ADR-034). One shared core (ADR-031) serves both the ``decided decisions-for`` CLI
and the additive ``path`` argument on the ``find_decisions`` MCP tool, so the two
faces can never diverge.

Only *live* decisions govern: a superseded or deprecated decision no longer binds
(the same liveness predicate ``find_decisions`` uses, one source of truth). Glob
matching is path-segment-aware (``*`` within a segment, ``**`` across segments)
and platform-independent — declared entries and the query normalise to POSIX
repo-relative form (ADR-002), so the same corpus yields identical results on any
OS.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from asdecided.core.artifacts import spec_for
from asdecided.core.corpus import CorpusEntry, walk_corpus
from asdecided.core.identity import artifact_identifier
from asdecided.services.agent_rules import artifact_status, is_live_decision
from asdecided.services.references import SCOPE_SECTIONS, extract_relationships_full
from asdecided.services.scope_paths import (
    classify_scope_entry,
    normalized_scope_path,
    repository_root,
)

_DECISION_TYPE = "decision"


@dataclass(frozen=True)
class GoverningDecision:
    """One live decision whose ``## Applies To`` scope covers the query path."""

    id: str
    title: str
    status: str
    path: str
    matching_entry: str  # the declared ## Applies To entry that covered the query

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "status": self.status,
            "path": self.path,
            "matching_entry": self.matching_entry,
        }


@dataclass(frozen=True)
class ScopeLookupResult:
    """The decisions governing a queried path (REQ-001/005).

    ``query`` is the POSIX repo-relative form of the queried path when it lies
    inside the repository, else the raw input. ``in_repository`` is False for an
    absolute or escaping path outside the repository root — a valid empty answer,
    never an error (REQ-004). ``decisions`` is deterministically ordered.
    """

    query: str
    in_repository: bool
    decisions: list[GoverningDecision]

    def to_dict(self) -> dict:
        return {
            "schema_version": "1",
            "query": self.query,
            "in_repository": self.in_repository,
            "decisions": [d.to_dict() for d in self.decisions],
        }


def _glob_to_regex(pattern: str) -> re.Pattern[str]:
    """Compile a POSIX path glob into an anchored, segment-aware regex.

    ``*`` and ``?`` match within a single path segment (never ``/``); ``**``
    matches across segments. ``**/`` matches zero or more whole segments, so
    ``src/**/*.py`` matches both ``src/a.py`` and ``src/a/b.py``. Character
    classes (``[...]``) are preserved. Deterministic and platform-independent —
    the whole path must match (``\\Z``).
    """
    i, n = 0, len(pattern)
    out: list[str] = []
    while i < n:
        c = pattern[i]
        if c == "*":
            if pattern[i : i + 2] == "**":
                i += 2
                if pattern[i : i + 1] == "/":
                    i += 1
                    out.append("(?:[^/]+/)*")  # zero or more whole segments
                else:
                    out.append(".*")  # trailing ** — cross any remaining segments
                continue
            out.append("[^/]*")
        elif c == "?":
            out.append("[^/]")
        elif c == "[":
            j = i + 1
            if j < n and pattern[j] in "!^":
                j += 1
            if j < n and pattern[j] == "]":
                j += 1
            while j < n and pattern[j] != "]":
                j += 1
            if j >= n:
                out.append(re.escape(c))  # unterminated class → literal '['
            else:
                inner = pattern[i + 1 : j]
                if inner and inner[0] in "!^":
                    inner = "^" + inner[1:]
                out.append("[" + inner + "]")
                i = j + 1
                continue
        else:
            out.append(re.escape(c))
        i += 1
    return re.compile("".join(out) + r"\Z")


def _entry_covers(entry: str, query: str) -> bool:
    """True when a declared ``## Applies To`` entry covers the query path.

    A literal directory or file entry covers the query when the query equals it
    or is nested beneath it; a glob entry covers the query when the pattern
    matches it segment-aware. Component-name entries never match a path (no
    registry this cycle). ``entry`` and ``query`` are POSIX repo-relative.
    """
    kind = classify_scope_entry(entry)
    if kind == "component":
        return False
    if kind == "glob":
        return _glob_to_regex(entry.strip()).match(query) is not None
    normalized = normalized_scope_path(entry)
    if normalized is None:
        return False  # absolute/escaping declared entry cannot name an in-repo scope
    return query == normalized or query.startswith(normalized + "/")


def _normalize_query(path: str, root: Path) -> str | None:
    """The query path as a POSIX repo-relative string, or None if outside the repo.

    An absolute path is made relative to ``root``; a relative path is treated as
    already repo-relative. Either way, ``.`` segments collapse and a path that
    escapes the root (a leading ``..``, or an absolute path outside it) returns
    None — an outside-repository query is a valid empty answer, not an error
    (REQ-004). Matching is pure string work: the query need not exist on disk.
    """
    text = path.strip()
    if not text:
        return None
    candidate = PurePosixPath(text)
    if candidate.is_absolute():
        try:
            candidate = candidate.relative_to(PurePosixPath(root.as_posix()))
        except ValueError:
            return None
    parts: list[str] = []
    for part in candidate.parts:
        if part in (".", "/"):
            continue
        if part == "..":
            return None
        parts.append(part)
    return "/".join(parts) if parts else None


def _governing(entry: CorpusEntry, query: str) -> GoverningDecision | None:
    """The :class:`GoverningDecision` for ``entry`` if its scope covers ``query``.

    Returns None when the entry is not a live decision, declares no ``## Applies
    To`` scope, or none of its entries cover the query. The reported
    ``matching_entry`` is the first covering entry in declared order (deterministic).
    """
    if entry.artifact_type != _DECISION_TYPE or not is_live_decision(entry.product):
        return None
    spec = spec_for(entry.artifact_type)
    if spec is None:  # the decision spec is always registered; narrow for the type checker
        return None
    relationships = extract_relationships_full(entry.product, spec)
    for section in SCOPE_SECTIONS:
        for declared in relationships.get(section.replace(" ", "_"), []):
            if _entry_covers(declared, query):
                return GoverningDecision(
                    id=artifact_identifier(entry.product, spec, str(entry.path)),
                    title=entry.product.title or "",
                    status=artifact_status(entry.product),
                    path=str(entry.path),
                    matching_entry=declared,
                )
    return None


def decisions_for_path(directory: str, path: str, recursive: bool = True) -> ScopeLookupResult:
    """Live decisions whose ``## Applies To`` scope governs ``path`` (REQ-001).

    ``directory`` is the corpus to search; ``path`` is the queried code path,
    resolved against the repository root (the nearest ``.decided/``, ADR-018). Reads
    fresh per call (ADR-032); results are sorted by decision id so the answer is
    byte-identical across runs and platforms (ADR-002). An ungoverned or
    outside-repository path yields an empty ``decisions`` list, never an error.
    """
    root = repository_root(directory)
    query = _normalize_query(path, root)
    if query is None:
        return ScopeLookupResult(query=path.strip(), in_repository=False, decisions=[])
    matches = [
        governing
        for entry in walk_corpus(directory, recursive=recursive)
        if (governing := _governing(entry, query)) is not None
    ]
    matches.sort(key=lambda d: (d.id.casefold(), d.path))
    return ScopeLookupResult(query=query, in_repository=True, decisions=matches)
