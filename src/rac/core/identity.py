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


def artifact_identifier(
    product: Product, spec: ArtifactSpec | None, path: str
) -> str:
    """The deterministic identifier for the artifact at ``path`` (v0.7.2).

    Precedence (first match wins); the discovered casing is preserved:

    1. an explicit ``## ID`` section value;
    2. the artifact type's declared ``spec.id_field`` section value;
    3. a recognized ``<letters>-<digits>`` prefix of the filename stem
       (e.g. ``adr-004`` from ``adr-004-parser-strategy.md``);
    4. the whole filename stem.

    The document title is never used, and inline ``[REQ-NNN]`` requirement lines
    are not identifiers — relationship targets are whole artifact files.
    """
    explicit = _first_value(product.sections.get(_ID_SECTION))
    if explicit:
        return explicit
    if spec is not None and spec.id_field:
        declared = _first_value(product.sections.get(spec.id_field))
        if declared:
            return declared
    stem = Path(path).stem
    prefix = _ID_PREFIX_RE.match(stem)
    return prefix.group(0) if prefix else stem
