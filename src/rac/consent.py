"""Usage-sharing consent — opt-in twice over, anonymous by construction (v0.10.6).

ADR-041 allows RAC one anonymous daily ping, and only with consent recorded
here. The record lives as JSON under ``$XDG_CONFIG_HOME/rac/telemetry.json``
with the Explorer-preferences posture: a missing or corrupt file means no
consent, loading never raises, and saving tolerates filesystem trouble
silently — a machine where consent cannot be persisted is a machine that
shares nothing.

The install id is random (``secrets.token_hex(16)``), minted at opt-in and
preserved across off-and-on toggles so the retention curve stays continuous.
Random beats a salted hash of machine attributes because it derives from
nothing (ADR-041). The separate ``salt`` digests repository paths for the
local active-repo count and never leaves the machine.

Either answer to the ``rac init`` prompt is persisted — including a decline —
so the question is asked at most once per machine: :func:`consent_recorded`
is the gate, not the answer.

This module lives outside ``rac.mcp`` because importing that package pays the
MCP SDK import, and ``rac init`` / ``rac telemetry`` must stay SDK-free. The
PostHog constants live here for the same reason — they are inert strings; the
only network code in RAC is :mod:`rac.mcp.ping`.
"""

from __future__ import annotations

import json
import os
import secrets
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

# The PostHog capture endpoint (EU region) and public project write key
# (ADR-041). The key is write-only by design and safe to embed; emptying it
# is the kill switch — nothing sends even with consent recorded, and
# `rac telemetry status` says so. The sink is swappable behind these two
# constants.
POSTHOG_ENDPOINT = "https://eu.i.posthog.com/capture/"
POSTHOG_API_KEY = "phc_whK4Ndn7Pae3ZtgNRJWswiafYEyPc9d3eVoFihxzDysZ"

CONSENT_FILENAME = "telemetry.json"


@dataclass(frozen=True)
class Consent:
    """The recorded sharing choice; the default is no consent."""

    share_usage: bool = False
    install_id: str = ""
    salt: str = ""
    consented_at: str = ""


@dataclass(frozen=True)
class ConsentStatus:
    """What `rac telemetry status` reports."""

    sharing: bool
    install_id: str
    consented_at: str
    path: str
    endpoint_configured: bool


def consent_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "rac" / CONSENT_FILENAME


def consent_recorded() -> bool:
    """True once any answer — including a decline — has been persisted."""
    return consent_path().is_file()


def load_consent() -> Consent:
    """Read the consent record; any problem means no consent (never raises)."""
    try:
        data = json.loads(consent_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Consent()
    if not isinstance(data, dict):
        return Consent()
    defaults = Consent()
    return Consent(
        share_usage=bool(data.get("share_usage", defaults.share_usage)),
        install_id=str(data.get("install_id", defaults.install_id)),
        salt=str(data.get("salt", defaults.salt)),
        consented_at=str(data.get("consented_at", defaults.consented_at)),
    )


def save_consent(consent: Consent) -> None:
    """Persist the record; tolerates filesystem trouble silently."""
    path = consent_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(consent), indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass


def opt_in() -> Consent:
    """Record consent, minting ids only where none exist yet."""
    existing = load_consent()
    consent = Consent(
        share_usage=True,
        install_id=existing.install_id or secrets.token_hex(16),
        salt=existing.salt or secrets.token_hex(16),
        consented_at=datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
    )
    save_consent(consent)
    return consent


def opt_out() -> Consent:
    """Withdraw consent; the ids are kept so a later opt-in stays continuous."""
    existing = load_consent()
    consent = Consent(
        share_usage=False,
        install_id=existing.install_id,
        salt=existing.salt,
        consented_at=existing.consented_at,
    )
    save_consent(consent)
    return consent


def decline() -> Consent:
    """Persist the default no-consent record, making ask-once true."""
    consent = Consent()
    save_consent(consent)
    return consent


def consent_status() -> ConsentStatus:
    consent = load_consent()
    return ConsentStatus(
        sharing=consent.share_usage,
        install_id=consent.install_id,
        consented_at=consent.consented_at,
        path=str(consent_path()),
        endpoint_configured=bool(POSTHOG_API_KEY),
    )
