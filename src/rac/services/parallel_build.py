"""Parallel cold build of the derived read-model (ADR-107).

The cold build's cost is dominated by parsing — a fresh whole-corpus walk spends
roughly three-quarters of its wall time in :func:`rac.core.markdown.parse_file`
(the markdown tokenise + frontmatter parse), the rest in deriving the index /
relationship / token structures and serialising the segment store. Parsing is
embarrassingly parallel and pure per file, so this module fans it out across
processes while leaving the derive and serialise phases exactly as the serial
path runs them.

**Determinism is the contract, not a nicety.** Workers each parse a *contiguous*
range of the sorted ``find_markdown_files`` list, and the parent concatenates the
ranges back in list order, so the parsed snapshot is byte-for-byte the same
sequence :func:`rac.core.corpus.walk_corpus` yields — regardless of how many
workers ran. The whole derive/serialise pipeline downstream is a pure function of
that ordered snapshot, so the store bytes and every served response are identical
across worker counts (the ADR-107 worker-invariance rule). A test hashes the
segment files of a ``workers=1`` and a ``workers=4`` build and asserts equality.

**Workers call the one true parse path.** ``_worker_parse`` imports and calls the
same :func:`parse_file` / :func:`classify` the serial walk does — never a
reimplementation — so every pinned parse behaviour (``errors="replace"`` lossy
decode, the BOM-defeats-frontmatter rule, the byte-cap oversize issue) is
reproduced exactly. The byte cap is read from ``RAC_MAX_FILE_BYTES`` on every
call, and spawned workers inherit the environment, so a lowered cap applies in
workers and serial alike.

**Correctness never depends on the parallel rung.** Below a measured file-count
threshold, or on a box with ``cpu_count() <= 2``, the build stays single-process
(forking costs more than it saves at small N). Any worker fault — an exception,
a crashed child, a pickling failure — is caught and the build falls back to the
serial :func:`walk_corpus`, which can never produce a partial or corrupt
snapshot. The parallel path is a latency lever, never a correctness dependency
(the same posture ADR-080 takes for the cache).

Stdlib only (``multiprocessing`` with the spawn context — no forked-state or
lambda closures cross the boundary; the worker is a module-level function).
"""

from __future__ import annotations

import multiprocessing as mp
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from rac.core.classification import classify
from rac.core.corpus import CorpusEntry, walk_corpus
from rac.core.fs import find_markdown_files
from rac.core.markdown import parse_file
from rac.services.derived_cache import DerivedIndex, build_derived_index_from_entries

_TIMING_ENV = "RAC_TIMING"

# Spawn-safe fault-injection hook. When this env var is set, every worker raises
# on entry — exercising the worker-crash -> serial-fallback path in a *real*
# subprocess (a parent-side monkeypatch cannot reach a spawned child, which
# re-imports this module fresh). The env is inherited across spawn, so setting it
# in a test makes the children fault. Never set in production.
_FAULT_ENV = "RAC_PARALLEL_BUILD_FAULT"

# Below this file count the spawn + IPC overhead outweighs the parse win, so the
# cold build stays single-process. Measured crossover on the 4-core reference
# node: a serial parse of ~5k small artifacts is a couple of seconds, and the
# spawn of a worker set plus the round-trip of the parsed snapshot eats most of
# the theoretical speedup below that. Above it the parse win dominates. Tunable
# via RAC_PARALLEL_BUILD_MIN_FILES for measurement; never lowers correctness.
DEFAULT_MIN_PARALLEL_FILES = 5_000
_MIN_FILES_ENV = "RAC_PARALLEL_BUILD_MIN_FILES"


@dataclass
class BuildStats:
    """Per-phase cold-build timings for the ``RAC_TIMING`` scorecard line.

    ``workers`` is the number of worker processes the parse actually used — ``1``
    means the single-process path ran (small corpus, ``cpu_count() <= 2``, or a
    worker fault fell back). ``write_ms`` is filled in by the caller that owns the
    store write (the cache or the compaction path), which is where serialisation
    happens; the build itself leaves it ``0``.
    """

    files: int
    workers: int
    parse_ms: float = 0.0
    derive_ms: float = 0.0
    write_ms: float = 0.0


def _min_parallel_files() -> int:
    raw = os.environ.get(_MIN_FILES_ENV)
    if raw is None:
        return DEFAULT_MIN_PARALLEL_FILES
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_MIN_PARALLEL_FILES
    return value if value >= 0 else DEFAULT_MIN_PARALLEL_FILES


def _resolve_workers(workers: int | None, n_files: int) -> int:
    """How many worker processes to use — 1 means run single-process.

    An explicit ``workers`` (the tests' worker-count-invariance lever) is honoured
    up to the file count, so a small corpus can still be built with 4 workers to
    prove determinism. With ``workers=None`` the default policy applies: stay
    single-process on a 1-2 core box or below the file-count threshold, otherwise
    use every core.
    """
    if n_files <= 1:
        return 1
    if workers is not None:
        return max(1, min(workers, n_files))
    cpu = os.cpu_count() or 1
    if cpu <= 2 or n_files < _min_parallel_files():
        return 1
    return min(cpu, n_files)


def _contiguous_chunks(items: list[Path], n: int) -> list[list[Path]]:
    """Split ``items`` into at most ``n`` contiguous, order-preserving ranges.

    Contiguity is the determinism guarantee: concatenating the ranges in list
    order reproduces the original sorted sequence exactly, so the merged snapshot
    is worker-count-invariant.
    """
    if n <= 1:
        return [items]
    size = (len(items) + n - 1) // n
    return [items[i : i + size] for i in range(0, len(items), size)]


def _worker_parse(paths: list[Path]) -> list[CorpusEntry]:
    """Parse a contiguous range of paths through the one true core parse path.

    Identical per-file work to :func:`rac.core.corpus.walk_corpus`:
    :func:`parse_file` then :func:`classify`, wrapped in a :class:`CorpusEntry`
    carrying the original :class:`~pathlib.Path`. No reimplementation — the pinned
    decode / BOM / oversize semantics come from ``parse_file`` verbatim.
    """
    if os.environ.get(_FAULT_ENV):
        raise RuntimeError("parallel-build worker fault (injected)")
    entries: list[CorpusEntry] = []
    for path in paths:
        product = parse_file(str(path))
        entries.append(CorpusEntry(path=path, product=product, classification=classify(product)))
    return entries


def _parse_serial(paths: list[Path]) -> list[CorpusEntry]:
    # The serial fallback parses directly (not via the fault-gated ``_worker_parse``)
    # so it succeeds even when the fault env var is set: the crash-resilience test
    # sets it to make the *workers* fault, then expects this single-process path to
    # complete. Same per-file work as ``walk_corpus`` / ``_worker_parse``.
    entries: list[CorpusEntry] = []
    for path in paths:
        product = parse_file(str(path))
        entries.append(CorpusEntry(path=path, product=product, classification=classify(product)))
    return entries


def _parse_parallel(paths: list[Path], n_workers: int) -> list[CorpusEntry] | None:
    """Fan the parse out across ``n_workers`` spawned processes, or ``None`` on fault.

    Returns the parsed entries in sorted-path order, or ``None`` if any worker
    fault occurred — the caller then falls back to the serial path. Uses the spawn
    context so no forked interpreter state and no closure crosses the boundary.
    """
    chunks = _contiguous_chunks(paths, n_workers)
    try:
        ctx = mp.get_context("spawn")
        with ctx.Pool(len(chunks)) as pool:
            results = pool.map(_worker_parse, chunks)
    except BaseException:
        # Any child fault (exception, crash, pickling failure) collapses to the
        # serial path. A partially-mapped result is discarded whole — the store is
        # never written from a truncated snapshot.
        return None
    return [entry for chunk in results for entry in chunk]


def parallel_parse_paths(
    paths: list[Path], *, workers: int | None = None
) -> tuple[list[CorpusEntry], int]:
    """Parse an explicit list of paths, parallel when it pays; entries in list order.

    Returns ``(entries, workers_used)``. ``workers_used == 1`` signals the
    single-process path ran (threshold, core count, or a fault fallback). The
    entry order matches ``paths`` exactly, so a caller passing sorted paths gets a
    sorted snapshot regardless of worker count.
    """
    n_workers = _resolve_workers(workers, len(paths))
    if n_workers <= 1:
        return _parse_serial(paths), 1
    entries = _parse_parallel(paths, n_workers)
    if entries is None:
        return _parse_serial(paths), 1
    return entries, n_workers


def parallel_walk(
    directory: str, *, recursive: bool = True, workers: int | None = None
) -> tuple[list[CorpusEntry], int]:
    """Parse a whole corpus, parallel when it pays; entries in sorted-path order.

    The parallel analogue of ``list(walk_corpus(directory))``: byte-identical
    output (same entries, same sorted order), only fanned across processes. When
    the single-process path runs it delegates to :func:`walk_corpus` so the two
    code paths share one definition of the serial walk.
    """
    paths = find_markdown_files(directory, recursive=recursive)
    n_workers = _resolve_workers(workers, len(paths))
    if n_workers <= 1:
        return list(walk_corpus(directory, recursive=recursive)), 1
    entries = _parse_parallel(paths, n_workers)
    if entries is None:
        return list(walk_corpus(directory, recursive=recursive)), 1
    return entries, n_workers


def build_derived_index_parallel(
    directory: str, *, recursive: bool = True, workers: int | None = None
) -> tuple[DerivedIndex, BuildStats]:
    """Build the derived read-model with a parallel parse, then the serial derive.

    Byte-identical to :func:`rac.services.derived_cache.build_derived_index`: the
    parse is fanned out but produces the same ordered snapshot, and the derive
    phase (:func:`build_derived_index_from_entries`) is the same pure function of
    that snapshot. Returns the derived index plus the per-phase timings the
    ``RAC_TIMING`` scorecard reports; ``write_ms`` is filled by the caller that
    serialises the store.
    """
    t0 = time.perf_counter()
    entries, used = parallel_walk(directory, recursive=recursive, workers=workers)
    t1 = time.perf_counter()
    derived = build_derived_index_from_entries(directory, entries, recursive=recursive)
    t2 = time.perf_counter()
    return derived, BuildStats(
        files=len(entries),
        workers=used,
        parse_ms=(t1 - t0) * 1000.0,
        derive_ms=(t2 - t1) * 1000.0,
    )


def emit_build_timing(stats: BuildStats) -> None:
    """Write the cold-build scorecard line to stderr when ``RAC_TIMING`` is set.

    Env-gated and stderr-only (stdout is a frozen contract); absent by default.
    Mirrors the incremental-validate ``rac-timing:`` line shape (ADR-106).
    """
    if _TIMING_ENV not in os.environ:
        return
    sys.stderr.write(
        f"rac-timing: build_parse_ms={stats.parse_ms:.3f} "
        f"build_derive_ms={stats.derive_ms:.3f} build_write_ms={stats.write_ms:.3f} "
        f"workers={stats.workers} files={stats.files}\n"
    )
