"""Movement-B bundle B5 — scale hardening: parallel cold build + RSS (ADR-104).

B5 fans the cold-build parse across processes and sheds the serving tracker's
resident parsed snapshot after compaction. These tests pin what that must
guarantee:

(a) **Worker-count determinism** — the same corpus built with ``workers=1`` and
    ``workers=4`` produces byte-identical store segment files (hashed) and
    byte-identical served responses. Merge order is fixed by sorted path, so the
    worker count is invisible to every output byte (the ADR-104 determinism rule).
    The ``workers=4`` build is asserted to have actually run parallel, so the
    equality is not vacuously the serial path twice.
(b) **Parse-semantics parity** — a corpus containing a non-UTF8 file, a BOM file,
    and an oversize file builds byte-identically parallel vs serial, because the
    workers call the one true ``parse_file`` (lossy ``errors="replace"`` decode,
    BOM-defeats-frontmatter, the byte-cap oversize issue), never a reimplementation.
    The byte cap is lowered through ``RAC_MAX_FILE_BYTES``, which spawned workers
    inherit, so the cap applies in workers and serial alike.
(c) **Post-compaction snapshot shed** — after a compaction the tracker drops its
    resident ``Product`` snapshot and re-serves from the mmap base; RSS stays
    bounded through the cycle, the shed is observable, and serving stays correct
    (the tracker re-parses changed files on demand). The RSS assertion mirrors
    B2's bounded-growth form through a compaction cycle (Python's allocator does
    not return arenas to the OS on free, so the reliable proof of the shed is the
    dropped snapshot plus continued correctness, not a raw RSS return-to-zero).
(d) **Worker-crash resilience** — a worker exception degrades to the serial path,
    never a corrupt or partial store: the fault-injected build's segments equal a
    clean serial build's, and it reports ``workers == 1`` (it fell back).
(e) **RAC_TIMING line shape** — the cold build emits one ``rac-timing:`` line to
    stderr under ``RAC_TIMING``, absent by default, stdout untouched.

Runtime is kept under a minute: the parity corpora are small (spawn overhead
dominates there) and only the RSS test uses a few thousand files.
"""

from __future__ import annotations

import ctypes
import gc
import hashlib
import os
import re
from pathlib import Path

from rac.services.derived_cache import DerivedIndexCache, build_derived_index
from rac.services.freshness import FreshnessTracker
from rac.services.index_store import open_read_model, store_dir, write_store
from rac.services.parallel_build import build_derived_index_parallel

_BUNDLE_VERSION = "2"


def _decision(i: int, *, title: str | None = None, body: str = "alpha beta gamma") -> str:
    ident = f"RAC-{i:012d}"
    return (
        f"---\nschema_version: 1\nid: {ident}\ntype: decision\n---\n"
        f"# {title or f'Decision {i}'}\n\n## Status\n\nAccepted\n\n## Category\n\n"
        f"Architecture\n\n## Context\n\n{body}\n\n## Decision\n\nD {i}.\n\n"
        f"## Consequences\n\nE {i}.\n"
    )


def _build_corpus(root: Path, n: int) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        shard = root / f"shard{i // 200:03d}"
        shard.mkdir(exist_ok=True)
        (shard / f"a{i:05d}.md").write_text(_decision(i, body=f"term{i % 30} shared word"), "utf-8")
    return root


def _corpus_hash(directory: str) -> str:
    from rac.core.corpus import corpus_content_hash

    return corpus_content_hash(directory)


def _segment_hashes(cache_dir: Path, corpus_hash: str) -> dict[str, str]:
    directory = store_dir(cache_dir, corpus_hash)
    return {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(directory.iterdir())
        if p.is_file()
    }


def _build_and_store(directory: str, cache_dir: Path, workers: int) -> tuple[dict[str, str], int]:
    """Build with a fixed worker count, write the store, return segment hashes + workers used."""
    derived, stats = build_derived_index_parallel(directory, workers=workers)
    assert write_store(cache_dir, _corpus_hash(directory), _BUNDLE_VERSION, derived)
    return _segment_hashes(cache_dir, _corpus_hash(directory)), stats.workers


# =============================================================================
# (a) Worker-count determinism — byte-identical store + serving across counts.
# =============================================================================


def test_workers1_and_workers4_produce_byte_identical_store(tmp_path):
    root = _build_corpus(tmp_path / "corpus", 240)

    serial_hashes, serial_used = _build_and_store(str(root), tmp_path / "cache1", workers=1)
    parallel_hashes, parallel_used = _build_and_store(str(root), tmp_path / "cache4", workers=4)

    # The parallel build must actually have run parallel — otherwise this is two
    # serial builds and the equality is vacuous.
    assert serial_used == 1
    assert parallel_used >= 2, "workers=4 must fan out, else the determinism check is vacuous"

    # Every segment file is byte-for-byte identical: docids, postings, termdict,
    # every derived row — the whole store — is worker-count-invariant.
    assert parallel_hashes == serial_hashes
    assert set(serial_hashes) >= {"header.seg", "postings.seg", "termdict.seg", "entries.seg"}


def test_serving_responses_identical_across_worker_counts(tmp_path):
    root = _build_corpus(tmp_path / "corpus", 240)
    corpus_hash = _corpus_hash(str(root))
    _build_and_store(str(root), tmp_path / "cache1", workers=1)
    _build_and_store(str(root), tmp_path / "cache4", workers=4)

    with (
        open_read_model(tmp_path / "cache1", corpus_hash, _BUNDLE_VERSION) as v1,
        open_read_model(tmp_path / "cache4", corpus_hash, _BUNDLE_VERSION) as v4,
    ):
        assert v1 is not None and v4 is not None
        # Search (Θ(N), touches the scoring tail), point identity, and the portfolio
        # aggregate all match across worker counts.
        assert v1.search("shared word").matches == v4.search("shared word").matches
        assert v1.identity_entries == v4.identity_entries
        assert v1.portfolio_summary == v4.portfolio_summary
        # And both equal a fresh serial build — parity is against the walk, not just
        # against each other.
        assert v4 == build_derived_index(str(root))


# =============================================================================
# (b) Parse-semantics parity — non-UTF8 / BOM / oversize, parallel vs serial.
# =============================================================================


def test_parse_semantics_parity_parallel_vs_serial(tmp_path, monkeypatch):
    root = tmp_path / "corpus"
    root.mkdir()
    # Enough valid files to split across four workers, plus the three edge files.
    for i in range(60):
        (root / f"d{i:03d}.md").write_text(_decision(i, body="valid content here"), "utf-8")

    # A non-UTF8 file: parse_file decodes errors="replace" and appends a
    # non-utf8-content warning — the worker must reproduce that exactly.
    (root / "nonutf8.md").write_bytes(
        b"---\nschema_version: 1\nid: RAC-000000009001\ntype: decision\n---\n"
        b"# Bad Bytes\n\n## Status\n\nAccepted\n\n## Context\n\n\xff\xfe not utf-8 \x80\x81\n"
    )
    # A BOM file: the leading BOM defeats frontmatter (decoded as utf-8, not
    # utf-8-sig), so identity falls back to the filename — core-data §1.3-1.
    (root / "bom.md").write_bytes(
        b"\xef\xbb\xbf---\nschema_version: 1\nid: RAC-000000009002\ntype: decision\n---\n"
        b"# BOM Title\n\n## Status\n\nAccepted\n"
    )
    # An oversize file, under a lowered cap that spawned workers inherit via the
    # environment — parse_file emits the artifact-oversize issue in both paths.
    monkeypatch.setenv("RAC_MAX_FILE_BYTES", "1500")
    (root / "oversize.md").write_text(
        "---\nschema_version: 1\nid: RAC-000000009003\ntype: decision\n---\n# Big\n\n"
        + "x " * 2000,
        "utf-8",
    )

    serial_hashes, serial_used = _build_and_store(str(root), tmp_path / "cache1", workers=1)
    parallel_hashes, parallel_used = _build_and_store(str(root), tmp_path / "cache4", workers=4)

    assert parallel_used >= 2
    assert parallel_hashes == serial_hashes, "workers diverged from serial on an edge-case file"


# =============================================================================
# (c) Post-compaction snapshot shed — bounded RSS, observable shed, correct serve.
# =============================================================================


def _rss_mb() -> float:
    # Current resident set (not the ru_maxrss high-water mark, which never falls),
    # so a shed is at least observable as a non-increase.
    with open("/proc/self/statm") as handle:
        resident_pages = int(handle.read().split()[1])
    return resident_pages * os.sysconf("SC_PAGE_SIZE") / (1024 * 1024)


def _trim() -> None:
    gc.collect()
    try:
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except OSError:  # pragma: no cover — non-glibc
        pass


def test_post_compaction_sheds_resident_snapshot_and_stays_correct(tmp_path):
    root = _build_corpus(tmp_path / "corpus", 3_000)
    cache = DerivedIndexCache(tmp_path / "cache")
    tracker = FreshnessTracker(cache, str(root), use_inotify=False, compaction_threshold=2)
    try:
        _trim()
        baseline = _rss_mb()

        # Cold start compacts (establishes base generation 1) and then sheds: the
        # mmap base is the whole answer, so the resident Products are dropped.
        assert tracker.read_model() == build_derived_index(str(root))
        assert tracker.base_generation == 1
        assert tracker._snapshot_shed is True
        assert tracker._entries == {}, "the resident parsed snapshot must be shed after compaction"

        # An unchanged read serves from the base with nothing re-parsed and stays shed.
        assert tracker.read_model() == build_derived_index(str(root))
        assert tracker._snapshot_shed is True

        # A change repopulates the snapshot on demand (the re-parse the shed trades
        # for the RSS win) and serves fresh, byte-identical bytes.
        (root / "shard000" / "a00000.md").write_text(
            _decision(0, title="Edited", body="moved token7"), "utf-8"
        )
        assert tracker.read_model() == build_derived_index(str(root))
        assert tracker._snapshot_shed is False
        resident_peak = _rss_mb()

        # A second change crosses the threshold -> compaction -> shed again.
        (root / "shard000" / "a00001.md").write_text(
            _decision(1, title="Edited Two", body="second token9"), "utf-8"
        )
        assert tracker.read_model() == build_derived_index(str(root))
        assert tracker.base_generation == 2
        assert tracker._snapshot_shed is True
        assert tracker._entries == {}

        _trim()
        shed_rss = _rss_mb()
        # The shed never costs memory (it can only reclaim or be neutral) and the
        # whole cycle stays within a generous absolute bound of the pre-parse
        # baseline — no whole-corpus snapshot is retained across compactions.
        assert shed_rss <= resident_peak + 25, "shedding must not grow RSS past the resident peak"
        assert shed_rss - baseline < 250, f"RSS grew {shed_rss - baseline:.0f} MB through the cycle"
    finally:
        tracker.close()


# =============================================================================
# (d) Worker-crash resilience — a fault degrades to the serial path, no corruption.
# =============================================================================


def test_worker_fault_degrades_to_serial_never_a_corrupt_store(tmp_path, monkeypatch):
    root = _build_corpus(tmp_path / "corpus", 240)

    # A clean serial build is the ground truth.
    clean_hashes, _ = _build_and_store(str(root), tmp_path / "clean", workers=1)

    # Every worker faults (env inherited across spawn); the build must fall back to
    # the single-process path and produce the identical store, never a partial one.
    monkeypatch.setenv("RAC_PARALLEL_BUILD_FAULT", "1")
    derived, stats = build_derived_index_parallel(str(root), workers=4)
    assert stats.workers == 1, "a worker fault must degrade to the single-process path"
    assert write_store(tmp_path / "recovered", _corpus_hash(str(root)), _BUNDLE_VERSION, derived)
    recovered_hashes = _segment_hashes(tmp_path / "recovered", _corpus_hash(str(root)))

    assert recovered_hashes == clean_hashes
    assert derived == build_derived_index(str(root))


# =============================================================================
# (e) RAC_TIMING line shape — stderr-only, opt-in.
# =============================================================================

_TIMING_RE = re.compile(
    r"rac-timing: build_parse_ms=[\d.]+ build_derive_ms=[\d.]+ "
    r"build_write_ms=[\d.]+ workers=\d+ files=\d+"
)


def test_timing_line_is_stderr_only_and_opt_in(tmp_path, capsys, monkeypatch):
    root = _build_corpus(tmp_path / "corpus", 40)

    # Absent by default on both streams.
    DerivedIndexCache(tmp_path / "cache_quiet").load_or_build(str(root))
    quiet = capsys.readouterr()
    assert "rac-timing" not in quiet.err
    assert "rac-timing" not in quiet.out

    # Present on stderr (only) under RAC_TIMING, on the cold build.
    monkeypatch.setenv("RAC_TIMING", "1")
    DerivedIndexCache(tmp_path / "cache_timed").load_or_build(str(root))
    timed = capsys.readouterr()
    assert "rac-timing" not in timed.out, "stdout is a frozen contract"
    assert _TIMING_RE.search(timed.err), f"timing line shape wrong: {timed.err!r}"
