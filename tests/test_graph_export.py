"""Tests for `rac export --graph` (v0.25.0 WS2, requirement rac-corpus-graph-export,
ADR-074).

The graph projection surfaces the *typed* relationship graph (ADR-055) for graph
backends — edges carry their registry kind and direction — while the viewer JSON's
flattened ``relates-to`` contract is unchanged. These tests pin the typed edges,
direction, resolved/unresolved handling, determinism (ADR-002), and additivity.
"""

from __future__ import annotations

import json

import pytest
from conftest import fixture_path

from rac.cli import main
from rac.services.export import build_graph_export

EXIT_USAGE = 2


# --- service layer -----------------------------------------------------------


def test_nodes_are_classified_artifacts_in_sorted_order():
    graph = build_graph_export(fixture_path("export"))
    assert [n.id for n in graph.nodes] == [
        "RAC-00000000EXP1",
        "notes-raw-html",
        "v0-portal-roadmap",
    ]
    assert all(n.type and n.status and n.title for n in graph.nodes)


def test_edges_are_typed_and_sorted():
    graph = build_graph_export(fixture_path("export"))
    types = {e.type for e in graph.edges}
    # Typed, not flattened to a single relates-to.
    assert types == {"related_requirements", "related_roadmaps", "related_decisions"}
    keys = [(e.source, e.type, e.target) for e in graph.edges]
    assert keys == sorted(keys)


def test_unresolved_reference_kept_and_flagged():
    graph = build_graph_export(fixture_path("export"))
    by_target = {e.target: e for e in graph.edges}
    # The dangling reference is preserved with its literal target, flagged, and
    # creates no node.
    dangling = by_target["REQ-DOES-NOT-EXIST"]
    assert dangling.resolved is False
    assert "REQ-DOES-NOT-EXIST" not in {n.id for n in graph.nodes}


def test_resolved_related_edge_is_undirected():
    graph = build_graph_export(fixture_path("export"))
    edge = next(e for e in graph.edges if e.type == "related_roadmaps")
    assert edge.resolved is True
    assert edge.directed is False  # related_* edges are undirected (ADR-055)


def test_supersedes_edge_is_directed_and_resolved():
    graph = build_graph_export(fixture_path("graph"))
    supersedes = [e for e in graph.edges if e.type == "supersedes"]
    assert len(supersedes) == 1
    edge = supersedes[0]
    assert edge.source == "RAC-00000000GRP2"  # adr-new
    assert edge.target == "RAC-00000000GRP1"  # adr-old, resolved to its canonical id
    assert edge.directed is True
    assert edge.resolved is True
    # The superseded node is still present, with its retired status.
    by_id = {n.id: n for n in graph.nodes}
    assert by_id["RAC-00000000GRP1"].status == "Superseded"


def test_build_graph_deterministic():
    first = build_graph_export(fixture_path("export")).to_dict()
    second = build_graph_export(fixture_path("export")).to_dict()
    assert first == second


# --- external ticket edges (ADR-087) -----------------------------------------


def _corpus_with_tickets(tmp_path, provider: str | None) -> None:
    config = tmp_path / ".rac"
    config.mkdir()
    body = "repository_key: ACME\n"
    if provider is not None:
        body += f"ticketing:\n  provider: {provider}\n"
    (config / "config.yaml").write_text(body, encoding="utf-8")
    (tmp_path / "adr-001.md").write_text(
        "# A1\n\n## Context\n\nc\n\n## Decision\n\nd\n\n## Consequences\n\nq\n\n"
        "## Related Tickets\n\n- PROJ-1234\n",
        encoding="utf-8",
    )


def test_external_ticket_edge_is_marked_and_invents_no_node(tmp_path):
    _corpus_with_tickets(tmp_path, "jira")
    graph = build_graph_export(str(tmp_path))
    ticket_edges = [e for e in graph.edges if e.type == "related_tickets"]
    assert len(ticket_edges) == 1
    edge = ticket_edges[0]
    assert edge.target == "PROJ-1234"
    assert edge.external is True
    assert edge.resolved is False
    assert edge.provider == "jira"
    # The external target is never promoted to a node.
    assert "PROJ-1234" not in {n.id for n in graph.nodes}


def test_external_ticket_provider_is_none_when_unset(tmp_path):
    _corpus_with_tickets(tmp_path, None)
    graph = build_graph_export(str(tmp_path))
    edge = next(e for e in graph.edges if e.type == "related_tickets")
    assert edge.external is True and edge.resolved is False
    assert edge.provider is None


# --- external-target verification edges (ADR-096) ----------------------------


def _corpus_with_verified_by(tmp_path, provider: str | None) -> None:
    """A requirement declaring ## Verified By, with an optional ticketing provider."""
    config = tmp_path / ".rac"
    config.mkdir()
    body = "repository_key: ACME\n"
    if provider is not None:
        body += f"ticketing:\n  provider: {provider}\n"
    (config / "config.yaml").write_text(body, encoding="utf-8")
    (tmp_path / "req-001.md").write_text(
        "# Cap\n\n## Problem\n\np\n\n## Requirements\n\n- [REQ-001] r\n\n"
        "## Verified By\n\n- `tests/cap.spec.ts`\n",
        encoding="utf-8",
    )


def test_verified_by_edge_is_external_directed_and_invents_no_node(tmp_path):
    _corpus_with_verified_by(tmp_path, None)
    graph = build_graph_export(str(tmp_path))
    edges = [e for e in graph.edges if e.type == "verified_by"]
    assert len(edges) == 1
    edge = edges[0]
    assert edge.target == "`tests/cap.spec.ts`"  # literal reference text
    assert edge.external is True
    assert edge.resolved is False
    assert edge.directed is True  # capability -> verifier (ADR-096)
    # The external file target is never promoted to a node.
    assert "`tests/cap.spec.ts`" not in {n.id for n in graph.nodes}


def test_verified_by_edge_is_never_tagged_with_the_ticketing_provider(tmp_path):
    # verified_by is external but its target is a file path, not a ticket — so
    # even when a ticketing provider is configured it must stay unprovidered
    # (distinct from related_tickets, ADR-096).
    _corpus_with_verified_by(tmp_path, "jira")
    graph = build_graph_export(str(tmp_path))
    edge = next(e for e in graph.edges if e.type == "verified_by")
    assert edge.external is True
    assert edge.provider is None


# --- CLI ---------------------------------------------------------------------


def test_cli_graph_emits_single_json(capsys):
    assert main(["export", fixture_path("graph"), "--graph"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == "1"
    assert payload["source"] == "graph"
    assert {n["id"] for n in payload["nodes"]} == {"RAC-00000000GRP1", "RAC-00000000GRP2"}
    edge = next(e for e in payload["edges"] if e["type"] == "supersedes")
    assert edge["directed"] is True and edge["resolved"] is True


def test_cli_graph_deterministic(capsys):
    assert main(["export", fixture_path("export"), "--graph"]) == 0
    first = capsys.readouterr().out
    assert main(["export", fixture_path("export"), "--graph"]) == 0
    assert capsys.readouterr().out == first


def test_cli_graph_leaves_default_export_untouched(capsys):
    assert main(["export", fixture_path("export"), "--graph"]) == 0
    graph_out = capsys.readouterr().out
    assert main(["export", fixture_path("export")]) == 0
    viewer = capsys.readouterr().out
    # The viewer keeps its flattened, untyped relates-to edges (ADR-074); the
    # graph mode is separate and additive.
    assert '"type": "relates-to"' in viewer
    assert '"type": "relates-to"' not in graph_out
    assert '"type": "supersedes"' not in viewer


def test_cli_graph_out_rejected(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["export", fixture_path("graph"), "--graph", "--out", "g.json"])
    assert exc.value.code == EXIT_USAGE
    assert "--out requires" in capsys.readouterr().err
