"""Adversarial-input caps for the parse and traversal paths (WS4).

The MCP server runs in an agent's critical path (ADR-032/ADR-033): a malformed
artifact, an oversized field, an alias-bombed frontmatter, or a high-fan-out hub
must never crash, hang, or exhaust memory. These module-level constants bound
*work* ahead of the ADR-033 response budget, with defaults proven safe against
the fixture corpus. Where width-independence matters the bound is a byte count,
so it holds regardless of unicode content.

Only the per-file byte cap is configurable (via ``RAC_MAX_FILE_BYTES``, for
repositories with genuinely large artifacts); the rest are fixed. Reading an
environment variable is configuration, not I/O against the artifact, so the
parse path stays deterministic for a given environment (ADR-002).
"""

from __future__ import annotations

import os

# Per-file / per-parse byte cap (REQ-001). Overridable with RAC_MAX_FILE_BYTES;
# a non-positive or unparseable override falls back to the default rather than
# disabling the guard.
DEFAULT_MAX_FILE_BYTES = 1 << 20  # 1 MiB
_MAX_FILE_BYTES_ENV = "RAC_MAX_FILE_BYTES"

# Raw frontmatter block caps (REQ-002), enforced before PyYAML sees the text:
# an overall byte size and a maximum nesting depth (deeper input is rejected as
# malformed rather than allowed to recurse).
MAX_FRONTMATTER_BYTES = 64 << 10  # 64 KiB
MAX_FRONTMATTER_DEPTH = 32

# Captured-body caps (REQ-003), independent of the ADR-033 response budget: a
# single oversized field is truncated rather than allowed to dominate the served
# Product, and the whole document has a non-blank-line ceiling. Both are generous
# enough that no real artifact is affected.
MAX_FIELD_CHARS = 256 << 10  # 256 KiB of text per ## section / field
MAX_CAPTURED_LINES = 50_000  # total non-blank body lines captured per document

# Per-call relationship edge cap for get_related (REQ-007): edge collection
# stops after this many, so a high-fan-out hub cannot build an unbounded list
# before the response budget trims it.
MAX_RELATED_EDGES = 1000

# Bounded multi-hop traversal caps for get_related (WS-D). A depth parameter can
# widen get_related past immediate neighbours, but four caps keep every walk
# bounded: the requested depth is clamped to a ceiling, each BFS level admits a
# limited frontier, a visited set makes the walk cycle-safe, and a total work
# budget limits edges examined across the whole walk.
MAX_TRAVERSAL_DEPTH = 5  # ceiling on the requested hop depth
MAX_TRAVERSAL_FRONTIER = 1000  # nodes admitted per level before the level truncates
MAX_TRAVERSAL_WORK = 10_000  # edges examined across the whole walk before it stops


def max_file_bytes() -> int:
    """The per-file byte cap, honouring ``RAC_MAX_FILE_BYTES`` (REQ-001).

    Re-read on every call so a test (or a caller) can change the environment
    between parses. Only a parseable, strictly positive override is honoured;
    anything else falls back to the default.
    """
    raw = os.environ.get(_MAX_FILE_BYTES_ENV)
    if raw is not None:
        try:
            value = int(raw)
        except ValueError:
            return DEFAULT_MAX_FILE_BYTES
        if value > 0:
            return value
    return DEFAULT_MAX_FILE_BYTES


def exceeds_byte_cap(text: str, cap: int) -> bool:
    """True when ``text`` exceeds ``cap`` UTF-8 bytes, encoding only if needed.

    The character count bounds the byte count on both sides — ``chars <= bytes
    <= 4 * chars`` — so the expensive ``encode`` runs only for input genuinely
    near the cap. Preserving this short-circuit keeps the parser cheap on small
    artifacts and linear on adversarial ones.
    """
    length = len(text)
    if length > cap:
        return True
    if length <= cap // 4:
        return False
    return len(text.encode("utf-8")) > cap
