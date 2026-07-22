"""Canonical artifact metadata — the machine-operational envelope (ADR-025).

``ArtifactMetadata`` is the normalized metadata abstraction consumers read
(``product.metadata.id``, ``.type``, ``.schema_version``, ``.relationships``)
without knowing whether the values came from YAML frontmatter or, during
migration, from legacy sources. ``provenance`` records where the identity
came from, which conflict detection and migration tooling require.

Frontmatter is the canonical location for every field here; product reasoning
(status, context, decisions, acceptance criteria) stays in Markdown sections
and must never migrate into this model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Where a metadata value was discovered (Initiative 3: provenance).
PROVENANCE_FRONTMATTER = "frontmatter"
PROVENANCE_LEGACY_SECTION = "legacy-section"
PROVENANCE_FILENAME = "filename"

# Frontmatter schema versions this build of RAC understands.
SUPPORTED_SCHEMA_VERSIONS = (1,)

# Canonical opaque artifact ID (ADR-026, v0.7.11 implementation contract):
# repository key (uppercase, leading letter, 2-10 chars) + 12-char Crockford
# base32 suffix (no I/L/O/U). Matched case-insensitively; normalized uppercase.
ID_RE = re.compile(r"^[A-Z][A-Z0-9]{1,9}-[0-9A-HJKMNP-TV-Z]{12}$")


def normalize_id(value: str) -> str:
    """Canonical (uppercase) form of an artifact ID."""
    return value.strip().upper()


def is_valid_id(value: str) -> bool:
    """True when ``value`` is a syntactically canonical opaque artifact ID."""
    return bool(ID_RE.match(normalize_id(value)))


@dataclass
class ArtifactMetadata:
    """Normalized machine-operational metadata for one artifact (ADR-025).

    ``relationships`` is reserved in v0.7.11: parsed and validated as a
    mapping of relationship kind to ID lists, but not yet consumed by
    relationship analysis (migration is staged separately).
    """

    schema_version: int
    id: str | None = None
    type: str | None = None
    relationships: dict[str, list[str]] = field(default_factory=dict)
    # OKF-reserved descriptive labels (ADR-050): optional, additive, never a
    # source of product reasoning. ADR-025 reserved ``tags``. Timestamps stay out
    # of frontmatter — recency is git-derived (ADR-045).
    tags: list[str] = field(default_factory=list)
    provenance: str = PROVENANCE_FRONTMATTER
