"""Movement-B bundle B5.2 — point resolution (ADR-104).

B5.2 puts exact ID RESOLUTION on the point path: when the cached read-model is
served from the memory-mapped base (the delta is empty), ``get_artifact`` and
``get_related`` resolve an id by binary-searching the persisted alias map and
reading only the matched doc's row — never reconstructing every identity row —
while staying byte-identical to a fresh whole-corpus walk. ``get_related`` also
stops materialising the whole identity projection: its ``identity_by_path`` is a
lazy path->identity map that resolves only the edges near the artifact through
the persisted path map. These tests pin:

(a) **Resolution parity, store vs walk.** ``ReadModelView.resolve`` equals
    ``resolve.resolve_in_index`` over the full corpus across a canonical hit, an
    alias (filename-stem) hit, case-insensitive hits, a stripped query, a
    duplicate id across files (its sorted paths pinned), a not-found, an empty
    query, and an unknown-type file present in the corpus.
(b) **Work-boundedness.** On a 500-doc corpus a point ``get_artifact`` lookup
    reconstructs exactly one identity row (not O(N)), touches no search row, and a
    not-found reconstructs none; ``get_related`` reconstructs only the artifact's
    row plus its incoming-edge sources' rows — bounded by the edges, not the
    corpus (asserted by counting the store row-reader's calls, not by timing).
(c) **Tool-response parity, cache-on vs cache-off.** ``get_artifact`` and
    ``get_related`` responses are byte-identical with the store on and off across
    the canonical / alias / case-insensitive / duplicate / not-found / unknown
    cases and a depth>1 neighbourhood.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from rac.mcp.server import build_server
from rac.services import index_store
from rac.services.derived_cache import DerivedIndexCache
from rac.services.index import build_repository_index
from rac.services.index_store import ReadModelView
from rac.services.resolve import resolve_in_index

# Crockford-base32-clean ids (no I/L/O/U) so Core never falls back to the stem
# for the *canonical* id — the stem is then a distinct legacy alias.
_A1 = "RAC-B5BAAA000001"
_A2 = "RAC-B5BBBB000001"
_A3 = "RAC-B5BCCC000001"
_DUP = "RAC-B5BDDD000001"


def _decision(
    ident: str,
    title: str,
    *,
    status: str = "Accepted",
    body: str = "alpha beta gamma",
    related: tuple[str, ...] = (),
) -> str:
    text = (
        f"---\nschema_version: 1\nid: {ident}\ntype: decision\n---\n"
        f"# {title}\n\n## Status\n\n{status}\n\n## Category\n\nArchitecture\n\n"
        f"## Context\n\n{body}\n\n## Decision\n\nD.\n\n## Consequences\n\nE.\n"
    )
    if related:
        text += "\n## Related Decisions\n\n" + "".join(f"- {t}\n" for t in related)
    return text


def _corpus(root: Path) -> Path:
    """A corpus with a stem alias, incoming edges, a duplicate id, and a non-artifact.

    ``legacy-alpha.md`` carries canonical id ``_A1`` and answers to its filename
    stem ``legacy-alpha`` (the legacy alias); two decisions reference it (incoming
    edges for get_related). ``dupe-a``/``dupe-b`` share ``_DUP`` (the duplicate).
    ``notes.md`` is prose — an unknown-type file present in the corpus.
    """
    root.mkdir(parents=True, exist_ok=True)
    (root / "legacy-alpha.md").write_text(
        _decision(_A1, "Alpha Decision", body="cache relation event"), encoding="utf-8"
    )
    (root / "beta.md").write_text(
        _decision(_A2, "Beta Decision", body="event beta", related=(_A1,)), encoding="utf-8"
    )
    (root / "gamma.md").write_text(
        _decision(_A3, "Gamma Decision", body="gamma delta", related=(_A1,)), encoding="utf-8"
    )
    (root / "dupe-a.md").write_text(_decision(_DUP, "Dupe A", body="x"), encoding="utf-8")
    (root / "dupe-b.md").write_text(_decision(_DUP, "Dupe B", body="y"), encoding="utf-8")
    (root / "notes.md").write_text("# Loose Notes\n\nJust prose, no artifact.\n", encoding="utf-8")
    return root


def _view(tmp_path: Path, root: Path) -> ReadModelView:
    """The store-backed, delta-empty read-model — the point-resolution fast path."""
    cache = DerivedIndexCache(tmp_path / "cache")
    view = cache.load_or_build(str(root))
    assert isinstance(view, ReadModelView), "load_or_build must serve from the mmap base"
    return view


def _text(server, name: str, args: dict) -> str:
    contents, _structured = asyncio.run(server.call_tool(name, args))
    assert len(contents) == 1
    return contents[0].text


# The id shapes the parity sweep covers: canonical, case-insensitive canonical,
# alias (filename stem), case-insensitive alias, a stripped query, the duplicate
# (both cases), an unknown-type file's stem, a not-found, and the empty query.
_QUERIES: tuple[str, ...] = (
    _A1,
    _A1.lower(),
    "legacy-alpha",
    "LEGACY-ALPHA",
    "  legacy-alpha  ",
    _DUP,
    _DUP.lower(),
    "notes",
    "RAC-DOES-NOT-EXIST",
    "",
)


# =============================================================================
# (a) Resolution parity, store vs walk.
# =============================================================================


def test_resolution_parity_store_vs_walk(tmp_path):
    root = _corpus(tmp_path / "corpus")
    fresh = build_repository_index(str(root)).artifacts
    view = _view(tmp_path, root)
    try:
        for query in _QUERIES:
            walk = resolve_in_index(fresh, query).to_dict()
            stored = view.resolve(query).to_dict()
            assert stored == walk, f"resolution parity drift: {query!r}"
    finally:
        view.close()


def test_duplicate_paths_sorted_and_pinned(tmp_path):
    root = _corpus(tmp_path / "corpus")
    view = _view(tmp_path, root)
    try:
        dup = view.resolve(_DUP).to_dict()
        assert dup["error"] == "duplicate"
        # Never resolved by path order; the paths are reported sorted, both cases.
        assert dup["paths"] == sorted(dup["paths"])
        assert dup["paths"] == [str(root / "dupe-a.md"), str(root / "dupe-b.md")]
        # A case-insensitive duplicate query reports the same sorted paths (the
        # ``id`` field echoes the query verbatim, as ``resolve_in_index`` does).
        assert view.resolve(_DUP.lower()).to_dict()["paths"] == dup["paths"]
    finally:
        view.close()


def test_alias_and_canonical_resolve_to_same_artifact(tmp_path):
    root = _corpus(tmp_path / "corpus")
    view = _view(tmp_path, root)
    try:
        canonical = view.resolve(_A1).to_dict()
        assert canonical["id"] == _A1
        assert canonical["path"] == str(root / "legacy-alpha.md")
        # The filename-stem alias and its case-folded form reach the same artifact.
        assert view.resolve("legacy-alpha").to_dict() == canonical
        assert view.resolve("LEGACY-ALPHA").to_dict() == canonical
        assert view.resolve(_A1.lower()).to_dict() == canonical
    finally:
        view.close()


# =============================================================================
# (b) Work-boundedness — a point lookup reconstructs O(1) rows, not O(N).
# =============================================================================


def _big_corpus(root: Path, n: int) -> tuple[str, list[str]]:
    """``n`` decisions; the target (index 0) is referenced by three others."""
    root.mkdir(parents=True, exist_ok=True)
    ids = ["RAC-" + f"{i:012d}"[:12] for i in range(n)]
    target = ids[0]
    for i in range(n):
        shard = root / f"shard{i // 1000:03d}"
        shard.mkdir(exist_ok=True)
        related = (target,) if i in (1, 2, 3) else ()
        (shard / f"a{i:05d}.md").write_text(
            _decision(ids[i], f"Title {i}", body=f"alpha beta term{i % 50}", related=related),
            encoding="utf-8",
        )
    return target, ids


def test_get_artifact_point_lookup_materializes_one_row(tmp_path, monkeypatch):
    root = tmp_path / "big"
    n = 500
    target, ids = _big_corpus(root, n)
    server = build_server(str(root), cache=DerivedIndexCache(tmp_path / "cache"))
    _text(server, "get_summary", {})  # cold: build + write + open the store

    identity_rows: list[int] = []
    search_rows: list[int] = []
    orig_identity = index_store.MmapIndexReader.identity_entry
    orig_full = index_store.MmapIndexReader.full_entry

    def counting_identity(self, docid):  # noqa: ANN001, ANN202
        identity_rows.append(docid)
        return orig_identity(self, docid)

    def counting_full(self, docid):  # noqa: ANN001, ANN202
        search_rows.append(docid)
        return orig_full(self, docid)

    monkeypatch.setattr(index_store.MmapIndexReader, "identity_entry", counting_identity)
    monkeypatch.setattr(index_store.MmapIndexReader, "full_entry", counting_full)

    # A resolved point lookup reconstructs exactly one identity row and touches no
    # search (section/token) row — not the other 499 docs.
    _text(server, "get_artifact", {"id": target})
    assert len(identity_rows) == 1, f"materialised {len(identity_rows)} identity rows (want 1)"
    assert search_rows == [], "get_artifact must not reconstruct any search row"

    # A not-found reconstructs no identity row at all (the binary search misses).
    identity_rows.clear()
    _text(server, "get_artifact", {"id": "RAC-DOES-NOT-EXIST"})
    assert identity_rows == []


def test_get_related_materializes_only_edges_not_corpus(tmp_path, monkeypatch):
    root = tmp_path / "big"
    n = 500
    target, ids = _big_corpus(root, n)
    server = build_server(str(root), cache=DerivedIndexCache(tmp_path / "cache"))
    _text(server, "get_summary", {})  # cold build

    identity_rows: list[int] = []
    orig_identity = index_store.MmapIndexReader.identity_entry

    def counting_identity(self, docid):  # noqa: ANN001, ANN202
        identity_rows.append(docid)
        return orig_identity(self, docid)

    monkeypatch.setattr(index_store.MmapIndexReader, "identity_entry", counting_identity)

    # The target resolves (1 row) and has three incoming edges whose sources are
    # resolved on demand (3 rows) — four in total, bounded by the edges near the
    # artifact, never the 500-doc corpus.
    _text(server, "get_related", {"id": target})
    assert 1 <= len(identity_rows) <= 8, f"materialised {len(identity_rows)} rows (edges: 3)"
    assert len(identity_rows) < n // 10, "get_related must not scan the whole corpus"


# =============================================================================
# (c) Tool-response parity — cache-on vs cache-off, byte for byte.
# =============================================================================

_TOOL_CALLS: tuple[tuple[str, dict], ...] = (
    ("get_artifact", {"id": _A1}),
    ("get_artifact", {"id": _A1.lower()}),
    ("get_artifact", {"id": "legacy-alpha"}),
    ("get_artifact", {"id": "LEGACY-ALPHA"}),
    ("get_artifact", {"id": _DUP}),  # duplicate -> error payload, sorted paths
    ("get_artifact", {"id": "RAC-DOES-NOT-EXIST"}),  # not-found -> error payload
    ("get_artifact", {"id": "notes"}),  # unknown-type file present
    ("get_related", {"id": _A1}),
    ("get_related", {"id": "legacy-alpha"}),
    ("get_related", {"id": _A1, "depth": 3}),  # neighbourhood via the lazy map
    ("get_related", {"id": _DUP}),  # duplicate -> error payload
    ("get_related", {"id": "RAC-DOES-NOT-EXIST"}),
)


def test_tool_responses_byte_equal_cache_on_vs_off(tmp_path):
    root = _corpus(tmp_path / "corpus")
    cached = build_server(str(root), cache=DerivedIndexCache(tmp_path / "cache"))
    plain = build_server(str(root))
    for name, args in _TOOL_CALLS:
        assert _text(cached, name, args) == _text(plain, name, args), f"parity drift: {name} {args}"
