"""Relationship metadata service — extract cross-artifact references (v0.7.0).

Relationships are explicit Markdown sections (``## Related Decisions``,
``## Supersedes``, ...) that reference other artifacts (ADR-016). This module is
the single home for turning those sections into reference strings, shared by
``rac inspect`` (which exposes them as the additive ``relationships`` field) and
``rac stats`` (which counts their presence).

It is pure and deterministic (ADR-002 / ADR-016): it parses section text only and
never resolves, validates, or graphs the references — v0.7.0 is metadata only.

Recognition is spec-driven (REQ-002): only the relationship sections an artifact
type declares in :attr:`ArtifactSpec.optional` are considered, so a section is
recognized exactly where its schema allows it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .artifacts import ArtifactSpec, spec_for
from .classification import classify
from .fs import find_markdown_files
from .models import Product
from .parser import parse_file

# The cross-artifact "Related X" sections. These populate the ``relationships``
# dict in ``rac inspect`` output. ``related designs`` is included so every peer
# artifact type can be referenced.
RELATED_SECTIONS: tuple[str, ...] = (
    "related requirements",
    "related decisions",
    "related roadmaps",
    "related prompts",
    "related designs",
)

# The full relationship-section vocabulary and its canonical ordering, including
# ``supersedes``. This module owns the ordering; ``stats`` and the
# ``relationships`` command both render by-type output in this order. ``supersedes``
# is the one section that does *not* appear in the inspect ``relationships`` dict:
# there it stays a top-level scalar for backwards compatibility (ADR-007).
RELATIONSHIP_SECTIONS: tuple[str, ...] = RELATED_SECTIONS + ("supersedes",)

# A *well-formed* leading Markdown list marker: ``-``, ``*``, ``+``, or ``N.``
# followed by whitespace. Only these are stripped; any other leading text is
# preserved verbatim, so references like "REQ-001 (blocked)" or a path beginning
# with "../" survive intact (the whole line is the reference, per ADR-016).
_LIST_MARKER_RE = re.compile(r"^(?:[-*+]|\d+\.)\s+")


def _snake(section: str) -> str:
    return section.replace(" ", "_")


def parse_references(body: str) -> list[str]:
    """Split a relationship section body into individual reference strings.

    One reference per non-empty line. A well-formed leading list marker is
    stripped; otherwise the line is preserved verbatim. No ID parsing and no
    resolution — the line text *is* the reference.
    """
    references: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        references.append(_LIST_MARKER_RE.sub("", stripped, count=1).strip())
    return references


def _collect(
    product: Product, spec: ArtifactSpec, allowed: tuple[str, ...]
) -> dict[str, list[str]]:
    """References for the relationship sections in ``spec.optional`` ∩ ``allowed``.

    Returns ``{snake_section -> [references]}`` in ``spec.optional`` order (each
    artifact's own schema order), including only sections present with at least
    one parsed reference. The single core behind the two public extractors.
    """
    relationships: dict[str, list[str]] = {}
    for section in spec.optional:
        if section not in allowed:
            continue
        body = product.sections.get(section)
        if not body:
            continue
        refs = parse_references(body)
        if refs:
            relationships[_snake(section)] = refs
    return relationships


def extract_relationships(product: Product, spec: ArtifactSpec) -> dict[str, list[str]]:
    """Cross-artifact references for ``rac inspect``.

    Excludes ``supersedes`` — that stays a top-level scalar in inspect output
    (ADR-007). Order follows ``spec.optional`` (the artifact's own schema order).
    """
    return _collect(product, spec, RELATED_SECTIONS)


def extract_relationships_full(
    product: Product, spec: ArtifactSpec
) -> dict[str, list[str]]:
    """Cross-artifact references for ``rac relationships`` — *including* Supersedes.

    The repository-level relationship command treats Supersedes as a first-class
    relationship (REQ-003), so it is reported here alongside the ``related_*``
    sections. Order follows ``spec.optional``.
    """
    return _collect(product, spec, RELATIONSHIP_SECTIONS)


def present_relationship_sections(product: Product, spec: ArtifactSpec) -> list[str]:
    """Relationship sections ``product`` declares *and* populates.

    Spec-driven and inclusive of ``supersedes`` (unlike
    :func:`extract_relationships`). A section counts only when present with at
    least one parsed reference (REQ-011). Returns the normalized section names in
    ``spec.optional`` order, for ``rac stats`` declared-presence counts.
    """
    present: list[str] = []
    for section in spec.optional:
        if section not in RELATIONSHIP_SECTIONS:
            continue
        body = product.sections.get(section)
        if body and parse_references(body):
            present.append(section)
    return present


# --- Repository-level relationship inspection (v0.7.1) -----------------------
#
# `rac relationships <path>` discovers the explicit relationships declared across
# a tree of artifacts (ADR-015: repository intelligence in Core, exposed via CLI +
# JSON for future consumers). It is read-only and deterministic: it reports the
# references that exist, but never resolves, validates, or graphs them.


@dataclass
class ArtifactRelationships:
    """One artifact's relationships in a repository report.

    ``relationships`` includes Supersedes (unlike ``rac inspect``) and is keyed by
    snake_case section name in the artifact's own ``spec.optional`` order.
    """

    path: str
    type: str
    relationships: dict[str, list[str]]


@dataclass
class RelationshipReport:
    """Repository-level relationship inspection result (ADR-003).

    ``total_files`` counts every Markdown file considered — including files with
    no relationships and Unknown artifacts. ``artifacts`` lists only those with at
    least one relationship. Counts are *reference* counts (each declared target is
    one relationship), aggregated by type in the canonical
    :data:`RELATIONSHIP_SECTIONS` order.
    """

    directory: str
    recursive: bool
    total_files: int
    artifacts: list[ArtifactRelationships] = field(default_factory=list)

    @property
    def artifacts_with_relationships(self) -> int:
        return len(self.artifacts)

    @property
    def counts(self) -> dict[str, int]:
        """References per relationship type, canonical order, zero types omitted."""
        totals: dict[str, int] = {}
        for artifact in self.artifacts:
            for section, refs in artifact.relationships.items():
                totals[section] = totals.get(section, 0) + len(refs)
        return {
            _snake(section): totals[_snake(section)]
            for section in RELATIONSHIP_SECTIONS
            if _snake(section) in totals
        }

    @property
    def relationship_count(self) -> int:
        """Total references found across all artifacts (sum of ``counts``)."""
        return sum(self.counts.values())


def _artifact_relationships(path: str) -> tuple[str, dict[str, list[str]]]:
    """Classify the file at ``path`` and extract its full relationships.

    Returns ``(type, relationships)``. Unknown artifacts (no spec) yield an empty
    relationship dict — extraction stays spec-driven (REQ-007), no generic scan.
    """
    product = parse_file(path)
    artifact_type = classify(product).type
    spec = spec_for(artifact_type)
    relationships = extract_relationships_full(product, spec) if spec else {}
    return artifact_type, relationships


def _build_report(
    directory: str, paths: list, recursive: bool
) -> RelationshipReport:
    """Assemble a :class:`RelationshipReport` from ``paths`` (already ordered)."""
    artifacts: list[ArtifactRelationships] = []
    for path in paths:
        artifact_type, relationships = _artifact_relationships(str(path))
        if relationships:
            artifacts.append(
                ArtifactRelationships(
                    path=str(path), type=artifact_type, relationships=relationships
                )
            )
    return RelationshipReport(
        directory=directory,
        recursive=recursive,
        total_files=len(paths),
        artifacts=artifacts,
    )


def build_relationship_report(
    directory: str, recursive: bool = True
) -> RelationshipReport:
    """Inspect explicit relationships across a directory of Markdown files."""
    paths = find_markdown_files(directory, recursive=recursive)
    return _build_report(directory, paths, recursive)


def build_relationship_report_file(path: str) -> RelationshipReport:
    """Inspect relationships in a single file (REQ-009).

    Same model as a directory report, with one file and ``recursive=False``.
    """
    return _build_report(path, [path], recursive=False)
