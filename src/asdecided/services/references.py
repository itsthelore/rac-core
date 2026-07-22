"""Relationship section vocabulary and reference extraction (the pure foundation).

Relationships are explicit Markdown sections (``## Related Decisions``,
``## Supersedes``, ...) that reference other artifacts (ADR-016). This module is
the single home for the relationship-section *vocabulary* and for turning those
sections into reference strings — the pure, dependency-light foundation that
:mod:`asdecided.services.relationships` (inspection, validation, the graph model) and
the ``decided inspect`` / ``decided stats`` surfaces all build on.

It is pure and deterministic (ADR-002 / ADR-016): it parses section text only and
never resolves, validates, or graphs the references.

Recognition is spec-driven (REQ-002): only the relationship sections an artifact
type declares in :attr:`ArtifactSpec.optional` are considered, so a section is
recognized exactly where its schema allows it.
"""

from __future__ import annotations

import re

from asdecided.core.artifacts import ArtifactSpec
from asdecided.core.models import Product

# The cross-artifact "Related X" sections. These populate the ``relationships``
# dict in ``decided inspect`` output. ``related designs`` is included so every peer
# artifact type can be referenced.
RELATED_SECTIONS: tuple[str, ...] = (
    "related requirements",
    "related decisions",
    "related roadmaps",
    "related prompts",
    "related designs",
)

# External-reference relationship sections (ADR-087): recognized sections whose
# target is an external identifier (a ticket), not a peer artifact. They are
# extracted and graphed like the others but format-linted (against the per-repo
# ticketing provider, ADR-088), never resolved. Kept separate from
# RELATED_SECTIONS, which is exactly the per-artifact-type vocabulary (one
# ``related <type>s`` per type).
EXTERNAL_SECTIONS: tuple[str, ...] = ("related tickets", "verified by")

# Filesystem-scoped relationship sections (decision-to-code-proximity, Initiative
# 1): recognized sections whose targets are repository file paths/components a
# decision governs, not peer artifacts. Extracted and graphed like the others, but
# their literal path/directory entries are existence-checked against the working
# tree (see :func:`asdecided.services.relationships._scope_validation_issues`) rather
# than resolved by identifier. Kept separate from EXTERNAL_SECTIONS, which are
# format-linted, never existence-checked.
SCOPE_SECTIONS: tuple[str, ...] = ("applies to",)

# The full relationship-section vocabulary and its canonical ordering: the per-type
# ``related *`` sections, then ``supersedes``, then the external-reference sections,
# then the filesystem-scoped sections. This module owns the ordering; ``stats`` and
# the ``relationships`` command both render by-type output in this order.
# ``supersedes`` is the one section that does *not* appear in the inspect
# ``relationships`` dict: there it stays a top-level scalar for backwards
# compatibility (ADR-007). Order is append-only (ADR-007).
RELATIONSHIP_SECTIONS: tuple[str, ...] = (
    RELATED_SECTIONS + ("supersedes",) + EXTERNAL_SECTIONS + SCOPE_SECTIONS
)

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
    """Cross-artifact references for ``decided inspect``.

    Excludes ``supersedes`` — that stays a top-level scalar in inspect output
    (ADR-007). External-reference sections (``related tickets``) and filesystem-
    scoped sections (``applies to``) are included. Order follows ``spec.optional``
    (the artifact's own schema order).
    """
    return _collect(product, spec, RELATED_SECTIONS + EXTERNAL_SECTIONS + SCOPE_SECTIONS)


def extract_relationships_full(product: Product, spec: ArtifactSpec) -> dict[str, list[str]]:
    """Cross-artifact references for ``decided relationships`` — *including* Supersedes.

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
    ``spec.optional`` order, for ``decided stats`` declared-presence counts.
    """
    present: list[str] = []
    for section in spec.optional:
        if section not in RELATIONSHIP_SECTIONS:
            continue
        body = product.sections.get(section)
        if body and parse_references(body):
            present.append(section)
    return present


def unsupported_relationship_sections(product: Product, spec: ArtifactSpec) -> list[str]:
    """Relationship sections ``product`` declares that its type does not support.

    A ``## Related <Type>`` / ``## Supersedes`` section present with at least one
    reference whose name is *not* in this type's ``spec.optional`` produces no edge
    today and is silently dropped (ADR-049 edge-legality;
    ``rac-cross-artifact-enforcement`` REQ-004). Returns the canonical section
    names in :data:`RELATIONSHIP_SECTIONS` order so the finding is deterministic.
    """
    unsupported: list[str] = []
    for section in RELATIONSHIP_SECTIONS:
        if section in spec.optional:
            continue
        body = product.sections.get(section)
        if body and parse_references(body):
            unsupported.append(section)
    return unsupported
