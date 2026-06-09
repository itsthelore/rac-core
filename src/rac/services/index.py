"""Repository index — `rac index` (v0.7.5).

``build_repository_index`` walks a directory once and produces a deterministic
inventory of every Markdown artifact discovered: its stable identity, classified
type, title, and path. It answers a single question — *what exists in this
repository?* — and deliberately nothing more: no validation, no relationship
traversal, no health scoring, no metadata interpretation. Those concerns belong
to ``rac inspect`` / ``rac relationships`` / ``rac portfolio``.

Discovery belongs to RAC Core (REQ-001, ADR-015): consumers such as Explorer,
IDE integrations, AI tools, and CI build navigation from this inventory rather
than scanning files themselves. The index is read-only (REQ-004) and pure /
deterministic (ADR-002): one parse per file, no cross-file resolution, entries in
sorted-path order.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from rac.core.artifacts import spec_for
from rac.core.classification import classify
from rac.core.fs import find_markdown_files
from rac.core.identity import artifact_identifier, artifact_identifiers
from rac.core.markdown import parse_file


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
    # Every identifier the artifact answers to, canonical first (v0.7.12,
    # additive): legacy aliases keep resolving during identity migration.
    aliases: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "title": self.title,
            "path": self.path,
            "aliases": self.aliases,
        }


@dataclass
class RepositoryIndex:
    """Deterministic inventory of every artifact in a repository (v0.7.5).

    ``to_dict`` is the stable JSON contract (ADR-007); ``schema_version`` lets
    consumers detect breaking changes. Entries follow discovery order (sorted by
    path), so the output is reproducible across runs and machines.
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


def build_repository_index(
    directory: str, recursive: bool = True
) -> RepositoryIndex:
    """Walk ``directory`` and inventory every Markdown artifact (one parse each)."""
    artifacts: list[IndexEntry] = []
    for path in find_markdown_files(directory, recursive=recursive):
        product = parse_file(str(path))
        artifact_type = classify(product).type
        spec = spec_for(artifact_type)  # None for Unknown
        artifacts.append(
            IndexEntry(
                id=artifact_identifier(product, spec, str(path)),
                type=artifact_type,
                title=product.title,
                path=str(path),
                aliases=artifact_identifiers(product, spec, str(path)),
            )
        )
    return RepositoryIndex(
        directory=directory, recursive=recursive, artifacts=artifacts
    )
