"""Repository identity configuration — `rac init` (v0.7.11).

``rac init`` establishes the repository identity namespace (ADR-026): a
``.rac/config.yaml`` holding the ``repository_key`` that prefixes every
generated artifact ID. The key is configuration, not artifact meaning — it
never determines folder structure, and changing an established key is an
error, never a silent rewrite (re-running with the same key is idempotent).

``load_repository_config`` is the discovery counterpart: it walks upward from
a starting directory toward the filesystem root and returns the first
configuration found, so ``rac new`` works from any subdirectory of an
initialized repository.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

# Repository key contract (v0.7.11): uppercase alphanumeric, leading letter,
# 2-10 characters. The key is the human-recognizable ID prefix, e.g. RAC.
KEY_RE = re.compile(r"^[A-Z][A-Z0-9]{1,9}$")
DEFAULT_KEY = "RAC"

CONFIG_DIR = ".rac"
CONFIG_FILE = "config.yaml"


class InvalidRepositoryKey(Exception):
    """The requested repository key fails the syntax contract (usage error)."""

    def __init__(self, key: str):
        self.key = key
        super().__init__(
            f"invalid repository key: {key!r} (expected 2-10 uppercase "
            "alphanumeric characters starting with a letter, e.g. RAC)"
        )


class RepositoryKeyConflict(Exception):
    """An established repository key differs from the requested one."""

    def __init__(self, existing: str, requested: str, config_path: str):
        self.existing = existing
        self.requested = requested
        self.config_path = config_path
        super().__init__(
            f"repository already initialized with key {existing!r} "
            f"({config_path}); refusing to change it to {requested!r} — "
            "established ID namespaces are never silently rewritten"
        )


class MalformedRepositoryConfig(Exception):
    """An existing configuration file cannot be read (operational error)."""

    def __init__(self, config_path: str, reason: str):
        self.config_path = config_path
        super().__init__(f"malformed repository config {config_path}: {reason}")


@dataclass
class RepositoryConfig:
    """A discovered repository identity configuration."""

    repository_key: str
    config_path: str  # the .rac/config.yaml this came from

    def to_dict(self) -> dict:
        return {
            "schema_version": "1",
            "repository_key": self.repository_key,
            "config_path": self.config_path,
        }


@dataclass
class InitResult:
    """Outcome of one `rac init` run (stable JSON contract, ADR-007)."""

    repository_key: str
    config_path: str
    created: bool  # False when init was idempotent (key already established)

    def to_dict(self) -> dict:
        return {
            "schema_version": "1",
            "repository_key": self.repository_key,
            "config_path": self.config_path,
            "created": self.created,
        }


def _read_config(config_path: Path) -> RepositoryConfig:
    try:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise MalformedRepositoryConfig(str(config_path), f"invalid YAML: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("repository_key"), str):
        raise MalformedRepositoryConfig(
            str(config_path), "missing required string field 'repository_key'"
        )
    key = data["repository_key"]
    if not KEY_RE.match(key):
        raise MalformedRepositoryConfig(str(config_path), f"invalid repository_key: {key!r}")
    return RepositoryConfig(repository_key=key, config_path=str(config_path))


def load_repository_config(start_dir: str) -> RepositoryConfig | None:
    """The nearest ``.rac/config.yaml`` at or above ``start_dir``, or None."""
    current = Path(start_dir).resolve()
    for directory in (current, *current.parents):
        config_path = directory / CONFIG_DIR / CONFIG_FILE
        if config_path.is_file():
            return _read_config(config_path)
    return None


def init_repository(directory: str, key: str = DEFAULT_KEY) -> InitResult:
    """Establish (or confirm) the repository identity namespace at ``directory``.

    Raises :class:`InvalidRepositoryKey` for a bad key,
    :class:`RepositoryKeyConflict` when a different key is already established
    in this exact directory, and :class:`MalformedRepositoryConfig` when an
    existing file cannot be read.
    """
    if not KEY_RE.match(key):
        raise InvalidRepositoryKey(key)
    config_path = Path(directory) / CONFIG_DIR / CONFIG_FILE
    if config_path.is_file():
        existing = _read_config(config_path)
        if existing.repository_key != key:
            raise RepositoryKeyConflict(existing.repository_key, key, str(config_path))
        return InitResult(repository_key=key, config_path=str(config_path), created=False)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(f"repository_key: {key}\n", encoding="utf-8")
    return InitResult(repository_key=key, config_path=str(config_path), created=True)
