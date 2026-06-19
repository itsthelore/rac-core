"""Single-schema cross-consumer agreement (v0.23.0, WS6).

The artifact schema is defined once in code (ADR-052, ADR-049): the front-matter
*envelope* (`_SUPPORTED_FIELDS` in `core/frontmatter.py`, `ArtifactMetadata` in
`core/metadata.py`) and the per-type *structure* (`ARTIFACT_SPECS` in
`core/artifacts.py`), with the relationship-kind vocabulary in
`RELATIONSHIP_SECTIONS` (`services/relationships.py`).

Four code paths consume that schema and must never drift from it:

- the **validator** — `spec_for`;
- the **four MCP serializers** — `get_artifact` / `search_artifacts` /
  `get_related` report a `type` produced by the classifier (`score_artifacts`),
  `get_summary` enumerates types via `build_portfolio_summary`, and `get_related`
  keys relationships by `RELATIONSHIP_SECTIONS`;
- the **TUI adapter** — `available_schemas` / `schema_reference`.

These tests assert each consumer derives its artifact types, status enums,
relationship kinds, and section sets from those single sources — *membership*,
not value formatting (REQ-003) — and fail loudly, naming the consumer and the
diverging field, when one drifts (REQ-004). They introduce no parallel schema
framework and depend on no fixture corpus (REQ-001/004).
"""

from __future__ import annotations

import dataclasses

import pytest

from rac.core.artifacts import ARTIFACT_SPECS, spec_for
from rac.core.classification import score_artifacts
from rac.core.frontmatter import _SUPPORTED_FIELDS
from rac.core.markdown import parse
from rac.core.metadata import ArtifactMetadata
from rac.core.schema import available_schemas, schema_reference
from rac.services.portfolio import build_portfolio_summary
from rac.services.relationships import RELATED_SECTIONS, RELATIONSHIP_SECTIONS

# --- single sources of truth -------------------------------------------------

TYPES = frozenset(spec.name for spec in ARTIFACT_SPECS)


def _sections(spec) -> set[str]:
    return {*spec.required, *spec.recommended, *spec.optional}


def _status_enum(spec) -> tuple[str, ...]:
    return spec.metadata.get("status", ())


def _agree(consumer: str, dimension: str, got, want) -> None:
    """Assert ``consumer``'s view of ``dimension`` matches the single source.

    Fails loudly with a diagnostic naming the consumer and exactly which members
    it invented (present in the consumer, absent from the source) or dropped
    (declared by the source, missing from the consumer) — REQ-004.
    """
    got, want = set(got), set(want)
    invented, dropped = got - want, want - got
    assert not invented and not dropped, (
        f"consumer {consumer!r} drifted from the single schema source on "
        f"{dimension}: invented={sorted(invented)} dropped={sorted(dropped)}"
    )


# --- artifact types ----------------------------------------------------------


def test_artifact_types_agree_across_consumers(tmp_path):
    # Validator: spec_for resolves exactly the source types and nothing else.
    resolved = {spec.name for spec in ARTIFACT_SPECS if spec_for(spec.name) is not None}
    _agree("validate.spec_for", "artifact types", resolved, TYPES)
    assert spec_for("not-a-type") is None
    assert spec_for("") is None

    # TUI adapter: the explorer's schema list is whatever available_schemas() returns.
    _agree("explorer.available_schemas", "artifact types", available_schemas(), TYPES)

    # MCP get_artifact / search_artifacts / get_related: every `type` they report
    # comes from the classifier, whose candidate vocabulary is score_artifacts'
    # per-spec names (plus the out-of-band "unknown" for non-artifacts).
    candidates = {score.name for score in score_artifacts(parse(""))}
    _agree("mcp.classify", "artifact types", candidates, TYPES)

    # MCP get_summary: the portfolio seeds its by-type tally from the source
    # (plus "unknown"); an empty directory exposes the vocabulary with no corpus.
    summary = build_portfolio_summary(str(tmp_path), recursive=True)
    _agree("mcp.get_summary", "artifact types", set(summary.by_type) - {"unknown"}, TYPES)


# --- status enums ------------------------------------------------------------


def test_status_enums_agree_across_consumers():
    for spec in ARTIFACT_SPECS:
        ref = schema_reference(spec.name)
        assert ref is not None, spec.name
        # TUI: the schema reference exposes the same status enum the spec declares.
        _agree(
            f"explorer.schema_reference[{spec.name}]",
            "status enum",
            ref.metadata.get("status", []),
            _status_enum(spec),
        )
        # Source self-consistency (ADR-051): retired statuses are a subset of the
        # declared status enum — a retired value outside the enum is undetectable.
        assert set(spec.retired_status) <= set(_status_enum(spec)), (
            f"{spec.name}: retired_status {spec.retired_status} not within "
            f"status enum {_status_enum(spec)}"
        )


# --- relationship kinds ------------------------------------------------------


def test_relationship_kinds_agree_across_consumers():
    # The vocabulary is RELATED_SECTIONS (the per-type "related X" kinds) plus the
    # standalone "supersedes"; get_related keys its `outgoing` object by it.
    assert RELATIONSHIP_SECTIONS == RELATED_SECTIONS + ("supersedes",)

    # No spec invents a relationship section outside the vocabulary, and none of
    # the vocabulary is orphaned: the relationship sections appearing across the
    # specs are exactly RELATIONSHIP_SECTIONS.
    spec_relationship_sections = {
        section
        for spec in ARTIFACT_SPECS
        for section in _sections(spec)
        if section in RELATIONSHIP_SECTIONS
    }
    _agree(
        "artifacts.ARTIFACT_SPECS",
        "relationship kinds",
        spec_relationship_sections,
        RELATIONSHIP_SECTIONS,
    )

    # Each artifact type has a matching "related <type>s" kind, tying the
    # relationship vocabulary to the type vocabulary: adding a type without its
    # relationship section (or vice versa) breaks this.
    _agree(
        "relationships.RELATED_SECTIONS",
        "per-type relationship kinds",
        RELATED_SECTIONS,
        {f"related {spec.name}s" for spec in ARTIFACT_SPECS},
    )


# --- required / recommended / optional sections ------------------------------


def test_section_sets_agree_across_consumers():
    for spec in ARTIFACT_SPECS:
        ref = schema_reference(spec.name)
        assert ref is not None, spec.name
        # TUI: the schema reference's section sets match the spec's, membership-wise.
        _agree(
            f"explorer.schema_reference[{spec.name}]",
            "required sections",
            ref.required,
            spec.required,
        )
        _agree(
            f"explorer.schema_reference[{spec.name}]",
            "recommended sections",
            ref.recommended,
            spec.recommended,
        )
        _agree(
            f"explorer.schema_reference[{spec.name}]",
            "optional sections",
            ref.optional,
            spec.optional,
        )
        # Source self-consistency: required / recommended / optional are disjoint,
        # so a section never lands in two buckets for one type.
        total = len(spec.required) + len(spec.recommended) + len(spec.optional)
        assert total == len(_sections(spec)), f"{spec.name}: overlapping section buckets"


# --- front-matter envelope ---------------------------------------------------


def test_envelope_fields_agree():
    # The parser's accepted front-matter fields and the typed envelope agree.
    # `provenance` is a derived internal marker (source vs ingested), not a
    # front-matter field; every other envelope field is a supported field.
    metadata_fields = {f.name for f in dataclasses.fields(ArtifactMetadata)}
    _agree(
        "frontmatter._SUPPORTED_FIELDS",
        "envelope fields",
        metadata_fields - {"provenance"},
        set(_SUPPORTED_FIELDS),
    )


# --- the gate itself fires (REQ-004) -----------------------------------------


def test_drift_is_detected_with_consumer_named_diagnostic():
    # An invented member (consumer adds a type the source never declared).
    with pytest.raises(AssertionError) as invented:
        _agree("explorer.available_schemas", "artifact types", TYPES | {"invented_type"}, TYPES)
    assert "explorer.available_schemas" in str(invented.value)
    assert "invented_type" in str(invented.value)

    # A dropped member (consumer silently omits a type the source declares).
    with pytest.raises(AssertionError) as dropped:
        _agree("validate.spec_for", "artifact types", TYPES - {"design"}, TYPES)
    assert "validate.spec_for" in str(dropped.value)
    assert "design" in str(dropped.value)
