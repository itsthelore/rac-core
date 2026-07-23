"""Relationship-type registry — the edge schema for Layer-3 graph integrity (ADR-055).

Edge *legality by source type* (domain) stays where v0.14.0 put it:
``ArtifactSpec.optional`` (the sections a type may declare). This registry adds
the *graph* properties of each relationship kind — target type (``range``),
directionality, acyclicity, and whether the edge forbids a retired target — so
the Layer-3 checks (range, acyclicity, status-consistency) read one declarative
source instead of hard-coded special cases.

The registry is **code-defined**. Custom, repo-declared relationship types are
deferred (ADR-052 defers the analogous custom artifact types); the built-in
vocabulary is ``asdecided.services.relationships.RELATIONSHIP_SECTIONS`` keyed in its
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
    # External-reference family (ADR-087): the target is an external identifier
    # (a ticket key or URL), not an in-corpus artifact. External edges are exempt
    # from range and referential-integrity resolution and are format-linted
    # instead (the provider is per-repo config, ADR-088); the graph export marks
    # them external and unresolved.
    external: bool = False
    # Whether an external edge's target lives in the repository's configured
    # external *provider* (ticketing, ADR-088), so the graph export tags it with
    # that provider. ``related_tickets`` sets this; ``verified_by`` (ADR-096) does
    # not — its targets are test/trace file paths, which have no provider.
    external_provider: bool = False
    # Whether the edge's targets are repository file paths existence-checked
    # against the working tree (decision-to-code-proximity, ``applies_to``). Unlike
    # the format-linted external edges (``related_tickets``/``verified_by``), a
    # filesystem-scoped edge's literal path/directory entries are checked to exist
    # relative to the repository root; glob and component-name entries are recorded
    # without existence-checking. Declared, never inferred (ADR-065/066).
    filesystem_scoped: bool = False


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
        # External-reference family (ADR-087): a single code-defined edge whose
        # target is an external ticket (a key or URL), not an in-corpus artifact.
        # No artifact range; format-linted against the per-repo ticketing provider
        # (ADR-088), never resolved. Organisations standardise on one ticketing
        # system, so the system is a repo-config choice rather than a per-provider
        # edge — future external systems reuse this edge, not a sibling one.
        EdgeSpec(name="related_tickets", range=(), external=True, external_provider=True),
        # External-target verification edge (ADR-096): a capability (requirement,
        # ADR-020) points at the external tests/traces that verify it. Like an
        # external ticket it skips resolution, range, and status checks, but its
        # target is a file path with no ticketing provider, so it is external
        # without being provider-tagged. Directional capability→verifier; the
        # consumer is Proofkeeper's coverage read-model (ADR-074).
        EdgeSpec(
            name="verified_by",
            range=(),
            external=True,
            directional=True,
            symmetric=False,
            inverse="verifies",
        ),
        # Code-scope declaration (decision-to-code-proximity, Initiative 1): a
        # decision points at the repository paths/components it governs. Like the
        # external edges it carries no artifact range and skips id resolution,
        # range, and status checks, but — unlike them — its literal path/directory
        # targets are existence-checked against the working tree
        # (``filesystem_scoped``). Directional decision→code; the consumers are the
        # path→decisions lookup, Explorer surfacing, and the freshness drift gate.
        EdgeSpec(
            name="applies_to",
            range=(),
            external=True,
            filesystem_scoped=True,
            directional=True,
            symmetric=False,
            inverse="governed_by",
        ),
    )
}


def edge_spec(name: str) -> EdgeSpec | None:
    """The :class:`EdgeSpec` for a snake_case relationship kind, or None."""
    return REGISTRY.get(name)
