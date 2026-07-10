"""Compound grounding retrieval — `rac retrieve` and the `retrieve_grounding` tool.

ADR-113 (grounding-retrieval-surface): one deterministic call composes keyword
discovery, scope binding, supersedes resolution to live successors, the existing
ranking, and budget capping into a provenance-carrying grounding block. The CLI
and MCP faces share one core (ADR-031), byte-identical for the same corpus and
arguments; determinism is a hard property (ADR-002/ADR-066/ADR-097). The two
facet additions ride along: the generalised `live_only` filter on search and the
per-call `budget` on `get_artifact` — both additive (ADR-007), so calls without
them are byte-identical to before.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from rac.cli import main
from rac.mcp.budget import serialize
from rac.mcp.server import build_server
from rac.services.resolve import find_artifacts, search_index
from rac.services.retrieve import retrieve_grounding

# --- fixture corpus ----------------------------------------------------------


def _decision(
    title: str,
    *,
    status: str = "Accepted",
    body: str = "d",
    applies_to: tuple[str, ...] = (),
    supersedes: tuple[str, ...] = (),
) -> str:
    text = (
        f"# {title}\n\n## Context\n\nc\n\n## Decision\n\n{body}\n\n"
        f"## Consequences\n\nq\n\n## Status\n\n{status}\n"
    )
    if applies_to:
        text += "\n## Applies To\n\n" + "".join(f"- {e}\n" for e in applies_to)
    if supersedes:
        text += "\n## Supersedes\n\n" + "".join(f"- {ref}\n" for ref in supersedes)
    return text


def _requirement(title: str, *, status: str = "Accepted", body: str = "r") -> str:
    return (
        f"# {title}\n\n## Status\n\n{status}\n\n## Problem\n\n{body}\n\n"
        "## Requirements\n\n- [REQ-001] must do the thing.\n\n"
        "## Success Metrics\n\ns\n\n## Risks\n\nk\n\n## Assumptions\n\na\n"
    )


@pytest.fixture
def corpus(tmp_path):
    """A corpus with a supersession chain, a scoped decision, and requirements.

    - adr-old: retired decision matching "token expiry", superseded by adr-new
      (which does not itself match "expiry" — substitution is observable pure).
    - adr-scope: governs src/auth/ but shares no token with the test tasks.
    - req-live / req-retired: the generalised (non-decision) liveness pair.
    """
    d = tmp_path / "rac"
    d.mkdir()
    (d / "adr-old.md").write_text(
        _decision("Static token expiry", status="Superseded", body="fixed token expiry window"),
        encoding="utf-8",
    )
    (d / "adr-new.md").write_text(
        _decision("Rotating token refresh", body="sliding token refresh", supersedes=("adr-old",)),
        encoding="utf-8",
    )
    (d / "adr-scope.md").write_text(
        _decision("Gateway owns authentication", body="gateway", applies_to=("src/auth/",)),
        encoding="utf-8",
    )
    (d / "req-live.md").write_text(
        _requirement("Offline drafting", body="offline drafting keeps working"), encoding="utf-8"
    )
    (d / "req-retired.md").write_text(
        _requirement("Offline sync legacy", status="Deprecated", body="offline sync legacy"),
        encoding="utf-8",
    )
    return str(tmp_path)


def _items(payload: dict) -> list[tuple[str, list[str]]]:
    return [(i["id"], i["provenance"]["channels"]) for i in payload["items"]]


def _tool(root: str, tool: str, args: dict) -> str:
    async def call() -> str:
        contents, _ = await build_server(root).call_tool(tool, args)
        return contents[0].text

    return asyncio.run(call())


# --- core: pipeline ----------------------------------------------------------


def test_scope_binds_regardless_of_keyword_match_and_ranks_first(corpus):
    payload = retrieve_grounding(corpus, "database migration plan", scope="src/auth/login.py")
    # The task shares no token with the scoped decision; it binds anyway, first.
    assert payload["items"][0]["id"] == "adr-scope"
    assert payload["items"][0]["provenance"]["channels"] == ["scope"]
    assert payload["items"][0]["provenance"]["matching_entry"] == "src/auth/"


def test_superseded_match_is_replaced_by_its_live_successor(corpus):
    payload = retrieve_grounding(corpus, "token expiry")
    # Only the retired adr-old matches "expiry"; live-only substitutes adr-new.
    ids = [i["id"] for i in payload["items"]]
    assert "adr-old" not in ids
    (successor,) = [i for i in payload["items"] if i["id"] == "adr-new"]
    assert successor["provenance"]["channels"] == ["supersedes"]
    assert successor["provenance"]["superseded"] == ["adr-old"]
    assert successor["status"] == "Accepted"


def test_channels_merge_when_an_item_arrives_by_more_than_one_route(corpus):
    # "token" matches both the retired old (→ substitution) and the new itself.
    payload = retrieve_grounding(corpus, "token")
    (item,) = [i for i in payload["items"] if i["id"] == "adr-new"]
    assert set(item["provenance"]["channels"]) == {"keyword", "supersedes"}
    assert item["provenance"]["superseded"] == ["adr-old"]
    # The keyword route carries the explain-hit evidence.
    assert item["provenance"]["evidence"]["terms"] == ["token"]


def test_all_mode_keeps_retired_matches_without_substitution(corpus):
    payload = retrieve_grounding(corpus, "token expiry", live_only=False)
    assert _items(payload) == [("adr-old", ["keyword"])]
    assert payload["live_only"] is False


def test_top_k_cuts_and_empty_result_is_valid(corpus):
    assert len(retrieve_grounding(corpus, "token", top_k=1)["items"]) == 1
    empty = retrieve_grounding(corpus, "zeppelin")
    assert empty["items"] == []
    assert empty["schema_version"] == "1"


def test_excerpts_share_the_budget_evenly(corpus):
    payload = retrieve_grounding(corpus, "offline", top_k=2, budget=400, live_only=False)
    assert len(payload["items"]) == 2
    assert all(len(i["excerpt"]) <= 400 // 2 for i in payload["items"])


def test_payload_is_deterministic(corpus):
    a = retrieve_grounding(corpus, "token expiry", scope="src/auth/x.py")
    b = retrieve_grounding(corpus, "token expiry", scope="src/auth/x.py")
    assert json.dumps(a) == json.dumps(b)


def test_serialized_payload_respects_the_budget_with_markers(corpus):
    payload = retrieve_grounding(corpus, "token offline", budget=600)
    out = json.loads(serialize(payload, 600))
    assert len(serialize(payload, 600)) <= 600 or out["truncated"] is True
    # Complete responses carry no marker (ADR-033: absent, not false).
    full = json.loads(serialize(retrieve_grounding(corpus, "zeppelin"), 10_000))
    assert "truncated" not in full


# --- faces: CLI and MCP are one implementation (ADR-031) ----------------------


def test_cli_json_is_byte_identical_to_the_mcp_tool(corpus, capsys):
    args = {"task": "token expiry", "scope": "src/auth/login.py", "top_k": 3, "budget": 4000}
    tool_text = _tool(corpus, "retrieve_grounding", args)
    code = main(
        [
            "retrieve",
            "token expiry",
            corpus,
            "--scope",
            "src/auth/login.py",
            "--top-k",
            "3",
            "--budget",
            "4000",
            "--json",
        ]
    )
    assert code == 0
    assert capsys.readouterr().out.rstrip("\n") == tool_text


def test_cli_empty_result_exits_zero_and_usage_errors_exit_two(corpus, capsys):
    assert main(["retrieve", "zeppelin", corpus]) == 0
    assert "No grounding" in capsys.readouterr().out
    with pytest.raises(SystemExit) as exc:
        main(["retrieve", "token", corpus + "/nope"])
    assert exc.value.code == 2
    with pytest.raises(SystemExit) as exc:
        main(["retrieve", "token", corpus, "--top-k", "0"])
    assert exc.value.code == 2
    with pytest.raises(SystemExit) as exc:
        main(["retrieve", "token", corpus, "--budget", "0"])
    assert exc.value.code == 2


def test_cli_human_output_shows_provenance(corpus, capsys):
    assert main(["retrieve", "token expiry", corpus, "--scope", "src/auth/x.py"]) == 0
    out = capsys.readouterr().out
    assert "via: scope [applies to: src/auth/]" in out
    assert "replaces: adr-old" in out


def test_mcp_tool_defaults_are_live_top5_server_budget(corpus):
    payload = json.loads(_tool(corpus, "retrieve_grounding", {"task": "token expiry"}))
    assert payload["live_only"] is True
    assert [i["id"] for i in payload["items"]] == ["adr-new"]


# --- facet: live_only on search (ADR-113, additive) ---------------------------


def test_live_only_drops_retired_artifacts_of_every_type(corpus):
    base = find_artifacts(corpus, "offline")
    live = find_artifacts(corpus, "offline", live_only=True)
    assert {m.id for m in base.matches} == {"req-live", "req-retired"}
    assert {m.id for m in live.matches} == {"req-live"}


def test_live_only_default_off_is_byte_identical(corpus):
    base = find_artifacts(corpus, "offline")
    explicit = find_artifacts(corpus, "offline", live_only=False)
    assert json.dumps(base.to_dict()) == json.dumps(explicit.to_dict())


def test_cli_find_live_flag_filters(corpus, capsys):
    assert main(["find", "offline", corpus, "--live", "--json", "--no-cache"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert [m["id"] for m in payload["matches"]] == ["req-live"]


def test_cli_find_live_flag_filters_with_cache(corpus, capsys):
    assert main(["find", "offline", corpus, "--live", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert [m["id"] for m in payload["matches"]] == ["req-live"]


def test_mcp_search_artifacts_live_only(corpus):
    base = json.loads(_tool(corpus, "search_artifacts", {"query": "offline"}))
    live = json.loads(_tool(corpus, "search_artifacts", {"query": "offline", "live_only": True}))
    assert {m["id"] for m in base["matches"]} == {"req-live", "req-retired"}
    assert {m["id"] for m in live["matches"]} == {"req-live"}


def test_unreadable_entry_is_treated_as_live(corpus):
    # Retirement must be provable: an entry whose file cannot be re-read stays in.
    from pathlib import Path

    from rac.services.index import build_repository_index

    entries = build_repository_index(corpus, recursive=True).artifacts
    Path(corpus, "rac", "req-retired.md").unlink()
    result = search_index(entries, "offline", live_only=True)
    assert {m.id for m in result.matches} == {"req-live", "req-retired"}


# --- facet: per-call budget on get_artifact (ADR-113, additive) ---------------


def test_get_artifact_per_call_budget_lowers_only(corpus):
    full = _tool(corpus, "get_artifact", {"id": "adr-new"})
    small = json.loads(_tool(corpus, "get_artifact", {"id": "adr-new", "budget": 300}))
    raised = _tool(corpus, "get_artifact", {"id": "adr-new", "budget": 10_000_000})
    assert small["truncated"] is True
    assert len(small["content"]) < len(json.loads(full)["content"])
    # A per-call value can never raise past the server budget.
    assert raised == full


def test_get_artifact_without_budget_is_byte_identical(corpus):
    assert _tool(corpus, "get_artifact", {"id": "adr-new"}) == _tool(
        corpus, "get_artifact", {"id": "adr-new"}
    )
