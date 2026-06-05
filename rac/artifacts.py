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
    # Truly optional sections: recognized and extracted, but never scored and
    # never reported as "missing" (e.g. a Decision's "supersedes" reference).
    optional: tuple[str, ...] = ()
    # Constrained metadata fields: {normalized section name -> allowed values}.
    # A value present in one of these sections that is not in its allowed set is
    # a validation error; a missing section is not (metadata stays optional).
    metadata: dict[str, tuple[str, ...]] = field(default_factory=dict)
    # Short authoring hints per normalized section name, surfaced by `rac improve
    # --template` as guidance comments. Optional; sections without a hint render
    # without one.
    descriptions: dict[str, str] = field(default_factory=dict)
    # Synonyms: alternate normalized headings that map onto a canonical section
    # name (e.g. "success criteria" -> "success metrics"). Applied before
    # matching, so synonyms contribute to confidence. Matching is deterministic
    # (dict lookup) and case-insensitive (headings are normalized first).
    synonyms: dict[str, str] = field(default_factory=dict)

    @property
    def expected(self) -> tuple[str, ...]:
        """Sections that count toward fit (required + recommended).

        ``optional`` sections are deliberately excluded — they are extracted but
        never scored, so they never show up as "missing".
        """
        return self.required + self.recommended


ARTIFACT_SPECS: tuple[ArtifactSpec, ...] = (
    ArtifactSpec(
        name="requirement",
        display="Requirement",
        required=("problem", "requirements"),
        recommended=("success metrics", "risks", "assumptions"),
        descriptions={
            "problem": "The user or business problem this addresses",
            "requirements": "Numbered requirement statements, e.g. [REQ-001] ...",
            "success metrics": "How success will be measured",
            "risks": "Potential implementation, delivery, or adoption risks",
            "assumptions": "Assumptions this artifact depends on",
        },
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
        recommended=("status", "category", "alternatives considered"),
        optional=("supersedes",),
        metadata={
            "status": ("Proposed", "Accepted", "Superseded", "Deprecated"),
            "category": ("Architecture", "Product", "Process", "Technical", "Other"),
        },
        synonyms={
            "alternatives": "alternatives considered",
            "options considered": "alternatives considered",
        },
    ),
)


def spec_for(name: str) -> ArtifactSpec | None:
    """Return the :class:`ArtifactSpec` with canonical ``name``, or None."""
    for spec in ARTIFACT_SPECS:
        if spec.name == name:
            return spec
    return None
