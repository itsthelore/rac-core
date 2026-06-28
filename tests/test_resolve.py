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
    resolve_in_index,
    search_index,
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
    # Order is the deterministic relevance score (ADR-078), not sorted path; the
    # contract is that identical bytes and query yield the identical order.
    a = find_artifacts(str(repo), "decisions/").matches
    b = find_artifacts(str(repo), "decisions/").matches
    assert [m.path for m in a] == [m.path for m in b]


def test_search_empty_repository_valid_no_match(tmp_path):
    result = find_artifacts(str(tmp_path), "anything")
    assert result.match_count == 0
    assert result.matches == []


# --- token-boundary battery (v0.10.3, ADR-037/ADR-038) --------------------------


def test_tokenize_splits_on_boundaries_and_camelcase():
    from rac.services.resolve import tokenize

    assert tokenize("soft-delete") == ["soft", "delete"]
    assert tokenize("relationships") == ["relationships"]
    assert tokenize("Explorer") == ["explorer"]
    assert tokenize("camelCaseWord") == ["camel", "case", "word"]
    assert tokenize("adr-002-legacy.md") == ["adr", "002", "legacy", "md"]
    assert tokenize("...") == []


def test_prefix_matching_finds_whole_token(repo):
    # `relation` must match a `relationships` token by prefix (ADR-037).
    (repo / "decisions" / "relationships.md").write_text(
        LEGACY_DECISION.replace("A Legacy Decision", "Relationship Validation"),
        encoding="utf-8",
    )
    matches = find_artifacts(str(repo), "relation").matches
    assert any(m.path.endswith("relationships.md") for m in matches)


def test_word_boundary_excludes_substring_false_positive(repo):
    # `lore` is a substring of "Explorer" but not a token prefix of it; the
    # named regression (lore vs Explorer) lives in test_dogfood against the
    # dogfood corpus. Here the unit form: a mid-word substring no longer hits.
    (repo / "decisions" / "explorer.md").write_text(
        LEGACY_DECISION.replace("A Legacy Decision", "The Explorer Surface"),
        encoding="utf-8",
    )
    matches = find_artifacts(str(repo), "lore").matches
    assert not any("explorer" in m.path.casefold() for m in matches)
    assert not any((m.title or "").casefold().find("explorer") >= 0 for m in matches)


def test_camelcase_split_is_searchable(repo):
    (repo / "decisions" / "camel.md").write_text(
        LEGACY_DECISION.replace("A Legacy Decision", "Use camelCase Identifiers"),
        encoding="utf-8",
    )
    # `camel` and `case` are separate tokens after the camelCase split.
    assert find_artifacts(str(repo), "camel").match_count >= 1
    assert any(m.path.endswith("camel.md") for m in find_artifacts(str(repo), "case").matches)


def test_multi_term_requires_every_term(repo):
    (repo / "decisions" / "ab.md").write_text(
        LEGACY_DECISION.replace("A Legacy Decision", "Alpha Bravo Decision"),
        encoding="utf-8",
    )
    # Both terms present -> match; one term absent -> no match (AND semantics).
    assert any(m.path.endswith("ab.md") for m in find_artifacts(str(repo), "alpha bravo").matches)
    assert not any(
        m.path.endswith("ab.md") for m in find_artifacts(str(repo), "alpha charlie").matches
    )


def test_tier_ordering_id_title_path_heading_body(tmp_path):
    # Five artifacts, each making "needle" match at exactly one tier; the result
    # order must be id, title, path, heading, body (ADR-038 ladder). Sorted-path
    # tiebreak is irrelevant here — every artifact wins at a distinct tier.
    base = (
        "---\nschema_version: 1\nid: {id}\ntype: decision\n---\n"
        "# {title}\n\n## Status\n\nAccepted\n\n## Category\n\nArchitecture\n\n"
        "## {heading}\n\n{body}\n\n## Decision\n\nd\n\n## Consequences\n\nq\n"
    )
    # id tier: a legacy artifact whose filename stem (its identifier) carries the
    # token. Path also carries it, but the id tier (rank 0) is the win.
    (tmp_path / "needle-by-id.md").write_text(
        "# Aaa\n\n## Context\n\nx\n\n## Decision\n\nd\n\n## Consequences\n\nq\n",
        encoding="utf-8",
    )
    # title tier: token only in the title.
    (tmp_path / "btitle.md").write_text(
        base.format(id="RAC-TIT000000001", title="Needle Title", heading="Context", body="x"),
        encoding="utf-8",
    )
    # path tier: token only in a directory component (not the stem, not id/title).
    (tmp_path / "needledir").mkdir()
    (tmp_path / "needledir" / "plain.md").write_text(
        base.format(id="RAC-PTH000000001", title="Ccc", heading="Context", body="x"),
        encoding="utf-8",
    )
    # heading tier: token only in a section heading.
    (tmp_path / "dhead.md").write_text(
        base.format(id="RAC-HED000000001", title="Ddd", heading="Needle Heading", body="x"),
        encoding="utf-8",
    )
    # body tier: token only in body text.
    (tmp_path / "ebody.md").write_text(
        base.format(id="RAC-BOD000000001", title="Eee", heading="Context", body="needle in body"),
        encoding="utf-8",
    )
    matches = find_artifacts(str(tmp_path), "needle").matches
    order = [m.path.split("/")[-1] for m in matches]
    assert order == ["needle-by-id.md", "btitle.md", "plain.md", "dhead.md", "ebody.md"]
    # Only the heading and body matches carry snippets.
    by_name = {m.path.split("/")[-1]: m for m in matches}
    assert by_name["needle-by-id.md"].snippet is None
    assert by_name["btitle.md"].snippet is None
    assert by_name["plain.md"].snippet is None
    assert by_name["dhead.md"].section == "Needle Heading"
    assert by_name["ebody.md"].snippet == "needle in body"


def test_body_only_match_carries_snippet(tmp_path):
    # A decision whose body, not its title/path/id, holds the query term is
    # found, with the section heading and matching line as its snippet (ADR-038).
    (tmp_path / "dec.md").write_text(
        "---\nschema_version: 1\nid: RAC-BODYONLY0001\ntype: decision\n---\n"
        "# Unrelated Title\n\n## Status\n\nAccepted\n\n## Category\n\nArchitecture\n\n"
        "## Context\n\nThe payments gateway must stay idempotent.\n\n"
        "## Decision\n\nd\n\n## Consequences\n\nq\n",
        encoding="utf-8",
    )
    matches = find_artifacts(str(tmp_path), "idempotent").matches
    assert len(matches) == 1
    m = matches[0]
    assert m.section == "Context"
    assert m.snippet == "The payments gateway must stay idempotent."
    # The snippet fields ride inside the match dict (additive, ADR-007).
    assert m.to_dict()["section"] == "Context"
    assert m.to_dict()["snippet"] == "The payments gateway must stay idempotent."


def test_metadata_match_has_no_snippet_fields(repo):
    # An id/title/path match carries no section/snippet. The pre-v0.10.3 shape is
    # recovered by excluding the additive WS2 evidence (REQ-003).
    match = find_artifacts(str(repo), CANONICAL_ID).matches[0]
    assert match.section is None and match.snippet is None
    assert set(match.to_dict(include_evidence=False)) == {"id", "type", "title", "path"}
    # Evidence is the only additive key on the search shape.
    assert set(match.to_dict()) == {"id", "type", "title", "path", "evidence"}


def test_body_snippet_is_first_matching_line_in_document_order(tmp_path):
    (tmp_path / "dec.md").write_text(
        "---\nschema_version: 1\nid: RAC-FIRSTLINE01\ntype: decision\n---\n"
        "# T\n\n## Status\n\nAccepted\n\n## Category\n\nArchitecture\n\n"
        "## Context\n\nFirst widget line.\nSecond widget line.\n\n"
        "## Decision\n\nThird widget line.\n\n## Consequences\n\nq\n",
        encoding="utf-8",
    )
    match = find_artifacts(str(tmp_path), "widget").matches[0]
    assert match.section == "Context"
    assert match.snippet == "First widget line."


# --- index seams (v0.8.1): same semantics without a directory walk --------------


def test_resolve_in_index_matches_directory_resolution(repo):
    from rac.services.index import build_repository_index

    entries = build_repository_index(str(repo)).artifacts
    for ref in (CANONICAL_ID, "adr-002", "nope"):
        assert (
            resolve_in_index(entries, ref).to_dict() == resolve_artifact(str(repo), ref).to_dict()
        )


def test_search_index_matches_directory_search(repo):
    from rac.services.index import build_repository_index

    entries = build_repository_index(str(repo)).artifacts
    for query, artifact_type in (("decision", None), ("legacy", "decision"), ("zzz", None)):
        assert search_index(entries, query, artifact_type=artifact_type).to_dict() == (
            find_artifacts(str(repo), query, artifact_type=artifact_type).to_dict()
        )


def test_seams_accept_repository_model_artifacts(repo):
    from rac.services.repository import load_repository

    artifacts = load_repository(str(repo)).artifacts
    resolved = resolve_in_index(artifacts, CANONICAL_ID)
    assert resolved.outcome == OUTCOME_RESOLVED
    assert search_index(artifacts, "legacy").match_count == 1


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


# --- relevance ranking (ADR-078): BM25 + RRF + bounded graph boost --------------

_RANK_DECISION = (
    "---\nschema_version: 1\nid: {id}\ntype: decision\n---\n"
    "# {title}\n\n## Status\n\nAccepted\n\n## Context\n\n{body}\n\n"
    "## Decision\n\nd\n\n## Consequences\n\nq\n"
)


def _rank_decision(root, name, aid, *, title="Topic", body="x", related=None):
    text = _RANK_DECISION.format(id=aid, title=title, body=body)
    if related:
        text += "## Related Decisions\n\n" + "\n".join(f"- {r}" for r in related) + "\n"
    (root / f"{name}.md").write_text(text, encoding="utf-8")


def test_bm25_ranks_higher_term_frequency_first(tmp_path):
    # Higher term frequency wins on lexical relevance, even when its path sorts
    # last — proving order is BM25, not alphabetical (both isolated, so the graph
    # signal ties).
    _rank_decision(tmp_path, "z-high", "RAC-AAAAAAAAAAAA", title="One", body="alpha alpha")
    _rank_decision(tmp_path, "a-low", "RAC-BBBBBBBBBBBB", title="Two", body="alpha gamma")
    order = [m.path.split("/")[-1] for m in find_artifacts(str(tmp_path), "alpha").matches]
    assert order[0] == "z-high.md"


def test_graph_boost_breaks_lexical_tie(tmp_path):
    # Two equally-relevant artifacts; the one with an inbound reference ranks
    # above the isolated one, overriding the path tiebreak (a-isolated sorts
    # first by path).
    _rank_decision(tmp_path, "z-popular", "RAC-AAAAAAAAAAAA", title="Topic", body="alpha")
    _rank_decision(tmp_path, "a-isolated", "RAC-BBBBBBBBBBBB", title="Topic", body="alpha")
    _rank_decision(
        tmp_path, "ref", "RAC-CCCCCCCCCCCC", title="Ref", body="zz", related=["RAC-AAAAAAAAAAAA"]
    )
    order = [m.path.split("/")[-1] for m in find_artifacts(str(tmp_path), "alpha").matches]
    assert order.index("z-popular.md") < order.index("a-isolated.md")


def test_graph_does_not_override_clear_lexical_winner(tmp_path):
    # A strong lexical match with no inbound edges beats a weak lexical match
    # with many — the graph boost is bounded, not dominant (REQ-004).
    _rank_decision(
        tmp_path, "strong", "RAC-AAAAAAAAAAAA", title="Alpha Alpha", body="alpha alpha alpha"
    )
    _rank_decision(tmp_path, "weak", "RAC-BBBBBBBBBBBB", title="Other", body="alpha")
    for suffix in ("CCCCCCCCCCCC", "DDDDDDDDDDDD", "EEEEEEEEEEEE", "FFFFFFFFFFFF"):
        _rank_decision(
            tmp_path, f"ref-{suffix}", f"RAC-{suffix}", body="zz", related=["RAC-BBBBBBBBBBBB"]
        )
    order = [m.path.split("/")[-1] for m in find_artifacts(str(tmp_path), "alpha").matches]
    assert order[0] == "strong.md"


def test_equal_relevance_breaks_by_path(tmp_path):
    # Identical relevance and zero inbound on both: the documented tiebreak is
    # sorted path, so order is total and byte-stable.
    _rank_decision(tmp_path, "b-two", "RAC-AAAAAAAAAAAA", title="Topic", body="alpha")
    _rank_decision(tmp_path, "a-one", "RAC-BBBBBBBBBBBB", title="Topic", body="alpha")
    order = [m.path.split("/")[-1] for m in find_artifacts(str(tmp_path), "alpha").matches]
    assert order == ["a-one.md", "b-two.md"]


def test_ranking_preserves_and_semantics(tmp_path):
    # Ranking only reorders the matched set; AND matching is unchanged.
    _rank_decision(tmp_path, "both", "RAC-AAAAAAAAAAAA", title="Alpha", body="beta here")
    _rank_decision(tmp_path, "one", "RAC-BBBBBBBBBBBB", title="Alpha", body="gamma here")
    names = {m.path.split("/")[-1] for m in find_artifacts(str(tmp_path), "alpha beta").matches}
    assert names == {"both.md"}


def test_evidence_carries_score_components(tmp_path):
    # Explainability is additive: evidence keeps {field, terms, tier} and gains
    # the fused score and its per-signal components (ADR-007).
    _rank_decision(tmp_path, "d", "RAC-AAAAAAAAAAAA", title="Topic", body="alpha")
    m = find_artifacts(str(tmp_path), "alpha").matches[0]
    assert set(m.evidence) == {"field", "terms", "tier", "score", "components"}
    assert set(m.evidence["components"]) == {"bm25", "lexical_rank", "graph_rank", "inbound"}
    # Default (no --explain) shape omits evidence entirely — byte-stable contract.
    assert "evidence" not in m.to_dict(include_evidence=False)


def test_ranking_is_byte_stable_across_runs(tmp_path):
    _rank_decision(tmp_path, "one", "RAC-AAAAAAAAAAAA", title="Topic", body="alpha alpha")
    _rank_decision(tmp_path, "two", "RAC-BBBBBBBBBBBB", title="Topic", body="alpha")
    a = find_artifacts(str(tmp_path), "alpha").to_dict()
    b = find_artifacts(str(tmp_path), "alpha").to_dict()
    assert json.dumps(a) == json.dumps(b)
