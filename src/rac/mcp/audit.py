"""Read-access audit recorder for the Guide MCP server (ADR-084).

The deliberate inversion of telemetry (ADR-040): where telemetry is content-free
and silently self-disabling, the audit recorder is content-BEARING by design and
fail-LOUD. It answers the question telemetry cannot — who consulted which
decision, when, and which artifact IDs came back — by appending one JSON line per
MCP read-tool call.

It is default-ABSENT: with no ``audit:`` stanza in ``.rac/config.yaml`` no
recorder is built, no file is created, and the engine's content-free guarantee is
byte-for-byte intact (ADR-084's strict-superset property). When enabled it is
local-only — this module imports no network code (the isolation battery enforces
it); shipping events to a sink is the ``lore-audit`` satellite's job, never the
engine's (ADR-002, ADR-073).

Recording is write-only observability outside the request/response contract
(ADR-032): :func:`observe` returns the tool payload unchanged, so responses are
byte-identical with and without the recorder — except, by design, under
``on_write_error: block`` when a write fails, where the call is refused with a
structured ``audit-unavailable`` error rather than serving un-audited content.

The principal is attributable, not authenticated (ADR-065, ADR-077): it records
who *claimed* to query (git identity by default, ``RAC_AUDIT_PRINCIPAL`` to
override), never a verified identity — the enforced boundary stays repository ACL
plus human pull-request review.
"""

from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import yaml

from rac.errors import RACError

# Pinned audit event schema version (ADR-084). Bumping it is a recorded decision.
SCHEMA_VERSION = "1"

# Repository config discovery (read-only half of the `.rac/config.yaml` contract).
# Mirrored here rather than imported from ``rac.services.init`` because the MCP
# layer must not import a write-capable service (ADR-031, the isolation battery).
CONFIG_DIR = ".rac"
CONFIG_FILE = "config.yaml"

AUDIT_FILENAME = "audit.jsonl"
PATH_ENV = "RAC_AUDIT_PATH"
PRINCIPAL_ENV = "RAC_AUDIT_PRINCIPAL"
UNATTRIBUTED = "unattributed"
ON_WRITE_ERROR_VALUES = ("warn", "block")
ERROR_AUDIT_UNAVAILABLE = "audit-unavailable"


class MalformedAuditConfig(RACError):
    """The ``audit:`` stanza in ``.rac/config.yaml`` is unreadable (ADR-084).

    A misconfigured audit posture refuses the server start rather than silently
    recording nothing — the compliance control is never quietly off.
    """

    def __init__(self, config_path: str, reason: str) -> None:
        self.config_path = config_path
        super().__init__(f"malformed audit config {config_path}: {reason}")


@dataclass(frozen=True)
class AuditConfig:
    """The ``audit:`` stanza from ``.rac/config.yaml`` (ADR-084)."""

    enabled: bool
    path: str  # the configured path, or "" to use the default
    on_write_error: str  # "warn" | "block"
    config_path: str | None = None


def _find_config_file(start_dir: str) -> Path | None:
    """The nearest ``.rac/config.yaml`` at or above ``start_dir``, or None."""
    current = Path(start_dir).resolve()
    for directory in (current, *current.parents):
        candidate = directory / CONFIG_DIR / CONFIG_FILE
        if candidate.is_file():
            return candidate
    return None


def _state_dir() -> Path:
    base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(base) / "rac"


def audit_path(config: AuditConfig | None = None) -> Path:
    """Resolve the audit log path: ``RAC_AUDIT_PATH`` > config ``path`` > XDG default."""
    env_override = os.environ.get(PATH_ENV)
    if env_override:
        return Path(env_override)
    if config is not None and config.path:
        return Path(config.path)
    return _state_dir() / AUDIT_FILENAME


def load_audit_config(start_dir: str) -> AuditConfig:
    """Read the ``audit`` stanza from the nearest ``.rac/config.yaml`` (ADR-084).

    Returns a disabled config when there is no config file or no ``audit``
    section. A malformed shape raises :class:`MalformedAuditConfig` — the audit
    posture is never silently misconfigured.
    """
    disabled = AuditConfig(enabled=False, path="", on_write_error="warn")
    config_path = _find_config_file(start_dir)
    if config_path is None:
        return disabled
    try:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise MalformedAuditConfig(str(config_path), f"invalid YAML: {exc}") from exc
    section = data.get("audit") if isinstance(data, dict) else None
    if section is None:
        return disabled
    if not isinstance(section, dict):
        raise MalformedAuditConfig(str(config_path), "'audit' must be a mapping")
    enabled = section.get("enabled", False)
    if not isinstance(enabled, bool):
        raise MalformedAuditConfig(str(config_path), "'audit.enabled' must be true or false")
    path = section.get("path", "")
    if not isinstance(path, str):
        raise MalformedAuditConfig(str(config_path), "'audit.path' must be a string")
    on_write_error = section.get("on_write_error", "warn")
    if on_write_error not in ON_WRITE_ERROR_VALUES:
        raise MalformedAuditConfig(
            str(config_path),
            f"'audit.on_write_error' must be one of {', '.join(ON_WRITE_ERROR_VALUES)}",
        )
    return AuditConfig(
        enabled=enabled,
        path=path,
        on_write_error=on_write_error,
        config_path=str(config_path),
    )


def _git_identity(root: str) -> str | None:
    """``"Name <email>"`` from git config in ``root``, or None when unavailable."""

    def _config(key: str) -> str | None:
        try:
            result = subprocess.run(
                ["git", "config", key],
                cwd=root,
                capture_output=True,
                check=False,
                text=True,
            )
        except OSError:  # no git binary, or root is gone
            return None
        if result.returncode != 0:
            return None
        return result.stdout.strip() or None

    name = _config("user.name")
    email = _config("user.email")
    if name and email:
        return f"{name} <{email}>"
    return email or name


def resolve_principal(root: str) -> str:
    """The audit principal: ``RAC_AUDIT_PRINCIPAL`` > git identity > ``unattributed``.

    Attributable, not authenticated (ADR-084): records who *claimed* to query.
    """
    override = os.environ.get(PRINCIPAL_ENV)
    if override and override.strip():
        return override.strip()
    return _git_identity(root) or UNATTRIBUTED


class AuditRecorder:
    """Append-only, content-bearing, fail-loud audit writer (ADR-084).

    Unlike :class:`~rac.mcp.telemetry.TelemetryRecorder`, a write failure is
    never silently swallowed: it is reported once on stderr (fail-loud), and the
    recorder keeps trying, so ``on_write_error: block`` can refuse every
    un-recordable call rather than disabling itself after the first.
    """

    def __init__(self, path: Path, principal: str, on_write_error: str = "warn") -> None:
        self.path = path
        self.principal = principal
        self.on_write_error = on_write_error
        self.session = secrets.token_hex(8)
        self._warned = False

    def record(self, event: dict) -> bool:
        """Append one event line; return True on success, False on write failure."""
        try:
            with open(self.path, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(event, ensure_ascii=False) + "\n")
            return True
        except OSError as exc:
            if not self._warned:
                action = "refusing tool calls" if self.on_write_error == "block" else "continuing"
                print(
                    f"rac mcp: audit write failed ({exc}); {action} "
                    f"(audit.on_write_error={self.on_write_error}, path={self.path}).",
                    file=sys.stderr,
                )
                self._warned = True
            return False


def create_recorder(config: AuditConfig, root: str) -> AuditRecorder | None:
    """Build an audit recorder when enabled, else ``None`` (the default-absent path)."""
    if not config.enabled:
        return None
    path = audit_path(config)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass  # the recorder's first write will fail loud
    return AuditRecorder(path, resolve_principal(root), config.on_write_error)


def observe(recorder: AuditRecorder | None, tool: str, args: dict, call: Callable[[], str]) -> str:
    """Run ``call``, record one audit event, and return the payload unchanged.

    With no recorder this is exactly ``call()`` — audit off creates nothing and
    leaves the response byte-identical (ADR-084's strict superset). A raised call
    is recorded as ``outcome: "exception"`` and re-raised, never swallowed
    (ADR-034). Under ``on_write_error: block`` a failed write refuses the call
    with a structured ``audit-unavailable`` error rather than serving un-audited
    content.
    """
    if recorder is None:
        return call()
    started = time.perf_counter()
    try:
        payload = call()
    except BaseException:
        recorder.record(_event(recorder, tool, args, [], "exception", started))
        raise
    event = _event(recorder, tool, args, _returned(payload), _outcome(payload), started)
    if not recorder.record(event) and recorder.on_write_error == "block":
        return json.dumps(
            {"schema_version": SCHEMA_VERSION, "error": ERROR_AUDIT_UNAVAILABLE, "tool": tool},
            ensure_ascii=False,
        )
    return payload


def _event(
    recorder: AuditRecorder,
    tool: str,
    args: dict,
    returned: list[str],
    outcome: str,
    started: float,
) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "ts": datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "session": recorder.session,
        "principal": recorder.principal,
        "tool": tool,
        "query": dict(args),
        "returned": returned,
        "outcome": outcome,
        "duration_ms": int((time.perf_counter() - started) * 1000),
    }


def _outcome(payload: str) -> str:
    """``"error"`` when the payload is a structured error, else ``"ok"`` (ADR-034)."""
    try:
        data = json.loads(payload)
    except ValueError:
        return "ok"
    if isinstance(data, dict) and isinstance(data.get("error"), str):
        return "error"
    return "ok"


def _returned(payload: str) -> list[str]:
    """The resolved artifact IDs a call surfaced, parsed from the serialized payload.

    Records IDs only, never bodies (ADR-084): the primary artifact (get_artifact,
    get_related), search/find matches, and get_related incoming + neighborhood
    neighbours. The queried artifact's own outgoing references are raw declared
    target text (``dict[str, list[str]]``), not resolved IDs, so they are not
    recorded as returned access; get_summary surfaces no IDs.
    """
    try:
        data = json.loads(payload)
    except ValueError:
        return []
    if not isinstance(data, dict) or isinstance(data.get("error"), str):
        return []
    ids: list[str] = []
    primary = data.get("id")
    if isinstance(primary, str):
        ids.append(primary)
    for key in ("matches", "incoming", "neighborhood"):
        value = data.get(key)
        if isinstance(value, list):
            ids.extend(
                item["id"]
                for item in value
                if isinstance(item, dict) and isinstance(item.get("id"), str)
            )
    seen: set[str] = set()
    deduped: list[str] = []
    for artifact_id in ids:
        if artifact_id not in seen:
            seen.add(artifact_id)
            deduped.append(artifact_id)
    return deduped
