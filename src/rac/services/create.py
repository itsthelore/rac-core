"""Artifact creation — `rac new` (v0.7.10, identity added in v0.7.11).

``create_artifact`` is the reusable creation capability (REQ: service-layer
creation API): it owns type lookup, template loading, identity assignment,
the no-overwrite check, and the result model, so Explorer and IDE
integrations can create artifacts without reimplementing template logic. The
CLI stays a thin adapter.

Since v0.7.11 every generated artifact carries canonical YAML frontmatter
(ADR-025) with a system-assigned opaque ID (ADR-026): the repository key is
read from the nearest ``.rac/config.yaml`` (``rac init``), one ID is
generated offline, checked against the repository index, and written with
stable key order (``schema_version``, ``id``, ``type``). Creation without an
initialized repository fails with an actionable error — no fallback, no
implicit init (v0.7.11 contract).

Failure contract:

- unsupported type          → :class:`~rac.core.templates.TemplateNotFound` (usage)
- existing output file      → :class:`OutputPathExists` (usage; never overwrite)
- missing parent directory  → :class:`OutputDirectoryMissing` (usage; no auto-create)
- no repository config      → :class:`MissingRepositoryConfig` (usage; run rac init)
- missing packaged template → :class:`~rac.core.templates.TemplateResourceMissing`
  (operational)
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from rac.core.idgen import generate_id
from rac.core.templates import load_template
from rac.errors import RACError
from rac.services.index import build_repository_index
from rac.services.init import load_repository_config

# Bounded regeneration attempts when a fresh ID collides with the index. A
# collision needs an identical millisecond tick *and* identical 20 random bits;
# more than a few retries indicates a broken entropy source, not bad luck.
_MAX_ID_ATTEMPTS = 5


class OutputPathExists(RACError):
    """The requested output path already exists; RAC never overwrites it."""

    def __init__(self, path: str):
        self.path = path
        super().__init__(f"{path} already exists; rac new never overwrites")


class OutputDirectoryMissing(RACError):
    """The output path's parent directory does not exist (no auto-create)."""

    def __init__(self, path: str):
        self.path = path
        super().__init__(f"directory does not exist: {path}")


class MissingRepositoryConfig(RACError):
    """No repository identity namespace is established (run `rac init`)."""

    def __init__(self, start_dir: str):
        self.start_dir = start_dir
        super().__init__(
            f"no repository identity found at or above {start_dir}; "
            "run `rac init` to establish a repository key first"
        )


class IdGenerationExhausted(RACError):
    """Repeated ID collisions — the entropy source is not behaving."""

    def __init__(self, attempts: int):
        self.attempts = attempts
        super().__init__(f"could not generate a unique artifact ID in {attempts} attempts")


@dataclass
class CreatedArtifact:
    """Result of one artifact creation (stable JSON contract, ADR-007)."""

    artifact_type: str
    path: str
    bytes_written: int
    id: str

    def to_dict(self) -> dict:
        return {
            "schema_version": "1",
            "created": True,
            "type": self.artifact_type,
            "path": self.path,
            "id": self.id,
        }


def render_frontmatter(artifact_id: str, artifact_type: str) -> str:
    """Canonical generated frontmatter, stable key order (v0.7.11 contract)."""
    return f"---\nschema_version: 1\nid: {artifact_id}\ntype: {artifact_type}\n---\n"


def render_artifact(artifact_type: str, frontmatter: str | None = None) -> str:
    """Deterministic artifact content: optional envelope + canonical body."""
    body = load_template(artifact_type)
    if frontmatter is None:
        return body
    return frontmatter + body


def _assign_id(
    repository_key: str,
    repository_root: str,
    id_generator: Callable[[str], str],
) -> str:
    """One repository-unique ID: generate, check the index, retry bounded."""
    existing = {entry.id.upper() for entry in build_repository_index(repository_root).artifacts}
    for _ in range(_MAX_ID_ATTEMPTS):
        candidate = id_generator(repository_key)
        if candidate.upper() not in existing:
            return candidate
    raise IdGenerationExhausted(_MAX_ID_ATTEMPTS)


def create_artifact(
    artifact_type: str,
    output_path: str,
    *,
    id_generator: Callable[[str], str] = generate_id,
) -> CreatedArtifact:
    """Write a new ``artifact_type`` artifact with assigned identity.

    The path is taken literally — no slug derivation, no extension magic, no
    directory creation. ``id_generator`` is injectable for deterministic
    tests; the default is the real offline generator.
    """
    body = load_template(artifact_type)  # validates the type first (cheap)
    out = Path(output_path)
    if out.exists():
        raise OutputPathExists(output_path)
    if not out.parent.is_dir():
        raise OutputDirectoryMissing(str(out.parent))

    config = load_repository_config(str(out.parent))
    if config is None:
        raise MissingRepositoryConfig(str(out.parent))
    repository_root = str(Path(config.config_path).parent.parent)
    artifact_id = _assign_id(config.repository_key, repository_root, id_generator)

    content = render_frontmatter(artifact_id, artifact_type) + body
    data = content.encode("utf-8")
    out.write_bytes(data)
    return CreatedArtifact(
        artifact_type=artifact_type,
        path=output_path,
        bytes_written=len(data),
        id=artifact_id,
    )
