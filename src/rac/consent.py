"""Usage-sharing consent — opt-in twice over, anonymous by construction.

ADR-041 permits RAC exactly one anonymous daily ping, and only once consent
has been recorded here. The record is JSON at ``$XDG_CONFIG_HOME/rac/
telemetry.json`` and carries the Explorer-preferences posture: a missing or
corrupt file means *no consent*, loading never raises, and saving swallows
filesystem trouble — a machine that cannot persist consent is a machine that
shares nothing.

The install id is random (``secrets.token_hex(16)``): it derives from no
machine attribute, so it identifies nothing (ADR-041). It is minted at opt-in
and preserved across off/on toggles so the retention curve stays continuous.
The separate ``salt`` digests repository paths for the local active-repo count
and never leaves the machine.

Either answer to the ``rac init`` prompt is persisted — a decline too — so the
question is asked at most once per machine: :func:`consent_recorded` gates the
ask, not the stored choice.

This module stays outside ``rac.mcp`` so ``rac init`` / ``rac telemetry`` never
pay the MCP SDK import cost; the PostHog constants live here as inert strings
(the only code that touches the network is :mod:`rac.mcp.ping`).
"""

from __future__ import annotations

import json
import os
import secrets
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

# PostHog capture endpoint (EU) and the public, write-only project key
# (ADR-041). The key is safe to embed; emptying it is the kill switch — with an
# empty key nothing sends even when consent is recorded, and `rac telemetry
# status` reports so. Tests monkeypatch these at runtime, so every consumer must
# read the module globals live rather than capturing a local copy.
POSTHOG_ENDPOINT = "https://eu.i.posthog.com/capture/"
POSTHOG_API_KEY = "phc_whK4Ndn7Pae3ZtgNRJWswiafYEyPc9d3eVoFihxzDysZ"

CONSENT_FILENAME = "telemetry.json"


@dataclass(frozen=True)
class Consent:
    """The recorded sharing choice; every default is the no-consent state."""

    share_usage: bool = False
    install_id: str = ""
    salt: str = ""
    consented_at: str = ""
    # ADR-086 enterprise hard-lock. While true the daily ping is forced off at
    # runtime regardless of share_usage or the PostHog key, and opting in is
    # refused until an explicit unlock.
    enterprise_locked: bool = False


@dataclass(frozen=True)
class ConsentStatus:
    """What ``rac telemetry status`` reports back to the user."""

    sharing: bool
    install_id: str
    consented_at: str
    path: str
    endpoint_configured: bool
    enterprise_locked: bool = False


def consent_path() -> Path:
    """Location of the consent record, resolved from the environment each call."""
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "rac" / CONSENT_FILENAME


def consent_recorded() -> bool:
    """True once any answer — including a decline — has been persisted."""
    return consent_path().is_file()


def load_consent() -> Consent:
    """Read the consent record; any problem is read as no consent (never raises)."""
    try:
        data = json.loads(consent_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Consent()
    if not isinstance(data, dict):
        return Consent()
    # Coerce each field defensively: the file is untrusted input (ADR-065), so a
    # hand-edited value of the wrong type must degrade to a default, not crash.
    default = Consent()
    return Consent(
        share_usage=bool(data.get("share_usage", default.share_usage)),
        install_id=str(data.get("install_id", default.install_id)),
        salt=str(data.get("salt", default.salt)),
        consented_at=str(data.get("consented_at", default.consented_at)),
        enterprise_locked=bool(data.get("enterprise_locked", default.enterprise_locked)),
    )


def save_consent(consent: Consent) -> None:
    """Persist the record; filesystem trouble is swallowed, never raised."""
    path = consent_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(consent), indent=2) + "\n", encoding="utf-8")
    except OSError:
        return


def _now_stamp() -> str:
    """Current UTC time as ``...Z`` — the zulu form we store, not ``+00:00``."""
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def opt_in() -> Consent:
    """Record consent, minting an install id and salt only where none exist yet.

    The enterprise lock is preserved, never cleared (ADR-086): turning sharing
    on does not lift a hard-lock — only :func:`enterprise_unlock` does. Callers
    refuse opting in while locked, and preserving the flag keeps the runtime
    ping gate safe even if that guard is bypassed. ``replace`` carries every
    unmentioned field (the lock included) forward untouched.
    """
    existing = load_consent()
    consent = replace(
        existing,
        share_usage=True,
        install_id=existing.install_id or secrets.token_hex(16),
        salt=existing.salt or secrets.token_hex(16),
        consented_at=_now_stamp(),
    )
    save_consent(consent)
    return consent


def opt_out() -> Consent:
    """Withdraw consent, keeping the ids so a later opt-in stays continuous."""
    consent = replace(load_consent(), share_usage=False)
    save_consent(consent)
    return consent


def enterprise_lock() -> Consent:
    """Force the ping off and hard-lock it (ADR-086).

    Sharing is turned off and the lock recorded; the ids survive so a later
    unlock-and-opt-in stays continuous. While locked, the runtime ping gate
    yields nothing and the CLI refuses ``opt_in``.
    """
    consent = replace(load_consent(), share_usage=False, enterprise_locked=True)
    save_consent(consent)
    return consent


def enterprise_unlock() -> Consent:
    """Remove the hard-lock (ADR-086); sharing stays off until an explicit opt-in."""
    consent = replace(load_consent(), enterprise_locked=False)
    save_consent(consent)
    return consent


def decline() -> Consent:
    """Persist the default no-consent record, making :func:`consent_recorded` true."""
    consent = Consent()
    save_consent(consent)
    return consent


def consent_status() -> ConsentStatus:
    """Snapshot the record for ``rac telemetry status``; reads the key live."""
    consent = load_consent()
    return ConsentStatus(
        sharing=consent.share_usage,
        install_id=consent.install_id,
        consented_at=consent.consented_at,
        path=str(consent_path()),
        endpoint_configured=bool(POSTHOG_API_KEY),
        enterprise_locked=consent.enterprise_locked,
    )
