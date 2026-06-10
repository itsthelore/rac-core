"""Artifact type definitions — the shared schema source for RAC.

An *artifact* is a structured kind of knowledge (a Requirement, a Decision, ...)
recognized by the sections it contains. This module owns those definitions and
nothing else: `rac inspect` (v0.4) *consumes* them, and future capabilities
(`improve`, artifact-aware `validate`, `normalize`) will import the same specs so
there is a single source of truth.

Section names are normalized (stripped + casefolded) for matching; ``display``
holds the human-facing label.

Five artifact types have a concrete schema today: Requirement (RAC's own format /
validator), Decision (the ADR format used in this repository), Roadmap (outcome- and
initiative-focused knowledge, added in v0.6.0), and Prompt (structured AI prompts as
knowledge, added in v0.6.2), and Design (UX and interaction knowledge, added in
v0.6.3). Meeting is intentionally deferred until its schema is formalized — see
rac/roadmaps/.
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
    # Canonical-identifier section (v0.7.2 relationship validation): the normalized
    # section name whose value is this artifact type's identifier, consulted by
    # ``rac.core.identity.artifact_identifier`` before falling back to the filename
    # stem. A forward hook — no spec sets it today; relationship resolution works
    # from the ``## ID`` section and filename stem until a type opts in.
    id_field: str | None = None

    @property
    def expected(self) -> tuple[str, ...]:
        """Sections that count toward fit (required + recommended).

        ``optional`` sections are deliberately excluded — they are extracted but
        never scored, so they never show up as "missing".
        """
        return self.required + self.recommended


# --- Relationship metadata (v0.7.0) -----------------------------------------
#
# Relationships are explicit Markdown sections that reference other artifacts
# (ADR-016). They ride the existing ``optional`` mechanism: recognized and
# extracted, but never scored, never templated, never reported as missing
# (REQ-002). v0.7.0 treats them as metadata only — RAC extracts and counts the
# references but does not resolve, validate, or graph them.
#
# The relationship-section vocabulary and its canonical ordering live in
# :mod:`rac.services.relationships` (the module that owns relationship logic). This module
# only owns the human-facing ``descriptions`` for those sections, which the specs
# below consume.

# One-line descriptions for every relationship section, surfaced by `rac schema`.
# Relationship sections deliberately carry no ``guidance`` — guidance gates
# `rac improve`, and relationships must stay out of improve and templates.
RELATIONSHIP_DESCRIPTIONS: dict[str, str] = {
    "related requirements": "Requirement artifacts this artifact references",
    "related decisions": "Decision artifacts this artifact references",
    "related roadmaps": "Roadmap artifacts this artifact references",
    "related prompts": "Prompt artifacts this artifact references",
    "related designs": "Design artifacts this artifact references",
    "supersedes": "The artifact this one supersedes",
}


def _relationship_descriptions(*sections: str) -> dict[str, str]:
    """Descriptions for the given relationship ``sections`` (declaration order)."""
    return {section: RELATIONSHIP_DESCRIPTIONS[section] for section in sections}


ARTIFACT_SPECS: tuple[ArtifactSpec, ...] = (
    ArtifactSpec(
        name="requirement",
        display="Requirement",
        required=("problem", "requirements"),
        recommended=("success metrics", "risks", "assumptions"),
        # Relationship sections (v0.7.0): metadata only — extracted and counted,
        # never scored or templated (REQ-003). ``related requirements`` lets a
        # requirement reference the requirements it depends on; appended last
        # because section order is append-only (ADR-007).
        optional=(
            "related decisions",
            "related roadmaps",
            "related prompts",
            "related designs",
            "related requirements",
        ),
        descriptions={
            "problem": "The user or business problem this addresses",
            "requirements": "Numbered requirement statements, e.g. [REQ-001] ...",
            "success metrics": "How success will be measured",
            "risks": "Potential implementation, delivery, or adoption risks",
            "assumptions": "Assumptions this artifact depends on",
            **_relationship_descriptions(
                "related decisions",
                "related roadmaps",
                "related prompts",
                "related designs",
                "related requirements",
            ),
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
        # ``supersedes`` stays first (the original v0.4.2 entry). The remaining
        # relationship sections are added in v0.7.0 (REQ-004). All are metadata
        # only; ``supersedes`` is also surfaced as a top-level scalar by inspect.
        optional=(
            "supersedes",
            "related requirements",
            "related roadmaps",
            "related designs",
        ),
        metadata={
            "status": ("Proposed", "Accepted", "Superseded", "Deprecated"),
            "category": ("Architecture", "Product", "Process", "Technical", "Other"),
        },
        descriptions=_relationship_descriptions(
            "supersedes",
            "related requirements",
            "related roadmaps",
            "related designs",
        ),
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
        # let a roadmap reference Decisions/Requirements/Prompts/Designs as text.
        # The first two predate v0.7.0; ``related prompts``/``related designs`` are
        # added in v0.7.0 (REQ-005). Order is append-only (ADR-007).
        optional=(
            "related decisions",
            "related requirements",
            "related prompts",
            "related designs",
        ),
        descriptions={
            "outcomes": "The user, business, or operational outcomes this roadmap pursues",
            "initiatives": "The major bodies of work that support those outcomes",
            "success measures": "How progress toward the outcomes will be measured",
            "assumptions": "Conditions that must hold for this roadmap to stay valid",
            "risks": "What could prevent the outcomes from being achieved",
            **_relationship_descriptions(
                "related decisions",
                "related requirements",
                "related prompts",
                "related designs",
            ),
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
                "What observable signals would show progress?",
            ),
            "assumptions": (
                "What must be true for this roadmap to remain valid?",
            ),
            "risks": (
                "What could prevent these outcomes from being achieved?",
            ),
        },
        # Artifact-scoped: this only normalizes "success metrics" when scoring a
        # document against the Roadmap spec (see rac.core.classification._mapped), so it
        # never affects the Requirement spec's canonical "success metrics" section.
        synonyms={
            "success metrics": "success measures",
        },
    ),
    ArtifactSpec(
        name="prompt",
        display="Prompt",
        required=("objective", "input", "instructions", "output"),
        recommended=("constraints", "examples", "evaluation"),
        # Relationship sections are recognized but never scored or templated; they
        # let a Prompt reference other artifacts as text. ``related designs`` is
        # added in v0.7.0 (REQ-006); order is append-only (ADR-007).
        optional=(
            "related requirements",
            "related decisions",
            "related roadmaps",
            "related designs",
        ),
        descriptions={
            "objective": "What this prompt is intended to achieve",
            "input": "The information, context, or source material the prompt expects",
            "instructions": "The steps, rules, or approach the model should follow",
            "output": "The expected response format or result",
            "constraints": "Boundaries or restrictions the response must respect",
            "examples": "Example inputs and outputs that clarify intended behavior",
            # Human criteria for judging a response — not automated testing or scoring.
            "evaluation": "Human criteria for judging whether a response is good",
            **_relationship_descriptions(
                "related requirements",
                "related decisions",
                "related roadmaps",
                "related designs",
            ),
        },
        guidance={
            "objective": (
                "What task should this prompt help complete?",
                "What outcome should the model produce?",
            ),
            "input": (
                "What context or source material does the prompt require?",
                "What assumptions should the model make about the input?",
            ),
            "instructions": (
                "What should the model do first?",
                "What process should it follow?",
            ),
            "output": (
                "What should the output contain?",
                "Should the response be structured as bullets, JSON, Markdown, or prose?",
            ),
            "constraints": (
                "What should the model avoid?",
                "Are there tone, format, safety, or scope constraints?",
            ),
            "examples": (
                "What examples would make the desired behavior clearer?",
            ),
            "evaluation": (
                "What makes a good response?",
                "How can the user tell whether the prompt worked?",
            ),
        },
        # Artifact-scoped (see rac.core.classification._mapped): these only normalize
        # headings when scoring against the Prompt spec, so they never affect other
        # artifact types. They aid classification and improve (both synonym-aware);
        # validation still expects the canonical headings, like Decision/Roadmap.
        synonyms={
            "expected output": "output",
            "output specification": "output",
            "input specification": "input",
        },
    ),
    ArtifactSpec(
        name="design",
        display="Design",
        required=("context", "user need", "design", "constraints"),
        recommended=(
            "rationale",
            "alternatives",
            "accessibility",
            "style guidance",
            "open questions",
        ),
        # Relationship sections are recognized but never scored or templated; they
        # let a Design reference other artifacts as text without RAC analyzing
        # those links (relationship analysis is v0.7.x).
        optional=(
            "related requirements",
            "related decisions",
            "related roadmaps",
            "related prompts",
        ),
        descriptions={
            "context": "The product area, situation, or experience this design addresses",
            "user need": "The user, audience, task, pain point, or goal this design supports",
            "design": "The proposed experience, interaction, layout, flow, or behavior",
            "constraints": "Technical, product, accessibility, platform, or implementation constraints",
            "rationale": "Why this design approach was chosen",
            "alternatives": "Other approaches considered and why they were not chosen",
            "accessibility": "Accessibility needs and expectations for the design",
            "style guidance": "Visual, tone, layout, or interaction style guidance",
            "open questions": "Unresolved design questions to validate or decide later",
            **_relationship_descriptions(
                "related requirements",
                "related decisions",
                "related roadmaps",
                "related prompts",
            ),
        },
        guidance={
            "context": (
                "What situation, product area, or user experience does this design address?",
                "Why is this design needed now?",
            ),
            "user need": (
                "Who is the user or audience?",
                "What task, pain point, or goal does this design support?",
            ),
            "design": (
                "What is the proposed design?",
                "How should the experience work?",
            ),
            "constraints": (
                "What constraints shape this design?",
                "What must the design respect or avoid?",
            ),
            "rationale": (
                "Why is this the preferred approach?",
                "What trade-offs does this design make?",
            ),
            "alternatives": (
                "What other approaches were considered?",
                "Why were they not chosen?",
            ),
            "accessibility": (
                "What accessibility needs should this design support?",
                "Are there keyboard, contrast, readability, or screen-reader considerations?",
            ),
            "style guidance": (
                "What visual or interaction style should be followed?",
                "What patterns should remain consistent?",
            ),
            "open questions": (
                "What still needs to be decided?",
                "What should be validated or explored further?",
            ),
        },
    ),
)


def spec_for(name: str) -> ArtifactSpec | None:
    """Return the :class:`ArtifactSpec` with canonical ``name``, or None."""
    for spec in ARTIFACT_SPECS:
        if spec.name == name:
            return spec
    return None
