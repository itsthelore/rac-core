"""Explainable retrieval battery (v0.23.0, WS2).

Pins the additive ``evidence`` object on search results: the winning field,
tier, and matched terms read off the matcher (ADR-037/ADR-038), never a second
heuristic. A controlled corpus isolates each tier (id / title / path / heading /
body) so the reported field is asserted against the matcher's real rank. Also
pins the `rac find --explain` faces and the one-source-of-truth equality between
the MCP search payload and `rac find --explain --json`.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from rac import cli
from rac.mcp.server import build_server
from rac.output import json as json_output
from rac.services.index import build_repository_index
from rac.services.resolve import find_artifacts, search_index

# One decision authored so each query term is unique to one match tier. The
# filename stem ("aaa") is an id alias, so no content word may collide with it.
ARTIFACT = """\
---
schema_version: 1
id: RAC-AAAAAAAAAAAA
type: decision
---
# Photosynthesis Charter

## Status

Accepted

## Context

The mitochondria powerhouse keeps the lights on.

## Decision

Adopt the charter.

## Consequences

Workable.

## Eviction Heuristics

Spell out the rules.
"""


def _corpus(tmp_path: Path) -> Path:
    # The parent directory name ("catalog") is a path-only token.
    root = tmp_path / "catalog"
    root.mkdir()
    (root / "aaa.md").write_text(ARTIFACT, encoding="utf-8")
    return root


def _evidence_for(root: Path, query: str) -> dict:
    result = find_artifacts(str(root), query)
    assert result.match_count == 1, f"{query!r} -> {result.match_count} matches"
    return result.matches[0].evidence


# --- one case per tier (Acceptance: id/title/path/heading/body) --------------


def _tier_evidence(ev: dict) -> dict:
    """The field/terms/tier subset, ignoring the additive ADR-078 score keys."""
    return {k: ev[k] for k in ("field", "terms", "tier")}


def test_title_tier_evidence(tmp_path):
    assert _tier_evidence(_evidence_for(_corpus(tmp_path), "photosynthesis")) == {
        "field": "title",
        "terms": ["photosynthesis"],
        "tier": 1,
    }


def test_path_tier_evidence(tmp_path):
    # "catalog" is only in the directory path — not the id, title, headings, or body.
    assert _tier_evidence(_evidence_for(_corpus(tmp_path), "catalog")) == {
        "field": "path",
        "terms": ["catalog"],
        "tier": 2,
    }


def test_heading_tier_evidence(tmp_path):
    # "eviction" appears only in the "Eviction Heuristics" section heading.
    ev = _evidence_for(_corpus(tmp_path), "eviction")
    assert ev["field"] == "heading" and ev["tier"] == 3
    assert ev["terms"] == ["eviction"]


def test_body_tier_evidence(tmp_path):
    # "mitochondria" appears only in the Context body line.
    ev = _evidence_for(_corpus(tmp_path), "mitochondria")
    assert ev["field"] == "body" and ev["tier"] == 4
    assert ev["terms"] == ["mitochondria"]


def test_id_tier_evidence(tmp_path):
    ev = _evidence_for(_corpus(tmp_path), "RAC-AAAAAAAAAAAA")
    assert ev["field"] == "id" and ev["tier"] == 0
    assert ev["terms"] == ["rac", "aaaaaaaaaaaa"]


def test_terms_follow_query_order(tmp_path):
    # Two terms, both in the title; evidence lists them in query order.
    ev = _evidence_for(_corpus(tmp_path), "charter photosynthesis")
    assert ev["terms"] == ["charter", "photosynthesis"]


# --- evidence is always present and never null on a search match -------------


def test_every_search_match_carries_non_empty_evidence(tmp_path):
    root = _corpus(tmp_path)
    for query in ("photosynthesis", "catalog", "eviction", "mitochondria"):
        for match in find_artifacts(str(root), query).matches:
            assert match.evidence is not None
            assert match.evidence["terms"]
            assert match.evidence["field"] in {"id", "title", "path", "heading", "body"}


# --- additive + backward compatible (REQ-003) --------------------------------


def test_evidence_is_purely_additive_to_the_metadata_shape(tmp_path):
    match = find_artifacts(str(_corpus(tmp_path)), "photosynthesis").matches[0]
    with_ev = match.to_dict(include_evidence=True)
    without_ev = match.to_dict(include_evidence=False)
    # The default JSON shape (no evidence) is the pre-WS2 shape; evidence is the
    # only added key, and it sits last.
    assert list(with_ev) == [*without_ev, "evidence"]
    assert {k: with_ev[k] for k in without_ev} == without_ev


def test_default_find_json_is_evidence_free_but_explain_adds_it(tmp_path):
    result = find_artifacts(str(_corpus(tmp_path)), "photosynthesis")
    plain = json.loads(json_output.render_find_json(result))
    explained = json.loads(json_output.render_find_json(result, explain=True))
    assert "evidence" not in plain["matches"][0]
    assert "evidence" in explained["matches"][0]


# --- determinism (REQ-007) ---------------------------------------------------


def test_evidence_is_byte_stable_across_runs(tmp_path):
    root = _corpus(tmp_path)
    entries = build_repository_index(str(root)).artifacts
    a = json.dumps(search_index(entries, "photosynthesis").to_dict(), sort_keys=True)
    b = json.dumps(search_index(entries, "photosynthesis").to_dict(), sort_keys=True)
    assert a == b


# --- one source of truth: MCP payload == rac find --explain --json (REQ-004) -


def test_mcp_search_payload_equals_find_explain_json(tmp_path):
    root = str(_corpus(tmp_path))
    server = build_server(root)
    contents, _ = asyncio.run(server.call_tool("search_artifacts", {"query": "photosynthesis"}))
    mcp_payload = json.loads(contents[0].text)
    cli_payload = json.loads(
        json_output.render_find_json(find_artifacts(root, "photosynthesis"), explain=True)
    )
    assert mcp_payload == cli_payload
    assert mcp_payload["matches"][0]["evidence"]["field"] == "title"


# --- CLI --explain faces (REQ-004, REQ-006) ----------------------------------


def _run(argv: list[str], capsys) -> tuple[int, str]:
    try:
        code = cli.main(argv)
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
    return code, capsys.readouterr().out


def test_find_explain_human_appends_attribution(tmp_path, capsys):
    root = str(_corpus(tmp_path))
    code, out = _run(["find", "photosynthesis", root, "--explain"], capsys)
    assert code == 0
    assert "field=title" in out and "terms=photosynthesis" in out


def test_find_without_explain_is_unchanged(tmp_path, capsys):
    root = str(_corpus(tmp_path))
    _, plain = _run(["find", "photosynthesis", root], capsys)
    assert "field=" not in plain


def test_explain_composes_with_type_and_decisions(tmp_path, capsys):
    root = str(_corpus(tmp_path))
    code_t, out_t = _run(
        ["find", "photosynthesis", root, "--type", "decision", "--explain"], capsys
    )
    assert code_t == 0 and "field=title" in out_t
    code_d, out_d = _run(["find", "photosynthesis", root, "--decisions", "--explain"], capsys)
    assert code_d == 0 and "field=title" in out_d


def test_explain_empty_result_still_exits_zero(tmp_path, capsys):
    root = str(_corpus(tmp_path))
    code, out = _run(["find", "no-such-token-xyz", root, "--explain"], capsys)
    assert code == 0
    assert "No artifacts match" in out


def test_explain_json_matches_mcp_evidence_shape(tmp_path, capsys):
    root = str(_corpus(tmp_path))
    code, out = _run(["find", "photosynthesis", root, "--explain", "--json"], capsys)
    assert code == 0
    payload = json.loads(out)
    evidence = payload["matches"][0]["evidence"]
    assert _tier_evidence(evidence) == {
        "field": "title",
        "terms": ["photosynthesis"],
        "tier": 1,
    }
    # The score components (ADR-078) ride alongside the tier evidence, additively.
    assert set(evidence) == {"field", "terms", "tier", "score", "components"}
