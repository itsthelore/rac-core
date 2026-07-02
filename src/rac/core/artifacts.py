"""The artifact schema — RAC's single source of truth for artifact structure.

Every artifact type (Requirement, Decision, Roadmap, Prompt, Design) is described
once here as an :class:`ArtifactSpec`: the sections that define it, the sections
that are merely encouraged, the constrained metadata fields, and the authoring
guidance. Classification, validation, the ``rac schema`` reference, starter
templates, ``rac improve``, statistics, and the relationship layer all read these
specs rather than hard-coding any type's shape. Add a type or move a section here
and every consumer follows.

Two conventions the rest of the codebase depends on:

* Section names are stored *normalized* — lowercase, single-spaced (``"success
  metrics"``, ``"user need"``, ``"alternatives considered"``). Human-facing casing
  is produced downstream with :meth:`str.title`; it is never stored.
* Ordering is a compatibility contract. Section tuples grow append-only (ADR-007),
  and the relationship (``related *``) sections are kept in lockstep with
  ``relationship_types.REGISTRY`` and ``services.relationships`` — the
  schema-agreement gate fails loudly if they drift.

Meeting has no schema yet; it is deliberately deferred until its structure is
settled (see ``rac/roadmaps/``).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ArtifactSpec:
    """The declared structure of one artifact type.

    Immutable: the specs are process-wide shared data, so nothing may mutate one
    after construction.
    """

    name: str
    """Canonical lowercase key, e.g. ``"requirement"``. The identity every consumer
    keys on."""

    display: str
    """Human label, e.g. ``"Requirement"``."""

    required: tuple[str, ...]
    """Sections that define the type. Their presence drives classification and
    their absence is a validation error."""

    recommended: tuple[str, ...] = ()
    """Expected-but-optional sections. They count toward classification fit (at
    half weight) but are only a warning when missing, never an error."""

    optional: tuple[str, ...] = ()
    """Recognized and extracted, but never scored, never templated, and never
    reported as missing — the mechanism relationship sections ride on."""

    metadata: dict[str, tuple[str, ...]] = field(default_factory=dict)
    """Constrained fields: ``{normalized section -> allowed values}``. A present
    value outside its allowed set is an error; an absent section is not (metadata
    stays optional)."""

    retired_status: tuple[str, ...] = ()
    """The subset of ``metadata["status"]`` marking a retired artifact (ADR-051).
    The one declarative source the status-consistency rule reads to decide a
    target is no longer live; empty when the type declares no status enum. The
    subset invariant is gate-enforced."""

    descriptions: dict[str, str] = field(default_factory=dict)
    """One-line section descriptions surfaced by ``rac schema``. These strings are
    golden-pinned."""

    guidance: dict[str, tuple[str, ...]] = field(default_factory=dict)
    """Prompting questions per section, rendered by ``rac improve`` and ``rac
    schema``. Informational only: classification, validation, and statistics must
    never read it. A type earns improve support by carrying guidance for every
    ``expected`` section."""

    synonyms: dict[str, str] = field(default_factory=dict)
    """Alternate normalized headings mapped onto a canonical section, applied
    before matching so a synonym contributes to classification fit. Scoped to this
    spec only (see ``classification._mapped``): a roadmap's ``"success metrics" ->
    "success measures"`` never touches the requirement's canonical ``"success
    metrics"``."""

    id_field: str | None = None
    """Forward hook (unused by design). No spec sets it today; ``identity``'s
    legacy-identifier path reads ``spec.id_field`` and falls back to the filename
    stem when it is ``None``. Kept because removing it changes the dataclass
    shape."""

    @property
    def expected(self) -> tuple[str, ...]:
        """Sections that count toward classification fit: required then recommended.

        ``optional`` is excluded on purpose — those sections are extracted but never
        scored, so they can never register as "missing".
        """
        return self.required + self.recommended


# --- Relationship sections ---------------------------------------------------
#
# Relationship sections (``related decisions``, ``supersedes``, ``verified by``, …)
# are explicit Markdown headings that point at other artifacts (ADR-016). They ride
# the ``optional`` mechanism: extracted and counted, but never scored, templated, or
# reported as missing. This module owns only their human-facing descriptions; the
# canonical vocabulary and edge semantics live in ``relationship_types`` and
# ``services.relationships``, and the three must move together (the schema-agreement
# gate enforces this).
#
# Deliberately no ``guidance`` here: guidance gates ``rac improve`` and templates,
# and relationships must stay out of both.
RELATIONSHIP_DESCRIPTIONS: dict[str, str] = {
    "related requirements": "Requirement artifacts this artifact references",
    "related decisions": "Decision artifacts this artifact references",
    "related roadmaps": "Roadmap artifacts this artifact references",
    "related prompts": "Prompt artifacts this artifact references",
    "related designs": "Design artifacts this artifact references",
    "supersedes": "The artifact this one supersedes",
    "related tickets": "External tickets this artifact traces to; provider set by"
    " .rac/config.yaml ticketing.provider (ADR-087)",
    "verified by": "External tests or traces that verify this capability; targets"
    " are file paths, not in-corpus artifacts (ADR-096)",
}


def _relationship_descriptions(*sections: str) -> dict[str, str]:
    """Select relationship descriptions for ``sections``, preserving their order."""
    return {section: RELATIONSHIP_DESCRIPTIONS[section] for section in sections}


# The registry. Order is contract: ``ARTIFACT_SPECS`` order is the tie-break order
# for classification and the display order for ``rac schema --list``.
ARTIFACT_SPECS: tuple[ArtifactSpec, ...] = (
    ArtifactSpec(
        name="requirement",
        display="Requirement",
        required=("problem", "requirements"),
        recommended=("success metrics", "risks", "assumptions"),
        # Relationship sections are append-only (ADR-007); ``related requirements``
        # (a requirement pointing at its dependencies) landed after the rest, so it
        # sits late in the tuple rather than beside the other ``related *`` kinds.
        optional=(
            "related decisions",
            "related roadmaps",
            "related prompts",
            "related designs",
            "related requirements",
            "related tickets",
            "verified by",
        ),
        # Status is a knowledge lifecycle (current vs replaced), never delivery
        # state (ADR-017/ADR-051).
        metadata={"status": ("Proposed", "Accepted", "Superseded", "Deprecated")},
        retired_status=("Superseded", "Deprecated"),
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
                "related tickets",
                "verified by",
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
        # ``supersedes`` predates the general relationship sections and stays first;
        # inspect also surfaces it as a top-level scalar.
        optional=(
            "supersedes",
            "related requirements",
            "related roadmaps",
            "related designs",
            "related decisions",
            "related tickets",
        ),
        metadata={
            "status": ("Proposed", "Accepted", "Superseded", "Deprecated"),
            "category": ("Architecture", "Product", "Process", "Technical", "Other"),
        },
        retired_status=("Superseded", "Deprecated"),
        # Decisions describe their canonical sections in prose, not here; only the
        # relationship sections carry a schema description.
        descriptions=_relationship_descriptions(
            "supersedes",
            "related requirements",
            "related roadmaps",
            "related designs",
            "related decisions",
            "related tickets",
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
            "status": ("Is this Proposed, Accepted, Superseded, or Deprecated?",),
            "category": ("Which area: Architecture, Product, Process, Technical, or Other?",),
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
        optional=(
            "related decisions",
            "related requirements",
            "related prompts",
            "related designs",
            "related roadmaps",
            "related tickets",
        ),
        # ADR-051/ADR-061: Planned is live, Achieved is the live terminal state
        # (delivered intent — still valid to reference, so not retired), while
        # Superseded/Abandoned mark replaced or dropped intent. All four are
        # knowledge states, not per-milestone work tracking (ADR-017).
        metadata={"status": ("Planned", "Achieved", "Superseded", "Abandoned")},
        retired_status=("Superseded", "Abandoned"),
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
                "related roadmaps",
                "related tickets",
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
            "assumptions": ("What must be true for this roadmap to remain valid?",),
            "risks": ("What could prevent these outcomes from being achieved?",),
        },
        synonyms={
            "success metrics": "success measures",
        },
    ),
    ArtifactSpec(
        name="prompt",
        display="Prompt",
        required=("objective", "input", "instructions", "output"),
        recommended=("constraints", "examples", "evaluation"),
        optional=(
            "related requirements",
            "related decisions",
            "related roadmaps",
            "related designs",
            "related tickets",
        ),
        # ADR-051: Active is live, Deprecated is retired.
        metadata={"status": ("Active", "Deprecated")},
        retired_status=("Deprecated",),
        descriptions={
            "objective": "What this prompt is intended to achieve",
            "input": "The information, context, or source material the prompt expects",
            "instructions": "The steps, rules, or approach the model should follow",
            "output": "The expected response format or result",
            "constraints": "Boundaries or restrictions the response must respect",
            "examples": "Example inputs and outputs that clarify intended behavior",
            "evaluation": "Human criteria for judging whether a response is good",
            **_relationship_descriptions(
                "related requirements",
                "related decisions",
                "related roadmaps",
                "related designs",
                "related tickets",
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
            "examples": ("What examples would make the desired behavior clearer?",),
            "evaluation": (
                "What makes a good response?",
                "How can the user tell whether the prompt worked?",
            ),
        },
        # Scoped synonyms: these normalize headings only when scoring against the
        # Prompt spec. They aid classification and improve, but validation still
        # expects the canonical headings.
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
        optional=(
            "related requirements",
            "related decisions",
            "related roadmaps",
            "related prompts",
            "related tickets",
        ),
        # ADR-051: shares the requirement/decision status spine.
        metadata={"status": ("Proposed", "Accepted", "Superseded", "Deprecated")},
        retired_status=("Superseded", "Deprecated"),
        descriptions={
            "context": "The product area, situation, or experience this design addresses",
            "user need": "The user, audience, task, pain point, or goal this design supports",
            "design": "The proposed experience, interaction, layout, flow, or behavior",
            "constraints": "Technical, product, accessibility, platform, or implementation"
            " constraints",
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
                "related tickets",
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
    """Return the :class:`ArtifactSpec` whose ``name`` matches, or ``None``.

    A linear scan over five specs; ``None`` for an unknown or empty ``name``.
    """
    for spec in ARTIFACT_SPECS:
        if spec.name == name:
            return spec
    return None
