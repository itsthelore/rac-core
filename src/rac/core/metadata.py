"""Canonical artifact metadata — the machine-operational envelope (ADR-025).

Downstream code reads one normalized abstraction (``product.metadata.id``,
``.type``, ``.schema_version``, ``.relationships``) and never has to know
whether those values arrived as YAML frontmatter or, mid-migration, from a
legacy source. ``provenance`` records that origin because conflict detection
and the migrate tooling branch on it.

Frontmatter owns every field here. Product reasoning — status, context,
decisions, acceptance criteria — stays in Markdown sections and must never be
promoted into this model (ADR-025).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Where a metadata value was discovered. Only ``PROVENANCE_FRONTMATTER`` is
# produced in this package (it is the default); the legacy/filename markers
# belong to the migrate service's contract but are declared here so the SDK
# shares one provenance vocabulary.
PROVENANCE_FRONTMATTER = "frontmatter"
PROVENANCE_LEGACY_SECTION = "legacy-section"
PROVENANCE_FILENAME = "filename"

# Frontmatter schema versions this build understands — a tuple so membership
# tests stay cheap and the value cannot be mutated.
SUPPORTED_SCHEMA_VERSIONS = (1,)

# Canonical opaque artifact ID (ADR-026): a repository key — an uppercase
# leading letter plus 1-9 more ``[A-Z0-9]`` (2-10 chars total) — a hyphen, then
# a 12-char Crockford base32 suffix that omits I/L/O/U to stay unambiguous. The
# pattern is fully anchored with no nested quantifiers, so it matches in linear
# time even on adversarial input (test_robustness pins this).
ID_RE = re.compile(r"^[A-Z][A-Z0-9]{1,9}-[0-9A-HJKMNP-TV-Z]{12}$")


def normalize_id(value: str) -> str:
    """Return the canonical (trimmed, uppercase) form of an artifact ID."""
    return value.strip().upper()


def is_valid_id(value: str) -> bool:
    """True when ``value`` is a syntactically canonical opaque artifact ID."""
    return bool(ID_RE.match(normalize_id(value)))


@dataclass
class ArtifactMetadata:
    """Normalized machine-operational metadata for one artifact (ADR-025).

    Field order and defaults are contract: ``schema_version`` is the only
    required field and must stay first. The field set minus ``provenance`` must
    equal ``frontmatter._SUPPORTED_FIELDS`` — ``test_envelope_fields_agree``
    fails loudly if the two drift.

    ``relationships`` is parsed and shape-validated here but consumed by
    relationship analysis separately. ``tags`` is the OKF-reserved descriptive
    field (ADR-025 reserved it, ADR-050 adopts it): optional and additive, never
    a source of product reasoning. Timestamps are deliberately absent — recency
    is git-derived, not stored in frontmatter (ADR-045).
    """

    schema_version: int
    id: str | None = None
    type: str | None = None
    relationships: dict[str, list[str]] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    provenance: str = PROVENANCE_FRONTMATTER
