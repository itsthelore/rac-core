"""Artifact type definitions — the shared schema source for RAC.

An *artifact* is a structured kind of knowledge (a Requirement, a Decision, ...)
recognized by the sections it contains. This module owns those definitions and
nothing else: `rac inspect` (v0.4) *consumes* them, and future capabilities
(`improve`, artifact-aware `validate`, `normalize`) will import the same specs so
there is a single source of truth.

Section names are normalized (stripped + casefolded) for matching; ``display``
holds the human-facing label.

Three artifact types have a concrete schema today: Requirement (RAC's own format /
validator), Decision (the ADR format used in this repository), and Roadmap
(outcome- and initiative-focused knowledge, added in v0.6.0). Prompt and Meeting
are intentionally deferred until their schemas are formalized — see planning/roadmap/.
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
    # Prompting questions per normalized section name. This is informational
    # metadata only: improve renders it, but classification, validation, and
    # statistics must not use it.
    guidance: dict[str, tuple[str, ...]] = field(default_factory=dict)
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
        guidance={
            "problem": (
                "What user or business problem does this solve?",
                "Who is affected, and why does it matter now?",
            ),
            "requirements": (
                "What must the system do?",
                "Is each one a testable [REQ-NNN] statement?",
            ),
            "success metrics": (
                "How will you know this succeeded?",
                "What measurable target indicates success?",
            ),
            "risks": (
                "What could prevent successful delivery?",
                "What dependencies or unknowns exist?",
            ),
            "assumptions": (
                "What are you assuming to be true?",
                "What would change the approach if it turned out false?",
            ),
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
        guidance={
            "context": (
                "What forces, constraints, or problems led to this decision?",
                "What background does a reader need?",
            ),
            "decision": (
                "What was decided?",
                "State it as a clear, active choice.",
            ),
            "consequences": (
                "What becomes easier or harder as a result?",
                "What trade-offs are you accepting?",
            ),
            "status": (
                "Is this Proposed, Accepted, Superseded, or Deprecated?",
            ),
            "category": (
                "Which area: Architecture, Product, Process, Technical, or Other?",
            ),
            "alternatives considered": (
                "What other options were weighed?",
                "Why were they not chosen?",
            ),
        },
        synonyms={
            "alternatives": "alternatives considered",
            "options considered": "alternatives considered",
        },
    ),
    ArtifactSpec(
        name="roadmap",
        display="Roadmap",
        required=("outcomes", "initiatives"),
        recommended=("success measures", "assumptions", "risks"),
        # Relationship sections are recognized but never scored or templated; they
        # exist so v0.6.0 roadmaps can reference Decisions/Requirements as text
        # without RAC analyzing those links (relationship analysis is v0.7.x).
        optional=("related decisions", "related requirements"),
        descriptions={
            "outcomes": "The user, business, or operational outcomes this roadmap pursues",
            "initiatives": "The major bodies of work that support those outcomes",
            "success measures": "How progress toward the outcomes will be measured",
            "assumptions": "Conditions that must hold for this roadmap to stay valid",
            "risks": "What could prevent the outcomes from being achieved",
        },
        guidance={
            "outcomes": (
                "What user, business, or operational outcomes matter?",
                "Why are these outcomes important now?",
            ),
            "initiatives": (
                "What major bodies of work support these outcomes?",
                "How does each initiative connect to an outcome?",
            ),
            "success measures": (
                "How will the team know the roadmap is succeeding?",
            ),
            "assumptions": (
                "What must be true for this roadmap to remain valid?",
            ),
            "risks": (
                "What could prevent these outcomes from being achieved?",
            ),
        },
        # Artifact-scoped: this only normalizes "success metrics" when scoring a
        # document against the Roadmap spec (see rac.classification._mapped), so it
        # never affects the Requirement spec's canonical "success metrics" section.
        synonyms={
            "success metrics": "success measures",
        },
    ),
)


def spec_for(name: str) -> ArtifactSpec | None:
    """Return the :class:`ArtifactSpec` with canonical ``name``, or None."""
    for spec in ARTIFACT_SPECS:
        if spec.name == name:
            return spec
    return None
