"""Canonical corpus traversal — the walk -> parse -> classify seam.

Every command that inventories Markdown artifacts does the same three things:
discover files (:func:`rac.core.fs.find_markdown_files`), parse each into a
:class:`~rac.core.models.Product` (:func:`rac.core.markdown.parse_file`), and
classify it (:func:`rac.core.classification.classify`). Defining that loop once,
here in deterministic core (ADR-032), keeps every consumer — services and the
Explorer alike — reading the same tree the same way.

Ordering is ``find_markdown_files``' sorted order throughout, so consumer output
(and the golden files pinning it) is stable, and parse errors bubble to the
caller rather than being swallowed. Three shapes share the one definition: a
lazy iterator (:func:`walk_corpus`), an eager snapshot with progress and
cancellation (:func:`collect_corpus`), and a content-hashed reuse cache
(:class:`CorpusCache`).
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from .classification import Classification, classify
from .fs import find_markdown_files
from .markdown import parse_file
from .models import Product
from .operations import CancelToken, Progress, ProgressCallback, checkpoint

# Every unreadable path collapses to this one digest. CorpusCache keys on the
# path, so distinct broken files never collide in a way that matters; the next
# successful read is what decides whether the file has actually changed.
_UNREADABLE_SENTINEL = b"\x00rac-unreadable-artifact"


@dataclass(frozen=True)
class CorpusEntry:
    """One Markdown document encountered during a corpus walk."""

    path: Path
    product: Product
    classification: Classification

    @property
    def artifact_type(self) -> str:
        """The classified type (``"unknown"`` is a valid outcome, REQ-010)."""
        return self.classification.type


def _entry_for(path: Path) -> CorpusEntry:
    """Parse and classify one file into a :class:`CorpusEntry`.

    The single point where a path becomes an entry, so the lazy, eager, and
    cached traversals cannot drift in how they parse or classify.
    """
    product = parse_file(str(path))
    return CorpusEntry(path=path, product=product, classification=classify(product))


def walk_corpus(directory: str, *, recursive: bool = True) -> Iterator[CorpusEntry]:
    """Yield every Markdown document under ``directory`` as a :class:`CorpusEntry`.

    Lazy and deterministic: files arrive in ``find_markdown_files`` order and
    parsing/classification are pure (ADR-002), so the caller controls how far
    the walk actually runs.
    """
    for path in find_markdown_files(directory, recursive=recursive):
        yield _entry_for(path)


def collect_corpus(
    directory: str,
    *,
    recursive: bool = True,
    on_progress: ProgressCallback | None = None,
    cancel: CancelToken | None = None,
) -> list[CorpusEntry]:
    """Materialise the corpus walk as a reusable snapshot.

    One walk can then feed every analysis a consumer needs instead of each
    re-walking the tree. The file count is known up front, so progress is
    reported per file with a real total; the cancellation checkpoint fires
    *before* each parse, so cancelling once ``completed == N`` leaves exactly N
    entries parsed.
    """
    paths = find_markdown_files(directory, recursive=recursive)
    total = len(paths)
    entries: list[CorpusEntry] = []
    for completed, path in enumerate(paths, start=1):
        checkpoint(cancel)
        entries.append(_entry_for(path))
        if on_progress is not None:
            on_progress(Progress(phase="scan", completed=completed, total=total))
    return entries


def content_hash(path: Path) -> str:
    """SHA-256 of an artifact's full on-disk source bytes (front matter + body).

    Source bytes only — never derived output, never mtime (WS8, REQ-002) — so
    any edit (whitespace and front matter included) changes the digest and forces
    a reprocess, while touching a file without changing its bytes does not. An
    unreadable file hashes to a stable sentinel rather than raising, so a walk
    can continue past it.
    """
    try:
        source = path.read_bytes()
    except OSError:
        source = _UNREADABLE_SENTINEL
    return hashlib.sha256(source).hexdigest()


class CorpusCache:
    """Per-invocation, content-hash-keyed reuse of parsed entries (WS8).

    Within one CLI invocation several phases each want the parsed corpus — the
    doctor pass alone runs validation, relationship integrity, and its own
    checks. This cache hashes each artifact's source bytes and, when a later
    phase asks for an artifact whose bytes are unchanged from an earlier phase of
    the same run, returns the already-parsed :class:`CorpusEntry` rather than
    reparsing it (REQ-001). Identical bytes always reparse to the same
    ``Product``, so a reused entry yields byte-identical derived output to a full
    reprocess (REQ-003).

    It is in-memory and invocation-scoped: nothing is persisted and no process
    boundary is crossed (REQ-001). It is deliberately not used by the MCP serving
    path, which re-reads from disk on every tool call (ADR-032, REQ-004). The
    ``reprocessed`` / ``reused`` counters exist only so tests can prove the
    short-circuit fires.
    """

    def __init__(self) -> None:
        self._by_path: dict[Path, tuple[str, CorpusEntry]] = {}
        self.reprocessed = 0
        self.reused = 0

    def collect(self, directory: str, *, recursive: bool = True) -> list[CorpusEntry]:
        """Return the corpus snapshot, reparsing only artifacts whose bytes changed.

        Order-stable in ``find_markdown_files`` order, exactly as
        :func:`walk_corpus`. Every call still reads each file to hash it (cheap);
        only the parse + classify is short-circuited on an unchanged digest.
        """
        entries: list[CorpusEntry] = []
        for path in find_markdown_files(directory, recursive=recursive):
            digest = content_hash(path)
            cached = self._by_path.get(path)
            if cached is not None and cached[0] == digest:
                self.reused += 1
                entries.append(cached[1])
                continue
            entry = _entry_for(path)
            self._by_path[path] = (digest, entry)
            self.reprocessed += 1
            entries.append(entry)
        return entries
