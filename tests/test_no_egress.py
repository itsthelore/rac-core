"""No-egress isolation test — the runnable backing for RAC's posture (v0.21.14).

RAC's security posture (``docs/security.md``, ADR-002) is *offline by design*: the
CLI and its services make no network calls. This test turns that claim into a
runnable control. It replaces ``socket.socket`` and ``socket.create_connection``
with stubs that raise on use, then exercises the core read paths over a temporary
fixture corpus — validation, relationships, review, gate, search, and export. If
any path opened a socket, the test fails. This is a v0.21.14 Success Measure: the
no-egress claim is backed by a runnable isolation test.

The corpus is built in ``tmp_path`` (one decision, one roadmap that references it),
so the test is hermetic and deterministic — it depends on no committed fixture and
touches nothing outside the temporary directory.
"""

from __future__ import annotations

import socket

import pytest

from asdecided.services.export import build_corpus_export
from asdecided.services.gate import build_gate
from asdecided.services.relationships import validate_relationships
from asdecided.services.resolve import find_artifacts
from asdecided.services.review import build_review
from asdecided.services.validate import validate_directory

_DECISION = """\
---
schema_version: 1
type: decision
---
# Use Markdown

## Status

Accepted

## Context

We need a deterministic, diffable format.

## Decision

We choose Markdown.

## Consequences

It works offline.
"""

_ROADMAP = """\
---
schema_version: 1
type: roadmap
---
# v0 Test Roadmap

## Outcomes

- A thing ships.

## Initiatives

### Initiative 1 — Do it

Build the thing.

## Related Decisions

- adr-001-use-markdown
"""


@pytest.fixture
def corpus(tmp_path):
    """A tiny valid corpus: one decision and one roadmap referencing it."""
    (tmp_path / "adr-001-use-markdown.md").write_text(_DECISION, encoding="utf-8")
    (tmp_path / "v0-test.md").write_text(_ROADMAP, encoding="utf-8")
    return str(tmp_path)


@pytest.fixture
def no_network(monkeypatch):
    """Make any socket creation raise, so a network call fails the test loudly."""

    def _blocked(*args, **kwargs):
        raise AssertionError("network access attempted")

    # Patch on the ``socket`` module itself so every import path that does
    # ``socket.socket(...)`` / ``socket.create_connection(...)`` is intercepted.
    monkeypatch.setattr(socket, "socket", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)


def test_validate_makes_no_network_call(corpus, no_network):
    result = validate_directory(corpus)
    assert result.ok


def test_relationships_makes_no_network_call(corpus, no_network):
    result = validate_relationships(corpus)
    assert result.ok


def test_review_makes_no_network_call(corpus, no_network):
    report = build_review(corpus)
    assert report.ok


def test_gate_makes_no_network_call(corpus, no_network):
    report = build_gate(corpus)
    assert report.ok


def test_find_makes_no_network_call(corpus, no_network):
    result = find_artifacts(corpus, "Markdown")
    # A completed search is enough; the assertion under test is "no socket".
    assert result is not None


def test_export_makes_no_network_call(corpus, no_network):
    export = build_corpus_export(corpus)
    assert export is not None
