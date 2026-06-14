"""Shared grounding-text block format.

Arms assemble grounding as a sequence of attributed blocks so the answering
model can cite the artifact id it relied on. Retrieval arms (naive_rag) attach
the same header to each retrieved chunk, so attribution works identically
regardless of arm — what differs is only which blocks are present.
"""

from __future__ import annotations

import re

_HEADER = re.compile(r"^\[artifact (?P<id>[^\s|]+) \| (?P<type>[^\]]+)\]$", re.MULTILINE)


def format_block(artifact_id: str, artifact_type: str, body: str) -> str:
    return f"[artifact {artifact_id} | {artifact_type}]\n{body.strip()}\n"


def parse_blocks(grounding_text: str) -> list[tuple[str, str, str]]:
    """Return (artifact_id, artifact_type, body) for each block in order."""
    blocks: list[tuple[str, str, str]] = []
    matches = list(_HEADER.finditer(grounding_text))
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(grounding_text)
        body = grounding_text[start:end].strip()
        blocks.append((m.group("id"), m.group("type"), body))
    return blocks
