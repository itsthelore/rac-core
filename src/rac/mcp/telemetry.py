"""Opt-in, local-only, content-free usage telemetry for the Guide server (ADR-040).

Telemetry answers a single product question — is the Guide used, and which tools
matter — without spending the trust the Guide asks for. Three properties make that
safe, and each is pinned by the battery rather than promised in prose:

* **Opt-in / default-off** — no recorder means nothing is written.
* **Local-only** — an append-only JSONL log under the XDG state directory; sharing
  is a separate, deliberate act (:func:`share_url` builds a prefilled issue URL the
  user submits from their own browser). This module imports only the standard
  library, so the isolation battery's consumer-boundary rule holds by construction.
* **Content-free** — events carry counts and metadata only. Tool arguments,
  artifact IDs, query strings, paths, and repository content are never recorded.

Recording is write-only observability outside the request/response contract
(ADR-032): :func:`observe` returns the tool payload unchanged, the log is never an
input to a response, and a recorder that cannot write disables itself silently —
telemetry trouble never breaks a tool call. Adding a field is a recorded decision,
not a patch; the event field order below is the contract (ADR-007).
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

# Rotation threshold. Events run ~120 bytes, so 1 MB is roughly 8,000 calls; one
# previous generation is kept (``.1``), bounding disk use near 2 MB with no
# in-flight rotation and no retention configuration (ADR-040).
MAX_LOG_BYTES = 1_000_000

# Share flow (ADR-040): a prefilled new-issue URL against the repository's
# usage-report issue form. Issue forms prefill from ``?field_id=value``; the
# user's browser transmits, RAC never does.
SHARE_ISSUE_URL = "https://github.com/itsthelore/rac-core/issues/new"
SHARE_TEMPLATE = "guide-usage-report.yml"
SHARE_FIELD = "report"


def telemetry_path() -> Path:
    """The local telemetry log path under the XDG state directory.

    ``XDG_STATE_HOME`` is read on every call, never cached at import: the test
    batteries set it per-test after this module is imported.
    """
    base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(base) / "rac" / TELEMETRY_FILENAME


def _iso_ms() -> str:
    """The current instant as ``...Z`` with millisecond precision (the ``ts`` format)."""
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class TelemetryRecorder:
    """Append-only event writer with a never-raise posture.

    Holds the log path and a random per-process session id, so the summary can
    count sessions without recording anything identifying. The first write failure
    disables the recorder for the rest of the process: a recorder that cannot write
    records nothing, and a tool call never pays for telemetry trouble.
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
    """Run ``call``, record one event, and return the payload unchanged.

    With no recorder this is exactly ``call()`` — telemetry off costs nothing and
    leaves the response byte-identical. A raised call is recorded as
    ``outcome: "exception"`` and re-raised, never swallowed: the reasoning boundary
    stays ADR-034's.
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
    """Outcome, error token, and truncation flag read from a serialized payload.

    The tools return structured JSON by contract; anything unparseable is treated
    as ``ok`` rather than letting telemetry raise over a payload the agent reads
    anyway. ``error`` is populated only when the payload is a structured error.
    """
    try:
        data = json.loads(payload)
    except ValueError:
        return "ok", None, False
    if not isinstance(data, dict):
        return "ok", None, False
    truncated = data.get("truncated") is True
    error = data.get("error")
    if isinstance(error, str):
        return "error", error, truncated
    return "ok", None, truncated


def _event(
    session: str, tool: str, outcome: str, error: str | None, started: float, truncated: bool
) -> dict:
    """One event dict in the pinned field order.

    ``error`` is inserted between ``outcome`` and ``duration_ms`` on error outcomes
    only; insertion order is the wire contract (ADR-007).
    """
    event: dict = {
        "schema_version": SCHEMA_VERSION,
        "ts": _iso_ms(),
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
    """Events at ``path`` plus the count of skipped unreadable lines.

    Corruption-tolerant: a missing file is an empty log, and a blank line is
    ignored while a garbled or non-object line is skipped and counted — never
    raised over.
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
    """Aggregated usage for one tool; the summary orders these by tool name."""

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
    """What the local log says about Guide usage (the ``mcp-stats`` payload)."""

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
    """The rounded mean duration over rows that carry an integer ``duration_ms``."""
    durations = [ev["duration_ms"] for ev in rows if isinstance(ev.get("duration_ms"), int)]
    if not durations:
        return 0
    return round(sum(durations) / len(durations))


def share_url(summary: TelemetrySummary) -> str:
    """The prefilled usage-report issue URL for ``summary``.

    String formatting only — the user opens the URL, reviews the prefilled report,
    and submits it under their own GitHub account (ADR-040). The local log path
    stays out of the shared report: a home-directory path can embed a username, and
    the report is counts and timestamps only.

    The report is serialized as indented JSON (``ensure_ascii=False, indent=2``)
    *before* being urlencoded — that exact serialization is a byte-exact pin (the
    ``mcp-stats --share`` golden and the share-URL round-trip test). Passing the raw
    dict would let ``urlencode`` stringify it via ``repr`` (single quotes), which is
    not JSON and would not round-trip.
    """
    report_data = summary.to_dict()
    del report_data["path"]
    report = json.dumps(report_data, ensure_ascii=False, indent=2)
    query = urllib.parse.urlencode({"template": SHARE_TEMPLATE, SHARE_FIELD: report})
    return f"{SHARE_ISSUE_URL}?{query}"
