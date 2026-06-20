"""Corpus export — `rac export` (v0.11.0).

``build_corpus_export`` walks a directory once and composes existing Core
services — corpus traversal, identity/aliases, relationship extraction and
resolution — into one deterministic :class:`CorpusExport` payload for the
Portal, the read-only HTML viewer (ADR-014: artifacts stay viewer-agnostic;
exports are how external viewers consume a corpus; ADR-012: export lives in
the open-source core). The payload shape is a stable public contract
(ADR-007), reconciled with ``rac-localview/VIEWER_CONTRACT.md`` v1.

Determinism (ADR-002): no timestamps, no environment-dependent fields,
artifacts in sorted-path order, relationships sorted by ``(from, to)`` —
two exports of the same tree are byte-identical.

Pinned semantics (the viewer treats both fields as open sets):

- ``status`` is the first non-empty line of the artifact's ``## Status``
  section, canonicalized against the type's declared metadata values exactly
  as ``rac inspect`` does (so a decision's ``accepted`` exports as
  ``Accepted``). ``rac inspect`` *omits* a missing status; the export
  contract requires a string, so an absent or empty section exports as
  ``"unknown"``.
- ``title`` is the document title; an untitled artifact falls back to its
  canonical identifier (``rac index`` emits ``null`` there, but the viewer
  contract pins ``title`` as a string).
- ``body_html`` is the Markdown body after the frontmatter envelope,
  rendered by the vendored ``markdown-it-py`` CommonMark preset with raw
  HTML *disabled*: HTML in sources is escaped, not executed (the Portal
  trust model in VIEWER_CONTRACT.md depends on this).
- Unknown-type files are not exported (classification is the gate, matching
  the skip semantics of directory validation); invalid but *recognizable*
  artifacts export as classified — classification stays separate from
  validation.
- Relationships are untyped ``relates-to`` edges. ``to`` is the target's
  canonical identifier when the reference resolves uniquely through the same
  alias index relationship validation uses; otherwise the literal reference
  text is preserved verbatim (ADR-016: the line text *is* the reference).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePath

from markdown_it import MarkdownIt

import rac
from rac.core.artifacts import ArtifactSpec, spec_for
from rac.core.corpus import walk_corpus
from rac.core.frontmatter import split_frontmatter
from rac.core.identity import artifact_identifier, artifact_identifiers
from rac.core.models import Product

from .inspect import canonical_value
from .relationships import relationships_from_corpus

# The only edge type Core emits today; richer typing (supersedes/refines/
# implements) is reserved for a future decision, not an export invention.
EDGE_TYPE = "relates-to"

# Exported status for artifacts with no (or an empty) ``## Status`` section.
STATUS_ABSENT = "unknown"


@dataclass
class ExportArtifact:
    """One artifact in the export payload (viewer contract v1)."""

    id: str
    aliases: list[str]
    type: str
    status: str
    title: str
    path: str
    body_html: str
    # OKF-reserved descriptive labels (ADR-050). Carried for the OKF bundle
    # projection; deliberately *not* in ``to_dict`` — the JSON contract (ADR-007)
    # is unchanged until a versioned addition is decided.
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "aliases": self.aliases,
            "type": self.type,
            "status": self.status,
            "title": self.title,
            "path": self.path,
            "body_html": self.body_html,
        }


@dataclass
class ExportRelationship:
    """One ``relates-to`` edge; reads "``from`` ``type`` ``to``".

    ``from_`` serializes as ``"from"`` (a Python keyword cannot be a field
    name). ``to`` is a canonical identifier when resolved, else the literal
    reference text — the viewer renders unresolved targets as "(not in
    corpus)" rather than dropping them.
    """

    from_: str
    to: str
    type: str = EDGE_TYPE

    def to_dict(self) -> dict:
        return {"from": self.from_, "to": self.to, "type": self.type}


@dataclass
class CorpusExport:
    """Deterministic corpus export (v0.11.0).

    ``to_dict`` is the stable JSON contract (ADR-007); ``schema_version`` is
    the string ``"1"``, matching the index contract. ``rac_version`` is the
    producing CLI's version — the one environment-derived field, captured at
    build time into the model so the payload itself stays a pure value.
    """

    corpus_name: str
    rac_version: str
    artifacts: list[ExportArtifact] = field(default_factory=list)
    relationships: list[ExportRelationship] = field(default_factory=list)

    @property
    def artifact_count(self) -> int:
        return len(self.artifacts)

    def to_dict(self) -> dict:
        return {
            "schema_version": "1",
            "corpus": {
                "name": self.corpus_name,
                "rac_version": self.rac_version,
                "artifact_count": self.artifact_count,
            },
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
            "relationships": [edge.to_dict() for edge in self.relationships],
        }


@dataclass
class ExportDocument:
    """One artifact as an ingestion-ready document (v0.25.0 WS1).

    Unlike :class:`ExportArtifact`, ``text`` is the artifact's **Markdown body**
    (frontmatter stripped), not rendered HTML: memory/RAG backends embed text,
    and HTML markup would be noise. The artifact is the atomic unit (ADR-004,
    ADR-010) — one document per artifact, never chunked.
    """

    id: str
    type: str
    status: str
    title: str
    text: str
    aliases: list[str]
    path: str
    tags: list[str] = field(default_factory=list)

    def to_dict(self, source: str) -> dict:
        """One JSONL record. ``source`` namespaces the corpus (e.g. a containerTag)."""
        return {
            "schema_version": "1",
            "id": self.id,
            "type": self.type,
            "status": self.status,
            "title": self.title,
            "text": self.text,
            "metadata": {
                "path": self.path,
                "aliases": self.aliases,
                "tags": self.tags,
                "source": source,
            },
        }


@dataclass
class DocumentsExport:
    """Deterministic, ingestion-shaped projection of the corpus (v0.25.0 WS1).

    One record per classified artifact, in sorted-path order with no timestamps
    (ADR-002), serialized as JSON Lines — the common ingestion shape for external
    memory/RAG backends. The contract is additive and separate from the viewer
    JSON (:class:`CorpusExport`), which is unchanged (ADR-007). Each record
    carries the canonical ``id`` so an agent can re-fetch the authoritative
    artifact from Lore, and ``status`` so a retired decision is filterable on read.
    """

    corpus_name: str
    documents: list[ExportDocument] = field(default_factory=list)

    @property
    def document_count(self) -> int:
        return len(self.documents)

    def to_records(self) -> list[dict]:
        return [doc.to_dict(self.corpus_name) for doc in self.documents]


def _corpus_name(directory: str) -> str:
    """The directory's basename, deterministic relative to the argument given.

    Trailing separators are stripped so ``rac/`` and ``rac`` name the same
    corpus; the path is *not* resolved against the filesystem, so output never
    depends on the working directory.
    """
    return PurePath(directory.rstrip("/")).name or directory


def _status(product: Product, spec: ArtifactSpec) -> str:
    """The artifact's lifecycle status, in inspect's canonical spelling."""
    body = product.sections.get("status")
    if not body:
        return STATUS_ABSENT
    return canonical_value(body, spec.metadata.get("status", ())) or STATUS_ABSENT


def _render_body(path: str, md: MarkdownIt) -> str:
    """Render the Markdown body after the frontmatter envelope to HTML."""
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    return md.render(split_frontmatter(text).body)


def _body_markdown(path: str) -> str:
    """The artifact's Markdown body after the frontmatter envelope (no render)."""
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    return split_frontmatter(text).body


def build_corpus_export(directory: str, recursive: bool = True) -> CorpusExport:
    """Export every classified artifact under ``directory`` (one corpus walk).

    Unknown-type files are skipped from ``artifacts`` but still feed the
    resolution index, exactly as relationship validation builds it — so a
    reference resolves here precisely when ``--validate`` reports no issue
    for it.
    """
    entries = list(walk_corpus(directory, recursive=recursive))
    # The commonmark preset *enables* raw HTML (the spec includes it); the
    # Portal trust model requires it off, so sources arrive escaped.
    md = MarkdownIt("commonmark", {"html": False})

    canonical_by_path: dict[str, str] = {}
    artifacts: list[ExportArtifact] = []
    for entry in entries:
        path = str(entry.path)
        spec = spec_for(entry.artifact_type)  # None for Unknown
        canonical = artifact_identifier(entry.product, spec, path)
        canonical_by_path[path] = canonical
        if spec is None:
            continue  # unknown files are not exported
        meta = entry.product.metadata
        artifacts.append(
            ExportArtifact(
                id=canonical,
                aliases=artifact_identifiers(entry.product, spec, path),
                type=entry.artifact_type,
                status=_status(entry.product, spec),
                title=entry.product.title or canonical,
                path=path,
                body_html=_render_body(path, md),
                tags=meta.tags if meta else [],
            )
        )

    edges = [
        ExportRelationship(
            from_=canonical_by_path[rel.source_path],
            to=(canonical_by_path[rel.resolved_path] if rel.resolved_path else rel.target),
        )
        for rel in relationships_from_corpus(entries)
    ]
    edges.sort(key=lambda edge: (edge.from_, edge.to))

    return CorpusExport(
        corpus_name=_corpus_name(directory),
        rac_version=rac.__version__,
        artifacts=artifacts,
        relationships=edges,
    )


def build_documents_export(directory: str, recursive: bool = True) -> DocumentsExport:
    """Project every classified artifact under ``directory`` as a document (one walk).

    Mirrors :func:`build_corpus_export`'s gate — unknown-type files are skipped,
    invalid-but-recognizable artifacts project as classified — but emits the
    Markdown body and the verify-in-Lore metadata rather than the viewer's HTML.
    Artifacts arrive in sorted-path order, so the projection is deterministic.
    """
    documents: list[ExportDocument] = []
    for entry in walk_corpus(directory, recursive=recursive):
        path = str(entry.path)
        spec = spec_for(entry.artifact_type)  # None for Unknown
        if spec is None:
            continue  # unknown files are not exported
        canonical = artifact_identifier(entry.product, spec, path)
        meta = entry.product.metadata
        documents.append(
            ExportDocument(
                id=canonical,
                type=entry.artifact_type,
                status=_status(entry.product, spec),
                title=entry.product.title or canonical,
                text=_body_markdown(path),
                aliases=artifact_identifiers(entry.product, spec, path),
                path=path,
                tags=meta.tags if meta else [],
            )
        )
    return DocumentsExport(corpus_name=_corpus_name(directory), documents=documents)
