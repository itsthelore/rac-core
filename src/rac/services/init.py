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

from rac.core.overrides import EMPTY, RULE_VALUES, TYPE_VALUES, SeverityOverrides
from rac.errors import RACError

# Repository key contract (v0.7.11): uppercase alphanumeric, leading letter,
# 2-10 characters. The key is the human-recognizable ID prefix, e.g. RAC.
KEY_RE = re.compile(r"^[A-Z][A-Z0-9]{1,9}$")
DEFAULT_KEY = "RAC"

CONFIG_DIR = ".rac"
CONFIG_FILE = "config.yaml"


class InvalidRepositoryKey(RACError):
    """The requested repository key fails the syntax contract (usage error)."""

    def __init__(self, key: str):
        self.key = key
        super().__init__(
            f"invalid repository key: {key!r} (expected 2-10 uppercase "
            "alphanumeric characters starting with a letter, e.g. RAC)"
        )


class RepositoryKeyConflict(RACError):
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


class MalformedRepositoryConfig(RACError):
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


def find_config_file(start_dir: str) -> Path | None:
    """The nearest ``.rac/config.yaml`` at or above ``start_dir``, or None.

    The shared discovery walk: identity (``load_repository_config``) and the
    validation overrides loader both resolve the same file from any
    subdirectory of an initialized repository.
    """
    current = Path(start_dir).resolve()
    for directory in (current, *current.parents):
        config_path = directory / CONFIG_DIR / CONFIG_FILE
        if config_path.is_file():
            return config_path
    return None


def load_repository_config(start_dir: str) -> RepositoryConfig | None:
    """The nearest ``.rac/config.yaml`` at or above ``start_dir``, or None."""
    config_path = find_config_file(start_dir)
    return _read_config(config_path) if config_path is not None else None


def load_overrides(start_dir: str) -> SeverityOverrides:
    """Read the ``validation`` severity overrides from the nearest config (ADR-053).

    Returns :data:`~rac.core.overrides.EMPTY` when there is no config file or no
    ``validation`` section. Malformed shapes or unknown severity values raise
    :class:`MalformedRepositoryConfig` — overrides are never silently ignored.
    """
    config_path = find_config_file(start_dir)
    if config_path is None:
        return EMPTY
    try:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise MalformedRepositoryConfig(str(config_path), f"invalid YAML: {exc}") from exc
    section = data.get("validation") if isinstance(data, dict) else None
    if section is None:
        return EMPTY
    if not isinstance(section, dict):
        raise MalformedRepositoryConfig(str(config_path), "'validation' must be a mapping")
    rules = _parse_severity_map(config_path, section.get("rules"), "validation.rules", RULE_VALUES)
    types = _parse_severity_map(config_path, section.get("types"), "validation.types", TYPE_VALUES)
    return SeverityOverrides(rules=rules, types=types)


def _parse_severity_map(
    config_path: Path, value: object, where: str, allowed: tuple[str, ...]
) -> dict[str, str]:
    """Validate one ``{name: severity}`` mapping, or empty when absent."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise MalformedRepositoryConfig(str(config_path), f"'{where}' must be a mapping")
    parsed: dict[str, str] = {}
    for name, sev in value.items():
        # YAML 1.1 resolves the bare word ``off`` to ``False`` (likewise on/yes/no
        # to booleans). ``off`` is the natural suppression keyword, so coerce a
        # bool back to text rather than forcing users to quote it; the membership
        # check below rejects ``on``/``yes`` (True) where they are not allowed.
        if isinstance(sev, bool):
            sev = "off" if sev is False else "on"
        if not isinstance(name, str) or not isinstance(sev, str) or sev not in allowed:
            raise MalformedRepositoryConfig(
                str(config_path),
                f"'{where}.{name}' must map a name to one of {', '.join(allowed)}",
            )
        parsed[name] = sev
    return parsed


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
