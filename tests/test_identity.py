"""Tests for rac.core.identity — the deterministic artifact identifier.

Identity was promoted from rac.services.relationships to rac.core.identity in
v0.7.5 so repository indexing, relationship resolution, and portfolio analysis
share one owner, with no compatibility shim (ADR-023). These cover the four-step
identifier precedence (REQ-002): explicit ``## ID`` > ``spec.id_field`` >
filename-stem prefix > whole stem.
"""

from __future__ import annotations

from dataclasses import replace

from rac.core.artifacts import spec_for
from rac.core.identity import artifact_identifier
from rac.core.markdown import parse


def test_identifier_explicit_id_section_wins():
    # Step 1: an explicit ## ID section overrides everything, casing preserved.
    product = parse("# Title\n\n## ID\n\nADR-XYZ\n\n## Context\n\nc\n")
    assert artifact_identifier(product, spec_for("decision"), "/x/adr-004-foo.md") == "ADR-XYZ"


def test_identifier_spec_id_field():
    # Step 2: the type's declared id_field section (no real spec sets it today).
    product = parse("# Title\n\n## Key\n\nDEC-7\n")
    spec = replace(spec_for("decision"), id_field="key")
    assert artifact_identifier(product, spec, "/x/whatever.md") == "DEC-7"


def test_identifier_recognized_prefix_from_stem():
    # Step 3: leading <letters>-<digits> prefix of the filename stem.
    product = parse("# Parser Strategy\n\n## Context\n\nc\n")
    assert artifact_identifier(product, spec_for("decision"), "/x/adr-004-parser-strategy.md") == "adr-004"


def test_identifier_falls_back_to_full_stem():
    # Step 4: no recognized prefix -> the whole stem.
    product = parse("# Q3 Roadmap\n\n## Outcomes\n\no\n\n## Initiatives\n\ni\n")
    assert artifact_identifier(product, spec_for("roadmap"), "/x/roadmap-q3.md") == "roadmap-q3"
