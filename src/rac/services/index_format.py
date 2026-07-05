"""Binary segment codec for the persistent index store (ADR-101).

The persistent store is a directory of length-prefixed binary *segment* files.
This module is the low-level format only: it knows how to encode Python scalars,
strings, and lists into bytes and how to read them back from a memory-mapped
view with bounds checks. It carries no domain knowledge (no artifacts, no
tokens) — :mod:`rac.services.index_store` layers those on top.

Two security constraints are structural here, not conventions:

- **No code-bearing deserialisation.** The format is fixed struct reads over a
  byte buffer; there is no ``pickle``, ``eval``, ``marshal``, or ``yaml.load``
  anywhere in the read path, so a hostile or truncated file can at worst raise
  :class:`IndexFormatError` — a cache miss — never execute. :data:`SEGMENT_MAGIC`
  is the assertion a test keys on to prove the format is not a pickle stream.
- **Fail-closed on corruption.** Every read is bounds-checked against the mapped
  length, and a segment's declared payload length must match its file exactly, so
  truncation or trailing garbage is caught on open (O(1), no whole-file scan) and
  degrades to a miss. Integrity of the *contents* rests on the content-addressed
  directory name the store chooses; these primitives add the structural gate.
"""

from __future__ import annotations

import struct

# 8 magic bytes open every segment file. A test asserts the store's files begin
# with this rather than a pickle/JSON opcode — the no-code-bearing-format proof.
SEGMENT_MAGIC = b"RACIDX01"
# The binary layout version. A bump makes every older segment file fail the gate
# on open (a miss, rebuilt fresh), so a format change can never rehydrate a stale
# shape — the same pinned-schema discipline the JSON cache used (ADR-007). Bumped
# to 2 by the postings-served search bundle (ADR-101), which adds the term-major
# postings segment: a store written before the bump lacks it and, even were the
# file present, fails this version gate closed, so the fast path never reads a
# half-old layout.
SEGMENT_FORMAT_VERSION = 2

_U32 = struct.Struct("<I")
_U64 = struct.Struct("<Q")
# magic(8) | format_version(u16) | payload_len(u64)
_SEGMENT_HEADER = struct.Struct("<8sHQ")
_HEADER_SIZE = _SEGMENT_HEADER.size

_U32_MAX = 0xFFFFFFFF


class IndexFormatError(Exception):
    """A segment is corrupt, truncated, wrong-magic, or wrong-version.

    The store treats this as a cache miss and rebuilds; it never escapes to a
    tool caller, so enabling the store can only change latency, not answers.
    """


class Writer:
    """Append-only encoder building one segment payload in memory."""

    def __init__(self) -> None:
        self._buf = bytearray()

    def u32(self, value: int) -> None:
        if not 0 <= value <= _U32_MAX:
            raise IndexFormatError(f"u32 out of range: {value}")
        self._buf += _U32.pack(value)

    def u64(self, value: int) -> None:
        self._buf += _U64.pack(value)

    def raw(self, data: bytes) -> None:
        self._buf += data

    def blob(self, data: bytes) -> None:
        self.u32(len(data))
        self._buf += data

    def text(self, value: str) -> None:
        self.blob(value.encode("utf-8"))

    def opt_text(self, value: str | None) -> None:
        # A single flag byte distinguishes ``None`` from the empty string, so an
        # optional field round-trips exactly (a missing ``resolved_path`` is not
        # a present empty path).
        if value is None:
            self._buf += b"\x00"
        else:
            self._buf += b"\x01"
            self.text(value)

    def text_list(self, values: list[str]) -> None:
        self.u32(len(values))
        for value in values:
            self.text(value)

    def u32_list(self, values: list[int]) -> None:
        self.u32(len(values))
        for value in values:
            self.u32(value)

    @property
    def payload(self) -> bytes:
        return bytes(self._buf)


class Reader:
    """Bounds-checked decoder over a mapped segment payload.

    Every accessor validates against the buffer length before reading, so a
    truncated or corrupt segment raises :class:`IndexFormatError` rather than
    reading past the mapping or returning garbage.
    """

    def __init__(self, view: memoryview, offset: int = 0) -> None:
        self._view = view
        self._pos = offset

    def _require(self, count: int) -> int:
        end = self._pos + count
        if count < 0 or end > len(self._view):
            raise IndexFormatError("segment read past end (truncated or corrupt)")
        start = self._pos
        self._pos = end
        return start

    def u32(self) -> int:
        start = self._require(4)
        return _U32.unpack_from(self._view, start)[0]

    def u64(self) -> int:
        start = self._require(8)
        return _U64.unpack_from(self._view, start)[0]

    def blob(self) -> bytes:
        length = self.u32()
        start = self._require(length)
        return bytes(self._view[start : start + length])

    def text(self) -> str:
        return self.blob().decode("utf-8")

    def opt_text(self) -> str | None:
        start = self._require(1)
        flag = self._view[start]
        if flag == 0:
            return None
        if flag != 1:
            raise IndexFormatError(f"bad optional flag: {flag}")
        return self.text()

    def text_list(self) -> list[str]:
        return [self.text() for _ in range(self.u32())]

    def u32_list(self) -> list[int]:
        return [self.u32() for _ in range(self.u32())]


def encode_segment(payload: bytes) -> bytes:
    """Frame a payload as a segment file's bytes: magic, version, length, payload."""
    return _SEGMENT_HEADER.pack(SEGMENT_MAGIC, SEGMENT_FORMAT_VERSION, len(payload)) + payload


def segment_payload(view: memoryview) -> memoryview:
    """Validate a mapped segment and return a view over its payload (fail-closed).

    Checks the magic, the format version, and — the truncation gate — that the
    file length is *exactly* the header plus the declared payload length. A short
    file (truncated) or a long one (trailing garbage) both fail here, on open, in
    O(1): no scan of the payload is needed to detect either.
    """
    if len(view) < _HEADER_SIZE:
        raise IndexFormatError("segment shorter than its header")
    magic, version, payload_len = _SEGMENT_HEADER.unpack_from(view, 0)
    if magic != SEGMENT_MAGIC:
        raise IndexFormatError("bad segment magic (not an index-store segment)")
    if version != SEGMENT_FORMAT_VERSION:
        raise IndexFormatError(f"unsupported segment format version: {version}")
    if len(view) != _HEADER_SIZE + payload_len:
        raise IndexFormatError("segment length mismatch (truncated or corrupt)")
    return view[_HEADER_SIZE:]


def write_indexed(rows: list[bytes]) -> bytes:
    """Encode row blobs with a docid-indexed offset table for O(1) point access.

    Layout: ``count(u32) | offsets(count × u64) | rows``, offsets relative to the
    end of the table. :class:`IndexedSegment` reads row *k* by seeking its offset,
    so a point lookup (one ``get_artifact``) never touches another row's pages.
    """
    writer = Writer()
    writer.u32(len(rows))
    running = 0
    offsets: list[int] = []
    for row in rows:
        offsets.append(running)
        running += len(row)
    for offset in offsets:
        writer.u64(offset)
    for row in rows:
        writer.raw(row)
    return writer.payload


class IndexedSegment:
    """Reader over a :func:`write_indexed` payload — random access by row index."""

    def __init__(self, view: memoryview) -> None:
        self._view = view
        header = Reader(view)
        self._count = header.u32()
        self._table_start = 4
        self._data_start = 4 + 8 * self._count
        if self._data_start > len(view):
            raise IndexFormatError("indexed-segment offset table truncated")

    @property
    def count(self) -> int:
        return self._count

    def row(self, index: int) -> Reader:
        if not 0 <= index < self._count:
            raise IndexFormatError(f"row index out of range: {index}")
        offset = _U64.unpack_from(self._view, self._table_start + 8 * index)[0]
        start = self._data_start + offset
        if start > len(self._view):
            raise IndexFormatError("indexed-segment row offset past end")
        return Reader(self._view, start)
