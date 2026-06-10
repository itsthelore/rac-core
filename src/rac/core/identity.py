"""Artifact identity — the deterministic identifier for an artifact.

Artifact identity is a core RAC concept: a stable, content-derived identifier for an
artifact file, shared by repository indexing, relationship resolution, and portfolio
analysis alike. It is pure and deterministic (ADR-002): it reads the parsed document
and the filename only — never the filesystem clock, git, or any external state.

Introduced for relationship validation (v0.7.2) and promoted to a core primitive in
v0.7.5 so that ``rac index``, ``rac relationships``, and ``rac portfolio`` share one
owner of identity rather than reaching through one another.
"""

from __future__ import annotations

import re
from pathlib import Path

from .artifacts import ArtifactSpec
from .models import Product

# A *well-formed* leading Markdown list marker: ``-``, ``*``, ``+``, or ``N.`` followed
# by whitespace, stripped from the first line of a single-value section (e.g. ``## ID``).
_LIST_MARKER_RE = re.compile(r"^(?:[-*+]|\d+\.)\s+")

# A recognized leading ID prefix in a filename stem: <letters>-<digits>, e.g.
# "adr-004" from "adr-004-parser-strategy". Case-insensitive at comparison time.
_ID_PREFIX_RE = re.compile(r"^[A-Za-z]+-\d+")

# The universal explicit-identifier section (normalized heading).
_ID_SECTION = "id"


def _first_value(body: str | None) -> str:
    """First non-empty line of a section body, leading list marker stripped."""
    if not body:
        return ""
    for line in body.splitlines():
        stripped = line.strip()
        if stripped:
            return _LIST_MARKER_RE.sub("", stripped, count=1).strip()
    return ""


def _legacy_identifier(product: Product, spec: ArtifactSpec | None) -> str:
    """Declared legacy identity: ``## ID`` section, then ``spec.id_field``."""
    explicit = _first_value(product.sections.get(_ID_SECTION))
    if explicit:
        return explicit
    if spec is not None and spec.id_field:
        declared = _first_value(product.sections.get(spec.id_field))
        if declared:
            return declared
    return ""


def artifact_identifier(product: Product, spec: ArtifactSpec | None, path: str) -> str:
    """The deterministic identifier for the artifact at ``path``.

    Precedence (first match wins):

    1. the canonical frontmatter ``id`` (ADR-026, v0.7.11) — already
       normalized to uppercase by the frontmatter parser;
    2. an explicit ``## ID`` section value (casing preserved);
    3. the artifact type's declared ``spec.id_field`` section value;
    4. a recognized ``<letters>-<digits>`` prefix of the filename stem
       (e.g. ``adr-004`` from ``adr-004-parser-strategy.md``);
    5. the whole filename stem.

    The document title is never used, and inline ``[REQ-NNN]`` requirement lines
    are not identifiers — relationship targets are whole artifact files.
    Conflicts between frontmatter and legacy identity are *not* resolved here —
    :func:`identity_conflict` detects them and validation reports them; this
    function answers "what is the canonical identity" (frontmatter wins).
    """
    if product.metadata is not None and product.metadata.id:
        return product.metadata.id
    legacy = _legacy_identifier(product, spec)
    if legacy:
        return legacy
    stem = Path(path).stem
    prefix = _ID_PREFIX_RE.match(stem)
    return prefix.group(0) if prefix else stem


def artifact_identifiers(product: Product, spec: ArtifactSpec | None, path: str) -> list[str]:
    """Every identifier this artifact answers to, canonical first (v0.7.11).

    The canonical identifier leads (same value :func:`artifact_identifier`
    returns); legacy identifiers — a declared ``## ID`` / ``spec.id_field``
    value, the filename prefix, and the filename stem — follow as migration
    aliases. Reference resolution indexes all of them so existing
    human-readable references (e.g. ``ADR-015``) keep resolving after an
    artifact adopts canonical frontmatter identity (Initiative 7: legacy
    compatibility). Duplicate-identity detection uses only the canonical
    identifier; aliases never create duplicates on their own.
    """
    ids: list[str] = []

    def _add(value: str) -> None:
        if value and value.casefold() not in {i.casefold() for i in ids}:
            ids.append(value)

    if product.metadata is not None and product.metadata.id:
        _add(product.metadata.id)
    _add(_legacy_identifier(product, spec))
    stem = Path(path).stem
    prefix = _ID_PREFIX_RE.match(stem)
    if prefix:
        _add(prefix.group(0))
    _add(stem)
    return ids


def identity_conflict(product: Product, spec: ArtifactSpec | None) -> tuple[str, str] | None:
    """Detect conflicting frontmatter and legacy declared identity (v0.7.11).

    Returns ``(frontmatter_id, legacy_id)`` when both are declared and differ
    (compared case-insensitively — matching values are accepted during
    migration), or None. Filename-derived identity never conflicts: it is a
    fallback, not a declaration.
    """
    if product.metadata is None or not product.metadata.id:
        return None
    legacy = _legacy_identifier(product, spec)
    if not legacy:
        return None
    if legacy.strip().upper() == product.metadata.id:
        return None
    return (product.metadata.id, legacy)
