"""Path-to-decisions lookup — `decided decisions-for` and the `find_decisions` path arg.

Initiative 2 of decision-to-code-proximity (`rac-path-decisions-lookup`): given a
code path, return the live decisions whose declared `## Applies To` scope covers
it. The answer is a pure function of the declared references and the query path
(ADR-066) — no code parsing, no index — deterministic and platform-independent
(POSIX-normalised, ADR-002). Only live decisions govern; a superseded one no
longer binds. An ungoverned or outside-repository path is a valid empty result
(exit 0), never an error (REQ-004). The CLI and the MCP `path` argument are one
shared core (ADR-031), so they never diverge.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from asdecided.cli import main
from asdecided.mcp.server import build_server
from asdecided.services.scope import decisions_for_path

# --- fixture corpus ----------------------------------------------------------


def _decision(title: str, applies_to: list[str], status: str = "Accepted") -> str:
    scope = "".join(f"- {e}\n" for e in applies_to)
    return (
        f"# {title}\n\n## Context\n\nc\n\n## Decision\n\nd\n\n## Consequences\n\nq\n"
        f"\n## Status\n\n{status}\n\n## Applies To\n\n{scope}"
    )


@pytest.fixture
def corpus(tmp_path):
    """A corpus with a directory, glob, file, retired, and component scope."""
    d = tmp_path / "decisions"
    d.mkdir()
    (d / "adr-a.md").write_text(_decision("A dir scope", ["src/auth/"]), encoding="utf-8")
    (d / "adr-b.md").write_text(_decision("B glob scope", ["src/**/*.py"]), encoding="utf-8")
    (d / "adr-c.md").write_text(_decision("C file scope", ["docs/config.md"]), encoding="utf-8")
    (d / "adr-d.md").write_text(
        _decision("D retired", ["src/auth/"], status="Superseded"), encoding="utf-8"
    )
    (d / "adr-e.md").write_text(_decision("E component", ["PaymentService"]), encoding="utf-8")
    return str(tmp_path)


def _ids(result):
    return [d.id for d in result.decisions]


# --- core service ------------------------------------------------------------


def test_covering_dir_and_glob_both_bind_a_nested_file(corpus):
    result = decisions_for_path(corpus, "src/auth/login.py")
    # Both the directory scope (src/auth/) and the glob (src/**/*.py) cover it;
    # the retired decision D is excluded even though its scope would match.
    entries = {d.title.split()[0]: d.matching_entry for d in result.decisions}
    assert entries == {"A": "src/auth/", "B": "src/**/*.py"}
    assert result.in_repository is True


def test_retired_decision_never_governs(corpus):
    # D declares src/auth/ but is Superseded, so it does not bind (live-only).
    titles = {d.title.split()[0] for d in decisions_for_path(corpus, "src/auth/x.py").decisions}
    assert "D" not in titles


def test_literal_file_scope_matches_exactly(corpus):
    result = decisions_for_path(corpus, "docs/config.md")
    assert [d.title.split()[0] for d in result.decisions] == ["C"]
    assert result.decisions[0].matching_entry == "docs/config.md"


def test_directory_query_does_not_pull_in_a_file_glob(corpus):
    # Querying the directory itself matches the dir scope but not `src/**/*.py`
    # (which requires a .py file), so segment-aware globbing holds.
    titles = {d.title.split()[0] for d in decisions_for_path(corpus, "src/auth/").decisions}
    assert titles == {"A"}


def test_component_name_scope_never_matches_a_path(corpus):
    # E declares a component label; no path query resolves it (no registry).
    assert all(
        d.title.split()[0] != "E"
        for d in decisions_for_path(corpus, "src/pay/service.py").decisions
    )


def test_ungoverned_path_is_empty_but_in_repository(corpus):
    result = decisions_for_path(corpus, "README.md")
    assert result.decisions == []
    assert result.in_repository is True


def test_outside_repository_path_is_empty_and_flagged(corpus):
    for outside in ("/etc/passwd", "../secrets/key"):
        result = decisions_for_path(corpus, outside)
        assert result.decisions == []
        assert result.in_repository is False


def test_glob_star_does_not_cross_a_segment(tmp_path):
    (tmp_path / "d").mkdir()
    (tmp_path / "d" / "adr.md").write_text(_decision("Flat", ["src/*.py"]), encoding="utf-8")
    assert _ids(decisions_for_path(str(tmp_path), "src/top.py"))  # direct child matches
    assert not _ids(decisions_for_path(str(tmp_path), "src/nested/deep.py"))  # `*` stops at `/`


def test_result_is_sorted_and_byte_deterministic(corpus):
    a = decisions_for_path(corpus, "src/auth/login.py").to_dict()
    b = decisions_for_path(corpus, "src/auth/login.py").to_dict()
    assert a == b
    ids = [d["id"] for d in a["decisions"]]
    assert ids == sorted(ids, key=str.casefold)


# --- CLI: rac decisions-for --------------------------------------------------


def test_cli_governed_path_lists_decisions_and_exits_zero(corpus, capsys):
    code = main(["decisions-for", "src/auth/login.py", corpus])
    out = capsys.readouterr().out
    assert code == 0
    assert "applies to: src/auth/" in out
    assert "2 decision(s) govern" in out


def test_cli_json_shape_is_stable(corpus, capsys):
    code = main(["decisions-for", "docs/config.md", corpus, "--json"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert list(payload) == ["schema_version", "query", "in_repository", "decisions"]
    assert set(payload["decisions"][0]) == {"id", "title", "status", "path", "matching_entry"}


def test_cli_ungoverned_and_outside_exit_zero(corpus, capsys):
    assert main(["decisions-for", "README.md", corpus]) == 0
    assert "No decisions declare scope" in capsys.readouterr().out
    assert main(["decisions-for", "/etc/passwd", corpus]) == 0
    assert "outside the repository" in capsys.readouterr().out


def test_cli_bad_directory_is_usage_error(corpus):
    with pytest.raises(SystemExit) as exc:
        main(["decisions-for", "src/auth/x.py", str(corpus) + "/nope"])
    assert exc.value.code == 2


# --- MCP: additive find_decisions path argument ------------------------------


def _call(root: str, args: dict) -> dict:
    server = build_server(root)
    contents, _structured = asyncio.run(server.call_tool("find_decisions", args))
    return json.loads(contents[0].text)


def test_mcp_path_argument_returns_governing_decisions(corpus):
    payload = _call(corpus, {"path": "src/auth/login.py"})
    assert list(payload) == ["schema_version", "query", "in_repository", "decisions"]
    assert {d["matching_entry"] for d in payload["decisions"]} == {"src/auth/", "src/**/*.py"}


def test_mcp_path_only_needs_no_topic(corpus):
    # The path mode requires no topic — the additive argument stands alone.
    payload = _call(corpus, {"path": "docs/config.md"})
    assert [d["title"].split()[0] for d in payload["decisions"]] == ["C"]


def test_mcp_topic_mode_is_unchanged_by_the_addition(corpus):
    # Without a path the tool is the existing live-decision topic query, keyed by
    # the same contract plus the live-filter marker (byte-identical, ADR-007).
    payload = _call(corpus, {"topic": "dir scope"})
    assert payload["filter"] == "live-decisions"
    assert "matches" in payload


def test_mcp_cli_and_tool_agree(corpus, capsys):
    main(["decisions-for", "src/auth/login.py", corpus, "--json"])
    cli_payload = json.loads(capsys.readouterr().out)
    mcp_payload = _call(corpus, {"path": "src/auth/login.py"})
    assert cli_payload == mcp_payload
