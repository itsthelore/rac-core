"""Characterization tests for the retrieval cluster (find / resolve / index).

These tests were added before the rebuild-scale examiner freeze (Phase 0.5).
They pin the CURRENT behavior of the legacy retrieval engine exactly as it is
produced today — including behavior that looks odd (empty-token queries return
an empty result rather than matching-all or erroring; ``--type`` is a
case-sensitive exact match even though ID resolution is case-insensitive). They
are deliberately not "fixes": each assertion records what the engine does now so
a reimplementation can be checked against it byte-for-byte.

Scope covers the human-readable rendering and input-edge behaviors left unpinned
by the existing batteries:

- ``rac find --explain`` human score-components line and attribution snippet
  (``src/rac/output/human.py`` ``render_find_human``);
- ``rac index`` human manifest layout, including the empty ``(none)`` output
  (``render_index_human``);
- punctuation/whitespace-only queries that tokenize to nothing;
- the case-sensitive ``--type`` filter (``search_index``);
- the ``--top-level`` / ``--recursive`` CLI recursion flags on ``index``;
- the ``rac resolve`` duplicate-ID human layout and sorted path order.
"""

from __future__ import annotations

import json

import pytest

import rac.output.human as human
from rac.cli import main
from rac.services.resolve import find_artifacts

# --- corpora ------------------------------------------------------------------

# One decision authored so each query term is unique to one match tier (the same
# shape the explain battery uses). The parent directory name ("catalog") is a
# path-only token; "mitochondria" appears only in the Context body.
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

# A minimal, single-title decision used for the index-layout characterization.
DECISION_ONE = (
    "---\nschema_version: 1\nid: RAC-AAAAAAAAAAAA\ntype: decision\n---\n"
    "# T\n\n## Context\n\nc\n\n## Decision\n\nd\n\n## Consequences\n\nq\n"
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


@pytest.fixture(autouse=True)
def _no_color(monkeypatch):
    # Pin plain output regardless of TTY, mirroring tests/test_golden.py.
    monkeypatch.setattr(human, "_USE_COLOR", False)


@pytest.fixture
def catalog(tmp_path):
    root = tmp_path / "catalog"
    root.mkdir()
    (root / "aaa.md").write_text(ARTIFACT, encoding="utf-8")
    return root


# --- Finding 1: human `find --explain` score-components line -------------------


def test_find_explain_human_score_line_layout(catalog, capsys):
    # Title-tier match. The `--explain` bullet line and the indented score line
    # below it are pinned exactly: label order, separators, the `•` bullet, the
    # two-space column indent, and the (deterministic) score/bm25 floats.
    assert main(["find", "photosynthesis", str(catalog), "--explain"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "RAC-AAAAAAAAAAAA  decision  Photosynthesis Charter"
    assert lines[1] == "                            • field=title terms=photosynthesis"
    assert lines[2] == (
        "                              "
        "score=0.02459 bm25=0.205487 lexical_rank=1 graph_rank=1 inbound=0"
    )
    assert lines[3] == ""
    assert lines[4] == "1 match(es) for 'photosynthesis'."


def test_find_without_explain_has_no_score_line(catalog, capsys):
    # The score line rides only on `--explain`; plain `find` never emits it.
    assert main(["find", "photosynthesis", str(catalog)]) == 0
    out = capsys.readouterr().out
    assert "score=" not in out
    assert "• field=" not in out


# --- Finding 2: `--explain` attribution snippet suffix `[section: snippet]` ----


def test_find_explain_human_body_snippet_bracket(catalog, capsys):
    # A body-tier match under `--explain`: the attribution line carries the
    # bracketed `[<section>: <snippet>]` suffix, and the score line follows it.
    assert main(["find", "mitochondria", str(catalog), "--explain"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "RAC-AAAAAAAAAAAA  decision  Photosynthesis Charter"
    assert lines[1] == (
        "                            ↳ Context: The mitochondria powerhouse keeps the lights on."
    )
    assert lines[2] == (
        "                            "
        "• field=body terms=mitochondria "
        "[Context: The mitochondria powerhouse keeps the lights on.]"
    )
    assert lines[3] == (
        "                              "
        "score=0.02459 bm25=0.130765 lexical_rank=1 graph_rank=1 inbound=0"
    )


# --- Finding 3: `rac index` human manifest layout -----------------------------


def test_index_human_row_layout(tmp_path, capsys):
    (tmp_path / "a.md").write_text(DECISION_ONE, encoding="utf-8")
    assert main(["index", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    lines = out.splitlines()
    assert lines[0] == "Repository Index"
    assert lines[1] == "================"
    assert lines[2] == ""
    assert lines[3] == f"Directory:  {tmp_path}"
    assert lines[4] == "Artifacts:  1"
    assert lines[5] == ""
    # Aligned row: two-space separators, id/type/title columns, path last.
    assert lines[6] == f"  RAC-AAAAAAAAAAAA  decision  T  {tmp_path / 'a.md'}"


def test_index_human_null_title_renders_em_dash(tmp_path, capsys):
    # A recognizable-but-titleless requirement indexes with an em dash for title.
    (tmp_path / "untitled.md").write_text(
        "## Problem\n\nUsers need X.\n\n## Requirements\n\n- [REQ-001] Do X.\n",
        encoding="utf-8",
    )
    assert main(["index", str(tmp_path)]) == 0
    row = capsys.readouterr().out.splitlines()[-1]
    assert row == f"  untitled  requirement  —  {tmp_path / 'untitled.md'}"


def test_index_human_empty_prints_none(tmp_path, capsys):
    assert main(["index", str(tmp_path)]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "Repository Index"
    assert lines[1] == "================"
    assert lines[3] == f"Directory:  {tmp_path}"
    assert lines[4] == "Artifacts:  0"
    assert lines[6] == "(none)"


# --- Finding 4: empty-token (punctuation/whitespace) query is a valid empty ----


def test_punctuation_only_query_is_empty_not_error(catalog):
    # "..." tokenizes to nothing -> zero matches, never match-all, never raise.
    result = find_artifacts(str(catalog), "...")
    assert result.match_count == 0
    assert result.matches == []


def test_whitespace_only_query_is_empty_not_error(catalog):
    result = find_artifacts(str(catalog), "   ")
    assert result.match_count == 0
    assert result.matches == []


def test_cli_find_punctuation_query_exit_0(catalog, capsys):
    assert main(["find", "...", str(catalog)]) == 0
    assert capsys.readouterr().out == "No artifacts match '...'.\n"


# --- Finding 5: `--type` filter is a case-sensitive exact match ----------------


def test_type_filter_is_case_sensitive(catalog):
    # "catalog" is a path token that matches the single decision. The type filter
    # compares raw strings, so a capitalized "Decision" matches nothing while the
    # lowercase "decision" matches — unlike case-insensitive ID resolution.
    assert find_artifacts(str(catalog), "catalog", artifact_type="Decision").match_count == 0
    assert find_artifacts(str(catalog), "catalog", artifact_type="decision").match_count == 1


def test_cli_find_type_filter_mismatched_case_is_empty(catalog, capsys):
    assert main(["find", "catalog", str(catalog), "--type", "Decision", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["match_count"] == 0


# --- Finding 6: CLI recursion flags on `index` --------------------------------


def _nested_repo(tmp_path):
    (tmp_path / "top.md").write_text(DECISION_ONE, encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "n.md").write_text(
        "---\nschema_version: 1\nid: RAC-BBBBBBBBBBBB\ntype: decision\n---\n"
        "# N\n\n## Context\n\nc\n\n## Decision\n\nd\n\n## Consequences\n\nq\n",
        encoding="utf-8",
    )
    return tmp_path


def test_cli_index_top_level_flag_limits_to_top(tmp_path, capsys):
    _nested_repo(tmp_path)
    assert main(["index", str(tmp_path), "--top-level", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["artifact_count"] == 1


def test_cli_index_default_recurses(tmp_path, capsys):
    _nested_repo(tmp_path)
    assert main(["index", str(tmp_path), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["artifact_count"] == 2


def test_cli_index_top_level_wins_over_recursive(tmp_path, capsys):
    # `--recursive` is a no-op "for clarity": `--top-level` is computed as
    # `not args.top_level`, so combining the two still recurses only at top level.
    _nested_repo(tmp_path)
    assert main(["index", str(tmp_path), "--top-level", "--recursive", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["artifact_count"] == 1


# --- Finding 7: `rac resolve` duplicate human layout --------------------------


def test_cli_resolve_duplicate_human_layout(tmp_path, capsys):
    d = tmp_path / "decisions"
    d.mkdir()
    (d / "markdown-first.md").write_text(DECISION, encoding="utf-8")
    (d / "copy.md").write_text(DECISION, encoding="utf-8")
    assert main(["resolve", CANONICAL_ID, str(tmp_path)]) == 1
    err = capsys.readouterr().err
    assert err.startswith(f"rac: duplicate artifact ID: {CANONICAL_ID}\n\nFound in:\n- ")
    # The "- " path bullets are emitted in sorted() order.
    paths = [ln[2:] for ln in err.splitlines() if ln.startswith("- ")]
    assert paths == [
        str(d / "copy.md"),
        str(d / "markdown-first.md"),
    ]
    assert paths == sorted(paths)
