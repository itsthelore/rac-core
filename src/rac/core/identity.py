"""The deterministic artifact identifier (ADR-026).

Identity is a shared core primitive: repository indexing, relationship
resolution, and portfolio analysis all ask this module "what does this artifact
answer to". It is pure and deterministic (ADR-002) — it reads only the parsed
:class:`~rac.core.models.Product` and the file path, never git, the clock, or any
other external state.

One precedence chain drives everything here: frontmatter ``id`` > an explicit
``## ID`` section > the type's declared ``spec.id_field`` > a ``<letters>-<digits>``
prefix of the filename stem > the whole stem. :func:`artifact_identifier` returns
the winner, :func:`artifact_identifiers` returns the whole chain deduped (the
migration aliases), and :func:`identity_conflict` flags a frontmatter id that
disagrees with a declared legacy id.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

from .artifacts import ArtifactSpec
from .models import Product

# A well-formed leading Markdown list marker — ``-``, ``*``, ``+`` or ``N.``
# plus whitespace — stripped from the first line of a single-value section so
# ``- ADR-099`` and ``ADR-099`` yield the same identity.
_LIST_MARKER_RE = re.compile(r"^(?:[-*+]|\d+\.)\s+")

# A recognised leading ID prefix in a filename stem: <letters>-<digits>, e.g.
# ``adr-004`` from ``adr-004-parser-strategy``. Compared case-insensitively.
_ID_PREFIX_RE = re.compile(r"^[A-Za-z]+-\d+")

# The universal explicit-identifier section, as a normalised heading key.
_ID_SECTION = "id"


def _first_value(body: str | None) -> str:
    """The first non-empty line of a section body, one list marker stripped."""
    if not body:
        return ""
    for line in body.splitlines():
        stripped = line.strip()
        if stripped:
            return _LIST_MARKER_RE.sub("", stripped, count=1).strip()
    return ""


def _legacy_identifier(product: Product, spec: ArtifactSpec | None) -> str:
    """The declared legacy identity: ``## ID`` first, then ``spec.id_field``."""
    explicit = _first_value(product.sections.get(_ID_SECTION))
    if explicit:
        return explicit
    if spec is not None and spec.id_field:
        declared = _first_value(product.sections.get(spec.id_field))
        if declared:
            return declared
    return ""


def _candidate_identifiers(product: Product, spec: ArtifactSpec | None, path: str) -> Iterator[str]:
    """Yield every identity candidate in precedence order (may include blanks).

    The single source of truth for the precedence chain: the canonical
    frontmatter id (already uppercase-normalised by the frontmatter parser),
    then the declared legacy id, then the filename-stem prefix (only when one
    matches), then the whole stem. Blanks are yielded as-is; the callers decide
    whether to skip them.
    """
    if product.metadata is not None and product.metadata.id:
        yield product.metadata.id
    yield _legacy_identifier(product, spec)
    stem = Path(path).stem
    prefix = _ID_PREFIX_RE.match(stem)
    if prefix:
        yield prefix.group(0)
    yield stem


def artifact_identifier(product: Product, spec: ArtifactSpec | None, path: str) -> str:
    """The single canonical identifier for the artifact at ``path``.

    The first non-blank candidate in the precedence chain wins (see
    :func:`_candidate_identifiers`); an empty stem with nothing else declared
    falls through to that same empty stem. Conflicts between frontmatter and
    legacy identity are *not* resolved here — :func:`identity_conflict` detects
    them and validation reports them; this function answers only "which identity
    is canonical" (frontmatter wins).
    """
    for candidate in _candidate_identifiers(product, spec, path):
        if candidate:
            return candidate
    return Path(path).stem


def artifact_identifiers(product: Product, spec: ArtifactSpec | None, path: str) -> list[str]:
    """Every identifier this artifact answers to, canonical first, deduped.

    The canonical identifier leads (the value :func:`artifact_identifier`
    returns); the declared legacy id, filename prefix, and whole stem follow as
    migration aliases. Reference resolution indexes all of them so an existing
    human-readable reference (e.g. ``ADR-015``) keeps resolving after an artifact
    adopts a canonical frontmatter id. Duplicates are dropped case-insensitively,
    and duplicate-identity detection elsewhere uses only the canonical (first)
    value, so an alias never manufactures a duplicate on its own.
    """
    ids: list[str] = []
    seen: set[str] = set()
    for candidate in _candidate_identifiers(product, spec, path):
        folded = candidate.casefold()
        if candidate and folded not in seen:
            ids.append(candidate)
            seen.add(folded)
    return ids


def identity_conflict(product: Product, spec: ArtifactSpec | None) -> tuple[str, str] | None:
    """Detect a frontmatter id that disagrees with a declared legacy id.

    Returns ``(frontmatter_id, legacy_id)`` when both are declared and differ
    (compared case-insensitively — matching values are accepted so an artifact
    can carry both during migration), otherwise None. Filename-derived identity
    is a fallback, not a declaration, so it never conflicts.
    """
    if product.metadata is None or not product.metadata.id:
        return None
    legacy = _legacy_identifier(product, spec)
    if not legacy:
        return None
    if legacy.strip().upper() == product.metadata.id:
        return None
    return (product.metadata.id, legacy)
