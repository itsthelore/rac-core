"""Artifact type definitions — the shared schema source for RAC.

An *artifact* is a structured kind of knowledge (a Requirement, a Decision, ...)
recognized by the sections it contains. This module owns those definitions and
nothing else: `rac inspect` (v0.4) *consumes* them, and future capabilities
(`improve`, artifact-aware `validate`, `normalize`) will import the same specs so
there is a single source of truth.

Section names are normalized (stripped + casefolded) for matching; ``display``
holds the human-facing label.

v0.4 defines only the two artifact types that have a concrete schema today:
Requirement (RAC's own format / validator) and Decision (the ADR format used in
this repository). Roadmap, Prompt, and Meeting are intentionally deferred until
their schemas are formalized — see planning/roadmap/.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ArtifactSpec:
    """The expected structure of one artifact type."""

    name: str  # canonical key, e.g. "requirement"
    display: str  # human label, e.g. "Requirement"
    required: tuple[str, ...]  # normalized section names that define the type
    recommended: tuple[str, ...] = ()  # expected-but-optional sections
    # Synonyms: alternate normalized headings that map onto a canonical section
    # name (e.g. "success criteria" -> "success metrics"). Applied before
    # matching, so synonyms contribute to confidence. Matching is deterministic
    # (dict lookup) and case-insensitive (headings are normalized first).
    synonyms: dict[str, str] = field(default_factory=dict)

    @property
    def expected(self) -> tuple[str, ...]:
        """All sections that belong to this artifact (required + recommended)."""
        return self.required + self.recommended


ARTIFACT_SPECS: tuple[ArtifactSpec, ...] = (
    ArtifactSpec(
        name="requirement",
        display="Requirement",
        required=("problem", "requirements"),
        recommended=("success metrics", "risks", "assumptions"),
        synonyms={
            "success criteria": "success metrics",
            "kpis": "success metrics",
            "kpi": "success metrics",
        },
    ),
    ArtifactSpec(
        name="decision",
        display="Decision",
        required=("context", "decision", "consequences"),
        recommended=("status", "alternatives considered"),
        synonyms={
            "alternatives": "alternatives considered",
            "options considered": "alternatives considered",
        },
    ),
)
