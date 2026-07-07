"""Movement-B bundle B1 — unified derived read-model (ADR-103).

B1 wires the two MCP tools that bypassed the ADR-099 derived-index cache —
``get_summary`` (a fresh ``build_portfolio_summary`` walk) and ``find_decisions``
path mode (a fresh ``decisions_for_path`` walk) — through the same read-model
composer every other tool uses, in both cache modes, byte-identically. These
tests pin what that unification must preserve:

(a) **Byte-parity across a mid-session edit** (mirrors ``test_char_mcp.py``
    finding #1): with the cache on, after the corpus changes between two calls,
    ``get_summary`` and ``find_decisions`` path mode stay byte-identical to the
    uncached serving path — and both stay byte-identical to the canonical
    ``build_portfolio_summary`` / ``decisions_for_path`` reference, so the unified
    path can never silently drift from the frozen output.
(b) **Cache-key-set == entry-set** (retrieve audit #2): the cached field-token,
    index, and summary inputs cover *exactly* the corpus entry set — no superset
    (which would silently inflate the BM25 stats) and no subset (which would
    KeyError on a matched entry) — asserted on a corpus with an unknown-type file
    and a retired decision.
(c) **SCHEMA_VERSION bump**: extending the cached bundle bumped the schema
    version, so an old-version cache file fails the gate and is rebuilt fresh,
    never rehydrated into the new shape.

The tool layer is driven in-process via ``build_server(...).call_tool`` (no
spawned server), exactly as ``test_char_mcp.py`` / ``test_derived_cache.py`` do.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from conftest import fixture_path

from rac.core.corpus import walk_corpus
from rac.mcp.server import build_server
from rac.services import derived_cache
from rac.services.derived_cache import (
    DerivedIndexCache,
    build_derived_index,
    from_json_obj,
    to_json_obj,
)
from rac.services.portfolio import build_portfolio_summary
from rac.services.scope import decisions_for_path

CORPUS = fixture_path("mcp", "corpus")

# A scoped-code path the fixtures below declare `## Applies To`, and the path-mode
# query used throughout — inside the (non-git, no-.rac) corpus, so it normalises
# to itself and `in_repository` is True.
SCOPE_PATH = "src/foo.py"

# Clean Crockford-base32 ids (no I/L/O/U) so Core never falls back to the stem.
_DEC_LIVE = "RAC-B1LIVE0000001"
_DEC_RETIRED = "RAC-B1RETIRED0001"

_SUMMARY_CALL: tuple[str, dict] = ("get_summary", {})
_PATH_CALL: tuple[str, dict] = ("find_decisions", {"topic": "", "path": SCOPE_PATH})


def _decision(ident: str, title: str, *, status: str = "Accepted", scope: str | None = None) -> str:
    body = (
        f"---\nschema_version: 1\nid: {ident}\ntype: decision\n---\n"
        f"# {title}\n\n## Status\n\n{status}\n\n## Category\n\nArchitecture\n\n"
        "## Context\n\nC.\n\n## Decision\n\nD.\n\n## Consequences\n\nE.\n"
    )
    if scope is not None:
        body += f"\n## Applies To\n\n- {scope}\n"
    return body


def _text(server, name: str, args: dict) -> str:
    contents, _structured = asyncio.run(server.call_tool(name, args))
    assert len(contents) == 1
    return contents[0].text


# =============================================================================
# (a) Byte-parity of get_summary and path-mode: cache-on == cache-off across a
#     mid-session edit, and both == the canonical reference (freeze protection).
# =============================================================================


def _scoped_corpus(tmp_path) -> Path:
    root = tmp_path / "corpus"
    root.mkdir()
    (root / "live.md").write_text(
        _decision(_DEC_LIVE, "Scoped Live Decision", scope=SCOPE_PATH), encoding="utf-8"
    )
    (root / "other.md").write_text(
        _decision("RAC-B1OTHER000001", "Unscoped Decision"), encoding="utf-8"
    )
    return root


def _assert_reference_parity(root: Path) -> None:
    """The uncached served bytes equal the canonical (legacy) functions' output.

    This is the freeze guard: ``governing_decisions`` must reproduce
    ``decisions_for_path`` and the read-model portfolio must reproduce
    ``build_portfolio_summary``, or the unified path has drifted.
    """
    plain = build_server(str(root))
    summary = json.loads(_text(plain, *_SUMMARY_CALL))
    assert summary == build_portfolio_summary(str(root), recursive=True).to_dict()
    path_mode = json.loads(_text(plain, *_PATH_CALL))
    assert path_mode == decisions_for_path(str(root), SCOPE_PATH, recursive=True).to_dict()


def test_summary_and_path_mode_parity_across_mid_session_edit(tmp_path):
    root = _scoped_corpus(tmp_path)
    cached = build_server(str(root), cache=DerivedIndexCache(tmp_path / "cache"))
    plain = build_server(str(root))

    def _assert_parity(tag: str) -> None:
        for name, args in (_SUMMARY_CALL, _PATH_CALL):
            assert _text(cached, name, args) == _text(plain, name, args), f"drift [{tag}] {name}"

    # Warm: parity on the unchanged corpus, and against the canonical reference.
    _assert_parity("warm")
    _assert_reference_parity(root)
    # The live decision governs the query path before the edit.
    assert json.loads(_text(plain, *_PATH_CALL))["decisions"], "expected a governing decision"

    # Edit: move the declared scope off the query path between two calls. The same
    # long-lived cached server must observe it and stay byte-identical to fresh.
    (root / "live.md").write_text(
        _decision(_DEC_LIVE, "Scoped Live Decision", scope="src/bar.py"), encoding="utf-8"
    )
    _assert_parity("after-edit")
    _assert_reference_parity(root)
    # Freshness actually observed: the query path is no longer governed.
    assert json.loads(_text(plain, *_PATH_CALL))["decisions"] == []

    # Add: a new decision that governs the query path again, plus grows the summary.
    (root / "added.md").write_text(
        _decision("RAC-B1ADDED000001", "Added Scoped Decision", scope=SCOPE_PATH),
        encoding="utf-8",
    )
    _assert_parity("after-add")
    _assert_reference_parity(root)
    assert json.loads(_text(plain, *_PATH_CALL))["decisions"], "add must be observed"


def test_path_mode_outside_repository_shape_is_preserved(tmp_path):
    # An escaping path is a valid empty answer (in_repository False, no `filter`
    # key) — governing_decisions must reproduce decisions_for_path's shape exactly.
    root = _scoped_corpus(tmp_path)
    plain = build_server(str(root))
    escaping = "../outside.py"
    served = json.loads(_text(plain, "find_decisions", {"topic": "", "path": escaping}))
    assert served == decisions_for_path(str(root), escaping, recursive=True).to_dict()
    assert served["in_repository"] is False
    assert "filter" not in served  # path mode never carries the topic-mode filter key


# =============================================================================
# (b) Cache-key-set == entry-set: the cached inputs cover EXACTLY the corpus
#     entry set (no superset/subset drift) — with an unknown file + a retired
#     decision in the corpus.
# =============================================================================


def _mixed_corpus(tmp_path) -> Path:
    root = tmp_path / "mixed"
    root.mkdir()
    (root / "live.md").write_text(
        _decision(_DEC_LIVE, "Live Scoped", scope=SCOPE_PATH), encoding="utf-8"
    )
    # A retired decision that ALSO declares scope: it must be excluded from the
    # live scope rows (liveness filter), proving the exclusion is by status.
    (root / "retired.md").write_text(
        _decision(_DEC_RETIRED, "Retired Scoped", status="Superseded", scope=SCOPE_PATH),
        encoding="utf-8",
    )
    # An unknown-type file: counted in the index but never a decision/scope row.
    (root / "notes.md").write_text(
        "# Loose Notes\n\nJust some prose, no artifact.\n", encoding="utf-8"
    )
    return root


def test_cached_key_set_equals_entry_set_exactly(tmp_path):
    root = _mixed_corpus(tmp_path)
    derived = build_derived_index(str(root))

    entry_paths = {e.path for e in derived.index_entries}
    walked_paths = {str(e.path) for e in walk_corpus(str(root))}

    # The invariant: field-token keys == index entries == the walked corpus set,
    # EXACTLY. A superset would silently inflate n/avglen/df; a subset would
    # KeyError on a matched entry. Equality rules out both directions.
    assert set(derived.field_tokens_by_path) == entry_paths
    assert entry_paths == walked_paths
    assert len(entry_paths) == 3  # live + retired + unknown, all indexed

    # The portfolio summary counts every walked entry (no drift in its denominator).
    assert derived.portfolio_summary["artifacts"]["total"] == len(walked_paths)

    # Scope rows: ONLY the live scoped decision. The retired decision declares the
    # same scope but is filtered out by liveness; the unknown file is not a decision.
    assert {r.path for r in derived.scope_rows} == {str(root / "live.md")}
    # live_decision_paths agrees — retired and unknown excluded.
    assert set(derived.live_decision_paths) == {str(root / "live.md")}


def test_extended_bundle_round_trips_losslessly(tmp_path):
    # The added fields (portfolio_summary + scope_rows) must serialise and
    # rehydrate to an identical bundle — asserted on a corpus where scope_rows is
    # non-empty, so the round-trip actually exercises them.
    derived = build_derived_index(str(_mixed_corpus(tmp_path)))
    assert derived.scope_rows, "fixture must produce at least one scope row"
    assert from_json_obj(to_json_obj(derived)) == derived


# =============================================================================
# (c) SCHEMA_VERSION bump: an old-version cache file is a miss (fresh build),
#     never rehydrated into the new shape.
# =============================================================================


def test_schema_version_was_bumped_by_adr_100():
    # ADR-103 moved it off "1"; ADR-109 (the tags field) bumped it to "3".
    assert derived_cache.SCHEMA_VERSION == "3"


def test_old_version_cache_file_is_a_miss_never_rehydrated(tmp_path):
    cache = DerivedIndexCache(tmp_path / "cache")
    fresh = cache.load_or_build(CORPUS)  # writes a current-version file
    cache_file = next((tmp_path / "cache").glob("*.json"))

    obj = json.loads(cache_file.read_text(encoding="utf-8"))
    assert obj["schema_version"] == "3"

    # The version gate rejects an old-shape file outright — from_json_obj raises,
    # which the reader treats as a miss (never a rehydration into the new shape).
    stale = dict(obj)
    stale["schema_version"] = "1"
    with pytest.raises(ValueError):
        from_json_obj(stale)

    # End to end: rewrite the on-disk file as the old version; the next load must
    # rebuild fresh and rewrite the file back to the current version.
    cache_file.write_text(json.dumps(stale), encoding="utf-8")
    rebuilt = cache.load_or_build(CORPUS)
    assert rebuilt == fresh == build_derived_index(CORPUS)
    assert json.loads(cache_file.read_text(encoding="utf-8"))["schema_version"] == "3"
