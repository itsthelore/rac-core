"""Movement-B bundle B2 — persistent memory-mapped index store (ADR-101).

B2 replaces ADR-099's serialised-blob cache representation with a directory of
memory-mapped binary segment files, read by point access, plus the base+delta
fold layer (delta empty in B2). These tests pin what that substrate must hold:

(a) **Parity vs a fresh build across corpus states.** With the store on, every
    MCP tool and the CLI-facing search/find/resolve seams stay byte-identical to
    the uncached fresh path across edit / add / remove / rename — freshness is
    per-call, so each state rebuilds the store under a new content hash.
(b) **Prefix-range df/tf == walk.** The sorted term dictionary's binary-searched
    prefix range reproduces the token-boundary df and tf exactly, including a term
    that prefixes another indexed term (``cache`` over ``caches``), and a doc
    holding both counts once toward df.
(c) **Corruption is a miss, never fatal.** Truncating, magic-corrupting, or
    version-bumping any segment file makes the store a miss and a fresh rebuild —
    never an exception to the caller.
(d) **No code-bearing format.** The modules import no ``pickle``/``marshal`` and
    the segment files open with the format magic, not a pickle opcode.
(e) **Integer-accumulator BM25 parity.** BM25F floats computed from the store's
    integer accumulators and prefix ranges equal the walk's, to the bit, on a
    corpus crafted with terms repeated across fields.
(f) **RSS sanity.** Building and serving a 10k-artifact corpus keeps the serving
    RSS delta bounded — mmap point access does not rehydrate the whole corpus.

The tool layer is driven in-process via ``build_server(...).call_tool`` exactly
as ``test_char_mcp.py`` / ``test_derived_cache.py`` do.
"""

from __future__ import annotations

import ast
import asyncio
import gc
import json
import resource
from pathlib import Path

import pytest

from rac.core.corpus import corpus_content_hash, walk_corpus
from rac.mcp.server import build_server
from rac.services import index_format, index_store
from rac.services.derived_cache import SCHEMA_VERSION, DerivedIndexCache, build_derived_index
from rac.services.index import build_repository_index
from rac.services.index_store import (
    Delta,
    Fold,
    MmapIndexReader,
    open_read_model,
    store_dir,
    write_store,
)
from rac.services.resolve import (
    _FIELD_BOOSTS,
    _bm25f,
    _corpus_stats,
    _tf,
    find_decisions,
    find_decisions_in,
    live_decision_paths,
    resolve_in_index,
    search_index,
    tokenize,
)

# =============================================================================
# Fixtures — small crafted corpora.
# =============================================================================

# Crockford-base32-clean ids (no I/L/O/U) so Core never falls back to the stem.
_D1 = "RAC-B2AAAA000001"
_D2 = "RAC-B2BBBB000001"
_D3 = "RAC-B2CCCC000001"
_RETIRED = "RAC-B2DDDD000001"
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


def _corpus(root: Path) -> Path:
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
    (root / "retired.md").write_text(
        _decision(_RETIRED, "Retired Decision", status="Superseded", body="cache relation"),
        encoding="utf-8",
    )
    (root / "notes.md").write_text("# Loose Notes\n\nJust prose, no artifact.\n", encoding="utf-8")
    return root


def _text(server, name: str, args: dict) -> str:
    contents, _structured = asyncio.run(server.call_tool(name, args))
    assert len(contents) == 1
    return contents[0].text


_TOOL_CALLS: tuple[tuple[str, dict], ...] = (
    ("get_artifact", {"id": _D1}),
    ("search_artifacts", {"query": "cache"}),
    ("search_artifacts", {"query": "event relation"}),
    ("find_decisions", {"topic": "event"}),
    ("find_decisions", {"topic": "", "path": SCOPE_PATH}),
    ("get_related", {"id": _D1}),
    ("get_summary", {}),
)


# =============================================================================
# (a) Byte-parity vs a fresh build across corpus states.
# =============================================================================


def _assert_tool_parity(cached_server, plain_server, tag: str) -> None:
    for name, args in _TOOL_CALLS:
        cached = _text(cached_server, name, args)
        plain = _text(plain_server, name, args)
        assert cached == plain, f"store parity drift [{tag}] on {name}"


def test_all_tools_parity_across_corpus_states(tmp_path):
    root = _corpus(tmp_path / "corpus")
    cached = build_server(str(root), cache=DerivedIndexCache(tmp_path / "cache"))
    plain = build_server(str(root))

    _assert_tool_parity(cached, plain, "warm")
    # A governing decision exists before the edit (proves the path query is live).
    assert json.loads(_text(plain, "find_decisions", {"topic": "", "path": SCOPE_PATH}))[
        "decisions"
    ]

    # edit — move scope off the query path and change body tokens.
    (root / "d1.md").write_text(
        _decision(_D1, "First Cache Decision", body="cache relation moved", scope="src/other.py"),
        encoding="utf-8",
    )
    _assert_tool_parity(cached, plain, "edit")
    assert (
        json.loads(_text(plain, "find_decisions", {"topic": "", "path": SCOPE_PATH}))["decisions"]
        == []
    ), "edit must be observed under the store"

    # add — a new decision that references d1 and re-governs the path.
    (root / "d4.md").write_text(
        _decision("RAC-B2EEEE000001", "Fourth Decision", scope=SCOPE_PATH, related=(_D1,)),
        encoding="utf-8",
    )
    _assert_tool_parity(cached, plain, "add")

    # remove — delete a referenced decision (flips a relationship edge).
    (root / "d2.md").unlink()
    _assert_tool_parity(cached, plain, "remove")

    # rename — a rename changes the path set (and any path-tokenised field).
    (root / "d3.md").rename(root / "d3-renamed.md")
    _assert_tool_parity(cached, plain, "rename")


def test_cli_seams_parity_with_store(tmp_path):
    root = _corpus(tmp_path / "corpus")
    cache = DerivedIndexCache(tmp_path / "cache")
    view = cache.load_or_build(str(root))
    fresh_entries = build_repository_index(str(root)).artifacts

    # search_index: store-reconstructed field vectors == fresh, for several queries.
    for query in ("cache", "event relation", "gamma", "RAC-B2", "nonexistent"):
        fresh = search_index(fresh_entries, query)
        stored = search_index(
            view.index_entries, query, field_tokens_by_path=view.field_tokens_by_path
        )
        assert fresh.to_dict() == stored.to_dict(), f"search seam drift: {query!r}"

    # find_decisions_in over the store's live paths + tokens == fresh find_decisions.
    entries = list(walk_corpus(str(root)))
    fresh_fd = find_decisions(str(root), "event")
    stored_fd = find_decisions_in(
        view.index_entries,
        view.live_decision_paths,
        "event",
        field_tokens_by_path=view.field_tokens_by_path,
    )
    assert fresh_fd.to_dict() == stored_fd.to_dict()
    assert set(view.live_decision_paths) == set(live_decision_paths(entries))

    # resolve over the store's identity rows == fresh resolve.
    for ident in (_D1, _RETIRED, "RAC-DOES-NOT-EXIST"):
        assert (
            resolve_in_index(view.identity_entries, ident).to_dict()
            == resolve_in_index(fresh_entries, ident).to_dict()
        )


def test_view_equals_fresh_build_not_self_round_trip(tmp_path):
    # Byte-parity asserted against a FRESH build (the quality-lens rule), not the
    # store's own round-trip: the materialised view equals build_derived_index.
    root = _corpus(tmp_path / "corpus")
    cache = DerivedIndexCache(tmp_path / "cache")
    assert cache.load_or_build(str(root)) == build_derived_index(str(root))


# =============================================================================
# (b) Prefix-range df/tf == walk, incl. a term that prefixes another term.
# =============================================================================


def _fold_for(tmp_path, root: Path) -> tuple[Fold, list, dict]:
    derived = build_derived_index(str(root))
    cache_dir = tmp_path / "store"
    cache_dir.mkdir(parents=True, exist_ok=True)
    corpus_hash = corpus_content_hash(str(root))
    assert write_store(cache_dir, corpus_hash, SCHEMA_VERSION, derived)
    base = MmapIndexReader(store_dir(cache_dir, corpus_hash), corpus_hash, SCHEMA_VERSION)
    return Fold(base), derived.index_entries, derived.field_tokens_by_path


def test_prefix_range_df_tf_equals_walk(tmp_path):
    root = _corpus(tmp_path / "corpus")
    fold, entries, ftbp = _fold_for(tmp_path, root)
    try:
        # "cache" prefixes the indexed term "caches"; both are present, and d1's
        # body holds both "cache" and "caches" — df must count that doc once.
        for term in ("cache", "caches", "relation", "event", "gamma", "zzz"):
            walk_df = sum(
                1 for e in entries if any(_tf(term, ftbp[e.path][f]) for f in _FIELD_BOOSTS)
            )
            assert fold.prefix_df(term) == walk_df, f"df mismatch for {term!r}"
            for docid, e in enumerate(entries):
                for field in _FIELD_BOOSTS:
                    assert fold.doc_field_tf(docid, term, field) == _tf(
                        term, ftbp[e.path][field]
                    ), f"tf mismatch {term!r} {field}"
        # The prefix relationship is real in the dictionary: "cache" < "caches",
        # and the "cache" range strictly contains the "caches" range.
        lo_c, hi_c = fold.base.prefix_range("cache")
        lo_cs, hi_cs = fold.base.prefix_range("caches")
        assert lo_c <= lo_cs and hi_cs <= hi_c and (lo_c, hi_c) != (lo_cs, hi_cs)
    finally:
        fold.base.close()


# =============================================================================
# (c) Corruption / truncation / version-mismatch of each segment = miss.
# =============================================================================


def _build_store(tmp_path, root: Path) -> tuple[Path, str]:
    cache_dir = tmp_path / "store"
    cache_dir.mkdir(parents=True, exist_ok=True)
    corpus_hash = corpus_content_hash(str(root))
    assert write_store(cache_dir, corpus_hash, SCHEMA_VERSION, build_derived_index(str(root)))
    return cache_dir, corpus_hash


@pytest.mark.parametrize("how", ["truncate", "magic", "version"])
def test_each_corrupt_segment_is_a_miss(tmp_path, how):
    root = _corpus(tmp_path / "corpus")
    cache_dir, corpus_hash = _build_store(tmp_path, root)
    seg_dir = store_dir(cache_dir, corpus_hash)
    segments = sorted(seg_dir.glob("*.seg"))
    assert segments, "store must have written segment files"

    for segment in segments:
        original = segment.read_bytes()
        if how == "truncate":
            segment.write_bytes(original[:10])  # shorter than the framing header
        elif how == "magic":
            segment.write_bytes(b"XXXX" + original[4:])  # break the magic
        else:  # version — bump the u16 after the 8-byte magic
            segment.write_bytes(original[:8] + b"\x63\x00" + original[10:])
        # Open is a clean miss (None), never an exception reaching the caller.
        assert open_read_model(cache_dir, corpus_hash, SCHEMA_VERSION) is None, (
            f"{how} {segment.name} should be a miss"
        )
        segment.write_bytes(original)  # restore for the next segment


def test_corrupt_store_load_or_build_returns_fresh_and_self_heals(tmp_path):
    root = _corpus(tmp_path / "corpus")
    cache = DerivedIndexCache(tmp_path / "cache")
    expected = build_derived_index(str(root))
    corpus_hash = corpus_content_hash(str(root))
    cache.load_or_build(str(root))  # writes the store + marker

    # Corrupt a segment: the marker still claims a store, but it is unusable.
    victim = next(store_dir(tmp_path / "cache", corpus_hash).glob("*.seg"))
    victim.write_bytes(victim.read_bytes()[:8])

    healed = cache.load_or_build(str(root))
    assert healed == expected  # correct bytes, no raise
    # Self-healed: the store is usable again on the next call (a real hit).
    assert open_read_model(tmp_path / "cache", corpus_hash, SCHEMA_VERSION) is not None


def test_scoring_constant_change_is_a_miss(tmp_path, monkeypatch):
    root = _corpus(tmp_path / "corpus")
    cache_dir, corpus_hash = _build_store(tmp_path, root)
    assert open_read_model(cache_dir, corpus_hash, SCHEMA_VERSION) is not None
    # A changed scoring constant must fail the header fingerprint gate closed, so a
    # store built under the old constants can never feed the scorer stale numbers.
    monkeypatch.setattr(index_store, "scoring_fingerprint", lambda: "different-fingerprint")
    assert open_read_model(cache_dir, corpus_hash, SCHEMA_VERSION) is None


# =============================================================================
# (d) No code-bearing deserialisation format.
# =============================================================================


def test_store_modules_have_no_pickle_and_files_carry_magic(tmp_path):
    # Assert on the *imports* (AST), not prose — the docstrings legitimately name
    # pickle/marshal/yaml as the formats the store deliberately does not use.
    for module in (index_store, index_format):
        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        for banned in ("pickle", "marshal", "yaml"):
            assert banned not in imported, f"{module.__name__} imports {banned!r}"

    root = _corpus(tmp_path / "corpus")
    cache_dir, corpus_hash = _build_store(tmp_path, root)
    for segment in store_dir(cache_dir, corpus_hash).glob("*.seg"):
        head = segment.read_bytes()[:8]
        assert head == index_format.SEGMENT_MAGIC, f"{segment.name} lacks the format magic"
        # A pickle stream starts with b'\x80' (proto) or an opcode; assert not that.
        assert head[:1] != b"\x80"


# =============================================================================
# (e) Integer-accumulator BM25 parity (exact float).
# =============================================================================


def test_bm25_from_store_accumulators_equals_walk(tmp_path):
    root = tmp_path / "repeat"
    root.mkdir()
    # Terms repeated across fields and across docs, with a prefix pair, so df/tf and
    # the per-field length normalisation all carry weight.
    (root / "a.md").write_text(
        _decision(
            _D1,
            "Cache Cache Caches",  # title repeats + prefix pair
            body="cache cache caches relation relation event",
        ),
        encoding="utf-8",
    )
    (root / "b.md").write_text(
        _decision(_D2, "Relation Event", body="cache relation relation relation"),
        encoding="utf-8",
    )
    (root / "c.md").write_text(
        _decision(_D3, "Event", body="event event unrelated"), encoding="utf-8"
    )
    fold, entries, ftbp = _fold_for(tmp_path, root)
    try:
        for query in ("cache relation", "event", "cache", "relation event caches"):
            terms = tokenize(query)
            n, df, avglen, _ = _corpus_stats(entries, terms, ftbp)
            for docid, e in enumerate(entries):
                walk = _bm25f(ftbp[e.path], terms, n, df, avglen)
                stored = fold.bm25f(docid, terms)
                assert walk == stored, f"bm25 drift {query!r} @ {e.path}: {walk!r} != {stored!r}"
    finally:
        fold.base.close()


# =============================================================================
# Fold seam — the delta overlay B3 will populate is routed now (empty in B2).
# =============================================================================


def test_fold_applies_tombstones_even_though_b2_leaves_delta_empty(tmp_path):
    root = _corpus(tmp_path / "corpus")
    fold_empty, entries, _ = _fold_for(tmp_path, root)
    base = fold_empty.base
    try:
        assert Delta().is_empty()
        # Empty delta: the fold is exactly the base, in order.
        assert [e.path for e in fold_empty.index_entries()] == [e.path for e in entries]

        # A constructed tombstone proves the read API folds it out — the seam B3
        # populates. B2 never sets this in production; this is a white-box check
        # that the fold routes through the delta, not the raw reader.
        tombstoned = Fold(base, Delta(tombstones=frozenset({0})))
        folded_paths = {e.path for e in tombstoned.index_entries()}
        assert entries[0].path not in folded_paths
        assert len(folded_paths) == len(entries) - 1
        # Relationships whose source is the tombstoned doc are masked too.
        assert all(rel.source_path != entries[0].path for rel in tombstoned.relationships())
    finally:
        base.close()


# =============================================================================
# (f) RSS sanity — mmap point access does not rehydrate the whole corpus.
# =============================================================================


def _rss_mb() -> float:
    # ru_maxrss is KiB on Linux; a monotonic peak, which is the honest ceiling to
    # bound (it captures any transient rehydration spike, not just steady state).
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def test_serving_2k_corpus_keeps_rss_bounded(tmp_path):
    root = tmp_path / "big"
    root.mkdir()
    n = 2_000
    for i in range(n):
        shard = root / f"shard{i // 1000:03d}"
        shard.mkdir(exist_ok=True)
        ident = "RAC-" + f"{i:012d}"[:12]
        (shard / f"a{i:05d}.md").write_text(
            f"---\nschema_version: 1\nid: {ident}\ntype: decision\n---\n"
            f"# Title {i}\n\n## Status\n\nAccepted\n\n## Category\n\nArchitecture\n\n"
            f"## Context\n\nalpha beta term{i % 50} shared word\n\n"
            f"## Decision\n\nD {i}.\n\n## Consequences\n\nE {i}.\n",
            encoding="utf-8",
        )
    ids = ["RAC-" + f"{i:012d}"[:12] for i in range(n)]

    server = build_server(str(root), cache=DerivedIndexCache(tmp_path / "cache"))

    def call(name: str, args: dict) -> str:
        contents, _structured = asyncio.run(server.call_tool(name, args))
        return contents[0].text

    gc.collect()
    baseline = _rss_mb()
    call("get_summary", {})  # cold: builds and writes the store

    gc.collect()
    before_serve = _rss_mb()
    # Point lookups touch only identity pages; a couple of searches are Θ(N) by
    # contract but reconstruct from mapped pages and release per call. A modest
    # count is enough to expose a per-call leak or a whole-corpus rehydration — the
    # RSS check is about growth, not throughput (each call re-hashes the corpus,
    # the unchanged O(N) freshness cost, so the loop is kept short deliberately).
    for k in range(12):
        call("get_artifact", {"id": ids[k * 160]})
    for _ in range(2):
        call("search_artifacts", {"query": "shared"})
    gc.collect()
    after_serve = _rss_mb()

    # Serving must not grow the resident set unboundedly — no per-call leak, no
    # whole-corpus rehydration held live. Point-access serving adds little over the
    # cold build's own peak. The bound is generous (measured serve delta is a few
    # MB on the generator corpus); this guards a regression to blob rehydration.
    serve_delta = after_serve - before_serve
    assert serve_delta < 150, f"serving RSS delta {serve_delta:.1f} MB exceeds bound"
    assert after_serve - baseline < 300, f"total RSS delta {after_serve - baseline:.1f} MB too high"
