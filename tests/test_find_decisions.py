"""Live decision query — `find_decisions` / `rac find --decisions` (v0.21.16).

ADR-067 fixes the boundary these tests pin: the engine retrieves *which live
decisions bind a topic* — structural search restricted to decisions, then to the
Accepted, non-retired ones — and asserts nothing about whether a change is wrong
(no semantic verdict, no score). A retired decision (Superseded/Deprecated) is
excluded even when its text matches; a non-decision is excluded; a topic with no
match is a valid empty answer (exit 0), not an error. Ranking is the existing
tiered ladder, and the `--json` shape is the stable `SearchResult` contract
(ADR-007), so it stays byte-deterministic across runs.
"""

from __future__ import annotations

import json

import pytest

from rac.cli import main
from rac.services.resolve import find_decisions

# An Accepted decision about caching — the live, matchable target.
LIVE_CACHE = """---
schema_version: 1
id: RAC-CACHE0000001
type: decision
---
# Cache invalidation strategy

## Context

We need a caching policy for the read path.

## Decision

Use a write-through cache keyed by artifact id.

## Consequences

Reads stay fresh; writes pay a small cost.

## Status

Accepted
"""

# A Superseded decision that *also* mentions caching: it must be excluded from
# the live query even though it matches the topic on every text tier.
RETIRED_CACHE = """---
schema_version: 1
id: RAC-RETRD0000001
type: decision
---
# Old cache approach

## Context

An earlier cache design we have since replaced.

## Decision

Cache everything in memory forever.

## Consequences

It leaked; we moved on.

## Status

Superseded
"""

# A Deprecated decision mentioning caching — the second retired state, proving
# the filter is spec-driven (not a single hard-coded status).
DEPRECATED_CACHE = """---
schema_version: 1
id: RAC-DPRCT0000001
type: decision
---
# Deprecated cache note

## Context

A cache convenience helper, now deprecated.

## Decision

Stop using the cache helper.

## Consequences

Removed in a later release.

## Status

Deprecated
"""

# A requirement that mentions caching — a non-decision, excluded by the type
# filter regardless of how well it matches.
CACHE_REQUIREMENT = """---
schema_version: 1
id: RAC-CACHEREQ0001
type: requirement
---
# Caching requirement

## Description

The system shall cache reads.

## Rationale

Performance.

## Acceptance Criteria

- Reads are cached.
"""


@pytest.fixture
def repo(tmp_path):
    d = tmp_path / "rac"
    (d / "decisions").mkdir(parents=True)
    (d / "requirements").mkdir(parents=True)
    (d / "decisions" / "live-cache.md").write_text(LIVE_CACHE, encoding="utf-8")
    (d / "decisions" / "retired-cache.md").write_text(RETIRED_CACHE, encoding="utf-8")
    (d / "decisions" / "deprecated-cache.md").write_text(DEPRECATED_CACHE, encoding="utf-8")
    (d / "requirements" / "cache-req.md").write_text(CACHE_REQUIREMENT, encoding="utf-8")
    return d


# --- service: structural retrieval + live filter -----------------------------


def test_live_decision_matching_topic_is_returned(repo):
    result = find_decisions(str(repo), "cache")
    ids = [m.id for m in result.matches]
    assert "RAC-CACHE0000001" in ids


def test_retired_decisions_are_excluded(repo):
    # Superseded and Deprecated both match the topic but must not appear: the
    # query returns *settled, live* decisions only (ADR-067).
    result = find_decisions(str(repo), "cache")
    ids = {m.id for m in result.matches}
    assert "RAC-RETRD0000001" not in ids
    assert "RAC-DPRCT0000001" not in ids


def test_non_decisions_are_excluded(repo):
    # The requirement matches "cache" but is not a decision.
    result = find_decisions(str(repo), "cache")
    assert all(m.type == "decision" for m in result.matches)
    assert "RAC-CACHEREQ0001" not in {m.id for m in result.matches}


def test_only_the_live_decision_remains(repo):
    result = find_decisions(str(repo), "cache")
    assert [m.id for m in result.matches] == ["RAC-CACHE0000001"]


def test_topic_with_no_match_is_empty_not_an_error(repo):
    result = find_decisions(str(repo), "telemetry")
    assert result.matches == []
    assert result.match_count == 0


def test_ranking_is_deterministic(repo, tmp_path):
    # A second live decision whose *title* matches ranks above a body-only match,
    # and equal-tier ties break by sorted path — the existing tiered ladder.
    second = """---
schema_version: 1
id: RAC-CACHE0000002
type: decision
---
# Cache topic title hit

## Context

Body only mentions something else.

## Decision

A cache title decision.

## Consequences

None.

## Status

Accepted
"""
    (repo / "decisions" / "aaa-title-cache.md").write_text(second, encoding="utf-8")
    first = find_decisions(str(repo), "cache").matches
    again = find_decisions(str(repo), "cache").matches
    assert [m.id for m in first] == [m.id for m in again]  # deterministic
    # The title hit (RAC-CACHE0000002) outranks the body hit (RAC-CACHE0000001).
    assert [m.id for m in first] == ["RAC-CACHE0000002", "RAC-CACHE0000001"]


# --- CLI face: `rac find <topic> --decisions [--json]` ------------------------


def test_cli_decisions_flag_exits_zero_on_match(repo, capsys):
    code = main(["find", "cache", str(repo), "--decisions"])
    assert code == 0
    out = capsys.readouterr().out
    assert "RAC-CACHE0000001" in out
    assert "RAC-RETRD0000001" not in out


def test_cli_decisions_flag_exits_zero_on_no_match(repo, capsys):
    # Finding nothing is a valid query outcome, not a failure.
    code = main(["find", "telemetry", str(repo), "--decisions"])
    assert code == 0


def test_cli_decisions_json_shape_is_stable(repo, capsys):
    code = main(["find", "cache", str(repo), "--decisions", "--json"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == "1"
    assert payload["query"] == "cache"
    assert payload["type"] == "decision"
    assert payload["match_count"] == 1
    match = payload["matches"][0]
    assert match["id"] == "RAC-CACHE0000001"
    assert match["type"] == "decision"
    assert match["path"].endswith("decisions/live-cache.md")


def test_cli_decisions_json_is_byte_deterministic(repo, capsys):
    main(["find", "cache", str(repo), "--decisions", "--json"])
    first = capsys.readouterr().out
    main(["find", "cache", str(repo), "--decisions", "--json"])
    second = capsys.readouterr().out
    assert first == second


def test_cli_decisions_and_type_are_mutually_exclusive(repo):
    # --decisions implies the decision type + live filter; pairing it with
    # --type is a usage error argparse rejects.
    with pytest.raises(SystemExit) as exc:
        main(["find", "cache", str(repo), "--decisions", "--type", "requirement"])
    assert exc.value.code != 0
