"""Trust-model battery (v0.23.0, WS11).

Covers the two things WS11 owns: the SECURITY.md trust narrative and the
additive `get_artifact` review signal (`provenance.status`). The injection-style
content flag itself is owned and exercised by WS3 (`test_doctor.py`), not here.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from rac.mcp.server import build_server

SECURITY_MD = Path(__file__).parent.parent / "SECURITY.md"

DECISION = (
    "---\nschema_version: 1\nid: {id}\ntype: decision\n---\n# {title}\n\n"
    "{status}## Context\n\nWhy.\n\n## Decision\n\nDo it.\n\n## Consequences\n\nFine.\n"
)


def _decision(root: Path, name: str, aid: str, *, status: str | None) -> None:
    block = f"## Status\n\n{status}\n\n" if status is not None else ""
    (root / f"{name}.md").write_text(
        DECISION.format(id=aid, title=name, status=block), encoding="utf-8"
    )


def _get_artifact(root: Path, artifact_id: str) -> dict:
    server = build_server(str(root))
    contents, _ = asyncio.run(server.call_tool("get_artifact", {"id": artifact_id}))
    return json.loads(contents[0].text)


# --- SECURITY.md trust narrative (REQ-001, REQ-002) --------------------------


def test_security_md_exists():
    assert SECURITY_MD.is_file()


def test_security_md_names_pr_review_as_the_boundary():
    text = SECURITY_MD.read_text(encoding="utf-8")
    assert "human PR review" in text
    assert "trust boundary" in text


def test_security_md_states_threat_and_aids_are_not_guarantees():
    text = SECURITY_MD.read_text(encoding="utf-8").lower()
    # The threat: steering the consuming agent.
    assert "steer" in text and ("injection" in text or "poisoned" in text)
    # The aids are named and explicitly not guarantees / not gates.
    assert "rac doctor" in text and "get_artifact" in text
    assert "neither is a guarantee" in text and "neither is a gate" in text


def test_security_md_makes_no_sla_or_sanitizer_promise():
    text = SECURITY_MD.read_text(encoding="utf-8").lower()
    # It must explicitly disclaim an SLA and a sanitizer, never promise them.
    assert "does not" in text and "sla" in text
    assert "sanitiz" in text  # mentioned only to disclaim it


# --- get_artifact review signal (REQ-004, REQ-005, REQ-006) ------------------


def test_provenance_status_reports_reviewed_status(tmp_path):
    _decision(tmp_path, "accepted", "RAC-AAAAAAAAAAAA", status="Accepted")
    payload = _get_artifact(tmp_path, "RAC-AAAAAAAAAAAA")
    assert payload["provenance"] == {"status": "Accepted"}


def test_provenance_status_present_but_empty_when_indeterminate(tmp_path):
    # A decision with no ## Status section: the field is present and empty,
    # never omitted (REQ-004).
    _decision(tmp_path, "draft", "RAC-BBBBBBBBBBBB", status=None)
    payload = _get_artifact(tmp_path, "RAC-BBBBBBBBBBBB")
    assert payload["provenance"] == {"status": ""}


def test_provenance_status_preserves_authored_case(tmp_path):
    _decision(tmp_path, "proposed", "RAC-CCCCCCCCCCCC", status="Proposed")
    payload = _get_artifact(tmp_path, "RAC-CCCCCCCCCCCC")
    assert payload["provenance"]["status"] == "Proposed"


def test_get_artifact_is_byte_identical_across_calls(tmp_path):
    _decision(tmp_path, "accepted", "RAC-AAAAAAAAAAAA", status="Accepted")
    server = build_server(str(tmp_path))
    first = asyncio.run(server.call_tool("get_artifact", {"id": "RAC-AAAAAAAAAAAA"}))[0][0].text
    second = asyncio.run(server.call_tool("get_artifact", {"id": "RAC-AAAAAAAAAAAA"}))[0][0].text
    assert first == second


def test_content_is_served_verbatim_not_mutated(tmp_path):
    # Read-only: the served content is the file's bytes exactly, with no
    # sanitization or rewrite (REQ-006).
    _decision(tmp_path, "accepted", "RAC-AAAAAAAAAAAA", status="Accepted")
    payload = _get_artifact(tmp_path, "RAC-AAAAAAAAAAAA")
    assert payload["content"] == (tmp_path / "accepted.md").read_text(encoding="utf-8")


def test_provenance_carries_no_trust_verdict(tmp_path):
    # The signal is reported status only — never a score or pass/fail verdict
    # (REQ-005, ADR-034).
    _decision(tmp_path, "accepted", "RAC-AAAAAAAAAAAA", status="Accepted")
    payload = _get_artifact(tmp_path, "RAC-AAAAAAAAAAAA")
    assert set(payload["provenance"]) == {"status"}
    for forbidden in ("score", "trust", "trusted", "safe", "verdict", "rating"):
        assert forbidden not in payload["provenance"]
