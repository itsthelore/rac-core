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

The concrete spec data is not hardcoded here. It is loaded at import time from the
bundled, language-neutral registry ``rac/spec/artifact-specs.json`` (ADR-063
Guard 1): the *same* file the Rust engine embeds, so the two engines cannot drift.
``ARTIFACT_SPECS`` and ``RELATIONSHIP_DESCRIPTIONS`` are reconstructed from that
file into the exact dataclasses and ordering the engine has always used — the load
is behavior-neutral (a golden test pins the reconstruction field-for-field).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from importlib import resources


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
    # Lifecycle status values that mark an artifact as retired (ADR-051): a subset
    # of ``metadata["status"]``. The single, declarative source of truth the
    # status-consistency rule reads to decide a target is no longer live. Empty
    # when the type declares no status enum.
    retired_status: tuple[str, ...] = ()
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
    # Validation-safe starter body per normalized section name, rendered by
    # ``rac schema --template`` / ``rac improve --template``. Spec-driven so
    # template rendering stays data-driven with no per-type branches. Metadata
    # sections (e.g. a Decision's ``status``/``category``) are intentionally
    # omitted — their starter value derives from the allowed metadata values, not
    # from this map. Sections absent from this map fall back to a generic
    # ``TODO: describe <section>.`` line at render time.
    starter_bodies: dict[str, str] = field(default_factory=dict)

    @property
    def expected(self) -> tuple[str, ...]:
        """Sections that count toward fit (required + recommended).

        ``optional`` sections are deliberately excluded — they are extracted but
        never scored, so they never show up as "missing".
        """
        return self.required + self.recommended


# --- Registry loading (ADR-063 Guard 1) -------------------------------------
#
# ``ARTIFACT_SPECS`` and ``RELATIONSHIP_DESCRIPTIONS`` are the deterministic
# contract that classification, validation, statistics, and templates read. Their
# data lives in the bundled ``rac/spec/artifact-specs.json`` — the one shared,
# language-neutral file the Rust engine embeds too. This module reconstructs the
# frozen dataclasses (and their declared field / map-key ordering) from that file.
#
# Order is load-bearing: the spec tuple order is the classification tie-break and
# ``available_schemas()`` order, and every map preserves its JSON insertion order
# (Python dicts are ordered, and ``json.loads`` keeps object order) so iteration
# matches what the engine has always produced.


def _spec_from_dict(d: dict) -> ArtifactSpec:
    """Rebuild one :class:`ArtifactSpec` from its JSON object, preserving order."""
    return ArtifactSpec(
        name=d["name"],
        display=d["display"],
        required=tuple(d["required"]),
        recommended=tuple(d["recommended"]),
        optional=tuple(d["optional"]),
        metadata={k: tuple(v) for k, v in d["metadata"].items()},
        retired_status=tuple(d["retired_status"]),
        descriptions=dict(d["descriptions"]),
        guidance={k: tuple(v) for k, v in d["guidance"].items()},
        synonyms=dict(d["synonyms"]),
        id_field=d["id_field"],
        starter_bodies=dict(d["starter_bodies"]),
    )


@lru_cache(maxsize=1)
def _registry() -> tuple[tuple[ArtifactSpec, ...], dict[str, str]]:
    """Load ``(ARTIFACT_SPECS, RELATIONSHIP_DESCRIPTIONS)`` from the bundled file."""
    raw = resources.files("rac.spec").joinpath("artifact-specs.json").read_text(encoding="utf-8")
    payload = json.loads(raw)
    specs = tuple(_spec_from_dict(s) for s in payload["artifact_specs"])
    relationship_descriptions = dict(payload["relationship_descriptions"])
    return specs, relationship_descriptions


# One-line descriptions for every relationship section, surfaced by `rac schema`.
# Relationship sections deliberately carry no ``guidance`` — guidance gates
# `rac improve`, and relationships must stay out of improve and templates. The
# relationship-section vocabulary and its canonical ordering live in
# :mod:`rac.services.relationships`; this map holds only the human-facing
# descriptions those sections render, loaded from the shared registry file.
RELATIONSHIP_DESCRIPTIONS: dict[str, str] = _registry()[1]


# The ordered artifact-type registry: requirement, decision, roadmap, prompt,
# design. This tuple order is load-bearing (classification tie-break, registry
# iteration, ``available_schemas()``).
ARTIFACT_SPECS: tuple[ArtifactSpec, ...] = _registry()[0]


def spec_for(name: str) -> ArtifactSpec | None:
    """Return the :class:`ArtifactSpec` with canonical ``name``, or None."""
    for spec in ARTIFACT_SPECS:
        if spec.name == name:
            return spec
    return None
