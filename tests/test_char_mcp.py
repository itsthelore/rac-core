"""MCP cluster characterization — cache byte-parity, budget, and cache-dir precedence.

Characterization tests added before the rebuild-scale examiner freeze. They pin
the *current* behavior of the ``lore`` MCP tools plus the derived-index cache
(ADR-099) exactly as the code serves it today; they never assert a preferred or
"fixed" behavior. If the rebuild changes any pinned output, the test fails on
purpose so the change is a conscious decision, not a silent drift.

The gaps these close (verified unpinned in the existing suite):

- The derived-index cache is only checked byte-identical to the uncached path on
  a *fixed, unchanging* fixture. The cache's whole reason to exist — staying
  byte-identical after the corpus changes *mid-session* (edit / add / remove /
  rename between two tool calls) — is unpinned at the tool level. An mtime-keyed,
  per-instance-memoized, or lazily-hashed rewrite would pass every current test
  yet serve stale MCP responses; these tests make that rewrite fail (finding #1).
- Cache parity is never checked *under budget truncation* (finding #2).
- ``default_cache_dir()`` precedence (``RAC_CACHE_DIR`` > ``$XDG_CACHE_HOME`` >
  ``~/.cache``) is untested (finding #4).
- ``get_related`` edge-cap overflow, reported-depth clamping, and the
  non-truncatable ``neighborhood`` field are unpinned at the tool level
  (findings #3, #5, #6).
- The on-disk cache filename shape and literal schema version (finding #7).

Invocation mirrors ``tests/test_mcp_tools.py`` and ``tests/test_derived_cache.py``:
the tool layer is driven in-process via ``build_server(...).call_tool`` (no
spawned server), so every test is fast.
"""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

import pytest
from conftest import fixture_path

from rac.core.corpus import corpus_content_hash
from rac.core.limits import MAX_RELATED_EDGES, MAX_TRAVERSAL_DEPTH
from rac.mcp.budget import DEFAULT_BUDGET, HINT_RELATED
from rac.mcp.server import build_server
from rac.services import derived_cache
from rac.services.derived_cache import DerivedIndexCache, default_cache_dir

CORPUS = fixture_path("mcp", "corpus")

DEC = "RAC-MCPDEC000001"
REQ = "RAC-MCPREQ000001"

# Every tool, so parity is checked across the whole surface. get_related on DEC
# carries both incoming (roadmap + requirement) and outgoing edges, so a stale
# relationship view would surface here; get_summary and search reflect any
# add/remove; get_artifact reflects an in-place edit.
ALL_TOOL_CALLS: tuple[tuple[str, dict], ...] = (
    ("get_artifact", {"id": DEC}),
    ("search_artifacts", {"query": "RAC-MCP"}),
    ("find_decisions", {"topic": "event"}),
    ("get_related", {"id": DEC}),
    ("get_summary", {}),
)

# A Crockford-base32-clean id template (no I/L/O/U): those letters make Core fall
# back to the filename stem, which would silently break resolution in a fixture.
_DECISION = (
    "---\nschema_version: 1\nid: {id}\ntype: decision\n---\n"
    "# {title}\n\n## Status\n\nAccepted\n\n## Category\n\nArchitecture\n\n"
    "## Context\n\nC.\n\n## Decision\n\nD.\n\n## Consequences\n\nE.\n{link}"
)


def _related_decisions(*targets: str) -> str:
    return "\n## Related Decisions\n\n" + "".join(f"- {t}\n" for t in targets)


def _write_decision(path: Path, ident: str, title: str, *targets: str) -> None:
    link = _related_decisions(*targets) if targets else ""
    path.write_text(_DECISION.format(id=ident, title=title, link=link), encoding="utf-8")


def _text(server, name: str, args: dict) -> str:
    """The single JSON text a tool call serializes (the wire payload)."""
    contents, _structured = asyncio.run(server.call_tool(name, args))
    assert len(contents) == 1
    return contents[0].text


def _call(root: str, name: str, args: dict, budget: int = DEFAULT_BUDGET) -> str:
    return _text(build_server(root, budget=budget), name, args)


def _fresh_corpus(tmp_path) -> Path:
    """A writable, non-git copy of the fixture corpus.

    Not a git repo, so git-derived recency degrades to null identically for the
    cache-on and cache-off servers — parity is about the cache, not git state.
    """
    root = tmp_path / "corpus"
    shutil.copytree(CORPUS, root)
    return root


def _assert_all_tools_parity(cached_server, plain_server, tag: str) -> None:
    """Every tool response from the cached server equals the uncached server's."""
    for name, args in ALL_TOOL_CALLS:
        cached = _text(cached_server, name, args)
        plain = _text(plain_server, name, args)
        assert cached == plain, f"cache parity drift [{tag}] on {name}"


# --- corpus mutations (applied to a live, already-warmed cached server) -------


def _edit(root: Path) -> None:
    target = root / "requirement.md"
    target.write_text(
        target.read_text(encoding="utf-8").replace("Decoupled Messaging", "Edited Messaging"),
        encoding="utf-8",
    )


def _add(root: Path) -> None:
    _write_decision(root / "extra.md", "RAC-EXTRADEC0001", "Extra Event Decision")


def _remove(root: Path) -> None:
    (root / "roadmap.md").unlink()


def _rename(root: Path) -> None:
    (root / "roadmap.md").rename(root / "roadmap-renamed.md")


# =============================================================================
# Finding #1 (HIGH, priority #1): cache byte-parity across mid-session corpus
# changes at the tool level. With --cache on, after the corpus changes between
# two tool calls, the next call must be byte-identical to the uncached serving
# path for the same corpus state. The cache recomputes corpus_content_hash every
# call (derived_cache.py:197-206); an mtime-keyed or per-instance-memoized
# rewrite would serve stale responses and fail these.
# =============================================================================


@pytest.mark.parametrize(
    "mutate,label",
    [(_edit, "edit"), (_add, "add"), (_remove, "remove"), (_rename, "rename")],
)
def test_cache_tool_parity_after_mid_session_mutation(tmp_path, mutate, label):
    root = _fresh_corpus(tmp_path)
    cached = build_server(str(root), cache=DerivedIndexCache(tmp_path / "cache"))
    plain = build_server(str(root))

    # Warm the cache and pin parity on the unchanged corpus first.
    _assert_all_tools_parity(cached, plain, f"warm:{label}")

    # Mutate the corpus between tool calls; the same long-lived cached server must
    # observe the change and stay byte-identical to the fresh (uncached) server.
    mutate(root)
    _assert_all_tools_parity(cached, plain, f"after:{label}")


def test_cache_tool_parity_across_mid_session_change_sequence(tmp_path):
    # The headline contract: one long-lived cached server pair, driven through a
    # full sequence of mid-session mutations (edit -> add -> remove -> rename),
    # byte-identical to the uncached path after every step. A cache that keyed on
    # anything but the corpus content — or memoized its first build — drifts here.
    root = _fresh_corpus(tmp_path)
    cached = build_server(str(root), cache=DerivedIndexCache(tmp_path / "cache"))
    plain = build_server(str(root))

    _assert_all_tools_parity(cached, plain, "seq:warm")

    # Distinct targets so each step acts on a file that still exists: edit an
    # original, add a file, remove that added file, rename an original.
    def _remove_added(r: Path) -> None:
        (r / "extra.md").unlink()

    steps = ((_edit, "edit"), (_add, "add"), (_remove_added, "remove"), (_rename, "rename"))
    for mutate, label in steps:
        mutate(root)
        _assert_all_tools_parity(cached, plain, f"seq:{label}")


# =============================================================================
# Finding #2 (MEDIUM-HIGH): cache byte-parity under budget truncation. The
# ADR-033 budget serializes after the derived structures are produced, so a
# subtly different post-rehydration list order would change which items survive
# tail-truncation. Parity must hold with a cache under a truncating budget.
# =============================================================================


@pytest.mark.parametrize(
    "name,args,budget",
    [
        ("search_artifacts", {"query": "RAC-MCP"}, 250),
        ("get_related", {"id": DEC}, 300),
        ("get_artifact", {"id": DEC}, 250),
    ],
)
def test_cache_parity_under_budget_truncation(tmp_path, name, args, budget):
    cached = build_server(CORPUS, budget=budget, cache=DerivedIndexCache(tmp_path / "cache"))
    plain = build_server(CORPUS, budget=budget)
    cached_text = _text(cached, name, args)
    plain_text = _text(plain, name, args)
    assert cached_text == plain_text
    # The budget actually bites here — parity is pinned under real truncation.
    assert json.loads(cached_text)["truncated"] is True


# =============================================================================
# Finding #4 (MEDIUM): default_cache_dir() resolution precedence.
# RAC_CACHE_DIR (absolute override) > $XDG_CACHE_HOME/rac/derived > ~/.cache/rac/derived.
# =============================================================================


def test_default_cache_dir_precedence(tmp_path, monkeypatch):
    # XDG tier: $XDG_CACHE_HOME/rac/derived when no override is set.
    monkeypatch.delenv("RAC_CACHE_DIR", raising=False)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))
    assert default_cache_dir() == tmp_path / "xdg" / "rac" / "derived"

    # Override tier: RAC_CACHE_DIR wins verbatim (no rac/derived suffix appended).
    monkeypatch.setenv("RAC_CACHE_DIR", str(tmp_path / "override"))
    assert default_cache_dir() == tmp_path / "override"

    # Home fallback: neither env var set -> ~/.cache/rac/derived.
    monkeypatch.delenv("RAC_CACHE_DIR", raising=False)
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    assert default_cache_dir() == tmp_path / "home" / ".cache" / "rac" / "derived"


# =============================================================================
# Finding #3 (MEDIUM): get_related edge-cap overflow marks the response
# truncated *before* the char budget, independent of it. With more than
# MAX_RELATED_EDGES inbound edges, the response is marked truncated with
# omitted == total_edges - MAX_RELATED_EDGES even under a huge budget.
# =============================================================================

_HUB = "RAC-TGT000000001"


def _hub_corpus(tmp_path, referrers: int) -> Path:
    root = tmp_path / "hub"
    root.mkdir()
    _write_decision(root / "hub.md", _HUB, "Hub")
    for i in range(referrers):
        _write_decision(root / f"r{i}.md", f"RAC-R{i:011d}", f"Referrer {i}", _HUB)
    return root


def test_get_related_edge_cap_marks_truncated_under_large_budget(tmp_path):
    overflow = 5
    root = _hub_corpus(tmp_path, referrers=MAX_RELATED_EDGES + overflow)
    # A budget far larger than the payload, so the marker can only come from the
    # edge cap, never from the char budget.
    payload = json.loads(_call(str(root), "get_related", {"id": _HUB}, budget=100_000_000))
    assert payload["truncated"] is True
    assert payload["hint"] == HINT_RELATED
    assert payload["omitted"] == overflow  # total_edges - MAX_RELATED_EDGES
    assert len(payload["incoming"]) == MAX_RELATED_EDGES


# =============================================================================
# Finding #5 (MEDIUM): get_related reported `depth` clamps to MAX_TRAVERSAL_DEPTH.
# A request with depth well above the ceiling must report the clamped value, not
# the requested one.
# =============================================================================

_CHAIN = ("RAC-MCPCHN000001", "RAC-MCPCHN000002", "RAC-MCPCHN000003")


def _chain_corpus(tmp_path) -> Path:
    root = tmp_path / "chain"
    root.mkdir()
    for i, ident in enumerate(_CHAIN):
        nxt = (_CHAIN[i + 1],) if i + 1 < len(_CHAIN) else ()
        _write_decision(root / f"dec{i}.md", ident, f"Chain {i}", *nxt)
    return root


def test_get_related_reported_depth_clamps_to_ceiling(tmp_path):
    root = _chain_corpus(tmp_path)
    payload = json.loads(_call(str(root), "get_related", {"id": _CHAIN[0], "depth": 99}))
    assert payload["depth"] == MAX_TRAVERSAL_DEPTH  # 5, never the requested 99


# =============================================================================
# Finding #6 (MEDIUM): `neighborhood` is not a budget-truncatable field. Under
# budget pressure the char budget cuts whole `incoming` entries while
# `neighborhood` rides along in full — so the response can exceed the budget
# because neighborhood is uncut. Characterization: pin the current behavior.
# =============================================================================

_HUB6 = "RAC-CENTER000001"


def _hub_and_chain_corpus(tmp_path) -> Path:
    # A hub with many inbound referrers (a trimmable `incoming` list) plus a chain
    # outward (so depth=5 populates `neighborhood` with hops>1 nodes).
    root = tmp_path / "hub6"
    root.mkdir()
    chain = [f"RAC-CHN{i:09d}" for i in range(1, 7)]
    _write_decision(root / "hub.md", _HUB6, "Center", chain[0])
    for i, cid in enumerate(chain):
        nxt = (chain[i + 1],) if i + 1 < len(chain) else ()
        _write_decision(root / f"c{i}.md", cid, f"Chain {i}", *nxt)
    for i in range(12):
        _write_decision(root / f"ref{i}.md", f"RAC-REF{i:09d}", f"Referrer {i}", _HUB6)
    return root


def test_get_related_budget_cuts_incoming_not_neighborhood(tmp_path):
    root = _hub_and_chain_corpus(tmp_path)

    full = json.loads(
        _call(str(root), "get_related", {"id": _HUB6, "depth": 5}, budget=100_000_000)
    )
    assert "truncated" not in full  # the roomy budget keeps everything
    assert len(full["incoming"]) == 12
    assert len(full["neighborhood"]) >= 1
    assert all(n["hops"] > 1 for n in full["neighborhood"])

    # A tight budget: whole `incoming` entries are dropped (to none, here) while
    # `neighborhood` is untouched — it is not in the truncatable set.
    budget = 600
    small_text = _call(str(root), "get_related", {"id": _HUB6, "depth": 5}, budget=budget)
    small = json.loads(small_text)
    assert small["truncated"] is True
    assert small["hint"] == HINT_RELATED
    assert len(small["incoming"]) < len(full["incoming"])
    assert small["incoming"] == []  # incoming fully dropped at this budget
    # neighborhood rides whole: same count, every entry structurally complete.
    assert len(small["neighborhood"]) == len(full["neighborhood"])
    for node in small["neighborhood"]:
        assert set(node) == {"id", "type", "title", "path", "hops"}
    assert small["depth"] == MAX_TRAVERSAL_DEPTH
    # Consequence of the uncut neighborhood: the response still exceeds the char
    # budget (the budget cannot trim neighborhood). Pinned as current behavior.
    assert len(small_text) > budget


# =============================================================================
# Finding #7 (LOW): on-disk cache filename shape and literal schema version.
# Cache files are `{corpus_hash}.json`; the JSON carries the current cache
# schema version. The literal was "1" at the freeze; ADR-103 bumped it to "2"
# when it extended the cached bundle (this is an internal cache-file detail, not
# an externally observable wire byte — a conscious schema change, not drift).
# =============================================================================


def test_cache_file_named_by_corpus_hash_carries_schema_version(tmp_path):
    cache_dir = tmp_path / "cache"
    DerivedIndexCache(cache_dir).load_or_build(CORPUS)
    expected = cache_dir / f"{corpus_content_hash(CORPUS)}.json"
    assert expected.exists()
    obj = json.loads(expected.read_text(encoding="utf-8"))
    assert obj["schema_version"] == derived_cache.SCHEMA_VERSION == "3"
