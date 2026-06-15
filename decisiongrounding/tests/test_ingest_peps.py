"""Offline unit tests for the PEP ingest tool.

No network: these exercise the pure parsing/derivation/rendering functions on an
inline reStructuredText fixture. The networked `build`/`verify` paths are covered
by the committed corpus + `provenance.json` (see test_real_scenarios.py).
"""

from __future__ import annotations

import hashlib

from ingest import peps

_FIXTURE = """\
PEP: 9999
Title: A Superseding Example
Author: First Author <a@example.com>,
        Second Author <b@example.com>
Status: Final
Type: Standards Track
Replaces: 8888
Created: 01-Jan-2020

Abstract
========

This PEP supersedes :pep:`8888`.
"""


def test_pep_id_and_url():
    assert peps.pep_id(386) == "PEP-0386"
    assert peps.pep_id(8) == "PEP-0008"
    assert peps.source_url(440, "deadbeef").endswith("/deadbeef/peps/pep-0440.rst")


def test_parse_headers_folds_continuation_lines():
    headers = peps.parse_headers(_FIXTURE)
    assert headers["PEP"] == "9999"
    assert headers["Status"] == "Final"
    assert headers["Replaces"] == "8888"
    # The wrapped Author value folds into one field, not two.
    assert "First Author" in headers["Author"] and "Second Author" in headers["Author"]
    # Parsing stops at the first blank line; body content is not a header.
    assert "Abstract" not in headers


def test_parse_headers_stops_at_blank_line():
    headers = peps.parse_headers("PEP: 1\n\nKey: not-a-header\n")
    assert headers == {"PEP": "1"}


def test_supersedes_targets_from_replaces_header():
    assert peps.supersedes_targets(peps.parse_headers(_FIXTURE)) == [8888]
    assert peps.supersedes_targets({"Replaces": "386, 345"}) == [386, 345]
    assert peps.supersedes_targets({}) == []


def test_corpus_markdown_is_rac_decision_wrapping_verbatim_body():
    md = peps.corpus_markdown(9999, _FIXTURE, "abc123", frozenset({9999, 8888}))
    # RAC-native decision artifact: front-matter + canonical decision sections so
    # rac classifies it as a decision.
    assert md.startswith("---\nschema_version: 1\nid: PEP-9999\ntype: decision")
    for section in ("## Status", "## Context", "## Decision", "## Consequences"):
        assert section in md, f"missing {section}"
    assert "Final" in md  # status carried from the fixture's own header
    assert "abc123" in md  # the pin is recorded in the Context provenance line
    # Replaces: 8888 (in corpus) -> a directional, resolvable Supersedes edge.
    assert "## Supersedes" in md and "- PEP-8888" in md
    # The upstream text is embedded verbatim after the Source Text marker.
    body = md.split(peps.SOURCE_TEXT_MARKER, 1)[1]
    assert body == _FIXTURE


def test_corpus_markdown_omits_supersedes_when_target_outside_corpus():
    # The Replaced PEP is not part of this corpus -> no dangling Supersedes ref.
    md = peps.corpus_markdown(9999, _FIXTURE, "abc123", frozenset({9999}))
    assert "## Supersedes" not in md


def test_build_provenance_derives_supersedes_edge():
    older = "PEP: 8888\nTitle: Old\nStatus: Superseded\nSuperseded-By: 9999\n\nbody\n"
    prov = peps.build_provenance(
        (8888, 9999), {8888: older, 9999: _FIXTURE}, "abc123"
    )
    assert prov["pinned_commit"] == "abc123"
    assert prov["supersedes_edges"] == [
        {"source": "PEP-9999", "type": "supersedes", "target": "PEP-8888"}
    ]
    by_id = {e["id"]: e for e in prov["peps"]}
    assert by_id["PEP-8888"]["superseded_by"] == ["PEP-9999"]
    assert by_id["PEP-9999"]["replaces"] == ["PEP-8888"]
    assert by_id["PEP-9999"]["source_sha256"] == hashlib.sha256(
        _FIXTURE.encode("utf-8")
    ).hexdigest()


def test_build_provenance_ignores_edges_outside_the_corpus():
    # Replaces a PEP not included in this corpus -> no dangling edge.
    prov = peps.build_provenance((9999,), {9999: _FIXTURE}, "abc123")
    assert prov["supersedes_edges"] == []
