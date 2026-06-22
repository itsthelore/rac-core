"""CLI usage telemetry — content-free, consent-gated, local-only (v0.24, WS-E).

ADR-046: when — and only when — sharing consent is recorded (ADR-041,
`rac telemetry on`), each completed `rac` command appends one content-free event
to a separate local log, `$XDG_STATE_HOME/rac/rac-usage.jsonl`. The event schema
is pinned: ``schema_version``, ``ts`` (ISO 8601 UTC), ``session`` (random
per-process hex), ``command`` (the subcommand name only), ``outcome``
(``ok`` | ``error`` | ``exception``), and ``duration_ms``. Argv, flag values,
positional arguments, file paths, artifact IDs, and repository content are never
recorded — the named absent fields are a test, not a comment (ADR-040).

Recording is write-only observability outside the command's output (ADR-032):
the recorder runs after dispatch, never feeds back into a command, leaves exit
codes unchanged, and disables itself silently when it cannot write — telemetry
failure never breaks a command.
"""

from __future__ import annotations

import json
import os
import secrets
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from rac.consent import load_consent

SCHEMA_VERSION = "1"
USAGE_FILENAME = "rac-usage.jsonl"
OUTCOME_OK = "ok"
OUTCOME_ERROR = "error"
OUTCOME_EXCEPTION = "exception"

# One random session id per process, so the read-back can count sessions without
# anything identifying. Generated at import, never persisted to config.
_SESSION = secrets.token_hex(8)


def usage_path() -> Path:
    """Location of the CLI-usage log (separate from the Guide log, ADR-046)."""
    base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(base) / "rac" / USAGE_FILENAME


def _event(command: str, outcome: str, duration_ms: int) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "ts": datetime.now(UTC).isoformat(),
        "session": _SESSION,
        "command": command,
        "outcome": outcome,
        "duration_ms": duration_ms,
    }


def record_command(command: str, outcome: str, duration_ms: int) -> None:
    """Append one content-free usage event, if consent is recorded (ADR-046).

    Silent on every failure path — no consent, no command name, or an
    unwritable log all mean "record nothing", never an exception.
    """
    if not command:
        return
    try:
        if not load_consent().share_usage:
            return
        path = usage_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(_event(command, outcome, duration_ms), ensure_ascii=False)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except OSError:
        return


def read_usage(path: Path | None = None) -> list[dict[str, Any]]:
    """Read usage events; a missing or malformed log yields what is parseable."""
    log = path if path is not None else usage_path()
    events: list[dict[str, Any]] = []
    try:
        text = log.read_text(encoding="utf-8")
    except OSError:
        return events
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            events.append(row)
    return events


@dataclass(frozen=True)
class CommandUsage:
    command: str
    calls: int
    errors: int

    def to_dict(self) -> dict[str, Any]:
        return {"command": self.command, "calls": self.calls, "errors": self.errors}


@dataclass(frozen=True)
class UsageSummary:
    total: int
    sessions: int
    commands: list[CommandUsage]
    recent: dict[str, int]  # date (YYYY-MM-DD, UTC) -> event count, last N days

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "total": self.total,
            "sessions": self.sessions,
            "commands": [c.to_dict() for c in self.commands],
            "recent": self.recent,
        }


def summarize_usage(path: Path | None = None, *, days: int = 7) -> UsageSummary:
    """Per-command counts, session count, and a recent-activity trend (REQ-001)."""
    events = read_usage(path)
    sessions = {ev["session"] for ev in events if isinstance(ev.get("session"), str)}
    by_command: dict[str, list[dict]] = {}
    for ev in events:
        command = ev.get("command")
        if isinstance(command, str):
            by_command.setdefault(command, []).append(ev)
    commands = [
        CommandUsage(
            command=command,
            calls=len(rows),
            errors=sum(1 for ev in rows if ev.get("outcome") in (OUTCOME_ERROR, OUTCOME_EXCEPTION)),
        )
        for command, rows in sorted(by_command.items())
    ]
    day_counts: Counter[str] = Counter()
    for ev in events:
        ts = ev.get("ts")
        if isinstance(ts, str) and len(ts) >= 10:
            day_counts[ts[:10]] += 1
    recent = dict(sorted(day_counts.items())[-days:])
    return UsageSummary(total=len(events), sessions=len(sessions), commands=commands, recent=recent)


# Read-back rendering (ADR-046): one surface summarises both the CLI-usage log
# and the Guide log. The Guide summary is passed as a plain dict so this module
# never imports the MCP SDK. Sharing reuses the local-first, user-submitted flow.

SHARE_ISSUE_URL = "https://github.com/itsthelore/rac-core/issues/new"
SHARE_TEMPLATE = "guide-usage-report.yml"
SHARE_FIELD = "report"


def _combined(summary: UsageSummary, guide: dict[str, Any] | None) -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "cli": summary.to_dict(), "guide": guide or {}}


def render_json(summary: UsageSummary, guide: dict[str, Any] | None) -> str:
    return json.dumps(_combined(summary, guide), ensure_ascii=False, indent=2)


def render_human(summary: UsageSummary, guide: dict[str, Any] | None) -> str:
    lines = ["RAC usage", ""]
    if summary.total == 0:
        lines.append("No CLI usage recorded — telemetry is off (enable with `rac telemetry on`).")
    else:
        lines.append(f"CLI commands: {summary.total} calls across {summary.sessions} session(s)")
        for c in summary.commands:
            errs = f"  ({c.errors} error{'s' if c.errors != 1 else ''})" if c.errors else ""
            lines.append(f"  {c.command:<16} {c.calls}{errs}")
        if summary.recent:
            trend = ", ".join(f"{day}: {n}" for day, n in summary.recent.items())
            lines.append(f"  recent: {trend}")
    tools = (guide or {}).get("tools") or []
    if tools:
        lines.extend(["", "Guide MCP tools:"])
        for tool in tools:
            errs = f"  ({tool['errors']} error(s))" if tool.get("errors") else ""
            lines.append(f"  {tool['tool']:<16} {tool['calls']}{errs}")
    return "\n".join(lines)


def share_url(summary: UsageSummary, guide: dict[str, Any] | None) -> str:
    """A prefilled GitHub issue URL — counts only, no local path (ADR-046, ADR-035)."""
    import urllib.parse

    report = json.dumps(_combined(summary, guide), ensure_ascii=False, indent=2)
    query = urllib.parse.urlencode({"template": SHARE_TEMPLATE, SHARE_FIELD: report})
    return f"{SHARE_ISSUE_URL}?{query}"
