"""Tests for rac.services.resolve and `rac resolve` / `rac find` (v0.7.12).

Exact resolution has three outcomes — resolved, not found, duplicate — and a
duplicate is never resolved by path order. Resolution survives renames,
moves, title and type changes (identity lives in frontmatter). Search is
deterministic: field-priority order, sorted-path tiebreak, empty results are
valid.
"""

from __future__ import annotations

import json

import pytest

from rac.cli import main
from rac.services.resolve import (
    OUTCOME_DUPLICATE,
    OUTCOME_NOT_FOUND,
    OUTCOME_RESOLVED,
    find_artifacts,
    resolve_artifact,
)

CANONICAL_ID = "RAC-01JY4M8X2QZ7"

DECISION = f"""---
schema_version: 1
id: {CANONICAL_ID}
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

LEGACY_DECISION = """# A Legacy Decision

## Context

c

## Decision

d

## Consequences

q
"""


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "decisions").mkdir()
    (tmp_path / "decisions" / "markdown-first.md").write_text(DECISION, encoding="utf-8")
    (tmp_path / "decisions" / "adr-002-legacy.md").write_text(LEGACY_DECISION, encoding="utf-8")
    return tmp_path


# --- exact resolution ----------------------------------------------------------


def test_resolves_canonical_id(repo):
    result = resolve_artifact(str(repo), CANONICAL_ID)
    assert result.outcome == OUTCOME_RESOLVED
    assert result.artifact.id == CANONICAL_ID
    assert result.artifact.type == "decision"
    assert result.artifact.title == "Markdown Is the Canonical Source Format"
    assert result.artifact.path.endswith("decisions/markdown-first.md")


def test_resolution_is_case_insensitive(repo):
    assert resolve_artifact(str(repo), CANONICAL_ID.lower()).outcome == OUTCOME_RESOLVED


def test_resolves_legacy_alias_to_canonical_record(repo):
    # Migration: a legacy filename alias resolves, and the answer carries the
    # canonical identity.
    result = resolve_artifact(str(repo), "markdown-first")
    assert result.outcome == OUTCOME_RESOLVED
    assert result.artifact.id == CANONICAL_ID


def test_resolves_legacy_artifact_by_filename_prefix(repo):
    result = resolve_artifact(str(repo), "ADR-002")
    assert result.outcome == OUTCOME_RESOLVED
    assert result.artifact.id == "adr-002"


def test_unknown_id_not_found(repo):
    result = resolve_artifact(str(repo), "RAC-ZZZZZZZZZZZZ")
    assert result.outcome == OUTCOME_NOT_FOUND
    assert result.artifact is None


def test_resolution_survives_rename_and_move(repo, tmp_path):
    moved = repo / "archive"
    moved.mkdir()
    (repo / "decisions" / "markdown-first.md").rename(moved / "renamed.md")
    result = resolve_artifact(str(repo), CANONICAL_ID)
    assert result.outcome == OUTCOME_RESOLVED
    assert result.artifact.path.endswith("archive/renamed.md")


def test_duplicate_id_never_resolved_by_path_order(repo):
    (repo / "decisions" / "copy.md").write_text(DECISION, encoding="utf-8")
    result = resolve_artifact(str(repo), CANONICAL_ID)
    assert result.outcome == OUTCOME_DUPLICATE
    assert result.artifact is None
    assert len(result.duplicate_paths) == 2
    assert result.duplicate_paths == sorted(result.duplicate_paths)


def test_empty_repository_not_found(tmp_path):
    assert resolve_artifact(str(tmp_path), "RAC-01JY4M8X2QZ7").outcome == (OUTCOME_NOT_FOUND)


# --- search --------------------------------------------------------------------


def test_search_matches_id_title_and_path(repo):
    assert find_artifacts(str(repo), CANONICAL_ID).match_count == 1
    assert find_artifacts(str(repo), "canonical source").match_count == 1
    assert find_artifacts(str(repo), "markdown-first").match_count == 1
    assert find_artifacts(str(repo), "decisions/").match_count == 2


def test_search_type_filter(repo):
    assert find_artifacts(str(repo), "decisions/", artifact_type="decision").match_count == 2
    assert find_artifacts(str(repo), "decisions/", artifact_type="prompt").match_count == 0


def test_search_id_matches_rank_before_title_matches(repo):
    # "legacy" hits adr-002's id alias (adr-002-legacy stem) and the other
    # file's nothing; craft a title hit to compare ordering.
    (repo / "decisions" / "zz-about.md").write_text(
        LEGACY_DECISION.replace("A Legacy Decision", "All About adr-002"),
        encoding="utf-8",
    )
    matches = find_artifacts(str(repo), "adr-002").matches
    assert matches[0].path.endswith("adr-002-legacy.md")  # id match first
    assert matches[1].path.endswith("zz-about.md")  # title match second


def test_search_order_is_deterministic(repo):
    a = find_artifacts(str(repo), "decisions/").matches
    b = find_artifacts(str(repo), "decisions/").matches
    assert [m.path for m in a] == [m.path for m in b]
    assert [m.path for m in a] == sorted(m.path for m in a)


def test_search_empty_repository_valid_no_match(tmp_path):
    result = find_artifacts(str(tmp_path), "anything")
    assert result.match_count == 0
    assert result.matches == []


# --- CLI: rac resolve ------------------------------------------------------------


def test_cli_resolve_human(repo, capsys):
    rc = main(["resolve", CANONICAL_ID, str(repo)])
    assert rc == 0
    out = capsys.readouterr().out
    assert CANONICAL_ID in out
    assert "Type: decision" in out
    assert "Title: Markdown Is the Canonical Source Format" in out


def test_cli_resolve_json_contract(repo, capsys):
    rc = main(["resolve", CANONICAL_ID, str(repo), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "schema_version": "1",
        "id": CANONICAL_ID,
        "type": "decision",
        "title": "Markdown Is the Canonical Source Format",
        "path": str(repo / "decisions" / "markdown-first.md"),
    }


def test_cli_resolve_not_found_exit_1(repo, capsys):
    rc = main(["resolve", "RAC-ZZZZZZZZZZZZ", str(repo)])
    assert rc == 1
    assert "artifact not found: RAC-ZZZZZZZZZZZZ" in capsys.readouterr().err


def test_cli_resolve_not_found_json(repo, capsys):
    rc = main(["resolve", "RAC-ZZZZZZZZZZZZ", str(repo), "--json"])
    assert rc == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"] == "not-found"
    assert payload["id"] == "RAC-ZZZZZZZZZZZZ"


def test_cli_resolve_duplicate_exit_1_with_paths(repo, capsys):
    (repo / "decisions" / "copy.md").write_text(DECISION, encoding="utf-8")
    rc = main(["resolve", CANONICAL_ID, str(repo)])
    assert rc == 1
    err = capsys.readouterr().err
    assert f"duplicate artifact ID: {CANONICAL_ID}" in err
    assert "copy.md" in err and "markdown-first.md" in err


def test_cli_resolve_duplicate_json(repo, capsys):
    (repo / "decisions" / "copy.md").write_text(DECISION, encoding="utf-8")
    rc = main(["resolve", CANONICAL_ID, str(repo), "--json"])
    assert rc == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"] == "duplicate"
    assert len(payload["paths"]) == 2


def test_cli_resolve_not_a_directory_exit_2(repo, capsys):
    with pytest.raises(SystemExit) as exc:
        main(["resolve", CANONICAL_ID, str(repo / "nope")])
    assert exc.value.code == 2


# --- CLI: rac find ----------------------------------------------------------------


def test_cli_find_human(repo, capsys):
    rc = main(["find", "markdown", str(repo)])
    assert rc == 0
    out = capsys.readouterr().out
    assert CANONICAL_ID in out
    assert "1 match(es)" in out


def test_cli_find_json_contract(repo, capsys):
    rc = main(["find", "markdown", str(repo), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == "1"
    assert payload["query"] == "markdown"
    assert payload["match_count"] == 1
    assert payload["matches"][0]["id"] == CANONICAL_ID


def test_cli_find_no_matches_exit_0(repo, capsys):
    rc = main(["find", "zzz-nothing", str(repo)])
    assert rc == 0
    assert "No artifacts match" in capsys.readouterr().out


def test_cli_find_type_filter(repo, capsys):
    rc = main(["find", "decisions/", str(repo), "--type", "prompt", "--json"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["match_count"] == 0


# --- relationship presentation (Initiative 5) -------------------------------------


CONSUMER_ROADMAP = """# Consumer Roadmap

## Outcomes

- o

## Initiatives

- i
"""


def test_relationship_human_output_resolves_labels(repo, capsys):
    (repo / "consumer.md").write_text(
        CONSUMER_ROADMAP + "\n## Related Decisions\n\n- " + CANONICAL_ID + "\n",
        encoding="utf-8",
    )
    rc = main(["relationships", str(repo)])
    assert rc == 0
    out = capsys.readouterr().out
    assert (
        f"- {CANONICAL_ID} — Markdown Is the Canonical Source Format "
        f"(decision · {CANONICAL_ID})" in out
    )


def test_relationship_json_keeps_stored_references_unchanged(repo, capsys):
    (repo / "consumer.md").write_text(
        CONSUMER_ROADMAP + "\n## Related Decisions\n\n- " + CANONICAL_ID + "\n",
        encoding="utf-8",
    )
    rc = main(["relationships", str(repo), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    consumer = next(a for a in payload["artifacts"] if a["path"].endswith("consumer.md"))
    # Stored references only — no resolved labels in the JSON contract.
    assert consumer["relationships"]["related_decisions"] == [CANONICAL_ID]
    assert "labels" not in payload


def test_unresolved_reference_renders_without_label(repo, capsys):
    (repo / "consumer.md").write_text(
        CONSUMER_ROADMAP + "\n## Related Decisions\n\n- ADR-404\n",
        encoding="utf-8",
    )
    main(["relationships", str(repo)])
    out = capsys.readouterr().out
    assert "  - ADR-404\n" in out + "\n"
    assert "ADR-404 —" not in out
