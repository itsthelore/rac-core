"""Characterization tests for the export / portfolio / stats cluster.

These characterization tests were added before the rebuild-scale examiner freeze.
They pin the *current* observable behavior of the report cluster exactly — even
where it is incidental or odd — so a from-scratch rebuild that diverges is caught.
Nothing here asserts what the behavior *ought* to be; every expected value was
produced by running the current code.

Priority pinning is the frozen cross-repo (rac-connectors) export contract:
``decided export --graph`` and ``decided export --documents`` are byte-pinned — field
order, the ``external``/``provider`` keys carried on *ordinary* in-corpus edges,
compact-vs-spaced separators, and ``ensure_ascii=False`` UTF-8 bodies — because
a connector parses those bytes. The portfolio/stats pins lock the health-score
formula, completeness rounding, attention message format, and human layout on a
small deterministic corpus (no git-derived fields).

Covers charmap findings 1-8 (report.md, export/portfolio/stats cluster).
"""

from __future__ import annotations

from conftest import fixture_path

from asdecided.cli import main
from asdecided.output import human
from asdecided.output.json import (
    render_documents_jsonl,
    render_graph_json,
    render_stats_json,
)
from asdecided.services.export import build_documents_export, build_graph_export
from asdecided.services.portfolio import build_portfolio_summary
from asdecided.services.stats import collect_stats

# The graph fixture's whole-graph JSON, byte-for-byte. It contains no
# filesystem paths, and ``source`` is the directory basename ("graph"), so the
# bytes are identical regardless of how the fixture is addressed.
EXPECTED_GRAPH_JSON = """{
  "schema_version": "1",
  "source": "graph",
  "nodes": [
    {
      "id": "RAC-00000000GRP2",
      "type": "decision",
      "status": "Accepted",
      "title": "ADR-NEW: The Replacement Choice"
    },
    {
      "id": "RAC-00000000GRP1",
      "type": "decision",
      "status": "Superseded",
      "title": "ADR-OLD: The Superseded Choice"
    }
  ],
  "edges": [
    {
      "source": "RAC-00000000GRP2",
      "target": "RAC-00000000GRP1",
      "type": "supersedes",
      "directed": true,
      "resolved": true,
      "external": false,
      "provider": null
    }
  ]
}"""


# ---------------------------------------------------------------------------
# Finding 1 (HIGH) — the frozen cross-repo edge contract: every edge carries
# the full seven-key set, including ``external``/``provider`` on ordinary edges.
# ---------------------------------------------------------------------------


def test_ordinary_undirected_edge_carries_full_key_set():
    graph = build_graph_export(fixture_path("export"))
    edge = next(e for e in graph.edges if e.type == "related_roadmaps")
    # A plain in-corpus resolved edge still emits external=false / provider=null
    # — a connector reading edge["provider"] must find the key present.
    assert edge.to_dict() == {
        "source": edge.source,
        "target": edge.target,
        "type": "related_roadmaps",
        "directed": False,
        "resolved": True,
        "external": False,
        "provider": None,
    }


def test_ordinary_directed_edge_carries_full_key_set():
    graph = build_graph_export(fixture_path("graph"))
    edge = next(e for e in graph.edges if e.type == "supersedes")
    assert edge.to_dict() == {
        "source": "RAC-00000000GRP2",
        "target": "RAC-00000000GRP1",
        "type": "supersedes",
        "directed": True,
        "resolved": True,
        "external": False,
        "provider": None,
    }


def test_edge_key_order_is_pinned():
    graph = build_graph_export(fixture_path("export"))
    edge = graph.edges[0]
    assert list(edge.to_dict()) == [
        "source",
        "target",
        "type",
        "directed",
        "resolved",
        "external",
        "provider",
    ]


# ---------------------------------------------------------------------------
# Finding 2 (HIGH) — graph JSON & documents JSONL serialization form / order.
# ---------------------------------------------------------------------------


def test_graph_json_is_byte_pinned():
    # The whole-graph object is the graph-backend contract; pin it byte-for-byte
    # (2-space indent, key order, `false`/`null` literals, sorted nodes/edges).
    assert render_graph_json(build_graph_export(fixture_path("graph"))) == EXPECTED_GRAPH_JSON


def test_cli_graph_json_byte_pinned(capsys):
    # The CLI wraps the same bytes in a single print() → one trailing newline.
    assert main(["export", fixture_path("graph"), "--graph"]) == 0
    assert capsys.readouterr().out == EXPECTED_GRAPH_JSON + "\n"


def test_graph_node_and_wrapper_key_order():
    graph = build_graph_export(fixture_path("export"))
    assert list(graph.nodes[0].to_dict()) == ["id", "type", "status", "title"]
    assert list(graph.to_dict()) == ["schema_version", "source", "nodes", "edges"]


def test_documents_record_key_order():
    rec = build_documents_export(fixture_path("export")).documents[0].to_dict("export")
    assert list(rec) == [
        "schema_version",
        "id",
        "type",
        "status",
        "title",
        "text",
        "metadata",
    ]
    assert list(rec["metadata"]) == ["path", "aliases", "tags", "source"]


# ---------------------------------------------------------------------------
# Findings 3 + 8 (MEDIUM / LOW) — documents JSONL is UTF-8 (not \\uXXXX-escaped)
# and uses default spaced separators, byte-for-byte on the full line.
# ---------------------------------------------------------------------------


def test_documents_jsonl_line_is_byte_pinned_utf8_and_spaced(tmp_path):
    corpus = tmp_path / "docu"
    corpus.mkdir()
    body = (
        "# Café\n\n## Status\n\nAccepted\n\n## Context\n\nnaïve — €\n\n"
        "## Decision\n\nd\n\n## Consequences\n\nq\n"
    )
    (corpus / "adr.md").write_text(body, encoding="utf-8")

    line = render_documents_jsonl(build_documents_export(str(corpus)))

    # ensure_ascii=False: multibyte characters survive literally, never escaped.
    assert "Café" in line and "naïve — €" in line
    assert "\\u" not in line
    # Default separators ", " / ": " (not compact) — space after every colon.
    assert '"schema_version": "1"' in line

    expected = (
        '{"schema_version": "1", "id": "adr", "type": "decision", '
        '"status": "Accepted", "title": "Café", '
        '"text": "# Café\\n\\n## Status\\n\\nAccepted\\n\\n## Context\\n\\n'
        'naïve — €\\n\\n## Decision\\n\\nd\\n\\n## Consequences\\n\\nq\\n", '
        '"metadata": {"path": "' + str(corpus / "adr.md") + '", '
        '"aliases": ["adr"], "tags": [], "source": "docu"}}'
    )
    assert line == expected


# ---------------------------------------------------------------------------
# Finding 7 (LOW) — empty-corpus documents/graph output.
# ---------------------------------------------------------------------------


def test_empty_corpus_documents_and_graph(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    assert render_documents_jsonl(build_documents_export(str(empty))) == ""
    assert render_graph_json(build_graph_export(str(empty))) == (
        '{\n  "schema_version": "1",\n  "source": "empty",\n  "nodes": [],\n  "edges": []\n}'
    )


def test_cli_empty_corpus_documents_prints_single_newline(tmp_path, capsys):
    empty = tmp_path / "empty"
    empty.mkdir()
    assert main(["export", str(empty), "--documents"]) == 0
    # An empty JSONL body still goes through print(), so the CLI emits "\n".
    assert capsys.readouterr().out == "\n"


# ---------------------------------------------------------------------------
# Portfolio corpus (findings 5 / 6 support) — a deterministic two-artifact
# corpus with no git-derived fields, exercising the health formula, completeness
# rounding, and both attention codes.
# ---------------------------------------------------------------------------


def _portfolio_corpus(root):
    """A valid+complete decision plus a requirement with one broken ref and a
    missing recommended section. Named subdir so ``directory`` is deterministic."""
    corpus = root / "pf"
    corpus.mkdir()
    (corpus / "adr.md").write_text(
        "# ADR: Use Widgets\n\n## Status\n\nAccepted\n\n## Context\n\n"
        "We need a component model.\n\n## Decision\n\nUse widgets everywhere.\n\n"
        "## Consequences\n\n- Simplicity.\n\n## Category\n\nArchitecture\n\n"
        "## Alternatives Considered\n\n- Gadgets.\n",
        encoding="utf-8",
    )
    (corpus / "req.md").write_text(
        "# Widget Rendering\n\n## Problem\n\nWidgets must render fast.\n\n"
        "## Requirements\n\n- [REQ-001] Render within 16ms.\n\n"
        "## Related Decisions\n\n- MISSING-ADR\n",
        encoding="utf-8",
    )
    return corpus


# ---------------------------------------------------------------------------
# Finding 5 (MEDIUM) — portfolio JSON scalar fields (health.score integer from
# the 0.5/0.25/0.25 formula, completeness.ratio 4dp, attention message format).
# ---------------------------------------------------------------------------


def test_portfolio_json_scalars_and_attention_pinned(tmp_path):
    corpus = _portfolio_corpus(tmp_path)
    d = build_portfolio_summary(str(corpus)).to_dict()

    assert d["directory"] == str(corpus)
    assert d["recursive"] is True
    assert d["empty"] is False
    assert d["artifacts"]["by_type"] == {
        "requirement": 1,
        "decision": 1,
        "roadmap": 0,
        "prompt": 0,
        "design": 0,
        "unknown": 0,
    }
    assert d["validation"] == {"valid": 2, "invalid": 0}
    # completeness: 3 filled / 6 recommended slots → 0.5 (rounded 4dp).
    assert d["completeness"] == {"recommended_slots": 6, "filled": 3, "ratio": 0.5}
    assert d["relationships"] == {
        "total": 1,
        "valid": 0,
        "broken": 1,
        "orphaned": 2,
        "coverage": 0.5,
    }
    # health = round(100 * (0.5*1.0 + 0.25*0.5 + 0.25*0.0)) = round(62.5) = 62.
    # (Pins Python banker's rounding of the .5 boundary, too.)
    assert d["health"] == {"score": 62}
    assert d["validation_status"] == {
        "artifacts_ok": True,
        "relationships_ok": False,
        "ok": False,
    }

    # Attention: broken-relationship then missing-recommended (both warnings,
    # tie-broken by path then code). Message formats pinned verbatim.
    assert d["attention"] == [
        {
            "path": str(corpus / "req.md"),
            "identifier": "req",
            "severity": "warning",
            "code": "broken-relationship",
            "message": "Related Decisions references missing artifact: MISSING-ADR",
        },
        {
            "path": str(corpus / "req.md"),
            "identifier": "req",
            "severity": "warning",
            "code": "missing-recommended-sections",
            "message": "Missing recommended sections: Success Metrics, Risks, Assumptions",
        },
    ]


# ---------------------------------------------------------------------------
# Finding 5 (MEDIUM) — portfolio human layout, byte-for-byte (color disabled).
# ---------------------------------------------------------------------------


def test_portfolio_human_layout_pinned(tmp_path, monkeypatch):
    corpus = _portfolio_corpus(tmp_path)
    # Color is a stdout.isatty() flag latched at import; force it off so the
    # bytes are stable regardless of how the test process is attached.
    monkeypatch.setattr(human, "_USE_COLOR", False)
    s = build_portfolio_summary(str(corpus))
    expected = (
        "Repository Summary\n"
        "==================\n"
        "\n"
        f"Directory:  {corpus}\n"
        "Artifacts:  2\n"
        "\n"
        "By Type\n"
        "-------\n"
        "\n"
        "  Requirement    1\n"
        "  Decision       1\n"
        "\n"
        "Validation\n"
        "----------\n"
        "\n"
        "  Valid:    2\n"
        "  Invalid:  0\n"
        "\n"
        "Completeness\n"
        "------------\n"
        "\n"
        "  50% (3 / 6 recommended slots filled)\n"
        "\n"
        "Relationships\n"
        "-------------\n"
        "\n"
        "  Total:    1\n"
        "  Valid:    0\n"
        "  Broken:   1\n"
        "  Orphaned: 2\n"
        "  Coverage: 50%\n"
        "\n"
        "Attention (2 items)\n"
        "----------\n"
        "\n"
        "  ! req\n"
        "      Related Decisions references missing artifact: MISSING-ADR\n"
        "  ! req\n"
        "      Missing recommended sections: Success Metrics, Risks, Assumptions\n"
        "\n"
        "Health Score\n"
        "------------\n"
        "\n"
        "  62 / 100"
    )
    assert human.render_portfolio_human(s) == expected


# ---------------------------------------------------------------------------
# Stats corpus (findings 4 / 6 support) — a decision (status + category) and a
# requirement declaring a resolved relationship.
# ---------------------------------------------------------------------------


def _stats_corpus(root):
    corpus = root / "st"
    corpus.mkdir()
    (corpus / "adr.md").write_text(
        "# ADR: Adopt Widgets\n\n## Status\n\nAccepted\n\n## Context\n\nCtx.\n\n"
        "## Decision\n\nUse widgets.\n\n## Consequences\n\n- Simplicity.\n\n"
        "## Category\n\nArchitecture\n",
        encoding="utf-8",
    )
    (corpus / "req.md").write_text(
        "# Widget Rendering\n\n## Problem\n\nFast render.\n\n## Requirements\n\n"
        "- [REQ-001] Render fast.\n\n## Related Decisions\n\n- adr\n",
        encoding="utf-8",
    )
    return corpus


# ---------------------------------------------------------------------------
# Finding 4 (MEDIUM) — stats JSON decision sub-object (by_status/by_category)
# and the relationships block keyed by section.replace(" ", "_").
# ---------------------------------------------------------------------------


def test_stats_json_decisions_and_relationships_pinned(tmp_path):
    import json

    corpus = _stats_corpus(tmp_path)
    payload = json.loads(render_stats_json(collect_stats(str(corpus))))

    assert payload["decisions"] == {
        "count": 1,
        "by_status": {"Accepted": 1},
        "by_category": {"Architecture": 1},
    }
    # Section label "Related Decisions" is re-keyed to "related_decisions".
    assert payload["relationships"] == {"related_decisions": 1}
    # Key order inside the decisions sub-object is pinned.
    assert list(payload["decisions"]) == ["count", "by_status", "by_category"]


# ---------------------------------------------------------------------------
# Finding 6 (MEDIUM) — stats human Decisions / Status / Category / Relationships
# sections. The human stats output carries no directory line, so it is fully
# byte-stable and pinned in whole.
# ---------------------------------------------------------------------------


def test_stats_human_all_sections_pinned(tmp_path, monkeypatch):
    corpus = _stats_corpus(tmp_path)
    monkeypatch.setattr(human, "_USE_COLOR", False)
    expected = (
        "Portfolio Overview\n"
        "==================\n"
        "\n"
        "Features: 1\n"
        "Requirements: 1\n"
        "Metrics: 0\n"
        "Risks: 0\n"
        "\n"
        "Quality\n"
        "=======\n"
        "\n"
        "Features Missing Metrics: 1\n"
        "  - Widget Rendering\n"
        "Features Missing Risks: 1\n"
        "  - Widget Rendering\n"
        "Average Requirements Per Feature: 1.0\n"
        "Largest Feature: Widget Rendering (1 requirements)\n"
        "\n"
        "Requirements by Feature\n"
        "=======================\n"
        "\n"
        "Widget Rendering    1\n"
        "\n"
        "Decisions\n"
        "=========\n"
        "\n"
        "Total: 1\n"
        "\n"
        "Status\n"
        "  - Accepted: 1\n"
        "\n"
        "Category\n"
        "  - Architecture: 1\n"
        "\n"
        "Relationships\n"
        "=============\n"
        "\n"
        "Artifacts with Related Decisions: 1"
    )
    assert human.render_stats_human(collect_stats(str(corpus))) == expected
