"""Tests for the friendly empty-corpus contract (v0.13.1).

A day-one corpus (no recognized artifacts) is a valid state, not a failure:
validate, stats, review, and portfolio all exit 0 and print one next-step
line, the summary JSON carries an additive `empty` marker, and the MCP
`get_summary` empty state carries additive `guidance`. None of this fires
once an artifact exists.
"""

from __future__ import annotations

import asyncio
import json

from rac.cli import main
from rac.mcp.budget import DEFAULT_BUDGET
from rac.mcp.server import build_server
from rac.output.human import EMPTY_CORPUS_HINT

# --- exit codes: empty is success across summary commands --------------------


def test_stats_empty_corpus_exits_zero_with_hint(tmp_path, capsys):
    rc = main(["stats", str(tmp_path)])
    assert rc == 0
    assert EMPTY_CORPUS_HINT in capsys.readouterr().out


def test_validate_empty_corpus_exits_zero_with_hint(tmp_path, capsys):
    rc = main(["validate", str(tmp_path)])
    assert rc == 0
    assert EMPTY_CORPUS_HINT in capsys.readouterr().out


def test_review_empty_corpus_exits_zero_with_hint(tmp_path, capsys):
    rc = main(["review", str(tmp_path)])
    assert rc == 0
    assert EMPTY_CORPUS_HINT in capsys.readouterr().out


def test_portfolio_empty_corpus_exits_zero_with_hint(tmp_path, capsys):
    rc = main(["portfolio", str(tmp_path)])
    assert rc == 0
    assert EMPTY_CORPUS_HINT in capsys.readouterr().out


# --- JSON additive `empty` marker --------------------------------------------


def test_stats_json_empty_marker(tmp_path, capsys):
    main(["stats", str(tmp_path), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["empty"] is True


def test_review_json_empty_marker(tmp_path, capsys):
    main(["review", str(tmp_path), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["empty"] is True


def test_portfolio_json_empty_marker(tmp_path, capsys):
    main(["portfolio", str(tmp_path), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["empty"] is True


# --- the hint and marker disappear once an artifact exists -------------------


def _seed_one_artifact(tmp_path) -> None:
    main(["quickstart", str(tmp_path)])


def test_no_hint_once_an_artifact_exists(tmp_path, capsys):
    _seed_one_artifact(tmp_path)
    capsys.readouterr()  # discard quickstart output
    rc = main(["portfolio", str(tmp_path)])
    assert rc == 0
    assert EMPTY_CORPUS_HINT not in capsys.readouterr().out


def test_json_marker_false_once_an_artifact_exists(tmp_path, capsys):
    _seed_one_artifact(tmp_path)
    capsys.readouterr()
    main(["review", str(tmp_path), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["empty"] is False


def test_stats_non_empty_but_all_invalid_still_exits_one(tmp_path, capsys):
    # A requirement-shaped file that fails validation is an invalid feature, not
    # an empty corpus: the existing "no valid known artifacts" failure stands.
    (tmp_path / "broken.md").write_text(
        "## Problem\n\nNo title.\n\n## Requirements\n\n[REQ-001] x\n", encoding="utf-8"
    )
    rc = main(["stats", str(tmp_path)])
    assert rc == 1
    out = capsys.readouterr().out
    assert EMPTY_CORPUS_HINT not in out


# --- MCP get_summary empty-state guidance ------------------------------------


def _call(root: str, tool: str, args: dict) -> dict:
    server = build_server(root, budget=DEFAULT_BUDGET)
    contents, _structured = asyncio.run(server.call_tool(tool, args))
    assert len(contents) == 1
    return json.loads(contents[0].text)


def test_get_summary_empty_carries_guidance(tmp_path):
    payload = _call(str(tmp_path), "get_summary", {})
    assert payload["empty"] is True
    assert "guidance" in payload
    assert "rac quickstart" in payload["guidance"]


def test_get_summary_non_empty_omits_guidance(tmp_path):
    main(["quickstart", str(tmp_path)])
    payload = _call(str(tmp_path), "get_summary", {})
    assert payload["empty"] is False
    assert "guidance" not in payload
