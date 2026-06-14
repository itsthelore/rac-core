"""Tests for OKF v0.1 conformance — the write-time gate (ADR-048).

Covers the golden (a clean corpus passes), the adversarial cases (a typed
artifact at a reserved filename, and a registered type with no OKF mapping), and
the negative boundary (untyped documents and untyped reserved entry points are
never flagged — ADR-010). The CLI is checked end-to-end through ``rac validate``.
"""

from __future__ import annotations

import json

from conftest import fixture_path

import rac.services.okf_conformance as okf_mod
from rac.cli import main
from rac.core.corpus import walk_corpus
from rac.services.okf_conformance import (
    CODE_RESERVED_FILENAME,
    CODE_UNMAPPED_TYPE,
    check_okf_conformance,
)


def _report(*parts):
    directory = fixture_path(*parts)
    entries = list(walk_corpus(directory))
    return check_okf_conformance(directory, entries)


def codes(report):
    return {f.code for f in report.findings}


# --- golden -----------------------------------------------------------------


def test_clean_corpus_is_conformant():
    report = _report("okf_conformance", "clean")
    assert report.ok
    assert report.findings == []
    # The typed decision is checked; the untyped document is excluded (ADR-010).
    assert report.artifacts_checked == 1


def test_real_corpus_is_okf_conformant():
    # Release A exit criterion: a RAC repository passes OKF v0.1 conformance.
    entries = list(walk_corpus("rac"))
    report = check_okf_conformance("rac", entries)
    assert report.ok, [f.to_dict() for f in report.findings]
    assert report.artifacts_checked > 0


def test_every_corpus_artifact_satisfies_rac_core():
    # Release A exit criterion: every existing RAC artifact validates against the
    # rac-core frontmatter envelope. In RAC's idiom the envelope is optional but
    # validated-when-present (ADR-025): legacy artifacts without frontmatter stay
    # valid (ADR-010), and any present envelope must parse clean (no metadata
    # issues). This is what "validates against rac-core" means here — not the
    # mandatory-id/type/title shape the brief illustrated.
    for entry in walk_corpus("rac"):
        assert entry.product.metadata_issues == [], (
            entry.path,
            entry.product.metadata_issues,
        )


# --- adversarial ------------------------------------------------------------


def test_typed_artifact_at_reserved_filename_is_flagged():
    report = _report("okf_conformance", "reserved_collision")
    assert not report.ok
    assert CODE_RESERVED_FILENAME in codes(report)
    finding = next(f for f in report.findings if f.code == CODE_RESERVED_FILENAME)
    assert finding.path.endswith("index.md")
    assert "index.md" in finding.message


def test_registered_type_without_okf_mapping_is_flagged(monkeypatch):
    # Simulate a future type registered without an OKF mapping: the bundle would
    # silently drop it, so conformance must flag it instead.
    trimmed = {k: v for k, v in okf_mod.OKF_TYPE.items() if k != "decision"}
    monkeypatch.setattr(okf_mod, "OKF_TYPE", trimmed)
    report = _report("okf_conformance", "clean")
    assert not report.ok
    assert CODE_UNMAPPED_TYPE in codes(report)
    finding = next(f for f in report.findings if f.code == CODE_UNMAPPED_TYPE)
    assert "decision" in finding.message


# --- negative boundary (ADR-010) --------------------------------------------


def test_untyped_reserved_entry_point_is_not_flagged():
    report = _report("okf_conformance", "reserved_ok")
    assert report.ok
    assert report.artifacts_checked == 0  # the untyped index.md is excluded


# --- CLI end-to-end ---------------------------------------------------------


def test_cli_reports_conformant_corpus(capsys):
    rc = main(["validate", fixture_path("okf_conformance", "clean")])
    assert rc == 0
    assert "OKF v0.1: conformant." in capsys.readouterr().out


def test_cli_fails_on_reserved_filename_collision(capsys):
    rc = main(["validate", fixture_path("okf_conformance", "reserved_collision")])
    assert rc == 1
    out = capsys.readouterr().out
    assert CODE_RESERVED_FILENAME in out
    assert "OKF conformance" in out


def test_cli_json_carries_okf_section(capsys):
    rc = main(["validate", fixture_path("okf_conformance", "reserved_collision"), "--json"])
    assert rc == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["valid"] is False
    assert payload["okf"]["conformant"] is False
    assert payload["okf"]["findings"][0]["code"] == CODE_RESERVED_FILENAME


def test_cli_json_clean_corpus_okf_conformant(capsys):
    rc = main(["validate", fixture_path("okf_conformance", "clean"), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["okf"] == {"conformant": True, "artifacts_checked": 1, "findings": []}
