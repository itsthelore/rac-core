"""Movement-B bundle B3 — event-sourced serving freshness (ADR-102).

B3 replaces the per-call whole-corpus ``corpus_content_hash`` re-hash with a
server-lifetime :class:`~rac.services.freshness.FreshnessTracker` on the opt-in
cache path. These tests pin what that tracker must guarantee:

(a) **Parity across every mutation class, mid-session** — one long-lived cached
    server, byte-identical to a fresh (cache-off) build after edit / add / remove
    / rename / new-subdirectory-with-file, and after an in-place edit *inside* the
    freshly created subdirectory (watch-then-rescan completeness). This is the
    finding-#1 contract extended to the shard-boundary case (v2 S3).
(b) **Delta serves without a base rebuild** — an ordinary edit is absorbed by the
    delta window: the on-disk base generation is unchanged, the delta is
    non-empty, and the served bytes are still fresh.
(c) **Compaction** — once the delta window crosses the threshold, a fresh base is
    written (generation bumps), the delta resets, and parity holds across the swap.
(d) **Degraded mode** — with inotify forced unavailable the stat-manifest scan is
    the active rung and stays parity-correct across mutations.
(e) **Accepted staleness (S5)** — an in-place rewrite preserving both size and
    mtime_ns is invisible to the stat rung until a content confirm, and the
    full-rehash floor catches it. The test *is* the record of the accepted trade.

The tool layer is driven in-process via ``build_server(...).call_tool`` exactly
as ``test_char_mcp.py`` / ``test_b2_index_store.py`` do.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

from rac.mcp.server import build_server
from rac.services import freshness
from rac.services.derived_cache import DerivedIndexCache, build_derived_index
from rac.services.freshness import (
    MODE_STAT,
    FreshnessTracker,
    INotifyUnavailable,
)
from rac.services.index_store import store_dir

# Crockford-base32-clean ids (no I/L/O/U) so Core never falls back to the stem.
_D1 = "RAC-B3AAAA000001"
_D2 = "RAC-B3BBBB000001"
_D3 = "RAC-B3CCCC000001"


def _decision(ident: str, title: str, *, body: str = "alpha beta gamma", related=()) -> str:
    text = (
        f"---\nschema_version: 1\nid: {ident}\ntype: decision\n---\n"
        f"# {title}\n\n## Status\n\nAccepted\n\n## Category\n\nArchitecture\n\n"
        f"## Context\n\n{body}\n\n## Decision\n\nD.\n\n## Consequences\n\nE.\n"
    )
    if related:
        text += "\n## Related Decisions\n\n" + "".join(f"- {t}\n" for t in related)
    return text


def _corpus(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "d1.md").write_text(
        _decision(_D1, "First Event Decision", body="cache relation event"), encoding="utf-8"
    )
    (root / "d2.md").write_text(
        _decision(_D2, "Second Decision", body="event relation beta", related=(_D1,)),
        encoding="utf-8",
    )
    (root / "d3.md").write_text(
        _decision(_D3, "Third Decision", body="gamma delta", related=(_D1, _D2)), encoding="utf-8"
    )
    return root


def _text(server, name: str, args: dict) -> str:
    contents, _structured = asyncio.run(server.call_tool(name, args))
    assert len(contents) == 1
    return contents[0].text


_TOOL_CALLS: tuple[tuple[str, dict], ...] = (
    ("get_artifact", {"id": _D1}),
    ("search_artifacts", {"query": "event relation"}),
    ("find_decisions", {"topic": "event"}),
    ("get_related", {"id": _D1}),
    ("get_summary", {}),
)


def _assert_parity(cached_server, plain_server, tag: str) -> None:
    for name, args in _TOOL_CALLS:
        cached = _text(cached_server, name, args)
        plain = _text(plain_server, name, args)
        assert cached == plain, f"freshness parity drift [{tag}] on {name}"


# =============================================================================
# (a) Parity across every mutation class, mid-session — finding-#1 extended.
# =============================================================================


def test_long_lived_parity_across_all_mutation_classes(tmp_path):
    root = _corpus(tmp_path / "corpus")
    cached = build_server(str(root), cache=DerivedIndexCache(tmp_path / "cache"))
    plain = build_server(str(root))

    _assert_parity(cached, plain, "warm")

    # edit — change a title + body tokens in place.
    (root / "d1.md").write_text(
        _decision(_D1, "First Edited Decision", body="cache relation moved"), encoding="utf-8"
    )
    _assert_parity(cached, plain, "edit")

    # add — a new decision in the root directory (already-watched dir).
    (root / "d4.md").write_text(
        _decision("RAC-B3EEEE000001", "Fourth Event Decision", related=(_D1,)), encoding="utf-8"
    )
    _assert_parity(cached, plain, "add")

    # remove — delete a referenced decision (flips a relationship edge).
    (root / "d2.md").unlink()
    _assert_parity(cached, plain, "remove")

    # rename — changes the path set (add + remove of the same content).
    (root / "d3.md").rename(root / "d3-renamed.md")
    _assert_parity(cached, plain, "rename")

    # add crossing a shard boundary — a NEW directory + a file within it (v2 S3):
    # the new-dir race the watch-then-rescan protocol must close.
    sub = root / "sub"
    sub.mkdir()
    (sub / "nested.md").write_text(
        _decision("RAC-B3FFFF000001", "Nested Event Decision", related=(_D1,)), encoding="utf-8"
    )
    _assert_parity(cached, plain, "new-subdir")

    # in-place edit INSIDE the freshly created subdirectory — proves the new dir's
    # watch was established (or the stat rung covers it) so future edits are seen.
    (sub / "nested.md").write_text(
        _decision("RAC-B3FFFF000001", "Nested Edited Decision", related=(_D1,)), encoding="utf-8"
    )
    _assert_parity(cached, plain, "edit-in-subdir")


# =============================================================================
# (b) Delta population — an edit serves fresh without rewriting the base.
# =============================================================================


def test_edit_served_from_delta_without_base_rebuild(tmp_path):
    root = _corpus(tmp_path / "corpus")
    tracker = FreshnessTracker(DerivedIndexCache(tmp_path / "cache"), str(root), use_inotify=False)
    try:
        # Cold: the first base is established (generation 1), delta window empty.
        assert tracker.read_model() == build_derived_index(str(root))
        assert tracker.base_generation == 1
        assert tracker.delta_size == 0
        base_gen = tracker.base_generation

        # An ordinary edit: absorbed by the delta window, NOT compacted (the default
        # threshold is large). The base on disk is untouched; the served bytes are
        # fresh, re-derived over the snapshot.
        (root / "d1.md").write_text(
            _decision(_D1, "First Edited Decision", body="cache relation moved"),
            encoding="utf-8",
        )
        served = tracker.read_model()
        assert tracker.base_generation == base_gen, "base must not be rebuilt on an ordinary edit"
        assert tracker.delta_size >= 1, "the changed file must populate the delta window"
        assert served == build_derived_index(str(root)), "delta must serve fresh bytes"
    finally:
        tracker.close()


# =============================================================================
# (c) Compaction — the delta window folds back into a fresh base, atomically.
# =============================================================================


def test_compaction_swaps_base_and_empties_delta(tmp_path):
    root = _corpus(tmp_path / "corpus")
    cache = DerivedIndexCache(tmp_path / "cache")
    # A low threshold so two distinct changed files cross it deterministically.
    tracker = FreshnessTracker(cache, str(root), use_inotify=False, compaction_threshold=2)
    try:
        tracker.read_model()  # cold — establishes base generation 1
        assert tracker.base_generation == 1
        gen_before = tracker.base_generation

        # First changed file: below threshold — served from the delta window.
        (root / "d1.md").write_text(_decision(_D1, "Edit One", body="cache one"), encoding="utf-8")
        tracker.read_model()
        assert tracker.base_generation == gen_before
        assert tracker.delta_size == 1

        # Second distinct changed file: window reaches the threshold -> compaction
        # rewrites the base for the current hash, bumps the generation, resets delta.
        (root / "d2.md").write_text(
            _decision(_D2, "Edit Two", body="event two", related=(_D1,)), encoding="utf-8"
        )
        served = tracker.read_model()
        assert tracker.base_generation == gen_before + 1, "compaction must swap in a new base"
        assert tracker.delta_size == 0, "compaction must reset the delta window"
        # The new base is a real on-disk store for the current corpus hash, and it
        # serves byte-identically to a fresh build.
        assert store_dir(cache.cache_dir, tracker.corpus_hash).is_dir()
        assert served == build_derived_index(str(root))
    finally:
        tracker.close()


# =============================================================================
# (d) Degraded mode — inotify unavailable, the stat rung stays parity-correct.
# =============================================================================


def test_degraded_stat_mode_is_parity_correct(tmp_path):
    root = _corpus(tmp_path / "corpus")
    tracker = FreshnessTracker(DerivedIndexCache(tmp_path / "cache"), str(root), use_inotify=False)
    try:
        assert tracker.mode == MODE_STAT
        assert tracker.read_model() == build_derived_index(str(root))
        # Every mutation class stays correct on the stat rung alone.
        (root / "d1.md").write_text(_decision(_D1, "Edited", body="moved cache"), encoding="utf-8")
        assert tracker.read_model() == build_derived_index(str(root))
        (root / "d5.md").write_text(_decision("RAC-B3GGGG000001", "Added"), encoding="utf-8")
        assert tracker.read_model() == build_derived_index(str(root))
        (root / "d3.md").unlink()
        assert tracker.read_model() == build_derived_index(str(root))
    finally:
        tracker.close()


def test_inotify_setup_failure_degrades_to_stat(tmp_path, monkeypatch):
    # When inotify cannot be established (an incapable filesystem, the watch limit),
    # the tracker records the degraded per-call-scan mode rather than failing — the
    # S1 fail-safe. Parity is unaffected; only the flat-latency claim is forfeited.
    def _boom(_root):
        raise INotifyUnavailable("stubbed incapable fs")

    monkeypatch.setattr(freshness, "INotifyWatcher", _boom)
    root = _corpus(tmp_path / "corpus")
    tracker = FreshnessTracker(DerivedIndexCache(tmp_path / "cache"), str(root), use_inotify=True)
    try:
        assert tracker.mode == MODE_STAT
        assert tracker.read_model() == build_derived_index(str(root))
    finally:
        tracker.close()


# =============================================================================
# (e) Accepted staleness (S5) — a size+mtime-preserving in-place rewrite.
# =============================================================================


def test_size_and_mtime_preserving_rewrite_is_the_accepted_stat_miss(tmp_path):
    root = _corpus(tmp_path / "corpus")
    tracker = FreshnessTracker(DerivedIndexCache(tmp_path / "cache"), str(root), use_inotify=False)
    try:
        tracker.read_model()  # cold — records the manifest (size, mtime_ns)

        target = root / "d1.md"
        before = target.stat()
        original = target.read_text(encoding="utf-8")
        # A same-length in-place rewrite (title "First" -> "Third", 5 chars each) so
        # the file size is byte-identical; then restore the exact mtime_ns.
        rewritten = original.replace("First Event Decision", "Third Event Decision")
        assert len(rewritten.encode("utf-8")) == before.st_size
        target.write_text(rewritten, encoding="utf-8")
        os.utime(target, ns=(before.st_atime_ns, before.st_mtime_ns))
        after = target.stat()
        assert (after.st_size, after.st_mtime_ns) == (before.st_size, before.st_mtime_ns)

        # The stat rung diffs on (size, mtime_ns) and so does NOT re-read the file:
        # the rewrite is the documented accepted miss (S5) — the served title is stale.
        stale = tracker.read_model()
        titles = {e.path: e.title for e in stale.index_entries}
        assert titles[str(target)] == "First Event Decision", "stat rung misses the S5 rewrite"

        # The full-rehash floor reads every file's bytes and catches it — parity with
        # a fresh build is restored on demand (the `--verify` path).
        confirmed = tracker.read_model(verify=True)
        titles = {e.path: e.title for e in confirmed.index_entries}
        assert titles[str(target)] == "Third Event Decision"
        assert confirmed == build_derived_index(str(root))
    finally:
        tracker.close()


@pytest.mark.parametrize("use_inotify", [False, True])
def test_unchanged_corpus_reuses_read_model_object(tmp_path, use_inotify):
    # The flat-line property at the object level: on an unchanged corpus the tracker
    # returns the very same cached read-model, doing no re-derive (and, under
    # inotify, no scan at all). Correctness is the same either way.
    root = _corpus(tmp_path / "corpus")
    tracker = FreshnessTracker(
        DerivedIndexCache(tmp_path / "cache"), str(root), use_inotify=use_inotify
    )
    try:
        first = tracker.read_model()
        second = tracker.read_model()
        assert first is second
    finally:
        tracker.close()
