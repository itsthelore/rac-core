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


def test_related_jira_edge_is_external_and_unresolved(tmp_path):
    (tmp_path / "adr-001.md").write_text(
        "# D\n\n## Status\n\nAccepted\n\n## Context\n\nc\n\n## Decision\n\nd\n\n"
        "## Consequences\n\nq\n\n## Related Jira\n\n- PROJ-1234\n",
        encoding="utf-8",
    )
    graph = build_graph_export(str(tmp_path))
    jira = [e for e in graph.edges if e.type == "related_jira"]
    assert len(jira) == 1
    assert jira[0].target == "PROJ-1234"
    assert jira[0].resolved is False
    assert jira[0].external is True  # distinct from a dangling in-corpus link
    assert "PROJ-1234" not in {n.id for n in graph.nodes}  # no phantom node


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
