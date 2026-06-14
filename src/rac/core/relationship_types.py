"""Relationship-type registry — the edge schema for Layer-3 graph integrity (ADR-055).

Edge *legality by source type* (domain) stays where v0.14.0 put it:
``ArtifactSpec.optional`` (the sections a type may declare). This registry adds
the *graph* properties of each relationship kind — target type (``range``),
directionality, acyclicity, and whether the edge forbids a retired target — so
the Layer-3 checks (range, acyclicity, status-consistency) read one declarative
source instead of hard-coded special cases.

The registry is **code-defined**. Custom, repo-declared relationship types are
deferred (ADR-052 defers the analogous custom artifact types); the built-in
vocabulary is ``rac.services.relationships.RELATIONSHIP_SECTIONS`` keyed in its
snake_case form (``related_decisions``, ``supersedes``), matching the keys
``extract_relationships_full`` produces.

``range``, ``acyclic``, and ``forbids_target_status`` are enforced today.
``symmetric``/``inverse``/``cardinality`` are declared for display and forward
compatibility (a viewer can label inverse edges) and are not yet enforced.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EdgeSpec:
    """The graph schema of one relationship kind."""

    name: str  # snake_case edge key, e.g. "related_decisions", "supersedes"
    range: tuple[str, ...]  # artifact types a target may be (enforced)
    directional: bool = False  # supersedes is directional; related_* are not
    acyclic: bool = False  # cycles are illegal for this kind (enforced)
    symmetric: bool = True  # an undirected "relates-to" link (declared)
    inverse: str | None = None  # inverse edge label (declared, display only)
    # When True, a live source must not point at a retired target via this edge
    # (the status-consistency rule). supersedes sets False — the replacing
    # decision legitimately points at the one it retires.
    forbids_target_status: bool = True
    cardinality: str = "many"  # declared; not yet enforced


def _related(target_type: str) -> EdgeSpec:
    """An undirected ``related_<type>s`` edge whose range is ``target_type``."""
    name = f"related_{target_type}s"
    return EdgeSpec(name=name, range=(target_type,), inverse=name)


# Built-in relationship kinds. The five ``related_*`` edges are undirected links
# whose target must be of the named type; ``supersedes`` is the one directional,
# acyclic, decision→decision edge, and the only one exempt from the retired-target
# rule (forbids_target_status=False).
REGISTRY: dict[str, EdgeSpec] = {
    spec.name: spec
    for spec in (
        _related("requirement"),
        _related("decision"),
        _related("roadmap"),
        _related("prompt"),
        _related("design"),
        EdgeSpec(
            name="supersedes",
            range=("decision",),
            directional=True,
            acyclic=True,
            symmetric=False,
            inverse="superseded-by",
            forbids_target_status=False,
        ),
    )
}


def edge_spec(name: str) -> EdgeSpec | None:
    """The :class:`EdgeSpec` for a snake_case relationship kind, or None."""
    return REGISTRY.get(name)
