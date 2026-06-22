"""Guide tool contracts — output shapes, truncation, errors (v0.10.0).

The golden practice applied to the MCP surface: every tool's output shape is
pinned against fixture corpora, truncation is pinned at whole-item boundaries,
and the structured error shapes are pinned to the resolver's own (ADR-007,
ADR-032, ADR-033). Equivalence tests prove the tool payloads are the same
objects the CLI's JSON output serializes — no second source of truth. A
freshness test edits the corpus between calls and observes the change, pinning
the stateless re-read contract (ADR-032).
"""

from __future__ import annotations

import asyncio
import json

import pytest
from conftest import fixture_path

from rac.mcp.budget import (
    DEFAULT_BUDGET,
    HINT_CONTENT,
    HINT_RELATED,
    HINT_SEARCH,
    HINT_SUMMARY,
    serialize,
)
from rac.mcp.server import build_server
from rac.output import json as json_output
from rac.services.portfolio import build_portfolio_summary
from rac.services.resolve import find_artifacts, find_decisions, resolve_artifact

CORPUS = fixture_path("mcp", "corpus")
DUPLICATE = fixture_path("mcp", "duplicate")

DEC = "RAC-MCPDEC000001"
REQ = "RAC-MCPREQ000001"
RDM = "RAC-MCPRDM000001"
DUP = "RAC-MCPDP0000001"


def call(root: str, tool: str, args: dict, budget: int = DEFAULT_BUDGET) -> dict:
    """Invoke a tool against ``root`` and parse its single JSON text result."""
    server = build_server(root, budget=budget)
    contents, _structured = asyncio.run(server.call_tool(tool, args))
    assert len(contents) == 1
    return json.loads(contents[0].text)


# --- get_artifact ------------------------------------------------------------


def test_get_artifact_resolved_shape():
    payload = call(CORPUS, "get_artifact", {"id": DEC})
    # WS11 + WS5: additive nested `provenance` — the reviewed status signal
    # (WS11) plus git-derived authorship/dates and status history (WS5). The
    # top-level keys are unchanged from before WS5 (purely additive, ADR-007).
    assert list(payload) == [
        "schema_version",
        "id",
        "type",
        "title",
        "path",
        "content",
        "provenance",
    ]
    prov = payload["provenance"]
    assert set(prov) == {
        "status",
        "last_committed",
        "last_author",
        "first_committed",
        "first_author",
        "status_history",
    }
    assert prov["status"] == "Accepted"
    # The fixture is git-tracked, so the git fields populate from its real
    # history; pin their shape (string-or-null, list), never the volatile values.
    assert isinstance(prov["status_history"], list)
    for git_field in ("last_committed", "last_author", "first_committed", "first_author"):
        assert prov[git_field] is None or isinstance(prov[git_field], str)
    assert payload["schema_version"] == "1"
    assert payload["id"] == DEC
    assert payload["type"] == "decision"
    assert payload["title"] == "Use an Event Bus"
    # content is the file text exactly as stored, frontmatter included.
    with open(payload["path"], encoding="utf-8") as fh:
        assert payload["content"] == fh.read()
    assert payload["content"].startswith("---\nschema_version: 1\n")
    assert "truncated" not in payload


def test_get_artifact_metadata_matches_cli_resolve_json():
    payload = call(CORPUS, "get_artifact", {"id": DEC})
    cli = json.loads(json_output.render_resolve_json(resolve_artifact(CORPUS, DEC)))
    # The resolver's answer (everything but the server-added content) is the
    # same object the CLI serializes.
    assert {k: payload[k] for k in cli} == cli


def test_get_artifact_not_found_error_shape():
    payload = call(CORPUS, "get_artifact", {"id": "RAC-MCPZZZ000099"})
    assert payload == {
        "schema_version": "1",
        "error": "not-found",
        "id": "RAC-MCPZZZ000099",
    }


def test_get_artifact_duplicate_error_shape():
    payload = call(DUPLICATE, "get_artifact", {"id": DUP})
    assert payload["schema_version"] == "1"
    assert payload["error"] == "duplicate"
    assert payload["id"] == DUP
    assert payload["paths"] == sorted(payload["paths"])
    assert len(payload["paths"]) == 2


def test_get_artifact_error_matches_cli_resolve_json():
    payload = call(DUPLICATE, "get_artifact", {"id": DUP})
    cli = json.loads(json_output.render_resolve_json(resolve_artifact(DUPLICATE, DUP)))
    assert payload == cli


# --- search_artifacts --------------------------------------------------------


def test_search_artifacts_shape_and_order():
    payload = call(CORPUS, "search_artifacts", {"query": "RAC-MCP"})
    assert list(payload) == ["schema_version", "query", "type", "match_count", "matches"]
    assert payload["query"] == "RAC-MCP"
    assert payload["type"] is None
    assert payload["match_count"] == 3
    for match in payload["matches"]:
        # WS2: search results carry an additive `evidence` object (always present).
        assert list(match) == ["id", "type", "title", "path", "evidence"]
        assert set(match["evidence"]) == {"field", "terms", "tier"}
    assert "truncated" not in payload


def test_search_artifacts_type_filter():
    payload = call(CORPUS, "search_artifacts", {"query": "RAC-MCP", "type": "decision"})
    assert payload["type"] == "decision"
    assert [m["id"] for m in payload["matches"]] == [DEC]


def test_search_artifacts_matches_cli_find_json():
    payload = call(CORPUS, "search_artifacts", {"query": "messaging"})
    # MCP search always carries evidence; the equal CLI face is `--explain --json`
    # (REQ-004, one source of truth).
    cli = json.loads(
        json_output.render_find_json(find_artifacts(CORPUS, "messaging"), explain=True)
    )
    assert payload == cli


def test_search_artifacts_empty_result_is_not_an_error():
    payload = call(CORPUS, "search_artifacts", {"query": "no-such-token"})
    assert payload["match_count"] == 0
    assert payload["matches"] == []
    assert "error" not in payload


def test_search_artifacts_body_match_carries_snippet():
    # `tightly` appears only in the requirement's body ("Services are tightly
    # coupled"). The body tier (ADR-038) surfaces it with section + snippet, and
    # the tool payload is byte-identical to the CLI's find JSON.
    payload = call(CORPUS, "search_artifacts", {"query": "tightly"})
    assert payload["match_count"] == 1
    match = payload["matches"][0]
    assert match["id"] == REQ
    assert match["section"] == "Problem"
    assert match["snippet"] == "Services are tightly coupled."
    cli = json.loads(json_output.render_find_json(find_artifacts(CORPUS, "tightly"), explain=True))
    assert payload == cli


def test_search_artifacts_metadata_match_omits_snippet_fields():
    # A title match (no body hit) keeps the four-field metadata shape exactly
    # (ADR-007): no section/snippet keys appear.
    payload = call(CORPUS, "search_artifacts", {"query": "decoupled", "type": "requirement"})
    assert [m["id"] for m in payload["matches"]] == [REQ]
    # No section/snippet on a metadata match; `evidence` is still additive.
    assert list(payload["matches"][0]) == ["id", "type", "title", "path", "evidence"]
    assert payload["matches"][0]["evidence"] == {
        "field": "title",
        "terms": ["decoupled"],
        "tier": 1,
    }


def test_search_snippet_match_truncates_as_whole_item():
    # A snippet-bearing match truncates as one whole item under a small budget:
    # the snippet rides inside its entry, so it is never split mid-element.
    full = call(CORPUS, "search_artifacts", {"query": "services"})
    assert full["match_count"] >= 2 and "truncated" not in full
    budget = 220
    payload = call(CORPUS, "search_artifacts", {"query": "services"}, budget=budget)
    assert payload["truncated"] is True
    assert payload["match_count"] == full["match_count"]
    assert len(payload["matches"]) < full["match_count"]
    # Every kept entry is structurally complete: either a metadata shape or a
    # metadata-plus-snippet shape, never a fragment.
    for m in payload["matches"]:
        assert {"id", "type", "title", "path", "evidence"} <= set(m)
        assert set(m) <= {"id", "type", "title", "path", "section", "snippet", "evidence"}
        if "snippet" in m or "section" in m:
            assert "section" in m and "snippet" in m


# --- find_decisions (v0.21.16, ADR-067) --------------------------------------


# A live and a retired decision sharing a topic token, so the live filter is the
# only thing that can separate them — pins the boundary, not just the search.
_LIVE_DECISION = """---
schema_version: 1
id: RAC-FD0000000001
type: decision
---
# Vault encryption policy

## Status

Accepted

## Context

Secrets need encryption at rest.

## Decision

Encrypt the vault with envelope keys.

## Consequences

Reads decrypt on access.
"""

_RETIRED_DECISION = """---
schema_version: 1
id: RAC-FD0000000002
type: decision
---
# Old vault approach

## Status

Superseded

## Context

An earlier vault design we replaced.

## Decision

Store the vault in plaintext.

## Consequences

Replaced.
"""


def _two_decision_corpus(tmp_path) -> str:
    root = tmp_path / "rac"
    (root / "decisions").mkdir(parents=True)
    (root / "decisions" / "live.md").write_text(_LIVE_DECISION, encoding="utf-8")
    (root / "decisions" / "old.md").write_text(_RETIRED_DECISION, encoding="utf-8")
    return str(root)


def test_find_decisions_shape_matches_search_contract():
    # The payload is the search contract plus the additive live-filter marker
    # (ADR-007): same keys search_artifacts returns, with type pinned to decision.
    payload = call(CORPUS, "find_decisions", {"topic": "event"})
    assert {"schema_version", "query", "type", "match_count", "matches"} <= set(payload)
    assert payload["type"] == "decision"
    assert payload["filter"] == "live-decisions"


def test_find_decisions_returns_live_decision_for_topic():
    # The fixture decision ("Use an Event Bus") is Accepted, so it is returned.
    payload = call(CORPUS, "find_decisions", {"topic": "event"})
    assert DEC in [m["id"] for m in payload["matches"]]


def test_find_decisions_excludes_retired(tmp_path):
    root = _two_decision_corpus(tmp_path)
    payload = call(root, "find_decisions", {"topic": "vault"})
    ids = [m["id"] for m in payload["matches"]]
    assert "RAC-FD0000000001" in ids
    assert "RAC-FD0000000002" not in ids  # Superseded — excluded


def test_find_decisions_matches_service_one_source_of_truth(tmp_path):
    # The tool serializes exactly what the find_decisions service returns, plus
    # the additive filter marker — no second retrieval path (ADR-031).
    root = _two_decision_corpus(tmp_path)
    payload = call(root, "find_decisions", {"topic": "vault"})
    service = find_decisions(root, "vault").to_dict()
    assert {k: v for k, v in payload.items() if k != "filter"} == service


def test_find_decisions_empty_topic_is_not_an_error():
    payload = call(CORPUS, "find_decisions", {"topic": "no-such-token"})
    assert payload["match_count"] == 0
    assert payload["matches"] == []
    assert "error" not in payload


# --- get_related -------------------------------------------------------------


def test_get_related_outgoing_and_incoming_shape():
    payload = call(CORPUS, "get_related", {"id": DEC})
    assert list(payload) == [
        "schema_version",
        "id",
        "type",
        "title",
        "path",
        "outgoing",
        "incoming",
    ]
    # outgoing: the artifact's own sections, snake_case, references as stored.
    assert payload["outgoing"] == {"related_requirements": [REQ]}
    # incoming: ordered by relationship type then ascending id (WS4, REQ-006).
    # Both edges are related_decisions, so RDM (...RDM...) precedes REQ (...REQ...).
    edge = {"direction": "incoming", "relationship": "related_decisions", "target": DEC}
    assert payload["incoming"] == [
        {
            "id": RDM,
            "type": "roadmap",
            "title": "Messaging Roadmap",
            "path": fixture_path("mcp", "corpus", "roadmap.md"),
            "section": "related_decisions",
            "evidence": edge,
        },
        {
            "id": REQ,
            "type": "requirement",
            "title": "Decoupled Messaging",
            "path": fixture_path("mcp", "corpus", "requirement.md"),
            "section": "related_decisions",
            "evidence": edge,
        },
    ]


def test_get_related_incoming_ordered_by_relationship_then_id():
    # WS4 (REQ-006): incoming is ordered by relationship type (canonical section
    # order) then ascending id, so budget tail-truncation is deterministic. Both
    # edges here are related_decisions, so ids ascend within that type.
    payload = call(CORPUS, "get_related", {"id": DEC})
    incoming = payload["incoming"]
    assert all(e["section"] == "related_decisions" for e in incoming)
    assert [e["id"] for e in incoming] == sorted(e["id"] for e in incoming)


def test_get_related_no_incoming_yields_empty_list():
    # The requirement is referenced by the decision and the roadmap, but a leaf
    # with no inbound references must still produce a valid empty incoming list.
    payload = call(CORPUS, "get_related", {"id": RDM})
    assert payload["incoming"] == []
    assert "related_decisions" in payload["outgoing"]


def test_get_related_not_found_error_shape():
    payload = call(CORPUS, "get_related", {"id": "RAC-MCPZZZ000099"})
    assert payload == {
        "schema_version": "1",
        "error": "not-found",
        "id": "RAC-MCPZZZ000099",
    }


def test_get_related_duplicate_error_shape():
    payload = call(DUPLICATE, "get_related", {"id": DUP})
    assert payload["error"] == "duplicate"
    assert payload["id"] == DUP


# --- get_summary -------------------------------------------------------------


def test_get_summary_matches_portfolio_to_dict():
    payload = call(CORPUS, "get_summary", {})
    assert payload == build_portfolio_summary(CORPUS, recursive=True).to_dict()


def test_get_summary_matches_cli_portfolio_json():
    payload = call(CORPUS, "get_summary", {})
    cli = json.loads(json_output.render_portfolio_json(build_portfolio_summary(CORPUS)))
    assert payload == cli


# --- determinism -------------------------------------------------------------


@pytest.mark.parametrize(
    "tool,args",
    [
        ("get_artifact", {"id": DEC}),
        ("search_artifacts", {"query": "RAC-MCP"}),
        ("get_related", {"id": DEC}),
        ("get_summary", {}),
    ],
)
def test_tool_output_is_deterministic(tool, args):
    first = build_server(CORPUS)
    second = build_server(CORPUS)
    out1 = asyncio.run(first.call_tool(tool, args))[0][0].text
    out2 = asyncio.run(second.call_tool(tool, args))[0][0].text
    assert out1 == out2


# --- truncation (budget enforcement) -----------------------------------------


def test_search_truncates_whole_matches_with_marker():
    # A budget that fits the envelope plus some but not all three matches.
    full = call(CORPUS, "search_artifacts", {"query": "RAC-MCP"})
    assert full["match_count"] == 3 and "truncated" not in full

    budget = 250
    payload = call(CORPUS, "search_artifacts", {"query": "RAC-MCP"}, budget=budget)
    assert payload["truncated"] is True
    assert payload["hint"] == HINT_SEARCH
    # match_count reports the true total; matches is a whole-item prefix.
    assert payload["match_count"] == 3
    assert len(payload["matches"]) < 3
    assert payload["omitted"] == 3 - len(payload["matches"])
    # Every kept match is a complete entry (never mid-element).
    for match in payload["matches"]:
        assert set(match) == {"id", "type", "title", "path", "evidence"}
    assert len(serialize(payload, budget)) <= budget or payload["matches"] == []


def test_related_truncates_whole_incoming_entries():
    budget = 300
    payload = call(CORPUS, "get_related", {"id": DEC}, budget=budget)
    assert payload["truncated"] is True
    assert payload["hint"] == HINT_RELATED
    assert payload["omitted"] == 2 - len(payload["incoming"])
    for entry in payload["incoming"]:
        assert set(entry) == {"id", "type", "title", "path", "section", "evidence"}


def test_artifact_truncates_content_tail():
    budget = 250
    payload = call(CORPUS, "get_artifact", {"id": DEC}, budget=budget)
    assert payload["truncated"] is True
    assert payload["hint"] == HINT_CONTENT
    full = call(CORPUS, "get_artifact", {"id": DEC})
    # The kept content is a head prefix of the full content (tail dropped).
    assert full["content"].startswith(payload["content"])
    assert payload["omitted"] == len(full["content"]) - len(payload["content"])


def test_truncated_marker_absent_on_complete_responses():
    for tool, args in [
        ("get_artifact", {"id": DEC}),
        ("search_artifacts", {"query": "RAC-MCP"}),
        ("get_related", {"id": DEC}),
        ("get_summary", {}),
    ]:
        payload = call(CORPUS, tool, args)
        assert "truncated" not in payload
        assert "omitted" not in payload
        assert "hint" not in payload


def test_serialize_respects_budget_at_boundary():
    # Whole-item truncation keeps the serialized response within budget once a
    # boundary fits, and the kept prefix is deterministic.
    payload = {
        "schema_version": "1",
        "query": "x",
        "type": None,
        "match_count": 3,
        "matches": [
            {"id": f"RAC-AAAAAAAAAA0{n}", "type": "t", "title": "T", "path": "p"} for n in range(3)
        ],
    }
    serialized = serialize(payload, budget=160)
    reparsed = json.loads(serialized)
    assert reparsed["truncated"] is True
    assert len(reparsed["matches"]) < 3


# --- freshness (stateless re-read, ADR-032) ----------------------------------


def test_each_call_rereads_the_repository(tmp_path):
    artifact = tmp_path / "thing.md"
    artifact.write_text(
        "---\nschema_version: 1\nid: RAC-MCPFRESH0001\ntype: decision\n---\n"
        "# Original Title\n\n## Status\n\nAccepted\n\n## Category\n\nArchitecture\n\n"
        "## Context\n\nC.\n\n## Decision\n\nD.\n\n## Consequences\n\nE.\n",
        encoding="utf-8",
    )
    root = str(tmp_path)

    before = call(root, "get_artifact", {"id": "RAC-MCPFRESH0001"})
    assert before["title"] == "Original Title"

    # Edit the file between calls; a stateless server must observe the change.
    artifact.write_text(
        artifact.read_text(encoding="utf-8").replace("Original Title", "Edited Title"),
        encoding="utf-8",
    )

    after = call(root, "get_artifact", {"id": "RAC-MCPFRESH0001"})
    assert after["title"] == "Edited Title"
    assert "Edited Title" in after["content"]


# --- unreadable artifact (errors as data, never protocol exceptions) ---------


def test_get_artifact_unreadable_returns_structured_error(tmp_path, monkeypatch):
    # A file that resolves but whose bytes cannot be read (deleted between walk
    # and read, permissions, non-UTF-8) must surface as the `unreadable` error
    # shape, never as a protocol exception. Monkeypatch the read so the test is
    # deterministic and independent of the runner's privileges (chmod 000 does
    # not block root on CI).
    artifact = tmp_path / "thing.md"
    artifact.write_text(
        "---\nschema_version: 1\nid: RAC-MNRDA0000001\ntype: decision\n---\n"
        "# Unreadable\n\n## Status\n\nAccepted\n\n## Category\n\nArchitecture\n\n"
        "## Context\n\nC.\n\n## Decision\n\nD.\n\n## Consequences\n\nE.\n",
        encoding="utf-8",
    )
    root = str(tmp_path)

    def _boom(_path: str) -> str:
        raise OSError("file vanished")

    monkeypatch.setattr("rac.mcp.server._read_content", _boom)

    payload = call(root, "get_artifact", {"id": "RAC-MNRDA0000001"})
    assert payload == {
        "schema_version": "1",
        "error": "unreadable",
        "id": "RAC-MNRDA0000001",
        "path": str(artifact),
    }


def test_get_artifact_non_utf8_returns_unreadable(tmp_path, monkeypatch):
    # A non-UTF-8 read surfaces the same structured shape (UnicodeDecodeError is
    # caught alongside OSError).
    artifact = tmp_path / "thing.md"
    artifact.write_text(
        "---\nschema_version: 1\nid: RAC-MNRDB0000001\ntype: decision\n---\n"
        "# Bytes\n\n## Status\n\nAccepted\n\n## Category\n\nArchitecture\n\n"
        "## Context\n\nC.\n\n## Decision\n\nD.\n\n## Consequences\n\nE.\n",
        encoding="utf-8",
    )
    root = str(tmp_path)

    def _bad_bytes(_path: str) -> str:
        raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")

    monkeypatch.setattr("rac.mcp.server._read_content", _bad_bytes)

    payload = call(root, "get_artifact", {"id": "RAC-MNRDB0000001"})
    assert payload["error"] == "unreadable"
    assert payload["id"] == "RAC-MNRDB0000001"
    assert payload["path"] == str(artifact)


# --- get_summary truncation hint ---------------------------------------------


def test_get_summary_over_budget_uses_summary_hint():
    # get_summary has no truncatable field; an over-budget summary is marked
    # (omitted == 0) with the summary-specific hint, not the content hint.
    budget = 50
    payload = call(CORPUS, "get_summary", {}, budget=budget)
    assert payload["truncated"] is True
    assert payload["omitted"] == 0
    assert payload["hint"] == HINT_SUMMARY


# --- unicode / multibyte budget accounting -----------------------------------


def test_budget_counts_characters_not_bytes_for_content():
    # The budget is a character count (ADR-033): a content of N multibyte
    # characters truncates by character count, independent of UTF-8 byte width.
    multibyte = "é" * 500  # each char is 2 bytes in UTF-8, 1 character
    payload = {
        "schema_version": "1",
        "id": "RAC-MCPDEC000001",
        "type": "decision",
        "title": "T",
        "path": "p.md",
        "content": multibyte,
    }
    full_len = len(serialize(payload))
    # Choose a budget below the full length so truncation must occur.
    budget = full_len - 100
    reparsed = json.loads(serialize(payload, budget))
    assert reparsed["truncated"] is True
    # The kept content is a head prefix measured in characters.
    assert multibyte.startswith(reparsed["content"])
    assert reparsed["omitted"] == len(multibyte) - len(reparsed["content"])
    # Character budget honored: serialized length stays within budget.
    assert len(serialize(reparsed, budget)) <= budget


def test_budget_multibyte_search_match_count_is_characters():
    # A search response whose serialized form is multibyte still truncates at
    # whole-match boundaries by character count.
    matches = [
        {"id": f"RAC-AAAAAAAAAA0{n}", "type": "t", "title": "café", "path": "naïve.md"}
        for n in range(5)
    ]
    payload = {
        "schema_version": "1",
        "query": "café",
        "type": None,
        "match_count": len(matches),
        "matches": matches,
    }
    reparsed = json.loads(serialize(payload, budget=200))
    assert reparsed["truncated"] is True
    assert reparsed["match_count"] == 5
    assert len(reparsed["matches"]) < 5
    assert reparsed["omitted"] == 5 - len(reparsed["matches"])


# --- over-budget fallback branches (envelope alone exceeds budget) -----------


def test_search_envelope_over_budget_yields_empty_matches_still_marked():
    # When even the empty-list envelope exceeds the budget, the list path
    # returns an empty `matches`, fully omitted, but still structurally valid
    # and marked (ADR-033: a valid over-budget response beats unparseable noise).
    payload = call(CORPUS, "search_artifacts", {"query": "RAC-MCP"}, budget=10)
    assert payload["truncated"] is True
    assert payload["matches"] == []
    assert payload["omitted"] == payload["match_count"] == 3
    assert payload["hint"] == HINT_SEARCH


def test_content_envelope_over_budget_yields_empty_content_still_marked():
    # The content path shrinks to an empty content string under a tiny budget,
    # still marked and parseable.
    payload = call(CORPUS, "get_artifact", {"id": DEC}, budget=10)
    assert payload["truncated"] is True
    assert payload["content"] == ""
    full = call(CORPUS, "get_artifact", {"id": DEC})
    assert payload["omitted"] == len(full["content"])


# --- type filter combined with truncation ------------------------------------


def test_search_type_filter_with_truncation():
    # A type-filtered search whose results still overflow a tiny budget
    # truncates at whole-match boundaries and preserves the filter in output.
    full = call(CORPUS, "search_artifacts", {"query": "RAC-MCP"})
    assert full["match_count"] == 3
    payload = call(
        CORPUS, "search_artifacts", {"query": "RAC-MCP", "type": "requirement"}, budget=180
    )
    assert payload["type"] == "requirement"
    assert payload["truncated"] is True
    # match_count reflects the filtered total, not the unfiltered one.
    assert payload["match_count"] == 1
    assert len(payload["matches"]) < payload["match_count"] or payload["matches"] == []


# --- get_related: ambiguous references and zero-outgoing leaves --------------

_DEC_TMPL = (
    "---\nschema_version: 1\nid: {id}\ntype: decision\n---\n"
    "# {title}\n\n## Status\n\nAccepted\n\n## Category\n\nArchitecture\n\n"
    "## Context\n\nC.\n\n## Decision\n\nD.\n\n## Consequences\n\nE.\n"
)


def test_get_related_ambiguous_reference_yields_no_incoming_edge(tmp_path):
    # `a/shared.md` resolves uniquely by its canonical frontmatter id, but both
    # files also answer to the filename-stem alias "shared". A reference to
    # "shared" is therefore ambiguous and must contribute no incoming edge —
    # resolution stays Core-owned (ADR-031); an unresolved (ambiguous) reference
    # is not an edge.
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "a" / "shared.md").write_text(
        _DEC_TMPL.format(id="RAC-AMBTGT000001", title="Target"), encoding="utf-8"
    )
    (tmp_path / "b" / "shared.md").write_text(
        _DEC_TMPL.format(id="RAC-AMBSEC000001", title="Other"), encoding="utf-8"
    )
    # A roadmap whose Related Decisions reference is the ambiguous stem "shared".
    (tmp_path / "roadmap.md").write_text(
        "---\nschema_version: 1\nid: RAC-AMBRDM000001\ntype: roadmap\n---\n"
        "# Source\n\n## Outcomes\n\nO.\n\n## Initiatives\n\nI.\n\n"
        "## Related Decisions\n\n- shared\n",
        encoding="utf-8",
    )
    payload = call(str(tmp_path), "get_related", {"id": "RAC-AMBTGT000001"})
    assert payload["id"] == "RAC-AMBTGT000001"
    assert payload["incoming"] == []


def test_get_related_zero_outgoing_yields_empty_outgoing_object(tmp_path):
    # An artifact that declares no relationship sections must produce an empty
    # `outgoing` object (a JSON object, not null or a list).
    (tmp_path / "leaf.md").write_text(
        _DEC_TMPL.format(id="RAC-MEAFDEC00001", title="Leaf"), encoding="utf-8"
    )
    payload = call(str(tmp_path), "get_related", {"id": "RAC-MEAFDEC00001"})
    assert payload["outgoing"] == {}
    assert payload["incoming"] == []


# --- walk-count regression: get_related performs exactly one corpus walk ------


def test_get_related_performs_exactly_one_corpus_walk(monkeypatch):
    # Change 1 collapses get_related to a single corpus walk feeding index and
    # relationships. Spy the canonical walk seam and assert it fires once.
    import rac.mcp.server as server

    calls = {"count": 0}
    real_walk = server.walk_corpus

    def _spy(*args, **kwargs):
        calls["count"] += 1
        return real_walk(*args, **kwargs)

    monkeypatch.setattr(server, "walk_corpus", _spy)

    server_obj = build_server(CORPUS)
    asyncio.run(server_obj.call_tool("get_related", {"id": DEC}))
    assert calls["count"] == 1


# --- get_related bounded multi-hop (v0.24, WS-D) -----------------------------


def _chain_corpus(root) -> None:
    """Three decisions linked head->tail: dec1 -> dec2 -> dec3."""
    from pathlib import Path

    base = Path(root)
    ids = ["RAC-MCPCHN000001", "RAC-MCPCHN000002", "RAC-MCPCHN000003"]
    for i, ident in enumerate(ids):
        link = f"\n## Related Decisions\n\n- {ids[i + 1]}\n" if i + 1 < len(ids) else ""
        (base / f"dec{i + 1}.md").write_text(
            f"---\nschema_version: 1\nid: {ident}\ntype: decision\n---\n"
            f"# Chain {i + 1}\n\n## Status\n\nAccepted\n\n## Category\n\nArchitecture\n\n"
            f"## Context\n\nC.\n\n## Decision\n\nD.\n\n## Consequences\n\nX.\n{link}",
            encoding="utf-8",
        )


def test_get_related_depth_one_has_no_neighborhood_field(tmp_path):
    _chain_corpus(tmp_path)
    payload = call(str(tmp_path), "get_related", {"id": "RAC-MCPCHN000001"})
    assert "neighborhood" not in payload and "depth" not in payload


def test_get_related_depth_two_surfaces_two_hop_neighbour(tmp_path):
    _chain_corpus(tmp_path)
    payload = call(str(tmp_path), "get_related", {"id": "RAC-MCPCHN000001", "depth": 2})
    assert payload["depth"] == 2
    # dec1 -> dec2 (1 hop, already in outgoing) -> dec3 (2 hops, in neighborhood).
    hood = {(n["id"], n["hops"]) for n in payload["neighborhood"]}
    assert ("RAC-MCPCHN000003", 2) in hood
