"""Opt-in local usage telemetry for Guide (v0.10.4).

Telemetry answers one product question — is Guide actually used, and which
tools matter — without spending the trust the Guide asks for (ADR-040). The
shape is pinned: opt-in and default-off, local-only, and content-free. Events
carry counts and metadata; tool arguments, artifact IDs, query strings, paths,
and repository content are never recorded.

Recording is write-only observability outside the request/response contract
(ADR-032): :func:`observe` returns the tool payload unchanged, the log is
never an input to a response, and a recorder that cannot write disables itself
silently — telemetry failure never breaks a tool call.

The log is append-only JSONL under the XDG state directory (the same pattern
Explorer uses for its workspace), one event per line:

    {"schema_version": "1", "ts": "2026-06-12T14:03:22.512Z",
     "session": "a3f29c1b", "tool": "search_artifacts", "outcome": "ok",
     "duration_ms": 12, "truncated": false}

``outcome`` classifies the structured payload the tools already return
(ADR-034): ``ok``, ``error`` (with the stable error token in ``error``), or
``exception`` for a raised call (recorded, then re-raised). ``truncated``
reads the ADR-033 marker. Adding a field is a recorded decision, not a patch.

Sharing is a deliberate act: :func:`share_url` formats the JSON summary into a
prefilled GitHub issue URL the user reviews and submits in their own browser.
RAC contains no network code — building a URL is string formatting;
transmission belongs to the user (ADR-035).

This module imports only the standard library, so the isolation battery's
consumer-boundary rules hold by construction.
"""

from __future__ import annotations

import json
import os
import secrets
import time
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

# Pinned event schema version (ADR-040). Bumping it is a recorded decision.
SCHEMA_VERSION = "1"

TELEMETRY_FILENAME = "guide-telemetry.jsonl"

# Rotation threshold: events are ~120 bytes, so 1 MB holds roughly 8,000
# calls. One previous generation is kept (``.1``), bounding disk use at about
# 2 MB with no in-flight rotation and no retention configuration (ADR-040).
MAX_LOG_BYTES = 1_000_000

# Share flow (ADR-040): a prefilled new-issue URL against the repository's
# usage-report issue form. Issue forms accept ``?field_id=value`` prefill;
# the user's browser transmits, RAC never does.
SHARE_ISSUE_URL = "https://github.com/tcballard/requirements-as-code/issues/new"
SHARE_TEMPLATE = "guide-usage-report.yml"
SHARE_FIELD = "report"


def telemetry_path() -> Path:
    """The local telemetry log path under the XDG state directory."""
    base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(base) / "rac" / TELEMETRY_FILENAME


class TelemetryRecorder:
    """Append-only event writer with a never-raise posture.

    Holds the log path and a random per-process session id, so the summary
    can count sessions without recording anything identifying. The first
    write failure disables the recorder for the rest of the process: a
    recorder that cannot write records nothing, and a tool call never pays
    for telemetry trouble.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self.session = secrets.token_hex(4)
        self._disabled = False

    def record(self, event: dict) -> None:
        """Append one event line; never raises."""
        if self._disabled:
            return
        try:
            with open(self.path, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(event, ensure_ascii=False) + "\n")
        except OSError:
            self._disabled = True


def create_recorder() -> TelemetryRecorder:
    """Build a recorder for the standard log path, rotating an oversized log.

    All filesystem trouble is tolerated: a recorder over an unwritable state
    directory simply records nothing once its first write fails.
    """
    path = telemetry_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size > MAX_LOG_BYTES:
            path.replace(path.with_suffix(path.suffix + ".1"))
    except OSError:
        pass
    return TelemetryRecorder(path)


def observe(recorder: TelemetryRecorder | None, tool: str, call: Callable[[], str]) -> str:
    """Run ``call`` and record one event; the payload returns unchanged.

    With no recorder this is exactly ``call()`` — telemetry off costs
    nothing. A raised call is recorded as ``outcome: "exception"`` and
    re-raised, never swallowed (the reasoning boundary stays ADR-034's).
    """
    if recorder is None:
        return call()
    started = time.perf_counter()
    try:
        payload = call()
    except BaseException:
        recorder.record(_event(recorder.session, tool, "exception", None, started, False))
        raise
    outcome, error, truncated = _classify(payload)
    recorder.record(_event(recorder.session, tool, outcome, error, started, truncated))
    return payload


def _classify(payload: str) -> tuple[str, str | None, bool]:
    """Outcome, error token, and truncation read from a serialized payload.

    The tools return structured JSON by contract; anything unparseable is
    classified as ``ok`` rather than letting telemetry raise over a payload
    the agent will read anyway.
    """
    try:
        data = json.loads(payload)
    except ValueError:
        return "ok", None, False
    if not isinstance(data, dict):
        return "ok", None, False
    error = data.get("error")
    truncated = data.get("truncated") is True
    if isinstance(error, str):
        return "error", error, truncated
    return "ok", None, truncated


def _event(
    session: str, tool: str, outcome: str, error: str | None, started: float, truncated: bool
) -> dict:
    event: dict = {
        "schema_version": SCHEMA_VERSION,
        "ts": datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "session": session,
        "tool": tool,
        "outcome": outcome,
    }
    if error is not None:
        event["error"] = error
    event["duration_ms"] = int((time.perf_counter() - started) * 1000)
    event["truncated"] = truncated
    return event


def read_events(path: Path) -> tuple[list[dict], int]:
    """Events from ``path`` plus the count of skipped unreadable lines.

    Corruption-tolerant by the same posture as Explorer's state files: a
    missing file is an empty log, and a garbled line is skipped and counted,
    never raised over.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return [], 0
    events: list[dict] = []
    skipped = 0
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except ValueError:
            skipped += 1
            continue
        if isinstance(data, dict):
            events.append(data)
        else:
            skipped += 1
    return events, skipped


@dataclass(frozen=True)
class ToolUsage:
    """Aggregated usage for one tool, ordered by tool name in the summary."""

    tool: str
    calls: int
    errors: int
    truncated: int
    avg_duration_ms: int

    def to_dict(self) -> dict:
        return {
            "tool": self.tool,
            "calls": self.calls,
            "errors": self.errors,
            "truncated": self.truncated,
            "avg_duration_ms": self.avg_duration_ms,
        }


@dataclass(frozen=True)
class TelemetrySummary:
    """What the local log says about Guide usage (the `mcp-stats` payload)."""

    path: str
    event_count: int
    session_count: int
    first_ts: str | None
    last_ts: str | None
    skipped_lines: int
    tools: list[ToolUsage] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "path": self.path,
            "event_count": self.event_count,
            "session_count": self.session_count,
            "first_ts": self.first_ts,
            "last_ts": self.last_ts,
            "skipped_lines": self.skipped_lines,
            "tools": [usage.to_dict() for usage in self.tools],
        }


def summarize(path: Path | None = None) -> TelemetrySummary:
    """Summarize the telemetry log; an empty or missing log is a valid answer."""
    log = path if path is not None else telemetry_path()
    events, skipped = read_events(log)
    sessions = {ev["session"] for ev in events if isinstance(ev.get("session"), str)}
    stamps = sorted(ev["ts"] for ev in events if isinstance(ev.get("ts"), str))
    by_tool: dict[str, list[dict]] = {}
    for ev in events:
        tool = ev.get("tool")
        if isinstance(tool, str):
            by_tool.setdefault(tool, []).append(ev)
    tools = [
        ToolUsage(
            tool=tool,
            calls=len(rows),
            errors=sum(1 for ev in rows if ev.get("outcome") in ("error", "exception")),
            truncated=sum(1 for ev in rows if ev.get("truncated") is True),
            avg_duration_ms=_average_duration(rows),
        )
        for tool, rows in sorted(by_tool.items())
    ]
    return TelemetrySummary(
        path=str(log),
        event_count=len(events),
        session_count=len(sessions),
        first_ts=stamps[0] if stamps else None,
        last_ts=stamps[-1] if stamps else None,
        skipped_lines=skipped,
        tools=tools,
    )


def _average_duration(rows: list[dict]) -> int:
    durations = [ev["duration_ms"] for ev in rows if isinstance(ev.get("duration_ms"), int)]
    if not durations:
        return 0
    return round(sum(durations) / len(durations))


def share_url(summary: TelemetrySummary) -> str:
    """The prefilled usage-report issue URL for ``summary``.

    String formatting only — the user opens the URL, reviews the prefilled
    report, and submits it with their own GitHub account (ADR-040). The
    local log path stays out of the shared report: a home-directory path
    can embed a username, and the report is counts and timestamps only.
    """
    report_data = summary.to_dict()
    del report_data["path"]
    report = json.dumps(report_data, ensure_ascii=False, indent=2)
    query = urllib.parse.urlencode({"template": SHARE_TEMPLATE, SHARE_FIELD: report})
    return f"{SHARE_ISSUE_URL}?{query}"
