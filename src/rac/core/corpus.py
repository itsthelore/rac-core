"""Canonical corpus traversal — the walk → parse → classify seam (v0.7.14).

Every repository command that inventories Markdown artifacts performs the
same three steps: discover files (:func:`rac.core.fs.find_markdown_files`),
parse each into a :class:`~rac.core.models.Product`
(:func:`rac.core.markdown.parse_file`), and classify the result
(:func:`rac.core.classification.classify`). v0.7.14 extracts that loop here —
in core, where deterministic analysis lives (ADR-015) — so the services and
the v0.8.x Explorer consume one traversal definition instead of seven copies.

Iteration is lazy and ordering is ``find_markdown_files``' sorted order, so
consumers' output (and the golden files that pin it) is unchanged. Parse
errors keep bubbling to the caller, matching the loops this replaces.
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


def walk_corpus(directory: str, *, recursive: bool = True) -> Iterator[CorpusEntry]:
    """Yield every Markdown document under ``directory`` as a :class:`CorpusEntry`.

    Deterministic: files arrive in ``find_markdown_files``' sorted order, and
    parsing/classification are pure (ADR-002).
    """
    for path in find_markdown_files(directory, recursive=recursive):
        product = parse_file(str(path))
        yield CorpusEntry(path=path, product=product, classification=classify(product))


def collect_corpus(
    directory: str,
    *,
    recursive: bool = True,
    on_progress: ProgressCallback | None = None,
    cancel: CancelToken | None = None,
) -> list[CorpusEntry]:
    """Materialize the corpus walk as a reusable snapshot (v0.8.0).

    The snapshot lets one walk feed every analysis a consumer needs — index,
    validation, relationships, portfolio — instead of each re-walking the
    tree. Long-lived consumers get per-file progress (the file count is known
    up front) and a cancellation checkpoint before each parse.
    """
    paths = find_markdown_files(directory, recursive=recursive)
    total = len(paths)
    entries: list[CorpusEntry] = []
    for completed, path in enumerate(paths, start=1):
        checkpoint(cancel)
        product = parse_file(str(path))
        entries.append(CorpusEntry(path=path, product=product, classification=classify(product)))
        if on_progress is not None:
            on_progress(Progress(phase="scan", completed=completed, total=total))
    return entries


def content_hash(path: Path) -> str:
    """SHA-256 of an artifact's full on-disk source bytes (front matter + body).

    Source content only — never derived output, never mtime (WS8, REQ-002) — so
    any edit (whitespace or front-matter included) changes the digest and forces
    a reprocess, while touching a file without changing its bytes does not. An
    unreadable file hashes to a stable sentinel rather than raising, so the walk
    continues past it (the next read decides whether it changed).
    """
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return hashlib.sha256(b"\x00rac-unreadable-artifact").hexdigest()


class CorpusCache:
    """Per-invocation, content-hash-keyed corpus snapshot reuse (v0.23.0, WS8).

    Within ONE CLI invocation several phases each want the parsed corpus — the
    doctor pass runs validation, relationship integrity, and its own degree /
    injection checks, each of which would otherwise re-walk and re-parse every
    artifact. This cache hashes each artifact's on-disk source bytes through the
    ``collect_corpus`` seam ADR-032 names and, when a later phase requests an
    artifact whose hash is unchanged from an earlier phase of the same run,
    returns the already-parsed :class:`CorpusEntry` instead of reparsing it
    (REQ-001).

    It is in-memory and invocation-scoped: it persists no state to disk and
    survives no process boundary (REQ-001), and it is deliberately NOT used by
    the MCP serving path, which re-reads from disk on every tool call (ADR-032,
    REQ-004). Because identical source bytes always reparse to the same
    ``Product``, reusing an entry yields byte-identical derived output to
    reprocessing it (REQ-003); ``reprocessed`` / ``reused`` are exposed only so
    tests can prove the short-circuit fires.
    """

    def __init__(self) -> None:
        self._by_path: dict[Path, tuple[str, CorpusEntry]] = {}
        self.reprocessed = 0
        self.reused = 0

    def collect(self, directory: str, *, recursive: bool = True) -> list[CorpusEntry]:
        """Return the corpus snapshot, reparsing only artifacts whose bytes changed.

        Deterministic and order-stable: files arrive in ``find_markdown_files``
        order, exactly as :func:`walk_corpus`. Every call still reads each file to
        hash it (cheap); only the parse + classify is short-circuited.
        """
        entries: list[CorpusEntry] = []
        for path in find_markdown_files(directory, recursive=recursive):
            digest = content_hash(path)
            cached = self._by_path.get(path)
            if cached is not None and cached[0] == digest:
                self.reused += 1
                entries.append(cached[1])
                continue
            product = parse_file(str(path))
            entry = CorpusEntry(path=path, product=product, classification=classify(product))
            self._by_path[path] = (digest, entry)
            self.reprocessed += 1
            entries.append(entry)
        return entries
