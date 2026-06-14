"""Tests for canonical identity over hybrid metadata (ADR-026, v0.7.11).

The frontmatter ID wins the identity precedence; matching legacy declarations
are accepted during migration; conflicting ones are an error RAC never
resolves silently; legacy artifacts keep their existing identity; duplicate
canonical IDs surface through the repository duplicate-identifier path.
"""

from __future__ import annotations

from rac.core.artifacts import spec_for
from rac.core.identity import artifact_identifier, identity_conflict
from rac.core.markdown import parse
from rac.core.validation import has_errors, validate
from rac.services.index import build_repository_index
from rac.services.relationships import validate_relationships

DECISION_BODY = """# Some Decision

## Context

c

## Decision

d

## Consequences

q
"""

FRONTMATTER = "---\nschema_version: 1\nid: RAC-01JY4M8X2QZ7\ntype: decision\n---\n"


def _spec(product):
    return spec_for("decision")


def test_frontmatter_id_wins_precedence():
    product = parse(FRONTMATTER + DECISION_BODY)
    assert (
        artifact_identifier(product, _spec(product), "adr-099-some-decision.md")
        == "RAC-01JY4M8X2QZ7"
    )


def test_identity_independent_of_filename_and_path():
    product = parse(FRONTMATTER + DECISION_BODY)
    for path in ("a.md", "moved/elsewhere/renamed.md", "adr-001-x.md"):
        assert artifact_identifier(product, _spec(product), path) == "RAC-01JY4M8X2QZ7"


def test_legacy_id_section_still_works_without_frontmatter():
    product = parse(DECISION_BODY + "\n## ID\n\nADR-099\n")
    assert artifact_identifier(product, _spec(product), "x.md") == "ADR-099"


def test_filename_fallback_unchanged_for_legacy_artifacts():
    product = parse(DECISION_BODY)
    assert artifact_identifier(product, _spec(product), "adr-004-parser-strategy.md") == "adr-004"


def test_matching_frontmatter_and_legacy_identity_accepted():
    product = parse(FRONTMATTER + DECISION_BODY + "\n## ID\n\nrac-01jy4m8x2qz7\n")
    assert identity_conflict(product, _spec(product)) is None
    assert not has_errors(validate(product))


def test_conflicting_identity_is_an_error():
    product = parse(FRONTMATTER + DECISION_BODY + "\n## ID\n\nADR-099\n")
    assert identity_conflict(product, _spec(product)) == (
        "RAC-01JY4M8X2QZ7",
        "ADR-099",
    )
    issues = validate(product)
    assert "conflicting-identity" in [i.code for i in issues]
    assert has_errors(issues)


def test_index_exposes_frontmatter_ids(tmp_path):
    (tmp_path / "d.md").write_text(FRONTMATTER + DECISION_BODY, encoding="utf-8")
    index = build_repository_index(str(tmp_path))
    assert index.artifacts[0].id == "RAC-01JY4M8X2QZ7"


def test_legacy_references_resolve_after_frontmatter_adoption(tmp_path):
    # Migration alias (Initiative 7): adopting a canonical ID must not break
    # existing human-readable references to the legacy identity.
    (tmp_path / "adr-015-explorer.md").write_text(FRONTMATTER + DECISION_BODY, encoding="utf-8")
    # A bare legacy alias (ADR-016: the whole line is the reference), matched
    # case-insensitively to the filename-derived identity "adr-015".
    (tmp_path / "consumer.md").write_text(
        DECISION_BODY + "\n## Related Decisions\n\n- ADR-015\n",
        encoding="utf-8",
    )
    report = validate_relationships(str(tmp_path))
    assert report.ok


def test_canonical_id_references_resolve(tmp_path):
    (tmp_path / "target.md").write_text(FRONTMATTER + DECISION_BODY, encoding="utf-8")
    (tmp_path / "consumer.md").write_text(
        DECISION_BODY + "\n## Related Decisions\n\n- RAC-01JY4M8X2QZ7\n",
        encoding="utf-8",
    )
    report = validate_relationships(str(tmp_path))
    assert report.ok


def test_alias_never_creates_duplicate_identity(tmp_path):
    # Same file answering to several aliases is not a duplicate; duplicates
    # require two files sharing a *canonical* identifier.
    (tmp_path / "adr-015-explorer.md").write_text(FRONTMATTER + DECISION_BODY, encoding="utf-8")
    report = validate_relationships(str(tmp_path))
    assert report.ok


def test_duplicate_canonical_ids_fail_repository_validation(tmp_path):
    (tmp_path / "a.md").write_text(FRONTMATTER + DECISION_BODY, encoding="utf-8")
    (tmp_path / "b.md").write_text(FRONTMATTER + DECISION_BODY, encoding="utf-8")
    report = validate_relationships(str(tmp_path))
    assert not report.ok
    assert any(i.code == "duplicate-artifact-identifier" for i in report.issues)
