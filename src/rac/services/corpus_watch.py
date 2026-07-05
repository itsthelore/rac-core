"""Event-driven corpus freshness for the long-lived server (ADR-100).

The persistent index (``persistent_index``) makes warm reads query-bound, but a
long-lived server must still notice when the corpus on disk changes between
calls. ADR-100 pins the mechanism: *native filesystem events, directory-level
watches, no polling daemon, no external service.* Events only mark the corpus
dirty; the next call splices the changeset with :meth:`PersistentIndex.refresh`,
where the byte hash remains the authority (events are a trigger, never a source
of truth). Where watches are unavailable — a non-Linux host, or the kernel's
per-user watch limit is exhausted — the server falls back to a stat-scan refresh
before every call, which restores ADR-032 semantics at a latency cost.

This module is the watch half: a Linux ``inotify`` reader built on ``ctypes``
alone (the packaging is frozen — no new dependency, and the isolation battery
forbids a network import, which this has none of). It adds a recursive set of
directory watches under the corpus root, follows directory creation so new
subtrees are covered, coalesces every relevant event into a dirty path set, and
runs its reader on a daemon thread that can die without taking the server with
it — a dead watcher simply reads as "not alive", and the coordinator degrades to
the per-call fallback. It is deliberately Core-side and offline: no ``mcp`` SDK,
no network, no writes to the corpus.
"""

from __future__ import annotations

import ctypes
import os
import select
import struct
import threading
from pathlib import Path

# inotify event mask bits (from <sys/inotify.h>) — the ones a corpus edit raises.
IN_MODIFY = 0x00000002
IN_MOVED_FROM = 0x00000040
IN_MOVED_TO = 0x00000080
IN_CREATE = 0x00000100
IN_DELETE = 0x00000200
IN_DELETE_SELF = 0x00000400
IN_ISDIR = 0x40000000
# inotify_init1 flag: non-blocking fd, so the reader can poll a stop event.
IN_NONBLOCK = 0x00000800

# Everything that changes the corpus: content edits, adds, removes, renames (both
# ends), and a watched directory vanishing. A term-index or graph answer can only
# change through one of these, so this is the complete trigger set.
_WATCH_MASK = IN_MODIFY | IN_MOVED_FROM | IN_MOVED_TO | IN_CREATE | IN_DELETE | IN_DELETE_SELF

# inotify_event header: int wd, uint32 mask, uint32 cookie, uint32 len.
_HEADER = struct.Struct("iIII")
_HEADER_SIZE = _HEADER.size
_READ_BUFFER = 64 * 1024  # many events per read; the kernel coalesces the rest.
_POLL_INTERVAL = 0.5  # seconds between stop-flag checks while idle.


def _load_libc() -> ctypes.CDLL | None:
    """The C library with ``inotify_*`` symbols, or None where they are absent."""
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        # Resolve the symbols now so a platform without them fails here (return
        # None -> fallback), not mid-watch.
        for symbol in ("inotify_init1", "inotify_add_watch", "inotify_rm_watch"):
            getattr(libc, symbol)
    except (OSError, AttributeError):
        return None
    return libc


class CorpusWatcher:
    """Recursive inotify watch over a corpus root, coalesced into a dirty set.

    :meth:`start` sets :attr:`available` — ``False`` on any host where inotify
    cannot be initialised or the root cannot be watched (the caller then uses the
    per-call fallback). While :attr:`available` and :attr:`alive`, the reader
    thread accumulates changed paths that :meth:`drain` hands back and clears; the
    coordinator refreshes exactly when a drain is non-empty. The thread is a
    daemon and exception-safe: any failure flips :attr:`alive` to ``False`` and
    the coordinator falls back, so a watcher death never crashes the server nor
    serves silently stale.
    """

    def __init__(self, root: str) -> None:
        self._root = str(Path(root))
        self._libc = _load_libc()
        self._fd = -1
        self._wd_to_path: dict[int, str] = {}
        self._lock = threading.Lock()
        self._dirty: set[str] = set()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.available = False
        self._alive = False

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> bool:
        """Initialise inotify, add the recursive watch set, start the reader.

        Returns True when watching is active (``available``); False when it is
        not — a non-Linux host, missing symbols, or the kernel watch limit — in
        which case the caller degrades to the stat-scan-per-call fallback.
        """
        if self._libc is None:
            return False
        fd = self._libc.inotify_init1(IN_NONBLOCK)
        if fd < 0:
            return False
        self._fd = fd
        # The root itself must be watchable; if even that fails (e.g. ENOSPC),
        # inotify is unusable here and the caller falls back wholesale.
        if self._add_watch(self._root) < 0:
            self._close_fd()
            return False
        self._add_watches_recursive(self._root)
        self.available = True
        self._alive = True
        self._thread = threading.Thread(target=self._run, name="rac-corpus-watch", daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        """Signal the reader to exit and release the inotify fd (idempotent)."""
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=2)
        self._close_fd()

    @property
    def alive(self) -> bool:
        """True while the reader thread is running without a fatal error."""
        return self._alive and self._thread is not None and self._thread.is_alive()

    # -- consumption -------------------------------------------------------

    def drain(self) -> set[str]:
        """Return and clear the accumulated changed paths (thread-safe).

        A non-empty result means at least one relevant event arrived since the
        last drain, i.e. the corpus may have changed and the caller should
        refresh. Empty means no event was seen — nothing to splice.
        """
        with self._lock:
            paths = self._dirty
            self._dirty = set()
            return paths

    # -- inotify plumbing --------------------------------------------------

    def _add_watch(self, directory: str) -> int:
        """Add (or update) a watch for one directory; record its wd→path map."""
        assert self._libc is not None  # only called once watching is active
        wd = self._libc.inotify_add_watch(self._fd, os.fsencode(directory), _WATCH_MASK)
        if wd >= 0:
            self._wd_to_path[wd] = directory
        return wd

    def _add_watches_recursive(self, directory: str) -> None:
        """Best-effort watch for every subdirectory under ``directory``.

        A watch that cannot be added (e.g. the per-user limit) is skipped rather
        than fatal: the subtree simply degrades to the recorded staleness bound,
        never a crash. os.walk is offline and read-only.
        """
        try:
            for current, dirnames, _files in os.walk(directory):
                dirnames.sort()
                for name in dirnames:
                    self._add_watch(os.path.join(current, name))
        except OSError:
            # A transient walk error (a directory removed mid-walk) is not fatal;
            # the events themselves will still mark the corpus dirty.
            pass

    def _run(self) -> None:
        """Reader loop: poll the fd, parse events, coalesce into the dirty set.

        Exception-safe by contract: any unexpected error flips ``alive`` off and
        exits the thread, so the coordinator falls back to per-call refresh rather
        than trusting a broken watcher (ADR-100).
        """
        try:
            while not self._stop.is_set():
                try:
                    ready, _, _ = select.select([self._fd], [], [], _POLL_INTERVAL)
                except (OSError, ValueError):
                    break  # fd closed under us during stop(), or gone bad.
                if not ready:
                    continue
                try:
                    data = os.read(self._fd, _READ_BUFFER)
                except BlockingIOError:
                    continue
                except OSError:
                    break
                if data:
                    self._consume(data)
        finally:
            self._alive = False

    def _consume(self, data: bytes) -> None:
        """Parse a batch of raw inotify events and record the changed paths."""
        changed: set[str] = set()
        offset = 0
        length = len(data)
        while offset + _HEADER_SIZE <= length:
            wd, mask, _cookie, name_len = _HEADER.unpack_from(data, offset)
            offset += _HEADER_SIZE
            raw_name = data[offset : offset + name_len]
            offset += name_len
            name = os.fsdecode(raw_name.split(b"\x00", 1)[0]) if name_len else ""
            base = self._wd_to_path.get(wd, self._root)
            path = os.path.join(base, name) if name else base
            changed.add(path)
            # A newly created (or moved-in) directory needs its own watch, so a
            # nested subtree created after startup is still covered.
            if mask & IN_ISDIR and mask & (IN_CREATE | IN_MOVED_TO):
                self._add_watch(path)
                self._add_watches_recursive(path)
        if changed:
            with self._lock:
                self._dirty.update(changed)

    def _close_fd(self) -> None:
        if self._fd >= 0:
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = -1
