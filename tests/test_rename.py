"""Safe artifact-id rename — engine and CLI coverage (v0.21.18).

The headline guarantees under test (roadmap v0.21.18, ADR-007 / ADR-016 /
ADR-063): a rename rewrites every inbound reference *and* the target's own
declared identity, leaves ``rac relationships --validate`` clean, is deterministic
(same inputs -> identical plan), and is reversible (apply old->new then new->old
restores the original bytes). Negative boundaries — unknown OLD, ambiguous OLD,
colliding NEW, invalid NEW, filename-only alias, dry-run writes nothing — are
covered alongside, per the session-start prompt.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from rac.cli import main
from rac.services.relationships import validate_relationships
from rac.services.rename import (
    IDENTITY_FRONTMATTER,
    IDENTITY_ID_SECTION,
    REASON_NEW_COLLIDES,
    REASON_NEW_INVALID,
    REASON_OLD_AMBIGUOUS,
    REASON_OLD_FILENAME_ONLY,
    REASON_OLD_NOT_FOUND,
    _replace_token,
    apply_rename,
    compute_rename,
)

# --- fixtures ----------------------------------------------------------------


def _decision(id_value: str, *, related: list[str] | None = None, id_section: bool = False) -> str:
    """A minimal valid decision artifact.

    ``id_value`` is the canonical identity. By default it is the frontmatter
    ``id``; with ``id_section=True`` it is declared as a ``## ID`` section instead
    (frontmatter omitted), so the rename has an editable in-file identity that is
    not the filename.
    """
    related_block = ""
    if related:
        lines = "\n".join(f"- {r}" for r in related)
        related_block = f"\n## Related Decisions\n\n{lines}\n"
    if id_section:
        return (
            f"# {id_value} A Decision\n\n"
            f"## ID\n\n{id_value}\n\n"
            "## Context\n\nWhy.\n\n"
            "## Decision\n\nWhat.\n\n"
            "## Consequences\n\nResults.\n"
            f"{related_block}"
        )
    return (
        "---\n"
        "schema_version: 1\n"
        f"id: {id_value}\n"
        "type: decision\n"
        "---\n"
        f"# {id_value} A Decision\n\n"
        "## Context\n\nWhy.\n\n"
        "## Decision\n\nWhat.\n\n"
        "## Consequences\n\nResults.\n"
        f"{related_block}"
    )


@pytest.fixture
def corpus(tmp_path: Path) -> Path:
    """A three-artifact corpus where two decisions reference a third by ## ID.

    The target ``ADR-001`` declares its identity in a ``## ID`` section (editable,
    not the filename), so a rename can rewrite both the inbound references and the
    target's own identity without renaming any file.
    """
    (tmp_path / "adr-001-target.md").write_text(_decision("ADR-001", id_section=True))
    (tmp_path / "adr-002-source.md").write_text(
        _decision("ADR-002", related=["ADR-001"], id_section=True)
    )
    (tmp_path / "adr-003-source.md").write_text(
        _decision("ADR-003", related=["ADR-001"], id_section=True)
    )
    return tmp_path


# --- the headline guarantee --------------------------------------------------


def test_rename_updates_references_and_identity_and_validates_clean(corpus: Path):
    plan = compute_rename(str(corpus), "ADR-001", "ADR-099")

    assert plan.ok
    assert plan.identity_field == IDENTITY_ID_SECTION
    assert plan.reference_edits == 2  # both inbound references
    assert plan.identity_edits == 1  # the target's own ## ID value
    assert plan.target_path == str(corpus / "adr-001-target.md")

    apply_rename(plan)

    # Every inbound reference now names ADR-099.
    assert "- ADR-099" in (corpus / "adr-002-source.md").read_text()
    assert "- ADR-099" in (corpus / "adr-003-source.md").read_text()
    # The target's identity is ADR-099.
    target = (corpus / "adr-001-target.md").read_text()
    assert "\n## ID\n\nADR-099\n" in target

    # The Success Measure: relationships resolve cleanly after the rename.
    result = validate_relationships(str(corpus))
    assert result.ok, [i.to_dict() for i in result.issues]


def test_note_after_reference_is_token_replaced(tmp_path: Path):
    """Surrounding text on a reference line survives a rename (token-only replace).

    The whole line is the reference (ADR-016), so a noted line like ``ADR-001
    (blocked)`` does not resolve — but if a corpus carries one, the rename must
    still rewrite only the ``ADR-001`` token and preserve ``(blocked)`` verbatim.
    """
    (tmp_path / "adr-001-target.md").write_text(_decision("ADR-001", id_section=True))
    (tmp_path / "adr-002-source.md").write_text(
        _decision("ADR-002", related=["ADR-001 (blocked)"], id_section=True)
    )
    apply_rename(compute_rename(str(tmp_path), "ADR-001", "ADR-099"))
    src = (tmp_path / "adr-002-source.md").read_text()
    assert "- ADR-099 (blocked)" in src


# --- determinism -------------------------------------------------------------


def test_plan_is_deterministic(corpus: Path):
    first = compute_rename(str(corpus), "ADR-001", "ADR-099")
    second = compute_rename(str(corpus), "ADR-001", "ADR-099")
    assert first.to_dict() == second.to_dict()
    # Edits are ordered by path then line.
    keys = [(e.path, e.line) for e in first.edits]
    assert keys == sorted(keys)


# --- reversibility -----------------------------------------------------------


def test_rename_is_reversible(corpus: Path):
    before = {p.name: p.read_text() for p in corpus.glob("*.md")}

    apply_rename(compute_rename(str(corpus), "ADR-001", "ADR-099"))
    apply_rename(compute_rename(str(corpus), "ADR-099", "ADR-001"))

    after = {p.name: p.read_text() for p in corpus.glob("*.md")}
    assert after == before


# --- frontmatter identity ----------------------------------------------------


def test_rename_frontmatter_id(tmp_path: Path):
    """When OLD is the canonical frontmatter id, that value is the one rewritten."""
    old = "RAC-01JY4M8X2QZ7"
    new = "RAC-01JY4M8X2QZ9"
    (tmp_path / "a.md").write_text(_decision(old))
    (tmp_path / "b.md").write_text(_decision("RAC-01JY4M8X2QZ8", related=[old]))

    plan = compute_rename(str(tmp_path), old, new)
    assert plan.ok
    assert plan.identity_field == IDENTITY_FRONTMATTER
    apply_rename(plan)

    assert f"id: {new}" in (tmp_path / "a.md").read_text()
    assert f"- {new}" in (tmp_path / "b.md").read_text()
    assert validate_relationships(str(tmp_path)).ok


# --- negative boundaries -----------------------------------------------------


def test_unknown_old_is_refused(corpus: Path):
    plan = compute_rename(str(corpus), "ADR-404", "ADR-099")
    assert not plan.ok
    assert plan.reason == REASON_OLD_NOT_FOUND
    assert plan.edits == []


def test_ambiguous_old_is_refused(tmp_path: Path):
    # Two artifacts both answer to ADR-001 (a duplicate identity in the corpus).
    (tmp_path / "one.md").write_text(_decision("ADR-001", id_section=True))
    (tmp_path / "two.md").write_text(_decision("ADR-001", id_section=True))
    plan = compute_rename(str(tmp_path), "ADR-001", "ADR-099")
    assert not plan.ok
    assert plan.reason == REASON_OLD_AMBIGUOUS


def test_colliding_new_is_refused(corpus: Path):
    # ADR-002 already exists, so renaming ADR-001 onto it would duplicate identity.
    plan = compute_rename(str(corpus), "ADR-001", "ADR-002")
    assert not plan.ok
    assert plan.reason == REASON_NEW_COLLIDES
    assert plan.edits == []


def test_invalid_new_is_refused(corpus: Path):
    for bad in ["", "  ", "ADR 001", "- ADR-001 (note)"]:
        plan = compute_rename(str(corpus), "ADR-001", bad)
        assert not plan.ok, bad
        assert plan.reason == REASON_NEW_INVALID, bad


def test_filename_only_alias_is_refused(tmp_path: Path):
    """A reference that resolves only via the filename prefix cannot be rewritten."""
    # No frontmatter id, no ## ID — identity is purely the filename prefix adr-001.
    body = (
        "# A Decision\n\n## Context\n\nWhy.\n\n## Decision\n\nWhat.\n\n"
        "## Consequences\n\nResults.\n"
    )
    (tmp_path / "adr-001-x.md").write_text(body)
    plan = compute_rename(str(tmp_path), "adr-001", "adr-099")
    assert not plan.ok
    assert plan.reason == REASON_OLD_FILENAME_ONLY


def test_token_boundary_does_not_match_prefix(tmp_path: Path):
    """Renaming ADR-1 must not touch a reference to ADR-10."""
    (tmp_path / "t1.md").write_text(_decision("ADR-1", id_section=True))
    (tmp_path / "t10.md").write_text(_decision("ADR-10", id_section=True))
    (tmp_path / "src.md").write_text(
        _decision("ADR-2", related=["ADR-1", "ADR-10"], id_section=True)
    )
    plan = compute_rename(str(tmp_path), "ADR-1", "ADR-7")
    apply_rename(plan)
    src = (tmp_path / "src.md").read_text()
    assert "- ADR-7\n" in src
    assert "- ADR-10\n" in src  # untouched


# --- dry run vs apply --------------------------------------------------------


def test_dry_run_writes_nothing(corpus: Path):
    before = {p.name: p.read_text() for p in corpus.glob("*.md")}
    plan = compute_rename(str(corpus), "ADR-001", "ADR-099")
    assert plan.ok  # a valid plan was computed
    after = {p.name: p.read_text() for p in corpus.glob("*.md")}
    assert after == before  # but computing it touched nothing


def test_apply_writes(corpus: Path):
    before = (corpus / "adr-002-source.md").read_text()
    apply_rename(compute_rename(str(corpus), "ADR-001", "ADR-099"))
    assert (corpus / "adr-002-source.md").read_text() != before


def test_apply_refused_plan_writes_nothing(corpus: Path):
    before = {p.name: p.read_text() for p in corpus.glob("*.md")}
    result = apply_rename(compute_rename(str(corpus), "ADR-404", "ADR-099"))
    assert not result.applied
    after = {p.name: p.read_text() for p in corpus.glob("*.md")}
    assert after == before


# --- CLI surface -------------------------------------------------------------


def test_cli_dry_run_exits_ok(corpus: Path, capsys):
    rc = main(["rename", "ADR-001", "ADR-099", str(corpus), "--json"])
    assert rc == 0
    out = capsys.readouterr().out
    assert '"ok": true' in out
    assert '"reference_edits": 2' in out


def test_cli_refusal_exits_nonzero(corpus: Path, capsys):
    rc = main(["rename", "ADR-404", "ADR-099", str(corpus), "--json"])
    assert rc == 1
    out = capsys.readouterr().out
    assert REASON_OLD_NOT_FOUND in out


def test_cli_apply_then_validate_clean(corpus: Path, capsys):
    rc = main(["rename", "ADR-001", "ADR-099", str(corpus), "--apply"])
    assert rc == 0
    assert validate_relationships(str(corpus)).ok


def test_cli_not_a_directory_is_usage_error(tmp_path: Path):
    target = tmp_path / "nope"
    with pytest.raises(SystemExit) as exc:
        main(["rename", "ADR-001", "ADR-099", str(target)])
    assert exc.value.code == 2


def test_replace_token_folds_only_the_sliced_prefix():
    # casefold can change a string's length (ß → ss). Folding all of the text
    # but slicing by the unfolded token length would split mid-token: here the
    # old behavior matched "ß" against "ss", sliced two characters ("ß "), and
    # returned a corrupted "REQ-002(kept)". The prefix that is compared must be
    # exactly the prefix that is sliced.
    assert _replace_token("ß (kept)", "ss", "REQ-002") is None
    # Case-insensitive ASCII matching is unchanged.
    assert _replace_token("adr-001 (kept)", "ADR-001", "ADR-100") == "ADR-100 (kept)"
