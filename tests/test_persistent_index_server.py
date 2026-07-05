"""Persistent index wired into the long-lived MCP server (ADR-100/101).

The index is an invisible optimisation behind the ``rac mcp --index`` serving
mode: the four corpus-bound seams serve from the memory-mapped index, kept fresh
by changeset, byte-identical to the default fresh path; get_summary and
find_decisions path mode keep the fresh path. These tests pin the wiring:

- the ``--index`` flag exists and defaults off (the additive-flag pin);
- server-level byte-parity — an index-backed server answers every tool exactly
  as the default server, over a git-inited corpus so recency is exercised;
- event-free freshness — a file edited after startup is reflected on the next
  call (forced into the deterministic per-call fallback so the test never races
  inotify delivery);
- the watcher itself marks a new file dirty (skipped where inotify is absent);
- ``PersistentIndex.relationships()`` reconstructs the full declared-reference
  list byte-identically, the seam get_related's outgoing/incoming shapes need.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import time
from pathlib import Path

import pytest
from conftest import fixture_path

from rac import cli
from rac.core.corpus import walk_corpus
from rac.mcp.server import IndexProvider, build_server
from rac.services.corpus_watch import CorpusWatcher
from rac.services.index import build_repository_index
from rac.services.persistent_index import build_index, load_index
from rac.services.relationships import relationships_from_corpus

CORPUS = fixture_path("mcp", "corpus")


# --- corpus builder (git-inited so recency is populated) ---------------------


def _git(repo: Path, *args: str, when: str | None = None) -> None:
    env = dict(os.environ)
    if when is not None:
        env["GIT_AUTHOR_DATE"] = when
        env["GIT_COMMITTER_DATE"] = when
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        cwd=repo,
        check=True,
        capture_output=True,
        env=env,
    )


def _relationship_corpus(root: Path) -> None:
    """Decisions (live + one superseded) and a requirement with a broken ref.

    ``adr-001`` <-> ``adr-002`` resolve to each other; ``req-001`` resolves to
    ``adr-001`` and declares an unresolved ``adr-999`` — so the full-relationship
    reconstruction the index must reproduce covers resolved, self-back, and
    not-found edges. ``adr-003`` is Superseded, so the liveness filter must drop
    it from find_decisions even when the topic matches.
    """
    root.mkdir(parents=True, exist_ok=True)
    (root / "adr-001.md").write_text(
        "# ADR-1 Persistent index architecture\n\n"
        "## Status\n\nAccepted\n\n"
        "## Context\n\nThe relationships subsystem needs an index decision.\n\n"
        "## Decision\n\nAdopt the persistent index.\n\n"
        "## Consequences\n\nGood.\n\n"
        "## Related Decisions\n\n- adr-002\n",
        encoding="utf-8",
    )
    (root / "adr-002.md").write_text(
        "# ADR-2 Recency column\n\n"
        "## Status\n\nAccepted\n\n"
        "## Context\n\nThe recency signal is materialised.\n\n"
        "## Decision\n\nStore recency in the index.\n\n"
        "## Consequences\n\nk\n\n"
        "## Related Decisions\n\n- adr-001\n",
        encoding="utf-8",
    )
    (root / "adr-003.md").write_text(
        "# ADR-3 Old recency approach\n\n"
        "## Status\n\nSuperseded\n\n"
        "## Context\n\nAn earlier recency approach.\n\n"
        "## Decision\n\nFork git per match.\n\n"
        "## Consequences\n\nSlow.\n",
        encoding="utf-8",
    )
    (root / "req-001.md").write_text(
        "# Requirement One index\n\n"
        "## Problem\n\np\n\n"
        "## Requirements\n\n[REQ-001] The system supports the persistent index.\n\n"
        "## Related Decisions\n\n- adr-001\n- adr-999\n",
        encoding="utf-8",
    )


def _git_corpus(tmp_path: Path) -> Path:
    root = tmp_path / "corpus"
    _relationship_corpus(root)
    _git(root, "init")
    _git(root, "add", "-A")
    _git(root, "commit", "-m", "seed", when="2024-01-01T12:00:00+00:00")
    return root


def _tool_text(server, name: str, args: dict) -> str:
    content, _structured = asyncio.run(server.call_tool(name, args))
    return content[0].text


def _index_server(root: str, index_dir: Path, *, watch: bool = False):
    """A build_server bound to a persistent index (fallback freshness by default)."""
    build_index(root, str(index_dir), workers=1)
    pindex = load_index(str(index_dir))
    watcher = None
    if watch:
        watcher = CorpusWatcher(root)
        if not watcher.start():
            watcher = None
    provider = IndexProvider(pindex, root, watcher=watcher)
    return build_server(root, index=provider), provider


# --- (a) flag exists, defaults off -------------------------------------------


def test_index_flag_defaults_off_and_parses():
    parser = cli.build_parser()
    assert parser.parse_args(["mcp", "--root", str(CORPUS)]).index is False
    assert parser.parse_args(["mcp", "--root", str(CORPUS), "--index"]).index is True


# --- (b) server-level byte-parity: index-on == default across tools ----------


def test_index_server_matches_default_across_tools(tmp_path):
    root = str(_git_corpus(tmp_path))
    fresh = build_repository_index(root).artifacts
    by_stem = {Path(e.path).stem: e.id for e in fresh}
    adr1, adr2, req1 = by_stem["adr-001"], by_stem["adr-002"], by_stem["req-001"]

    calls: tuple[tuple[str, dict], ...] = (
        ("get_artifact", {"id": adr1}),
        ("get_artifact", {"id": req1}),
        ("search_artifacts", {"query": "index"}),
        ("search_artifacts", {"query": "recency"}),
        ("search_artifacts", {"query": "index", "type": "decision"}),
        ("get_related", {"id": adr1}),
        ("get_related", {"id": adr2}),
        ("get_related", {"id": req1}),  # exercises the unresolved outgoing edge
        ("get_related", {"id": adr1, "depth": 3}),  # neighborhood
        ("find_decisions", {"topic": "recency"}),  # adr-003 superseded -> dropped
        ("find_decisions", {"topic": "index"}),
        ("find_decisions", {"topic": "", "path": "adr-001.md"}),  # path mode stays fresh
        ("get_summary", {}),  # not index-backed, must still match
    )

    off = build_server(root)
    on, provider = _index_server(root, tmp_path / "idx")
    try:
        for name, args in calls:
            assert _tool_text(off, name, args) == _tool_text(on, name, args), (
                f"parity drift: {name} {args}"
            )
    finally:
        provider.close()


def test_find_decisions_drops_superseded_on_index_path(tmp_path):
    # A stronger, explicit liveness pin: the superseded adr-003 matches "recency"
    # but must be absent from the index-served result, exactly as on the fresh
    # path (the per-matched-decision liveness filter must not fork the predicate).
    root = str(_git_corpus(tmp_path))
    on, provider = _index_server(root, tmp_path / "idx")
    try:
        payload = json.loads(_tool_text(on, "find_decisions", {"topic": "recency"}))
    finally:
        provider.close()
    paths = {Path(m["path"]).name for m in payload["matches"]}
    assert "adr-003.md" not in paths
    assert payload["filter"] == "live-decisions"


# --- (c) freshness: an edit after startup shows on the next call -------------


def test_edit_after_startup_reflected_next_call_fallback(tmp_path):
    # Force the deterministic per-call fallback (no watcher), so the test asserts
    # freshness without racing inotify delivery.
    root = str(_git_corpus(tmp_path))
    on, provider = _index_server(root, tmp_path / "idx", watch=False)
    try:
        before = json.loads(_tool_text(on, "search_artifacts", {"query": "photosynthesis"}))
        assert before["matches"] == []

        target = Path(root) / "adr-002.md"
        target.write_text(
            target.read_text(encoding="utf-8").replace(
                "# ADR-2 Recency column", "# ADR-2 Recency photosynthesis"
            ),
            encoding="utf-8",
        )

        q = {"query": "photosynthesis"}
        after = json.loads(_tool_text(on, "search_artifacts", q))
        fresh = json.loads(_tool_text(build_server(root), "search_artifacts", q))
        assert after == fresh, "index did not refresh to the edited corpus"
        assert len(after["matches"]) == 1
    finally:
        provider.close()


def test_get_related_and_get_artifact_reflect_edit_no_stale_memo(tmp_path):
    # The memoised index seams (resolution map, per-node edge groups, neighbourhood
    # adjacency) must not serve a pre-edit answer after the corpus changes: an added
    # back-edge and a title edit show up on the next call, byte-identical to the
    # default fresh server. Fallback freshness (no watcher) forces a per-call
    # refresh so the test never races inotify.
    root = str(_git_corpus(tmp_path))
    fresh = build_repository_index(root).artifacts
    by_stem = {Path(e.path).stem: e.id for e in fresh}
    adr1, adr2 = by_stem["adr-001"], by_stem["adr-002"]

    on, provider = _index_server(root, tmp_path / "idx", watch=False)
    try:
        # Warm the memos on the initial corpus.
        for name, args in (
            ("get_artifact", {"id": adr2}),
            ("get_related", {"id": adr1, "depth": 3}),
            ("get_related", {"id": adr2}),
        ):
            assert _tool_text(on, name, args) == _tool_text(build_server(root), name, args)

        # Edit adr-002: change its title and drop its back-edge to adr-001, so both
        # the identity (get_artifact content/title) and the graph (get_related
        # incoming/outgoing/neighborhood) change.
        target = Path(root) / "adr-002.md"
        target.write_text(
            target.read_text(encoding="utf-8")
            .replace("# ADR-2 Recency column", "# ADR-2 Recency column revised")
            .replace("## Related Decisions\n\n- adr-001\n", ""),
            encoding="utf-8",
        )

        # Every seam now reflects the edited corpus, matching a fresh default server.
        for name, args in (
            ("get_artifact", {"id": adr2}),
            ("get_related", {"id": adr1, "depth": 3}),
            ("get_related", {"id": adr2}),
        ):
            assert _tool_text(on, name, args) == _tool_text(build_server(root), name, args), (
                f"stale memo on {name} {args}"
            )
    finally:
        provider.close()


# --- (d) watcher unit test ---------------------------------------------------


def test_watcher_marks_new_file_dirty(tmp_path):
    root = tmp_path / "watched"
    root.mkdir()
    (root / "seed.md").write_text("# Seed\n", encoding="utf-8")
    watcher = CorpusWatcher(str(root))
    if not watcher.start():
        pytest.skip("inotify unavailable on this host")
    try:
        target = root / "new.md"
        target.write_text("# New file\n", encoding="utf-8")
        seen: set[str] = set()
        deadline = time.time() + 5.0
        while time.time() < deadline:
            seen |= watcher.drain()
            if str(target) in seen:
                break
            time.sleep(0.05)
        assert str(target) in seen, f"watcher never reported {target}; saw {seen}"
    finally:
        watcher.stop()


def test_watcher_falls_back_cleanly_when_unavailable(tmp_path, monkeypatch):
    # When inotify cannot initialise, start() reports False and the provider must
    # degrade to per-call refresh rather than raising — the recorded fallback.
    monkeypatch.setattr("rac.services.corpus_watch._load_libc", lambda: None)
    watcher = CorpusWatcher(str(tmp_path))
    assert watcher.start() is False
    assert watcher.available is False
    assert watcher.alive is False
    assert watcher.drain() == set()


# --- relationships() reconstruction parity (get_related's backing) -----------


def test_index_relationships_match_from_corpus(tmp_path):
    root = _git_corpus(tmp_path)
    idx = tmp_path / "idx"
    build_index(str(root), str(idx), workers=1)
    expected = relationships_from_corpus(list(walk_corpus(str(root))))
    with load_index(str(idx)) as index:
        assert index.relationships() == expected
