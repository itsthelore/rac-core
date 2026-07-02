"""Corpus projections — `rac export` and its `--documents` / `--graph` / `--okf` modes.

Three deterministic, read-only projections of a corpus, each composed from the
same Core services (traversal, identity/aliases, relationship resolution) so a
single walk yields a stable public payload (ADR-007):

- :func:`build_corpus_export` — the viewer/Portal payload (:class:`CorpusExport`):
  every classified artifact with its rendered HTML body and flattened, untyped
  ``relates-to`` edges.
- :func:`build_documents_export` — the ingestion projection (:class:`DocumentsExport`):
  one Markdown-body document per artifact for memory/RAG backends.
- :func:`build_graph_export` — the typed graph (:class:`GraphExport`, ADR-074):
  nodes plus edges carrying their registry edge kind and direction.

Determinism (ADR-002): no timestamps, no environment-dependent fields (bar the
producing CLI's version, captured into the model at build time), artifacts and
nodes in sorted-path order, edges sorted by a total key — two exports of the
same tree are byte-identical.

Shared gate: ``spec_for(type) is None`` (an unknown file) is excluded from the
projection, but the file still feeds reference resolution — an edge resolves
here exactly when ``relationships --validate`` reports it resolved.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePath
from typing import NamedTuple

from markdown_it import MarkdownIt

import rac
from rac.core.artifacts import ArtifactSpec, spec_for
from rac.core.corpus import CorpusEntry, walk_corpus
from rac.core.frontmatter import split_frontmatter
from rac.core.identity import artifact_identifier, artifact_identifiers
from rac.core.models import Product
from rac.core.relationship_types import edge_spec

from .init import load_ticketing_provider
from .inspect import canonical_value
from .relationships import relationships_from_corpus

# The single edge type the viewer payload emits; richer typing lives in the
# graph projection, not here.
EDGE_TYPE = "relates-to"

# Exported status for an artifact whose ``## Status`` section is missing or empty
# (the viewer contract requires a string where ``rac inspect`` would omit it).
STATUS_ABSENT = "unknown"


@dataclass
class ExportArtifact:
    """One artifact in the viewer payload (viewer contract v1)."""

    id: str
    aliases: list[str]
    type: str
    status: str
    title: str
    path: str
    body_html: str
    # OKF-reserved descriptive labels (ADR-050), carried for the OKF bundle
    # projection only. Deliberately absent from ``to_dict``: the frozen JSON
    # contract (ADR-007) predates tags and stays unchanged until a versioned add.
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
    """One flattened ``relates-to`` edge, read "``from`` ``type`` ``to``".

    ``from_`` serializes as ``"from"`` (the keyword cannot name a field). ``to``
    is a canonical identifier when the reference resolves, else the literal
    reference text preserved verbatim — the viewer renders unresolved targets
    rather than dropping them.
    """

    from_: str
    to: str
    type: str = EDGE_TYPE

    def to_dict(self) -> dict:
        return {"from": self.from_, "to": self.to, "type": self.type}


@dataclass
class CorpusExport:
    """Deterministic viewer/Portal payload.

    ``to_dict`` is the stable JSON contract (ADR-007); ``schema_version`` is the
    string ``"1"``. ``rac_version`` is captured from the producing CLI at build
    time so the payload value itself carries no live environment lookup.
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
    """One artifact as an ingestion-ready document.

    ``text`` is the artifact's Markdown *body* (frontmatter stripped), not
    rendered HTML: memory/RAG backends embed text, and markup would be noise.
    The artifact is the atomic unit (ADR-004, ADR-010) — one document each,
    never chunked.
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
        """One JSONL record; ``source`` namespaces the corpus (e.g. a container tag)."""
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
    """Deterministic ingestion projection, serialized as JSON Lines.

    One record per classified artifact, sorted-path order, no timestamps
    (ADR-002). Additive and separate from the viewer JSON (ADR-007). Each record
    carries the canonical ``id`` (re-fetch hook) and ``status`` (so a retired
    artifact is filterable on read).
    """

    corpus_name: str
    documents: list[ExportDocument] = field(default_factory=list)

    @property
    def document_count(self) -> int:
        return len(self.documents)

    def to_records(self) -> list[dict]:
        return [doc.to_dict(self.corpus_name) for doc in self.documents]


@dataclass
class GraphNode:
    """One artifact as a graph node."""

    id: str
    type: str
    status: str
    title: str

    def to_dict(self) -> dict:
        return {"id": self.id, "type": self.type, "status": self.status, "title": self.title}


@dataclass
class GraphEdge:
    """One typed relationship edge (ADR-074).

    ``type`` is the registry edge kind and ``directed`` follows the registry
    (``supersedes`` is directed; the ``related_*`` edges are not). ``resolved``
    is False when the reference does not resolve, in which case ``target`` is the
    literal reference text — no phantom node is invented. ``external`` is True for
    an external-reference edge (``related_tickets``, ADR-087; ``verified_by``,
    ADR-096) whose target is not an in-corpus artifact, distinguishing it from a
    dangling in-corpus link. ``provider`` carries the configured ticketing system
    (ADR-088) only for provider-backed external edges — ``verified_by`` is
    external and directed but not provider-tagged.
    """

    source: str
    target: str
    type: str
    directed: bool
    resolved: bool
    external: bool = False
    provider: str | None = None

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "target": self.target,
            "type": self.type,
            "directed": self.directed,
            "resolved": self.resolved,
            "external": self.external,
            "provider": self.provider,
        }


@dataclass
class GraphExport:
    """Deterministic typed node+edge projection (ADR-074).

    Surfaces the *typed* relationship graph for graph backends, unlike the
    viewer JSON's flattened ``relates-to`` edges (unchanged). Nodes in
    sorted-path order, edges sorted by ``(source, type, target)``, no timestamps.
    """

    corpus_name: str
    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "schema_version": "1",
            "source": self.corpus_name,
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
        }


class _Projection(NamedTuple):
    """A classified entry ready to project: path, entry, its spec, canonical id."""

    path: str
    entry: CorpusEntry
    spec: ArtifactSpec
    canonical: str


def _project(entries: list[CorpusEntry]) -> tuple[dict[str, str], list[_Projection]]:
    """Split a walked corpus into the resolution index and the projectable artifacts.

    The returned ``canonical_by_path`` maps *every* entry's path to its canonical
    id — unknown files included, because a reference that resolves to an unknown
    file must still name it in an edge. The list holds only classified entries
    (``spec is not None``), in the walk's sorted-path order, so all three builders
    share one gate and one loop instead of three near-duplicates.
    """
    canonical_by_path: dict[str, str] = {}
    projections: list[_Projection] = []
    for entry in entries:
        path = str(entry.path)
        spec = spec_for(entry.artifact_type)  # None for unknown
        canonical = artifact_identifier(entry.product, spec, path)
        canonical_by_path[path] = canonical
        if spec is not None:
            projections.append(_Projection(path, entry, spec, canonical))
    return canonical_by_path, projections


def _corpus_name(directory: str) -> str:
    """The directory's basename, stable relative to the argument as given.

    Trailing separators are stripped so ``rac/`` and ``rac`` name one corpus; the
    path is not resolved against the filesystem, so output is independent of the
    working directory.
    """
    return PurePath(directory.rstrip("/")).name or directory


def _status(product: Product, spec: ArtifactSpec) -> str:
    """The lifecycle status in inspect's canonical spelling, else ``STATUS_ABSENT``.

    Canonicalizes the ``## Status`` value against the type's declared metadata
    (``accepted`` -> ``Accepted``); the rendered body still keeps the literal
    source spelling.
    """
    body = product.sections.get("status")
    if not body:
        return STATUS_ABSENT
    return canonical_value(body, spec.metadata.get("status", ())) or STATUS_ABSENT


def _body_markdown(path: str) -> str:
    """The Markdown body after the frontmatter envelope (a fresh read).

    The parsed ``Product`` keeps sections, not the raw body, and a ``CorpusEntry``
    does not carry the source text — so the file is re-read here. This is the one
    place export reaches back to disk, shared by the HTML and document bodies.
    """
    with open(path, encoding="utf-8") as fh:
        return split_frontmatter(fh.read()).body


def _render_body(path: str, md: MarkdownIt) -> str:
    """Render the artifact's Markdown body to HTML (raw HTML escaped, never run)."""
    return md.render(_body_markdown(path))


def build_corpus_export(directory: str, recursive: bool = True) -> CorpusExport:
    """Export every classified artifact under ``directory`` as the viewer payload."""
    entries = list(walk_corpus(directory, recursive=recursive))
    # The commonmark preset enables raw HTML (the spec includes it); the Portal
    # trust model requires it off, so source HTML arrives escaped, not executed
    # (ADR-059: one parser instance per build).
    md = MarkdownIt("commonmark", {"html": False})
    canonical_by_path, projections = _project(entries)

    artifacts: list[ExportArtifact] = []
    for path, entry, spec, canonical in projections:
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
    """Project every classified artifact under ``directory`` as an ingestion document.

    Same gate as :func:`build_corpus_export`, but emits the Markdown body and the
    verify-in-Lore metadata rather than the viewer's HTML.
    """
    entries = list(walk_corpus(directory, recursive=recursive))
    _, projections = _project(entries)

    documents = [
        ExportDocument(
            id=canonical,
            type=entry.artifact_type,
            status=_status(entry.product, spec),
            title=entry.product.title or canonical,
            text=_body_markdown(path),
            aliases=artifact_identifiers(entry.product, spec, path),
            path=path,
            tags=(entry.product.metadata.tags if entry.product.metadata else []),
        )
        for path, entry, spec, canonical in projections
    ]
    return DocumentsExport(corpus_name=_corpus_name(directory), documents=documents)


def build_graph_export(directory: str, recursive: bool = True) -> GraphExport:
    """Project the corpus as typed nodes and edges (ADR-074).

    Nodes are the classified artifacts; edges carry the registry edge kind and
    its direction. Resolved targets become canonical-id edges; unresolved
    references keep their literal target with ``resolved: False`` rather than
    being dropped.
    """
    entries = list(walk_corpus(directory, recursive=recursive))
    # The configured ticketing provider tags provider-backed external edges
    # (ADR-088); read once for the whole build.
    provider = load_ticketing_provider(directory)
    canonical_by_path, projections = _project(entries)

    nodes = [
        GraphNode(
            id=canonical,
            type=entry.artifact_type,
            status=_status(entry.product, spec),
            title=entry.product.title or canonical,
        )
        for _path, entry, spec, canonical in projections
    ]

    edges: list[GraphEdge] = []
    for rel in relationships_from_corpus(entries):
        kind = edge_spec(rel.relationship)
        target = (
            canonical_by_path[rel.resolved_path] if rel.resolved_path is not None else rel.target
        )
        edges.append(
            GraphEdge(
                source=canonical_by_path[rel.source_path],
                target=target,
                type=rel.relationship,
                directed=kind.directional if kind else False,
                resolved=rel.resolved_path is not None,
                external=kind.external if kind else False,
                provider=provider if (kind and kind.external_provider) else None,
            )
        )
    edges.sort(key=lambda edge: (edge.source, edge.type, edge.target))

    return GraphExport(corpus_name=_corpus_name(directory), nodes=nodes, edges=edges)
