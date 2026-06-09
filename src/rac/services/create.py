"""Artifact creation — `rac new` (v0.7.10).

``create_artifact`` is the reusable creation capability (REQ: service-layer
creation API): it owns type lookup, template loading, the no-overwrite check,
and the result model, so Explorer and IDE integrations can create artifacts
without reimplementing template logic. The CLI stays a thin adapter.

Rendering is deliberately structured as *envelope + body*: today the envelope
is empty and the body is the bundled canonical template, so v0.7.11 can add
YAML frontmatter (identity, metadata) without replacing this architecture.

Failure contract (pinned in the v0.7.10 implementation contract):

- unsupported type        → :class:`~rac.core.templates.TemplateNotFound` (usage)
- existing output file    → :class:`OutputPathExists` (usage; never overwrite)
- missing parent directory→ :class:`OutputDirectoryMissing` (usage; no auto-create)
- missing packaged template → :class:`~rac.core.templates.TemplateResourceMissing`
  (operational)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rac.core.templates import load_template


class OutputPathExists(Exception):
    """The requested output path already exists; RAC never overwrites it."""

    def __init__(self, path: str):
        self.path = path
        super().__init__(f"{path} already exists; rac new never overwrites")


class OutputDirectoryMissing(Exception):
    """The output path's parent directory does not exist (no auto-create)."""

    def __init__(self, path: str):
        self.path = path
        super().__init__(f"directory does not exist: {path}")


@dataclass
class CreatedArtifact:
    """Result of one artifact creation (stable JSON contract, ADR-007)."""

    artifact_type: str
    path: str
    bytes_written: int

    def to_dict(self) -> dict:
        return {
            "schema_version": "1",
            "created": True,
            "type": self.artifact_type,
            "path": self.path,
        }


def render_artifact(artifact_type: str, frontmatter: str | None = None) -> str:
    """Deterministic artifact content: optional envelope + canonical body.

    ``frontmatter`` is unused in v0.7.10 (always ``None``); the seam exists so
    v0.7.11 metadata integration extends rendering instead of replacing it.
    """
    body = load_template(artifact_type)
    if frontmatter is None:
        return body
    return frontmatter + body


def create_artifact(artifact_type: str, output_path: str) -> CreatedArtifact:
    """Write the canonical ``artifact_type`` template to ``output_path``.

    The path is taken literally — no slug derivation, no extension magic, no
    directory creation (v0.7.10 contract).
    """
    content = render_artifact(artifact_type)
    out = Path(output_path)
    if out.exists():
        raise OutputPathExists(output_path)
    if not out.parent.is_dir():
        raise OutputDirectoryMissing(str(out.parent))
    data = content.encode("utf-8")
    out.write_bytes(data)
    return CreatedArtifact(
        artifact_type=artifact_type,
        path=output_path,
        bytes_written=len(data),
    )
