"""The persisted one-shot freshness manifest (`.fseg`, ADR-112).

The one-shot find cache verifies freshness through a per-root stat manifest
persisted beside the store. The store primitives fail closed (missing, corrupt,
truncated, or version-mismatched segments are a miss, never an error), writes
are atomic and best-effort, keys separate corpus roots and recursion modes, and
the manifest-recomposed corpus key is byte-identical to the full re-hash.
"""

from __future__ import annotations

from pathlib import Path

from rac.core.corpus import corpus_content_hash
from rac.services.freshness import FileState, corpus_hash_from_manifest, stat_scan
from rac.services.index_store import (
    manifest_root_key,
    manifest_store_root,
    open_freshness_manifest,
    write_freshness_manifest,
)


def _state(path: Path) -> FileState:
    from rac.core.corpus import content_hash

    st = path.stat()
    return FileState(content_hash=content_hash(path), size=st.st_size, mtime_ns=st.st_mtime_ns)


def _write_corpus(tmp_path: Path) -> dict[str, FileState]:
    (tmp_path / "sub").mkdir()
    files = {
        "a.md": "# Alpha\n\nbody alpha\n",
        "b.md": "# Beta\n\nbody beta\n",
        "sub/c.md": "# Gamma\n\nbody gamma\n",
    }
    for rel, text in files.items():
        (tmp_path / rel).write_text(text, encoding="utf-8")
    return {rel: _state(tmp_path / rel) for rel in files}


def test_manifest_round_trips(tmp_path):
    manifest = _write_corpus(tmp_path)
    cache = tmp_path / "cache"
    key = manifest_root_key(str(tmp_path))
    assert write_freshness_manifest(cache, key, manifest)
    assert open_freshness_manifest(cache, key) == manifest


def test_missing_corrupt_and_truncated_manifests_are_a_miss(tmp_path):
    manifest = _write_corpus(tmp_path)
    cache = tmp_path / "cache"
    key = manifest_root_key(str(tmp_path))
    assert open_freshness_manifest(cache, key) is None, "missing file is a miss"

    write_freshness_manifest(cache, key, manifest)
    seg = manifest_store_root(cache) / f"{key}.fseg"
    payload = seg.read_bytes()

    seg.write_bytes(b"garbage")
    assert open_freshness_manifest(cache, key) is None, "corrupt segment is a miss"

    seg.write_bytes(payload[: len(payload) // 2])
    assert open_freshness_manifest(cache, key) is None, "truncated segment is a miss"


def test_manifest_write_failure_degrades_to_false(tmp_path, monkeypatch):
    manifest = _write_corpus(tmp_path)
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "manifest").touch()  # a file where the store dir must go → mkdir fails
    assert write_freshness_manifest(cache, manifest_root_key(str(tmp_path)), manifest) is False


def test_root_key_separates_roots_and_recursion_modes(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(), b.mkdir()
    assert manifest_root_key(str(a)) != manifest_root_key(str(b))
    assert manifest_root_key(str(a)) != manifest_root_key(str(a), recursive=False)
    assert manifest_root_key(str(a)) == manifest_root_key(str(a), recursive=True)


def test_manifest_hash_matches_full_rehash_for_both_modes(tmp_path):
    _write_corpus(tmp_path)
    for recursive in (True, False):
        manifest, _ = stat_scan(
            tmp_path, str(tmp_path), {}, content_confirm_all=True, recursive=recursive
        )
        assert corpus_hash_from_manifest(
            tmp_path, manifest, recursive=recursive
        ) == corpus_content_hash(str(tmp_path), recursive=recursive)


def test_stat_scan_recursive_flag_bounds_the_walk(tmp_path):
    _write_corpus(tmp_path)
    top_only, _ = stat_scan(tmp_path, str(tmp_path), {}, content_confirm_all=True, recursive=False)
    assert set(top_only) == {"a.md", "b.md"}


def test_warm_scan_against_persisted_manifest_reads_no_bytes(tmp_path, monkeypatch):
    manifest = _write_corpus(tmp_path)
    cache = tmp_path / "cache"
    key = manifest_root_key(str(tmp_path))
    write_freshness_manifest(cache, key, manifest)

    import rac.services.freshness as freshness

    reads: list[str] = []
    real = freshness.content_hash
    monkeypatch.setattr(freshness, "content_hash", lambda p: (reads.append(str(p)), real(p))[1])
    prev = open_freshness_manifest(cache, key)
    rescanned, changed = stat_scan(tmp_path, str(tmp_path), prev, content_confirm_all=False)
    assert reads == [], "an unchanged corpus must be confirmed by stats alone"
    assert changed == set() and rescanned == manifest


# =============================================================================
# load_or_build over the persisted manifest (ADR-112).
# =============================================================================


def _artifact(ident: str, title: str, body: str) -> str:
    return (
        f"---\nschema_version: 1\nid: {ident}\ntype: decision\n---\n"
        f"# {title}\n\n## Status\n\nAccepted\n\n## Category\n\nArchitecture\n\n"
        f"## Context\n\n{body}\n\n## Decision\n\nD.\n\n## Consequences\n\nE.\n"
    )


def _cache_corpus(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "corpus"
    root.mkdir()
    (root / "a.md").write_text(_artifact("RAC-01JY4MAN1FA1", "Alpha", "body one"), "utf-8")
    (root / "b.md").write_text(_artifact("RAC-01JY4MAN1FB2", "Beta", "body two"), "utf-8")
    return root, tmp_path / "cache"


def test_load_or_build_persists_the_manifest_and_warms_by_stat(tmp_path, monkeypatch):
    from rac.services.derived_cache import DerivedIndexCache

    root, cache_dir = _cache_corpus(tmp_path)
    cache = DerivedIndexCache(cache_dir)
    cold = cache.load_or_build(str(root))
    key = manifest_root_key(str(root))
    assert open_freshness_manifest(cache_dir, key), "a cold run must persist the manifest"

    import rac.services.freshness as freshness

    reads: list[str] = []
    real = freshness.content_hash
    monkeypatch.setattr(freshness, "content_hash", lambda p: (reads.append(str(p)), real(p))[1])
    warm = cache.load_or_build(str(root))
    assert reads == [], "a warm run against an unchanged corpus must read zero artifact bytes"
    assert warm == cold


def test_ordinary_edit_is_detected_through_the_manifest(tmp_path):
    from rac.services.derived_cache import DerivedIndexCache, build_derived_index

    root, cache_dir = _cache_corpus(tmp_path)
    cache = DerivedIndexCache(cache_dir)
    cache.load_or_build(str(root))
    (root / "a.md").write_text(_artifact("RAC-01JY4MAN1FA1", "Alpha Prime", "body one"), "utf-8")
    assert cache.load_or_build(str(root)) == build_derived_index(str(root))


def test_s5_rewrite_is_the_accepted_miss_and_verify_repairs(tmp_path):
    """The one enumerated stale case (ADR-105 S5, extended by ADR-112).

    A rewrite preserving both size and mtime_ns is invisible to the stat rung,
    so the default warm run serves the previous corpus state — the documented
    accepted miss. ``verify=True`` (the full-hash floor) returns fresh output
    and repairs the manifest, so the *next* default run is fresh too.
    """
    import os

    from rac.services.derived_cache import DerivedIndexCache, build_derived_index

    root, cache_dir = _cache_corpus(tmp_path)
    cache = DerivedIndexCache(cache_dir)
    stale = cache.load_or_build(str(root))

    target = root / "a.md"
    st = target.stat()
    old = target.read_text(encoding="utf-8")
    new = old.replace("body one", "body ten")  # same byte length
    assert len(new.encode()) == st.st_size and new != old
    target.write_text(new, encoding="utf-8")
    os.utime(target, ns=(st.st_atime_ns, st.st_mtime_ns))

    assert cache.load_or_build(str(root)) == stale, "the S5 rewrite is the accepted stat miss"
    fresh = build_derived_index(str(root))
    assert cache.load_or_build(str(root), verify=True) == fresh, "--verify is the floor"
    assert cache.load_or_build(str(root)) == fresh, "verify must repair the manifest"


def test_corrupt_manifest_self_heals_through_full_confirm(tmp_path):
    from rac.services.derived_cache import DerivedIndexCache, build_derived_index

    root, cache_dir = _cache_corpus(tmp_path)
    cache = DerivedIndexCache(cache_dir)
    cache.load_or_build(str(root))
    key = manifest_root_key(str(root))
    (manifest_store_root(cache_dir) / f"{key}.fseg").write_bytes(b"garbage")
    assert cache.load_or_build(str(root)) == build_derived_index(str(root))
    assert open_freshness_manifest(cache_dir, key), "the corrupt manifest must be rewritten"


def test_default_cache_dir_survives_a_homeless_environment(monkeypatch):
    from rac.services.derived_cache import default_cache_dir

    def _no_home() -> Path:
        raise RuntimeError("no usable home directory")

    monkeypatch.delenv("RAC_CACHE_DIR", raising=False)
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    monkeypatch.setattr(Path, "home", staticmethod(_no_home))
    assert default_cache_dir().name  # resolves somewhere instead of raising
