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
