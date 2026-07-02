"""Repository index — `rac index`.

``build_repository_index`` walks a directory once and returns a deterministic
inventory of every Markdown artifact: its stable identity, classified type,
title, and path. It answers exactly one question — *what exists here?* — and
deliberately nothing more: no validation, no relationship traversal, no health
scoring, no metadata interpretation. Those belong to ``rac inspect`` /
``rac relationships`` / ``rac portfolio``.

Discovery is a Core responsibility (REQ-001, ADR-015): Explorer, IDE
integrations, AI tools, and CI navigate from this inventory instead of scanning
files themselves. The index is read-only (REQ-004) and deterministic (ADR-002):
one parse per file, no cross-file resolution, entries in sorted-path order.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from rac.core.artifacts import spec_for
from rac.core.corpus import CorpusEntry, walk_corpus
from rac.core.identity import artifact_identifier, artifact_identifiers
from rac.core.models import SearchSection


@dataclass
class IndexEntry:
    """One row in the repository manifest (ADR-003).

    Structural, not analytical: identity, type, title, and path only. Unknown
    documents are included with ``type == "unknown"`` and a filename-stem
    identifier (ADR-010) so consumers can render the whole tree.
    """

    id: str
    type: str
    title: str | None
    path: str
    # Every identifier the artifact answers to, canonical first (additive): legacy
    # aliases keep resolving during identity migration.
    aliases: list[str] = field(default_factory=list)
    # Searchable headings and body lines with original text preserved. The
    # heading/body tiers of ``rac find`` and their snippets read from here,
    # sourced from this same walk — never a second file read. Carried in memory
    # only: the index JSON contract (id/type/title/path/aliases) excludes it.
    search_sections: list[SearchSection] = field(default_factory=list)
    # Resolved relationship edges pointing at this artifact — the deterministic
    # graph signal the ``rac find`` relevance ranker fuses (ADR-078). Also
    # in-memory only; not part of the JSON contract.
    inbound_count: int = 0

    def to_dict(self) -> dict:
        # search_sections/inbound_count are deliberately excluded — the JSON
        # contract (ADR-007) is exactly these five keys.
        return {
            "id": self.id,
            "type": self.type,
            "title": self.title,
            "path": self.path,
            "aliases": self.aliases,
        }


@dataclass
class RepositoryIndex:
    """Deterministic inventory of every artifact in a repository.

    ``to_dict`` is the stable JSON contract (ADR-007); ``schema_version`` lets
    consumers detect breaking changes. Entries follow discovery order (sorted by
    path), so output is reproducible across runs and machines.
    """

    directory: str
    recursive: bool
    artifacts: list[IndexEntry] = field(default_factory=list)

    @property
    def artifact_count(self) -> int:
        return len(self.artifacts)

    def to_dict(self) -> dict:
        return {
            "schema_version": "1",
            "directory": self.directory,
            "recursive": self.recursive,
            "artifact_count": self.artifact_count,
            "artifacts": [entry.to_dict() for entry in self.artifacts],
        }


def build_repository_index(directory: str, recursive: bool = True) -> RepositoryIndex:
    """Walk ``directory`` and inventory every Markdown artifact (one parse each)."""
    entries = list(walk_corpus(directory, recursive=recursive))
    return index_from_corpus(directory, entries, recursive=recursive)


def index_from_corpus(
    directory: str, entries: list[CorpusEntry], recursive: bool = True
) -> RepositoryIndex:
    """Inventory an already-walked corpus snapshot.

    Same result as :func:`build_repository_index`, but taking a snapshot lets one
    walk feed several analyses. Each entry also gets its inbound resolved-edge
    count (ADR-078), computed once from the same snapshot. The import is deferred
    inside the function body to keep the index -> relationships dependency
    one-way — relationships never imports index.
    """
    from rac.services.relationships import inbound_counts_from_corpus

    inbound = inbound_counts_from_corpus(entries)
    artifacts: list[IndexEntry] = []
    for entry in entries:
        path = str(entry.path)
        product = entry.product
        spec = spec_for(entry.artifact_type)  # None for unknown
        artifacts.append(
            IndexEntry(
                id=artifact_identifier(product, spec, path),
                type=entry.artifact_type,
                title=product.title,
                path=path,
                aliases=artifact_identifiers(product, spec, path),
                search_sections=product.search_sections,
                inbound_count=inbound.get(path, 0),
            )
        )
    return RepositoryIndex(directory=directory, recursive=recursive, artifacts=artifacts)
