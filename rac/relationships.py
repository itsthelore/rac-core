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

from .artifacts import RELATED_SECTIONS, RELATIONSHIP_SECTIONS, ArtifactSpec
from .models import Product

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


def extract_relationships(product: Product, spec: ArtifactSpec) -> dict[str, list[str]]:
    """Cross-artifact references declared by ``product`` under ``spec``.

    Returns ``{snake_section -> [references]}`` in ``spec.optional`` order,
    including only sections present with at least one parsed reference. Excludes
    ``supersedes`` — that stays a top-level scalar in inspect output (ADR-007).
    """
    relationships: dict[str, list[str]] = {}
    for section in spec.optional:
        if section not in RELATED_SECTIONS:
            continue
        body = product.sections.get(section)
        if not body:
            continue
        refs = parse_references(body)
        if refs:
            relationships[_snake(section)] = refs
    return relationships


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
