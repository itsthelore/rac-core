"""Robustness limits — the input-size and traversal caps (v0.23.0, WS4).

The MCP server sits in an agent's critical path (ADR-032/ADR-033): a malformed
artifact, an oversized field, an alias-bombed front matter, or a high-fan-out
hub must never crash, hang, or exhaust memory. These module-level caps bound
*work* ahead of the ADR-033 response budget, with safe defaults proven against
the fixture corpus. They are measured in bytes where width-independence matters,
so the bound is the same regardless of unicode content.

The per-file byte cap is overridable via ``RAC_MAX_FILE_BYTES`` for repositories
with genuinely large artifacts; the rest are fixed constants. Reading an
environment variable is configuration, not I/O against the artifact, so the
parse path stays deterministic for a given environment (ADR-002).
"""

from __future__ import annotations

import os

# Per-file / per-parse byte cap (REQ-001). Default 1 MiB; override with
# RAC_MAX_FILE_BYTES. A non-positive or unparseable override falls back to the
# default rather than disabling the guard.
DEFAULT_MAX_FILE_BYTES = 1 << 20  # 1 MiB
_MAX_FILE_BYTES_ENV = "RAC_MAX_FILE_BYTES"

# Raw front-matter block byte cap, before PyYAML sees it (REQ-002).
MAX_FRONTMATTER_BYTES = 64 << 10  # 64 KiB
# Maximum YAML nesting depth permitted in front matter (REQ-002): deeper input
# is rejected as malformed before PyYAML recurses.
MAX_FRONTMATTER_DEPTH = 32

# Per-field captured-body caps (REQ-003), independent of the ADR-033 response
# budget. A single oversized field is truncated, never allowed to dominate the
# served Product. Generous enough that no real artifact is affected.
MAX_FIELD_CHARS = 256 << 10  # 256 KiB of text per ## section / field
MAX_CAPTURED_LINES = 50_000  # total non-blank body lines captured per document

# Per-call relationship edge cap for get_related (REQ-007): incoming/outgoing
# edge collection stops building after this many, so a high-fan-out hub cannot
# force an unbounded in-memory list before the response budget trims it.
MAX_RELATED_EDGES = 1000

# Bounded multi-hop traversal caps for get_related (v0.24, WS-D;
# rac-multi-hop-relationship-traversal REQ-002). A depth parameter widens
# get_related beyond immediate neighbours, but every traversal stays bounded by
# four caps so a deep or high-fan-out graph cannot hang or exhaust memory:
#   - a maximum depth (the requested N is clamped to this ceiling),
#   - a maximum frontier size per BFS level,
#   - a visited set that prevents revisiting a node (cycle-safe), and
#   - a total work budget on edges examined across the whole walk.
MAX_TRAVERSAL_DEPTH = 5  # ceiling on the requested hop depth
MAX_TRAVERSAL_FRONTIER = 1000  # nodes admitted per level before the level truncates
MAX_TRAVERSAL_WORK = 10_000  # edges examined across the whole walk before it stops


def max_file_bytes() -> int:
    """The per-file byte cap, honoring ``RAC_MAX_FILE_BYTES`` (REQ-001)."""
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

    A character count is a cheap lower bound (``bytes >= chars``) and upper bound
    (``bytes <= 4 * chars``), so the costly ``encode`` runs only for inputs near
    the cap — never for the common small artifact.
    """
    length = len(text)
    if length > cap:
        return True
    if length <= cap // 4:
        return False
    return len(text.encode("utf-8")) > cap
