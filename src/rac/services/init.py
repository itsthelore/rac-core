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
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from rac.services.gate import EnforcementPolicy

from rac.core.overrides import EMPTY, RULE_VALUES, TYPE_VALUES, SeverityOverrides
from rac.core.validation import TICKETING_PROVIDER_NAMES
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


class InvalidTicketingProvider(RACError):
    """The requested ticketing provider is not a recognised provider (usage error)."""

    def __init__(self, provider: str):
        self.provider = provider
        super().__init__(
            f"invalid ticketing provider: {provider!r} "
            f"(expected one of {', '.join(TICKETING_PROVIDER_NAMES)})"
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


def load_enforcement_policy(start_dir: str) -> EnforcementPolicy:
    """Read the ``enforcement`` policy from the nearest config (ADR-049 / v0.21.14).

    The enforcement section maps finding *codes* to an enforcement class for
    ``rac gate``: three optional list-of-strings keys ``blocking``, ``advisory``,
    and ``off``. It is the central, governed knob that decides which finding
    classes fail the gate versus merely annotate (ADR-063: the policy lives in the
    committed corpus, not hardcoded in a consumer)::

        enforcement:
          advisory:
            - relationship-target-superseded
          off:
            - stale-corpus

    Returns :data:`~rac.services.gate.EMPTY_POLICY` when there is no config file or
    no ``enforcement`` section. Malformed shapes (a non-mapping section, a
    non-list key, or a non-string entry) raise :class:`MalformedRepositoryConfig`,
    mirroring :func:`load_overrides` — policy is never silently ignored.
    """
    # Imported lazily to avoid a cycle: gate.py imports this loader, and the
    # policy model lives alongside the gate service.
    from rac.services.gate import EMPTY_POLICY, EnforcementPolicy

    config_path = find_config_file(start_dir)
    if config_path is None:
        return EMPTY_POLICY
    try:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise MalformedRepositoryConfig(str(config_path), f"invalid YAML: {exc}") from exc
    section = data.get("enforcement") if isinstance(data, dict) else None
    if section is None:
        return EMPTY_POLICY
    if not isinstance(section, dict):
        raise MalformedRepositoryConfig(str(config_path), "'enforcement' must be a mapping")
    blocking = _parse_code_list(config_path, section.get("blocking"), "enforcement.blocking")
    advisory = _parse_code_list(config_path, section.get("advisory"), "enforcement.advisory")
    # YAML 1.1 resolves the bare key ``off`` to ``False`` (the same gotcha the
    # severity loader handles for values). ``off`` is the natural suppression
    # keyword, so accept the coerced ``False`` key rather than forcing quotes.
    off_value = section["off"] if "off" in section else section.get(False)
    off = _parse_code_list(config_path, off_value, "enforcement.off")
    return EnforcementPolicy(
        blocking=frozenset(blocking), advisory=frozenset(advisory), off=frozenset(off)
    )


def _parse_code_list(config_path: Path, value: object, where: str) -> list[str]:
    """Validate one ``enforcement`` key as a list of finding-code strings.

    ``None`` (absent) is an empty list. Any non-list shape, or a non-string entry,
    is a malformed config — finding codes are plain strings (ADR-007 stable codes).
    """
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise MalformedRepositoryConfig(
            str(config_path), f"'{where}' must be a list of finding-code strings"
        )
    return value


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


def load_ticketing_provider(start_dir: str) -> str | None:
    """Read ``ticketing.provider`` from the nearest config (ADR-087 / ADR-088).

    Returns the configured external ticketing provider (``jira``, ``github``,
    ``linear``, ``azure-devops``, ``servicenow``, or ``none``), or ``None`` when
    there is no config file or no ``ticketing`` section. An organisation
    standardises on one provider, so this is the single value the external
    ticket format-lint reads (ADR-087). A non-mapping section or an unrecognised
    provider raises :class:`MalformedRepositoryConfig`, mirroring
    :func:`load_overrides` — config is never silently ignored.
    """
    config_path = find_config_file(start_dir)
    if config_path is None:
        return None
    try:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise MalformedRepositoryConfig(str(config_path), f"invalid YAML: {exc}") from exc
    section = data.get("ticketing") if isinstance(data, dict) else None
    if section is None:
        return None
    if not isinstance(section, dict):
        raise MalformedRepositoryConfig(str(config_path), "'ticketing' must be a mapping")
    provider = section.get("provider")
    if provider is None:
        return None
    if not isinstance(provider, str) or provider not in TICKETING_PROVIDER_NAMES:
        raise MalformedRepositoryConfig(
            str(config_path),
            f"'ticketing.provider' must be one of {', '.join(TICKETING_PROVIDER_NAMES)}",
        )
    return provider


def init_repository(
    directory: str, key: str = DEFAULT_KEY, ticketing: str | None = None
) -> InitResult:
    """Establish (or confirm) the repository identity namespace at ``directory``.

    When ``ticketing`` is given (a recognised provider, ADR-087/088), a
    ``ticketing.provider`` stanza is written alongside ``repository_key`` at
    creation. It is creation-time configuration, like the key: an already-
    initialized repository is left untouched (edit ``.rac/config.yaml`` to change
    a provider later).

    Raises :class:`InvalidRepositoryKey` for a bad key,
    :class:`InvalidTicketingProvider` for an unknown provider,
    :class:`RepositoryKeyConflict` when a different key is already established
    in this exact directory, and :class:`MalformedRepositoryConfig` when an
    existing file cannot be read.
    """
    if not KEY_RE.match(key):
        raise InvalidRepositoryKey(key)
    if ticketing is not None and ticketing not in TICKETING_PROVIDER_NAMES:
        raise InvalidTicketingProvider(ticketing)
    config_path = Path(directory) / CONFIG_DIR / CONFIG_FILE
    if config_path.is_file():
        existing = _read_config(config_path)
        if existing.repository_key != key:
            raise RepositoryKeyConflict(existing.repository_key, key, str(config_path))
        return InitResult(repository_key=key, config_path=str(config_path), created=False)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    body = f"repository_key: {key}\n"
    if ticketing is not None:
        body += f"ticketing:\n  provider: {ticketing}\n"
    config_path.write_text(body, encoding="utf-8")
    return InitResult(repository_key=key, config_path=str(config_path), created=True)
