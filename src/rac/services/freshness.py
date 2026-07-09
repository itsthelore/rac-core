"""Event-sourced serving freshness for the long-lived MCP server (ADR-105).

ADR-032 kept every ``rac mcp`` tool call re-reading the whole repository, and
ADR-099/ADR-104 kept that posture on the opt-in cache path: the corpus content
hash — an Ω(bytes) read of *every* file — is recomputed on every call, so warm
serving latency scales with corpus size even when nothing changed. This module
replaces that per-call full re-hash with a **server-lifetime freshness tracker**
that answers "did the corpus change since the last call, and if so which files?"
without reading the bytes of unchanged files.

**The fallback ladder** (v2 §2.1, ADR-105). Change detection degrades cleanly,
and *correctness never depends on the fast rung*:

1. **inotify** (Linux, ctypes, stdlib only) — a watch set over every directory
   the walk descends. A drain that yields **zero events** proves the corpus is
   unchanged, so the tracker skips detection entirely and returns the cached
   read-model: warm latency independent of corpus size (the flat line). inotify
   is only ever trusted to say *clean*; the moment it reports *anything* — an
   event, a queue overflow, a watch it could not establish — the authoritative
   stat-scan runs. It is an accelerator, never the arbiter.
2. **stat-manifest scan** (the primary, always-available differ) — enumerate the
   walk's files (``find_markdown_files`` — the exact same scope), ``stat`` each
   for ``(size, mtime_ns)``, and content-confirm (read + hash) only the files
   whose stat changed or that are new. Enumeration makes add / remove / rename
   staleness-free (the path set is ground truth); the sole missable case is an
   in-place rewrite that preserves *both* size and mtime_ns (S5).
3. **full re-hash** (the floor, always correct) — read and hash every file, byte
   for byte the legacy ``corpus_content_hash``. It catches even S5 and is the
   ``verify=True`` path.

**Events are triggers, content is truth.** Every path a detector flags is
content-hash-confirmed (its bytes read) before it mutates the tracker's state, so
a spurious event costs one file read, never a wrong answer.

**Byte-parity is the contract.** Whatever the detection rung, the served
read-model is re-derived from the tracker's incrementally-maintained parsed
snapshot through :func:`build_derived_index_from_entries` — re-parsing only the
changed files — so it is byte-identical to a fresh whole-corpus walk at the
current corpus state. The residual race is exactly the walk's own: a write that
*completes* before a call is observed by it (the kernel queues the inotify event,
or the stat reflects the completed write); a write racing *concurrently* with a
call is unordered against it precisely as it is against a fresh walk. The tracker
is no weaker than ADR-032's re-read for completed writes.

**The delta window and compaction.** The on-disk memory-mapped base (ADR-104) is
written for a corpus hash; while the corpus drifts within a bounded window of
changed files, reads are served from the re-derived snapshot (the delta) without
rewriting the base. When the window crosses the compaction threshold a fresh base
is written for the current hash (atomic ``os.replace`` under the store writer) and
the window resets — the LSM-style base+delta+compaction shape ADR-104 built the
fold seam for.

Stdlib only (``ctypes``/``os``/``struct``); no watchdog, no mcp file-watch dep.
"""

from __future__ import annotations

import ctypes
import errno
import os
import struct
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from rac.core.corpus import CorpusEntry, content_hash
from rac.core.fs import find_markdown_files
from rac.services.derived_cache import (
    SCHEMA_VERSION,
    CorpusReadModel,
    DerivedIndex,
    DerivedIndexCache,
    build_derived_index_from_entries,
)
from rac.services.parallel_build import (
    BuildStats,
    emit_build_timing,
    parallel_parse_paths,
)

# Detection modes, worst-rung last — the fallback ladder made explicit so a
# scorecard (and the degraded-mode test) can name the active rung honestly.
MODE_INOTIFY = "inotify"
MODE_STAT = "stat"
MODE_REHASH = "rehash"


@dataclass(frozen=True)
class FileState:
    """The freshness proxy for one file: its content hash and its stat pair.

    ``content_hash`` is the parity-bearing truth (the same digest
    ``corpus_content_hash`` composes); ``size``/``mtime_ns`` are the cheap stat
    proxy the stat-scan diffs on, never a parity input (v2 §1.2 manifest note).
    """

    content_hash: str
    size: int
    mtime_ns: int


def _relposix(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def stat_scan(
    root: Path,
    root_str: str,
    prev_manifest: dict[str, FileState],
    *,
    content_confirm_all: bool,
    recursive: bool = True,
) -> tuple[dict[str, FileState], set[str]]:
    """Diff the corpus against ``prev_manifest`` by stat, content-confirming changes.

    The stat-manifest rung (v2 §2.2) factored out so the long-lived
    :class:`FreshnessTracker`, the one-shot CLI incremental-validate path
    (ADR-106), and the one-shot find manifest (ADR-112) share one differ — the
    manifest-scan machinery is identical, so it is defined once here rather
    than copied. Pure over ``(filesystem, root, prev_manifest)`` with no
    tracker state, so a caller can drive it with any persisted manifest.

    Enumerates the walk's files (``find_markdown_files`` — the exact walk scope),
    stats each for ``(size, mtime_ns)``, and reuses the previous manifest's hash
    when the stat proxy is unchanged (the S5-accepted stat rung) unless
    ``content_confirm_all`` forces a read (cold build and the ``verify`` floor).
    Enumeration makes add / remove / rename staleness-free — a vanished relpath is
    a change even though no file was read for it. Returns the rebuilt manifest and
    the set of relpaths whose *content* changed, plus removals; the caller owns
    what to do with them (re-parse, re-validate, drop) and where to persist the
    manifest.
    """
    changed: set[str] = set()
    new_manifest: dict[str, FileState] = {}
    for path in find_markdown_files(root_str, recursive=recursive):
        rel = _relposix(root, path)
        try:
            st = path.stat()
        except OSError:
            # Vanished between enumeration and stat — treat as absent; it simply
            # does not enter the new manifest and the next scan settles it.
            continue
        prev = prev_manifest.get(rel)
        if (
            not content_confirm_all
            and prev is not None
            and prev.size == st.st_size
            and prev.mtime_ns == st.st_mtime_ns
        ):
            new_manifest[rel] = prev  # stat proxy unchanged — S5 accepted miss
            continue
        digest = content_hash(path)  # content confirm — the trigger's truth
        new_manifest[rel] = FileState(content_hash=digest, size=st.st_size, mtime_ns=st.st_mtime_ns)
        if prev is None or prev.content_hash != digest:
            changed.add(rel)
    for rel in prev_manifest:
        if rel not in new_manifest:
            changed.add(rel)  # removed (or renamed away) — enumeration is truth
    return new_manifest, changed


def corpus_hash_from_manifest(
    root: Path, manifest: dict[str, FileState], *, recursive: bool = True
) -> str:
    """Reproduce :func:`corpus_content_hash` from the manifest's cached hashes.

    Iterates the *same* sorted ``find_markdown_files`` order and folds the same
    ``rel\\0hash\\0`` bytes, but reuses each file's already-known content hash
    instead of re-reading it — so the key is byte-identical to a full re-hash for
    every non-S5 state, at O(files) enumeration cost with no O(bytes) reads.
    Public because the one-shot find path (ADR-112) recomposes its
    content-addressed store key through the same fold.
    """
    import hashlib

    hasher = hashlib.sha256()
    for path in find_markdown_files(str(root), recursive=recursive):
        rel = _relposix(root, path)
        state = manifest.get(rel)
        digest = state.content_hash if state is not None else content_hash(path)
        hasher.update(rel.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(digest.encode("ascii"))
        hasher.update(b"\0")
    return hasher.hexdigest()


# =============================================================================
# inotify — the flat-line accelerator (Linux, ctypes, stdlib only).
# =============================================================================

# inotify_add_watch mask: the events that can change a *.md the walk sees. Dir
# creates/moves extend the watch set; modify/create/delete/move flag dirtiness.
_IN_MODIFY = 0x00000002
_IN_MOVED_FROM = 0x00000040
_IN_MOVED_TO = 0x00000080
_IN_CREATE = 0x00000100
_IN_DELETE = 0x00000200
_IN_DELETE_SELF = 0x00000400
_IN_MOVE_SELF = 0x00000800
_IN_CLOSE_WRITE = 0x00000008
_IN_ISDIR = 0x40000000
_IN_Q_OVERFLOW = 0x00004000
_IN_NONBLOCK = 0x00000800  # O_NONBLOCK for inotify_init1

_WATCH_MASK = (
    _IN_MODIFY
    | _IN_CLOSE_WRITE
    | _IN_CREATE
    | _IN_DELETE
    | _IN_DELETE_SELF
    | _IN_MOVED_FROM
    | _IN_MOVED_TO
    | _IN_MOVE_SELF
)

# struct inotify_event { int wd; uint32 mask; uint32 cookie; uint32 len; char[] }
_EVENT_HEADER = struct.Struct("iIII")


class INotifyUnavailable(Exception):
    """inotify could not be initialised or the watch set could not be completed."""


class INotifyWatcher:
    """A conservative directory watch set that only ever asserts *clean*.

    The correctness contract is narrow on purpose: :meth:`poll_dirty` returns
    ``False`` (skip the stat-scan) **only** when the watch set is known complete,
    no queue overflow has ever been seen, and the drain yielded no event. Any
    doubt — an unwatchable directory, an overflow, a failed rescan of a freshly
    created directory — latches ``self._trusted = False`` so every future call
    reports dirty and the authoritative stat-scan runs. A missed event can never
    be silently absorbed into a *clean* verdict.
    """

    def __init__(self, root: Path) -> None:
        self._root = root
        self._libc = self._load_libc()
        fd = self._libc.inotify_init1(_IN_NONBLOCK)
        if fd < 0:
            raise INotifyUnavailable("inotify_init1 failed")
        self._fd = fd
        self._wd_to_dir: dict[int, Path] = {}
        self._dir_to_wd: dict[Path, int] = {}
        self._trusted = True
        try:
            for directory in _walk_dirs(root):
                self._add_watch(directory)
        except BaseException:
            self.close()
            raise
        if not self._trusted:
            self.close()
            raise INotifyUnavailable("could not establish a complete watch set")

    @staticmethod
    def _load_libc() -> ctypes.CDLL:
        if not hasattr(ctypes, "CDLL") or os.name != "posix":
            raise INotifyUnavailable("no ctypes/posix")
        try:
            libc = ctypes.CDLL(None, use_errno=True)
            if not hasattr(libc, "inotify_init1") or not hasattr(libc, "inotify_add_watch"):
                raise INotifyUnavailable("libc lacks inotify")
        except OSError as exc:  # pragma: no cover — platform-dependent
            raise INotifyUnavailable(str(exc)) from exc
        libc.inotify_init1.argtypes = [ctypes.c_int]
        libc.inotify_add_watch.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32]
        libc.inotify_rm_watch.argtypes = [ctypes.c_int, ctypes.c_int]
        return libc

    def _add_watch(self, directory: Path) -> None:
        wd = self._libc.inotify_add_watch(self._fd, os.fsencode(str(directory)), _WATCH_MASK)
        if wd < 0:
            # An unwatchable directory (permissions, a filesystem inotify cannot
            # observe, the watch limit) means the clean signal can no longer be
            # trusted — degrade permanently to always-dirty (stat-scan runs).
            self._trusted = False
            return
        self._wd_to_dir[wd] = directory
        self._dir_to_wd[directory] = wd

    def poll_dirty(self) -> bool:
        """Drain the queue to EAGAIN; return whether anything (may have) changed.

        ``True`` on any event, any overflow, or lost trust; new directories are
        watched-then-flagged-dirty so their entries are picked up by the ensuing
        stat-scan (watch-then-rescan). ``False`` only under full trust with an
        empty drain — the flat-line skip.
        """
        if not self._trusted:
            return True
        dirty = False
        while True:
            try:
                buf = os.read(self._fd, 64 * 1024)
            except OSError as exc:
                if exc.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
                    break
                self._trusted = False
                return True
            if not buf:
                break
            dirty = True
            self._consume(buf)
        return dirty or not self._trusted

    def _consume(self, buf: bytes) -> None:
        offset = 0
        n = len(buf)
        while offset + _EVENT_HEADER.size <= n:
            wd, mask, _cookie, length = _EVENT_HEADER.unpack_from(buf, offset)
            offset += _EVENT_HEADER.size
            name = buf[offset : offset + length].split(b"\0", 1)[0]
            offset += length
            if mask & _IN_Q_OVERFLOW:
                # The queue overflowed: rebuild the watch set first, then let the
                # caller's stat-scan re-verify (v2 §2.1 step 5). Rewatching before
                # verify means directories created during the gap are watched
                # before the scan that would otherwise miss their future edits.
                self._rebuild_watches()
                continue
            parent = self._wd_to_dir.get(wd)
            if parent is not None and mask & _IN_ISDIR and mask & (_IN_CREATE | _IN_MOVED_TO):
                child = parent / os.fsdecode(name)
                self._watch_new_subtree(child)

    def _watch_new_subtree(self, directory: Path) -> None:
        # A new directory: watch it and everything beneath it, so entries created
        # before the watch existed are covered by the stat-scan and future edits
        # within it are observed (recursive-inotify correctness, v2 §2.1 step 2).
        try:
            if not directory.is_dir() or directory.is_symlink():
                return
            for sub in _walk_dirs(directory):
                if sub not in self._dir_to_wd:
                    self._add_watch(sub)
        except OSError:
            self._trusted = False

    def _rebuild_watches(self) -> None:
        for wd in list(self._wd_to_dir):
            self._libc.inotify_rm_watch(self._fd, wd)
        self._wd_to_dir.clear()
        self._dir_to_wd.clear()
        try:
            for directory in _walk_dirs(self._root):
                self._add_watch(directory)
        except OSError:
            self._trusted = False

    def close(self) -> None:
        fd = getattr(self, "_fd", -1)
        if fd >= 0:
            try:
                os.close(fd)
            except OSError:
                pass
            self._fd = -1


def _walk_dirs(root: Path) -> Iterator[Path]:
    """Every directory the corpus walk descends: dotted dirs pruned, symlinks not
    followed — the same scope ``find_markdown_files`` traverses, so a watched-set
    edit to any in-scope ``*.md`` is observed (v2 §2.1 step 6 scope-equality)."""
    root = Path(root)
    if not root.is_dir():
        return
    yield root
    for dirpath, dirnames, _files in os.walk(root, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        for name in dirnames:
            yield Path(dirpath) / name


# =============================================================================
# FreshnessTracker — the server-lifetime state ADR-105 records.
# =============================================================================


class FreshnessTracker:
    """Server-lifetime freshness for one repository root under the cache (ADR-105).

    Replaces the per-call ``corpus_content_hash`` re-hash with the fallback
    ladder. It owns:

    - ``_manifest`` — relpath -> :class:`FileState`, the current known corpus.
    - ``_entries`` — the parsed snapshot, re-parsed only where files change.
    - ``_read_model`` + ``_hash`` — the last served read-model and its corpus hash.
    - ``_base_hash`` / ``_base_generation`` — the on-disk mmap base the store holds
      and how many times it has been (re)written; ``_delta_paths`` is the window of
      files changed since that base, which compaction folds back in.

    :meth:`read_model` is the whole serving surface; every MCP tool reads through
    it instead of ``cache.load_or_build``.
    """

    def __init__(
        self,
        cache: DerivedIndexCache,
        root: str,
        *,
        compaction_threshold: int | None = None,
        use_inotify: bool = True,
    ) -> None:
        self._cache = cache
        self._root = Path(root)
        self._root_str = root
        self._threshold = compaction_threshold
        self._use_inotify = use_inotify

        self._manifest: dict[str, FileState] = {}
        self._entries: dict[str, CorpusEntry] = {}
        self._read_model: CorpusReadModel | None = None
        self._hash: str | None = None
        self._base_hash: str | None = None
        self._base_generation = 0
        self._delta_paths: set[str] = set()
        # ADR-107 RSS finalization: after compaction the resident parsed snapshot
        # (`_entries`) is shed and the mmap base becomes the whole answer. This flag
        # records that shed state so the next change repopulates the snapshot by a
        # re-parse on demand rather than assuming the (now empty) dict is complete.
        self._snapshot_shed = False
        self._last_parse_workers = 1

        self._watcher: INotifyWatcher | None = None
        self._mode = MODE_STAT
        if use_inotify:
            try:
                self._watcher = INotifyWatcher(self._root)
                self._mode = MODE_INOTIFY
            except INotifyUnavailable:
                self._watcher = None
                self._mode = MODE_STAT

    # --- observable state (for scorecards and the pinning tests) --------------

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def base_generation(self) -> int:
        return self._base_generation

    @property
    def delta_size(self) -> int:
        return len(self._delta_paths)

    @property
    def corpus_hash(self) -> str | None:
        return self._hash

    # --- the serving surface --------------------------------------------------

    def read_model(self, *, verify: bool = False) -> CorpusReadModel:
        """The current read-model, freshened through the fallback ladder.

        Drains the watcher to a barrier, detects the changed set (content-confirmed),
        and — only when the corpus actually changed — re-parses the changed files and
        re-derives the read-model, byte-identically to a fresh walk. An unchanged
        corpus returns the cached read-model with no re-hash and no re-derive.
        """
        cold = self._read_model is None
        changed = self._detect(verify=verify)
        if not changed and self._read_model is not None:
            return self._read_model
        if not cold:
            self._apply(changed)
            self._rebuild_read_model()
            self._maybe_compact()
            assert self._read_model is not None
            return self._read_model
        # Cold start: the whole corpus is parsed from nothing. Time the three cold
        # phases (parallel parse, derive, store write) and emit the RAC_TIMING
        # scorecard line, mirroring the cache's cold-build line (ADR-107).
        import time

        parse_start = time.perf_counter()
        self._apply(changed)
        derive_start = time.perf_counter()
        self._rebuild_read_model()
        write_start = time.perf_counter()
        self._maybe_compact()
        end = time.perf_counter()
        emit_build_timing(
            BuildStats(
                files=len(self._manifest),
                workers=self._last_parse_workers,
                parse_ms=(derive_start - parse_start) * 1000.0,
                derive_ms=(write_start - derive_start) * 1000.0,
                write_ms=(end - write_start) * 1000.0,
            )
        )
        assert self._read_model is not None
        return self._read_model

    # --- detection: the fallback ladder ---------------------------------------

    def _detect(self, *, verify: bool) -> set[str]:
        """Return the set of changed/added/removed relpaths since the last call.

        Cold (empty manifest) or ``verify`` forces the full authoritative scan.
        Otherwise the inotify clean signal can skip the scan; a dirty (or absent)
        watcher runs the stat-manifest scan.
        """
        if self._read_model is None:
            return self._scan(content_confirm_all=True)
        if verify:
            return self._scan(content_confirm_all=True)
        if self._watcher is not None and not self._watcher.poll_dirty():
            return set()  # inotify proved clean — the flat-line skip
        return self._scan(content_confirm_all=False)

    def _scan(self, *, content_confirm_all: bool) -> set[str]:
        """Stat-manifest scan (or full re-hash when ``content_confirm_all``).

        Enumeration over ``find_markdown_files`` makes add/remove/rename
        staleness-free; per-file it reuses the manifest's hash when ``(size,
        mtime_ns)`` is unchanged (the stat rung) unless ``content_confirm_all``
        forces a read (cold build and the full-rehash floor). The returned set is
        the relpaths whose *content* actually changed, plus removals.
        """
        new_manifest, changed = stat_scan(
            self._root, self._root_str, self._manifest, content_confirm_all=content_confirm_all
        )
        self._manifest = new_manifest
        return changed

    # --- applying the changed set --------------------------------------------

    def _apply(self, changed: set[str]) -> None:
        """Re-parse only the changed files; drop the removed; update the window.

        Two regimes:

        - **Snapshot resident** (the common case): re-parse just the changed,
          still-present files and splice them into ``_entries``; drop the removed.
          The cold start is this regime with ``changed`` equal to the whole corpus,
          so the initial full parse is fanned across processes (ADR-107).
        - **Snapshot shed** (the call after a compaction dropped ``_entries`` to
          reclaim RSS): the dict is empty, so the changed set alone would leave the
          unchanged files unrepresented. Repopulate the whole snapshot by re-parsing
          the current tree — the on-demand re-parse the shed traded for the RSS win.
          The re-parsed bytes already reflect ``changed``, so no separate splice is
          needed.
        """
        current = set(self._manifest)
        if self._snapshot_shed:
            self._reparse_full()
            self._snapshot_shed = False
        else:
            present = [rel for rel in changed if rel in current]
            for rel in changed:
                if rel not in current:
                    self._entries.pop(rel, None)  # removed
            parsed, workers = parallel_parse_paths([self._root / rel for rel in present])
            self._last_parse_workers = workers
            for entry in parsed:
                self._entries[_relposix(self._root, entry.path)] = entry
        # Drop any snapshot entry no longer enumerated (defensive; removals above
        # already cover the common path).
        for rel in list(self._entries):
            if rel not in current:
                self._entries.pop(rel, None)
        if changed:
            self._delta_paths |= changed
        self._hash = corpus_hash_from_manifest(self._root, self._manifest)

    def _reparse_full(self) -> None:
        """Rebuild the full parsed snapshot from the current manifest (parallel).

        Used on cold start (via ``_apply`` when ``_snapshot_shed`` was never set,
        the manifest is empty and this is skipped — the changed set covers all) and,
        crucially, after a shed: the mmap base holds derived rows but not parsed
        Products, so the snapshot the fold re-derives from is rebuilt by re-parsing
        the current tree. Byte-parity is preserved because the parse is of the exact
        current bytes, in the same order the serial walk would yield.
        """
        rels = list(self._manifest)
        parsed, workers = parallel_parse_paths([self._root / rel for rel in rels])
        self._last_parse_workers = workers
        self._entries = {_relposix(self._root, entry.path): entry for entry in parsed}

    def _ordered_entries(self) -> list[CorpusEntry]:
        """The snapshot in ``find_markdown_files`` order — the fresh-walk order."""
        return [
            self._entries[_relposix(self._root, path)]
            for path in find_markdown_files(self._root_str)
            if _relposix(self._root, path) in self._entries
        ]

    def _rebuild_read_model(self) -> None:
        assert self._hash is not None
        # A store already on disk for this exact hash (cold, compacted, or a revert
        # to a prior state) serves from the memory-mapped base — point access, no
        # resident derived structures (ADR-104). Otherwise re-derive over the
        # snapshot: byte-identical to a fresh walk, re-parsing only changed files.
        if self._hash == self._base_hash and not self._delta_paths:
            view = self._open_base(self._hash)
            if view is not None:
                self._read_model = view
                return
        self._read_model = build_derived_index_from_entries(self._root_str, self._ordered_entries())

    def _open_base(self, corpus_hash: str) -> CorpusReadModel | None:
        from rac.services.index_store import open_read_model

        return open_read_model(self._cache.cache_dir, corpus_hash, SCHEMA_VERSION)

    # --- compaction: fold the delta window back into a fresh base -------------

    def _threshold_for(self, base_count: int) -> int:
        if self._threshold is not None:
            return self._threshold
        # v2 §1.2: delta docs > max(10k, 1% of base). A small corpus therefore
        # never compacts on an ordinary edit — the delta window absorbs it and the
        # base is left intact (the delta-without-rebuild property) until the window
        # is genuinely large.
        return max(10_000, base_count // 100)

    def _maybe_compact(self) -> None:
        """Rewrite the on-disk base for the current hash when the window is large.

        The atomic swap is the store writer's ``os.replace`` (ADR-104); on success
        the base hash advances, the generation bumps, and the delta window resets,
        so subsequent unchanged reads serve from the mapped base again.
        """
        assert self._hash is not None
        if self._base_hash is None:
            self._compact()  # cold: establish the first base
            return
        if len(self._delta_paths) >= self._threshold_for(len(self._manifest)):
            self._compact()

    def _compact(self) -> None:
        from rac.services.index_store import write_store

        assert self._hash is not None
        derived = self._read_model
        if not isinstance(derived, DerivedIndex):
            derived = build_derived_index_from_entries(self._root_str, self._ordered_entries())
        written = write_store(self._cache.cache_dir, self._hash, SCHEMA_VERSION, derived)
        if not written:
            return  # unwritable cache dir: keep serving from the snapshot (ADR-080)
        self._cache._write_marker(self._hash, True)  # noqa: SLF001 — same-package gate
        view = self._open_base(self._hash)
        if view is None:
            return
        self._read_model = view
        self._base_hash = self._hash
        self._base_generation += 1
        self._delta_paths.clear()
        # ADR-107 RSS finalization: the base for this hash is now on disk and the
        # served read-model is the mmap view, so the resident parsed Products are
        # redundant — shed them and re-serve from the base. Unchanged reads then hold
        # no whole-corpus snapshot; the next change re-parses on demand (`_apply`'s
        # shed branch). This retires the resident-snapshot residual ADR-105 named.
        self._entries = {}
        self._snapshot_shed = True

    # --- lifecycle ------------------------------------------------------------

    def close(self) -> None:
        if self._watcher is not None:
            self._watcher.close()
            self._watcher = None
