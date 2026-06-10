"""Tests for rac.core.frontmatter — the metadata envelope parser (ADR-025).

Strictness is the contract: malformed YAML, duplicate keys, unknown fields,
wrong types, and unsupported schema versions are actionable errors; artifacts
without frontmatter are untouched; body line numbers stay file-accurate.
"""

from __future__ import annotations

from rac.core.frontmatter import parse_frontmatter, split_frontmatter
from rac.core.markdown import parse
from rac.core.validation import has_errors, validate

VALID = """---
schema_version: 1
id: RAC-01JY4M8X2QZ7
type: decision
---
# Markdown Is the Canonical Source Format

## Context

c

## Decision

d

## Consequences

q
"""


# --- split -------------------------------------------------------------------


def test_split_absent_frontmatter_is_untouched():
    split = split_frontmatter("# Title\n\nbody\n")
    assert split.raw is None
    assert split.body == "# Title\n\nbody\n"
    assert split.line_offset == 0
    assert not split.unterminated


def test_split_extracts_block_and_offset():
    split = split_frontmatter(VALID)
    assert split.raw == "schema_version: 1\nid: RAC-01JY4M8X2QZ7\ntype: decision"
    assert split.body.startswith("# Markdown Is the Canonical Source Format")
    assert split.line_offset == 5  # body line 1 is file line 6


def test_split_unterminated_block_is_flagged():
    text = "---\nschema_version: 1\n# Title\n"
    split = split_frontmatter(text)
    assert split.raw is None
    assert split.body == text
    assert split.unterminated


def test_split_document_end_marker_closes_block():
    split = split_frontmatter("---\nschema_version: 1\n...\n# Title\n")
    assert split.raw == "schema_version: 1"


def test_split_mid_document_rule_is_not_frontmatter():
    split = split_frontmatter("# Title\n\n---\n\nbody\n")
    assert split.raw is None
    assert split.line_offset == 0


# --- parse: valid ------------------------------------------------------------


def test_parse_valid_frontmatter():
    metadata, issues = parse_frontmatter("schema_version: 1\nid: RAC-01JY4M8X2QZ7\ntype: decision")
    assert issues == []
    assert metadata.schema_version == 1
    assert metadata.id == "RAC-01JY4M8X2QZ7"
    assert metadata.type == "decision"
    assert metadata.relationships == {}


def test_parse_normalizes_id_case():
    metadata, issues = parse_frontmatter("schema_version: 1\nid: rac-01jy4m8x2qz7")
    assert issues == []
    assert metadata.id == "RAC-01JY4M8X2QZ7"


def test_parse_relationships_mapping():
    metadata, issues = parse_frontmatter(
        "schema_version: 1\nrelationships:\n  implements:\n    - rac-01jy4m8x2qz7"
    )
    assert issues == []
    assert metadata.relationships == {"implements": ["RAC-01JY4M8X2QZ7"]}


# --- parse: errors -----------------------------------------------------------


def _codes(issues):
    return [i.code for i in issues]


def test_parse_malformed_yaml():
    metadata, issues = parse_frontmatter("schema_version: [unclosed")
    assert metadata is None
    assert _codes(issues) == ["malformed-frontmatter"]


def test_parse_non_mapping_yaml():
    metadata, issues = parse_frontmatter("- a\n- b")
    assert metadata is None
    assert _codes(issues) == ["malformed-frontmatter"]


def test_parse_duplicate_keys_rejected():
    metadata, issues = parse_frontmatter("schema_version: 1\nschema_version: 2")
    assert metadata is None
    assert _codes(issues) == ["duplicate-frontmatter-key"]


def test_parse_unknown_field():
    _, issues = parse_frontmatter("schema_version: 1\nassignee: bob")
    assert "invalid-metadata-field" in _codes(issues)


def test_parse_missing_schema_version():
    _, issues = parse_frontmatter("id: RAC-01JY4M8X2QZ7")
    assert "invalid-metadata-field" in _codes(issues)


def test_parse_non_integer_schema_version():
    _, issues = parse_frontmatter("schema_version: one")
    assert "invalid-metadata-field" in _codes(issues)


def test_parse_unsupported_schema_version():
    _, issues = parse_frontmatter("schema_version: 99")
    assert _codes(issues) == ["unsupported-schema-version"]


def test_parse_invalid_id_syntax():
    metadata, issues = parse_frontmatter("schema_version: 1\nid: ADR-015")
    assert _codes(issues) == ["invalid-id-syntax"]
    assert metadata.id is None


def test_parse_unregistered_type():
    metadata, issues = parse_frontmatter("schema_version: 1\ntype: meeting")
    assert _codes(issues) == ["invalid-metadata-field"]
    assert metadata.type is None


def test_parse_malformed_relationships():
    _, issues = parse_frontmatter("schema_version: 1\nrelationships: nope")
    assert _codes(issues) == ["invalid-metadata-field"]


# --- parser integration ------------------------------------------------------


def test_parse_attaches_metadata_to_product():
    product = parse(VALID)
    assert product.metadata is not None
    assert product.metadata.id == "RAC-01JY4M8X2QZ7"
    assert product.metadata_issues == []
    assert product.title == "Markdown Is the Canonical Source Format"


def test_parse_without_frontmatter_has_no_metadata():
    product = parse("# Title\n\n## Problem\n\np\n")
    assert product.metadata is None
    assert product.metadata_issues == []


def test_body_line_numbers_stay_file_accurate():
    # Two titles: the duplicate is on file line 8 (after 5 frontmatter lines).
    text = "---\nschema_version: 1\ntype: decision\n---\n\n# One\n\n# Two\n"
    product = parse(text)
    assert product.extra_title_lines == [8]


def test_requirement_line_numbers_stay_file_accurate():
    # 3 frontmatter lines; "[REQ-1A] bad" is body line 9 → file line 12.
    text = (
        "---\nschema_version: 1\n---\n# F\n\n## Problem\n\np\n\n## Requirements\n\n[REQ-1A] bad\n"
    )
    product = parse(text)
    assert product.malformed_requirements[0].line == 12


def test_validation_surfaces_frontmatter_issues():
    text = (
        "---\nschema_version: 99\n---\n# T\n\n## Problem\n\np\n\n## Requirements\n\n[REQ-001] x\n"
    )
    issues = validate(parse(text))
    assert has_errors(issues)
    assert "unsupported-schema-version" in [i.code for i in issues]


def test_validation_surfaces_unterminated_frontmatter():
    text = "---\nschema_version: 1\n# T\n\n## Problem\n\np\n\n## Requirements\n\n[REQ-001] x\n"
    issues = validate(parse(text))
    assert "malformed-frontmatter" in [i.code for i in issues]
