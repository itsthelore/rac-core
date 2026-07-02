"""Relationship-type registry -- the edge schema for Layer-3 graph integrity (ADR-055).

Which relationship sections a *source* type may declare (the edge domain) stays
in ``ArtifactSpec.optional``. This registry adds the complementary *graph*
properties of each relationship kind -- its target type (``range``),
directionality, acyclicity, and whether it forbids pointing at a retired target
-- so the Layer-3 checks (range, acyclicity, status-consistency) read one
declarative table instead of hard-coding each edge as a special case.

The registry is code-defined; repo-declared custom relationship types are
deferred (ADR-052 defers the analogous custom artifact types). Keys are the
snake_case edge names (``related_decisions``, ``supersedes``) that
``extract_relationships_full`` produces and that
``rac.services.relationships.RELATIONSHIP_SECTIONS`` mirrors.

Enforced today: ``range``, ``acyclic``, ``forbids_target_status``. The
``symmetric`` / ``inverse`` / ``cardinality`` fields are declared for display
and forward compatibility (a viewer can label the inverse edge) but are not yet
enforced.
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
    symmetric: bool = True  # an undirected "relates-to" link (declared only)
    inverse: str | None = None  # inverse edge label (declared, display only)
    # When True, a live source may not point at a retired target through this
    # edge (the status-consistency rule). ``supersedes`` sets False: the
    # replacing decision legitimately points at the decision it retires.
    forbids_target_status: bool = True
    cardinality: str = "many"  # declared; not yet enforced
    # External-reference family (ADR-087): the target is an external identifier
    # (a ticket key or URL) rather than an in-corpus artifact. External edges
    # skip range and referential-integrity resolution and are format-linted
    # instead; the graph export marks them external and unresolved.
    external: bool = False
    # For an external edge, whether its target lives in the repository's
    # configured ticketing *provider* (ADR-088), so the export can tag it with
    # that provider. ``related_tickets`` sets this; ``verified_by`` does not --
    # its targets are file paths, which have no provider.
    external_provider: bool = False


def _related(target_type: str) -> EdgeSpec:
    """Build the undirected ``related_<type>s`` edge whose range is ``target_type``."""
    name = f"related_{target_type}s"
    return EdgeSpec(name=name, range=(target_type,), inverse=name)


# The built-in relationship kinds, keyed by edge name.
#
# The five ``related_*`` edges are undirected links whose target must be of the
# named type. ``supersedes`` is the sole directional, acyclic decision->decision
# edge and the only one exempt from the retired-target rule. The two external
# edges (``related_tickets``, ``verified_by``) carry no artifact range.
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
        # One code-defined external-ticket edge (ADR-087): its target is a ticket
        # key or URL, never an in-corpus artifact, so it is format-linted against
        # the per-repo ticketing provider (ADR-088) rather than resolved.
        # Organisations standardise on a single ticketing system, so this is one
        # provider-configured edge, not a family of per-provider siblings.
        EdgeSpec(name="related_tickets", range=(), external=True, external_provider=True),
        # External-target verification edge (ADR-096): a capability (a
        # requirement, ADR-020) points at the external tests or traces that verify
        # it. Like a ticket it skips resolution, range, and status checks, but its
        # target is a file path with no ticketing provider -- external yet not
        # provider-tagged, and directional capability->verifier. Consumed by
        # Proofkeeper's coverage read-model (ADR-074).
        EdgeSpec(
            name="verified_by",
            range=(),
            external=True,
            directional=True,
            symmetric=False,
            inverse="verifies",
        ),
    )
}


def edge_spec(name: str) -> EdgeSpec | None:
    """Return the :class:`EdgeSpec` for a snake_case relationship kind, or None."""
    return REGISTRY.get(name)
