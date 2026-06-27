"""The anonymous daily ping — RAC's entire network surface (v0.10.6).

ADR-041 allows one transmission and pins it in full: with consent recorded
(:mod:`rac.consent`) and a PostHog key configured, the Guide server sends at
most one ping per 24 hours carrying a random install id, the RAC version, and
an active-repo count. Never repository contents, paths, artifact text,
queries, or tool arguments. Adding a field is a new recorded decision.

This is the only module in RAC permitted to import ``urllib.request`` — the
isolation battery enforces it — so "what does RAC phone home" is answerable
by reading one file.

Fire-and-forget posture: a daemon thread started by ``run_server``, a
three-second socket timeout, every exception swallowed, no retries, no
queueing. The 24-hour marker is written after each attempt regardless of
outcome, so a failing endpoint costs one attempt per day, never a storm. The
ping runs outside the request/response contract (ADR-032): nothing it reads
or writes ever feeds a tool response.

Active repos are counted locally: each served repository root is recorded as
a salted digest (the per-install salt from the consent record, never
transmitted) with a last-seen date, pruned to a thirty-day window. Only the
count crosses the wire.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import urllib.request
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from rac import __version__
from rac import consent as consent_record
from rac.consent import Consent

PING_EVENT = "lore-daily-ping"
PING_SCHEMA_VERSION = "1"
PING_INTERVAL_SECONDS = 24 * 3600
CHECK_INTERVAL_SECONDS = 3600
SOCKET_TIMEOUT_SECONDS = 3.0
ACTIVE_WINDOW_DAYS = 30

LAST_PING_FILENAME = "last-ping"
ACTIVE_REPOS_FILENAME = "active-repos.json"


def _state_dir() -> Path:
    base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(base) / "rac"


def repo_digest(root: str, salt: str) -> str:
    """A salted digest of the resolved repository root; the salt never transmits."""
    return hashlib.sha256((salt + str(Path(root).resolve())).encode("utf-8")).hexdigest()


def record_active_repo(root: str, salt: str) -> None:
    """Mark ``root`` active today in the local digest file; never raises."""
    path = _state_dir() / ACTIVE_REPOS_FILENAME
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    today = datetime.now(UTC).date()
    data[repo_digest(root, salt)] = today.isoformat()
    cutoff = today - timedelta(days=ACTIVE_WINDOW_DAYS)
    kept = {digest: seen for digest, seen in data.items() if _within_window(seen, cutoff)}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(kept, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass


def active_repo_count() -> int:
    """Distinct repos seen within the window; any trouble counts as zero."""
    path = _state_dir() / ACTIVE_REPOS_FILENAME
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    if not isinstance(data, dict):
        return 0
    cutoff = datetime.now(UTC).date() - timedelta(days=ACTIVE_WINDOW_DAYS)
    return sum(1 for seen in data.values() if _within_window(seen, cutoff))


def _within_window(seen: object, cutoff: date) -> bool:
    if not isinstance(seen, str):
        return False
    parsed = _parse_date(seen)
    return parsed is not None and parsed >= cutoff


def _parse_date(text: str) -> date | None:
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def last_ping_at() -> datetime | None:
    """When the last attempt happened; missing or corrupt means never."""
    path = _state_dir() / LAST_PING_FILENAME
    try:
        text = path.read_text(encoding="utf-8").strip()
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (OSError, ValueError):
        return None


def mark_pinged(now: datetime) -> None:
    """Record the attempt time; never raises."""
    path = _state_dir() / LAST_PING_FILENAME
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_iso(now) + "\n", encoding="utf-8")
    except OSError:
        pass


def should_ping(now: datetime) -> bool:
    last = last_ping_at()
    return last is None or (now - last).total_seconds() >= PING_INTERVAL_SECONDS


def _iso(now: datetime) -> str:
    return now.isoformat(timespec="seconds").replace("+00:00", "Z")


def build_payload(install_id: str, active_repos: int, now: datetime) -> dict:
    """The entire transmission, pinned by ADR-041; additions are a new ADR.

    The shape follows PostHog's documented capture contract: ``distinct_id``
    rides inside ``properties``, and ``$process_person_profile: false`` marks
    the event anonymous so PostHog creates no person profile — cheaper, and
    one more enforcement of the anonymity posture.
    """
    return {
        "api_key": consent_record.POSTHOG_API_KEY,
        "event": PING_EVENT,
        "timestamp": _iso(now),
        "properties": {
            "distinct_id": install_id,
            "$process_person_profile": False,
            "schema_version": PING_SCHEMA_VERSION,
            "rac_version": __version__,
            "active_repos": active_repos,
        },
    }


def send_ping(payload: dict) -> None:
    """One POST, short timeout, every failure swallowed, no retries."""
    request = urllib.request.Request(
        consent_record.POSTHOG_ENDPOINT,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=SOCKET_TIMEOUT_SECONDS):
            pass
    except Exception:
        pass


def _tick(install_id: str) -> None:
    """One loop body: at most one attempt per 24 hours.

    The marker is written after the attempt regardless of outcome — a failing
    endpoint costs one attempt per day, never a retry storm.
    """
    now = datetime.now(UTC)
    if not should_ping(now):
        return
    send_ping(build_payload(install_id, active_repo_count(), now))
    mark_pinged(now)


def start_ping_thread(consent: Consent) -> threading.Thread | None:
    """Start the daily-ping daemon thread, or return None when nothing may send.

    Requires recorded consent, a minted install id, and a configured key (the
    empty-key kill switch, ADR-041), and that the enterprise hard-lock is not
    set (ADR-086) — the lock forces the ping off at runtime regardless of
    consent or key. The thread dies with the process; there is no shutdown
    choreography.
    """
    if consent.enterprise_locked:
        return None
    if not (consent.share_usage and consent.install_id and consent_record.POSTHOG_API_KEY):
        return None

    def _loop() -> None:
        while True:
            try:
                _tick(consent.install_id)
            except Exception:
                pass
            time.sleep(CHECK_INTERVAL_SECONDS)

    thread = threading.Thread(target=_loop, daemon=True, name="lore-ping")
    thread.start()
    return thread
