"""Movement-B bundle B3b — postings-served search (ADR-104).

B3b puts SEARCH on the postings path: when the cached read-model is served from
the memory-mapped base (the delta is empty), ``search_artifacts`` and the topic
mode of ``find_decisions`` read only the query terms' prefix ranges in the term
dictionary and the rows of the docs that match at least one term — never the
whole corpus — while staying byte-identical to a fresh whole-corpus walk. These
tests pin:

(a) **Search parity, store vs walk.** ``ReadModelView.search`` /
    ``find_decisions`` equal ``resolve.search_index`` / ``find_decisions`` over
    the full corpus across multi-term queries, prefix-overlapping terms, type
    filters, retired decisions, empty results, a non-ASCII (ASCII-tokenizer-pin)
    doc, and equal-score tie-break cases.
(b) **Delta-window parity.** Driven through the long-lived cached server, search
    stays byte-identical to a cache-off build after an edit to a matched doc, an
    edit to a non-matched doc, an add, and a remove — whichever route the tracker
    takes (the postings fast path when the delta is empty, the re-derived snapshot
    scan when it is not).
(c) **Work-boundedness.** On a 2k corpus a rare-term search reconstructs only its
    matching docs' rows — non-matching docs are never materialised (asserted by
    counting the store row-reader's calls, not by timing).
(d) **match_count parity for broad terms.** A term matching most of the corpus
    still reports the exact same ``match_count`` and order as the full scan.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from asdecided.mcp.server import build_server
from asdecided.services import index_store
from asdecided.services.derived_cache import DerivedIndexCache
from asdecided.services.index import build_repository_index
from asdecided.services.index_store import ReadModelView
from asdecided.services.resolve import find_decisions, search_index

# Crockford-base32-clean ids (no I/L/O/U) so Core never falls back to the stem.
_D1 = "RAC-B3BAAA000001"
_D2 = "RAC-B3BBBB000001"
_D3 = "RAC-B3BCCC000001"
_D4 = "RAC-B3BDDD000001"
_RETIRED = "RAC-B3BEEE000001"
_REQ = "RAC-B3BREQ000001"
_TIE_A = "RAC-B3BTIA000001"
_TIE_B = "RAC-B3BTIB000001"

SCOPE_PATH = "src/pkg/mod.py"


def _decision(
    ident: str,
    title: str,
    *,
    status: str = "Accepted",
    body: str = "alpha beta gamma",
    scope: str | None = None,
    related: tuple[str, ...] = (),
) -> str:
    text = (
        f"---\nschema_version: 1\nid: {ident}\ntype: decision\n---\n"
        f"# {title}\n\n## Status\n\n{status}\n\n## Category\n\nArchitecture\n\n"
        f"## Context\n\n{body}\n\n## Decision\n\nD.\n\n## Consequences\n\nE.\n"
    )
    if scope is not None:
        text += f"\n## Applies To\n\n- {scope}\n"
    if related:
        text += "\n## Related Decisions\n\n" + "".join(f"- {t}\n" for t in related)
    return text


def _requirement(ident: str, title: str, *, body: str) -> str:
    return (
        f"---\nschema_version: 1\nid: {ident}\ntype: requirement\n---\n"
        f"# {title}\n\n## Problem\n\n{body}\n\n## Requirements\n\n- {body}\n"
    )


def _corpus(root: Path) -> Path:
    """A mixed corpus: prefix-overlapping terms, a retired decision, a requirement
    (for the type filter), a non-ASCII body (the ASCII-tokenizer pin), and two
    equal-scoring docs (the tie-break pin)."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "d1.md").write_text(
        _decision(
            _D1, "First Cache Decision", body="cache caches relation event", scope=SCOPE_PATH
        ),
        encoding="utf-8",
    )
    (root / "d2.md").write_text(
        _decision(_D2, "Second Event Decision", body="event relation beta", related=(_D1,)),
        encoding="utf-8",
    )
    (root / "d3.md").write_text(
        _decision(_D3, "Third Decision", body="gamma delta caches", related=(_D1, _D2)),
        encoding="utf-8",
    )
    (root / "d4.md").write_text(
        # A non-ASCII body: `café résumé` tokenizes ASCII-only (café -> [caf]),
        # so a store-reconstructed search must diverge nowhere from the walk.
        _decision(_D4, "Fourth Decision", body="café résumé cache naïve"),
        encoding="utf-8",
    )
    (root / "retired.md").write_text(
        _decision(_RETIRED, "Retired Cache Decision", status="Superseded", body="cache relation"),
        encoding="utf-8",
    )
    (root / "req.md").write_text(
        _requirement(_REQ, "Cache Requirement", body="cache relation event"),
        encoding="utf-8",
    )
    # Two docs identical in every scorable field -> equal bm25, equal inbound (0) ->
    # equal fused score -> the tie is broken by the path string. Distinct dir names
    # so the path order (t-a < t-b) is unambiguous.
    (root / "t-a.md").write_text(
        _decision(_TIE_A, "Tie Topic", body="synonym synonym payload"), encoding="utf-8"
    )
    (root / "t-b.md").write_text(
        _decision(_TIE_B, "Tie Topic", body="synonym synonym payload"), encoding="utf-8"
    )
    (root / "notes.md").write_text("# Loose Notes\n\nJust prose, no artifact.\n", encoding="utf-8")
    return root


def _view(tmp_path: Path, root: Path) -> ReadModelView:
    """The store-backed, delta-empty read-model — the postings fast path."""
    cache = DerivedIndexCache(tmp_path / "cache")
    view = cache.load_or_build(str(root))
    assert isinstance(view, ReadModelView), "load_or_build must serve from the mmap base"
    return view


# The query shapes the parity pins sweep: single/multi-term, prefix pairs, the
# camelCase seam, an id-token query, a non-ASCII query, and the empty/no-match
# cases. Paired with each artifact-type filter value below.
_QUERIES: tuple[str, ...] = (
    "cache",
    "caches",
    "cache relation",
    "event relation",
    "relation event caches",
    "gamma",
    "café",
    "caf",
    "résumé",
    "synonym",
    "Tie Topic",
    "RAC-B3B",
    "FirstCacheDecision",
    "nonexistent",
    "!!!",
    "",
)

_TYPES: tuple[str | None, ...] = (None, "decision", "requirement", "Decision")


# =============================================================================
# (a) Search parity, store vs walk.
# =============================================================================


def test_search_parity_store_vs_walk(tmp_path):
    root = _corpus(tmp_path / "corpus")
    fresh = build_repository_index(str(root)).artifacts
    view = _view(tmp_path, root)
    try:
        for artifact_type in _TYPES:
            for query in _QUERIES:
                walk = search_index(fresh, query, artifact_type=artifact_type).to_dict()
                stored = view.search(query, artifact_type=artifact_type).to_dict()
                assert stored == walk, f"search parity drift: {query!r} type={artifact_type!r}"
    finally:
        view.close()


def test_find_decisions_topic_parity_store_vs_walk(tmp_path):
    root = _corpus(tmp_path / "corpus")
    view = _view(tmp_path, root)
    try:
        # Retired decisions match the text but must be filtered out; a requirement
        # matching the topic must never appear (type-restricted to decisions).
        for topic in ("cache", "cache relation", "event", "gamma", "nonexistent", ""):
            walk = find_decisions(str(root), topic).to_dict()
            stored = view.find_decisions(topic).to_dict()
            assert stored == walk, f"find_decisions parity drift: {topic!r}"
        # The retired decision matches "cache" on the walk's raw search but is not
        # a live decision, so it is absent from both answers.
        live_paths = {m["path"] for m in view.find_decisions("cache").to_dict()["matches"]}
        assert not any(p.endswith("retired.md") for p in live_paths)
    finally:
        view.close()


def test_equal_score_tie_break_is_path_order(tmp_path):
    root = _corpus(tmp_path / "corpus")
    view = _view(tmp_path, root)
    fresh = build_repository_index(str(root)).artifacts
    try:
        stored = view.search("synonym payload").to_dict()
        walk = search_index(fresh, "synonym payload").to_dict()
        assert stored == walk
        paths = [m["path"] for m in stored["matches"]]
        # The two tie docs are present and ordered by path string (t-a before t-b).
        tie_paths = [p for p in paths if Path(p).name in {"t-a.md", "t-b.md"}]
        assert tie_paths == sorted(tie_paths)
        assert tie_paths == [str(root / "t-a.md"), str(root / "t-b.md")]
    finally:
        view.close()


def test_empty_and_punctuation_queries_are_empty_results(tmp_path):
    root = _corpus(tmp_path / "corpus")
    view = _view(tmp_path, root)
    try:
        for query in ("", "   ", "!!!", "...", "###"):
            result = view.search(query).to_dict()
            assert result["match_count"] == 0
            assert result["matches"] == []
    finally:
        view.close()


# =============================================================================
# (b) Delta-window parity — through the long-lived cached server.
# =============================================================================


def _text(server, name: str, args: dict) -> str:
    contents, _structured = asyncio.run(server.call_tool(name, args))
    assert len(contents) == 1
    return contents[0].text


_SEARCH_CALLS: tuple[tuple[str, dict], ...] = (
    ("search_artifacts", {"query": "cache"}),
    ("search_artifacts", {"query": "event relation"}),
    ("search_artifacts", {"query": "caches"}),
    ("search_artifacts", {"query": "synonym payload"}),
    ("search_artifacts", {"query": "cache", "type": "requirement"}),
    ("find_decisions", {"topic": "cache"}),
    ("find_decisions", {"topic": "event"}),
)


def _assert_search_parity(cached, plain, tag: str) -> None:
    for name, args in _SEARCH_CALLS:
        assert _text(cached, name, args) == _text(plain, name, args), f"[{tag}] {name} {args}"


def test_delta_window_search_parity_across_mutations(tmp_path):
    root = _corpus(tmp_path / "corpus")
    cached = build_server(str(root), cache=DerivedIndexCache(tmp_path / "cache"))
    plain = build_server(str(root))

    _assert_search_parity(cached, plain, "warm")  # delta empty -> postings fast path

    # edit a MATCHED doc — d1 matches "cache"; change its tokens in place.
    (root / "d1.md").write_text(
        _decision(_D1, "First Cache Decision", body="cache relation moved"), encoding="utf-8"
    )
    _assert_search_parity(cached, plain, "edit-matched")  # delta non-empty -> scan route

    # edit a NON-MATCHED doc — the requirement never matches an "event" search.
    (root / "req.md").write_text(
        _requirement(_REQ, "Cache Requirement", body="cache relation event extra"),
        encoding="utf-8",
    )
    _assert_search_parity(cached, plain, "edit-nonmatched")

    # add — a new matched decision.
    (root / "d5.md").write_text(
        _decision("RAC-B3BFFF000001", "Fifth Cache Decision", body="cache caches", related=(_D1,)),
        encoding="utf-8",
    )
    _assert_search_parity(cached, plain, "add")

    # remove — delete a matched decision.
    (root / "d2.md").unlink()
    _assert_search_parity(cached, plain, "remove")


# =============================================================================
# (c) Work-boundedness — a rare-term search materialises only its matches.
# =============================================================================


def test_rare_term_search_does_not_materialize_non_matching_docs(tmp_path, monkeypatch):
    root = tmp_path / "big"
    root.mkdir()
    n = 2_000
    for i in range(n):
        shard = root / f"shard{i // 1000:03d}"
        shard.mkdir(exist_ok=True)
        ident = "RAC-" + f"{i:012d}"[:12]
        body = "alpha beta shared common"
        if i == 1234:
            body += " zzqrareunique"  # a term held by exactly one doc
        (shard / f"a{i:05d}.md").write_text(
            f"---\nschema_version: 1\nid: {ident}\ntype: decision\n---\n"
            f"# Title {i}\n\n## Status\n\nAccepted\n\n## Category\n\nArchitecture\n\n"
            f"## Context\n\n{body}\n\n## Decision\n\nD {i}.\n\n## Consequences\n\nE {i}.\n",
            encoding="utf-8",
        )
    view = _view(tmp_path, root)
    try:
        # Count the store row-reader's full-row reconstructions: the fast path calls
        # it once per candidate doc (docs matching >=1 term), never per corpus doc.
        touched: list[int] = []
        original = index_store.MmapIndexReader.full_entry

        def counting_full_entry(self, docid):  # noqa: ANN001, ANN202
            touched.append(docid)
            return original(self, docid)

        monkeypatch.setattr(index_store.MmapIndexReader, "full_entry", counting_full_entry)

        result = view.search("zzqrareunique").to_dict()
        assert result["match_count"] == 1, "the rare term matches exactly one doc"
        # Only the single matching doc's row was reconstructed — not the other 1999.
        assert len(touched) == 1, f"materialised {len(touched)} rows for a 1-match query"
    finally:
        view.close()


# =============================================================================
# (d) match_count parity for broad terms.
# =============================================================================


def test_broad_term_match_count_parity(tmp_path):
    root = tmp_path / "broad"
    root.mkdir()
    n = 300
    for i in range(n):
        ident = "RAC-" + f"{i:012d}"[:12]
        # Every doc holds "shared"; only even docs hold "evenonly".
        body = "shared token" + (" evenonly" if i % 2 == 0 else "")
        (root / f"a{i:05d}.md").write_text(
            f"---\nschema_version: 1\nid: {ident}\ntype: decision\n---\n"
            f"# Title {i}\n\n## Status\n\nAccepted\n\n## Category\n\nArchitecture\n\n"
            f"## Context\n\n{body}\n\n## Decision\n\nD.\n\n## Consequences\n\nE.\n",
            encoding="utf-8",
        )
    fresh = build_repository_index(str(root)).artifacts
    view = _view(tmp_path, root)
    try:
        for query, expected in (("shared", n), ("evenonly", n // 2)):
            walk = search_index(fresh, query).to_dict()
            stored = view.search(query).to_dict()
            assert stored["match_count"] == expected
            assert stored["match_count"] == walk["match_count"]
            # Full order parity too, not just the count.
            assert [m["path"] for m in stored["matches"]] == [m["path"] for m in walk["matches"]]
            assert stored == walk
    finally:
        view.close()


def test_json_shape_is_stable(tmp_path):
    # The store search's SearchResult serialises to the same JSON shape the wire
    # contract fixes (schema_version/query/type/match_count/matches).
    root = _corpus(tmp_path / "corpus")
    view = _view(tmp_path, root)
    try:
        payload = json.loads(json.dumps(view.search("cache").to_dict()))
        assert set(payload) == {"schema_version", "query", "type", "match_count", "matches"}
        assert payload["schema_version"] == "1"
    finally:
        view.close()
