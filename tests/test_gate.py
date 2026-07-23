"""Tests for `decided gate` — policy-aware unified enforcement (v0.21.14, ADR-049).

The gate composes validation, relationships, and review into one enforced verdict
under the corpus enforcement policy. These tests pin the contract that matters:

- with no policy, ``ok`` equals ``validate.ok AND relationships.ok AND
  review.ok`` (the v0.21.13 behaviour the policy refines);
- an ``advisory`` policy entry downgrades a blocking finding so the gate passes
  while the finding still annotates;
- an ``off`` entry drops a finding entirely;
- a malformed ``enforcement`` shape is rejected, not silently ignored;
- the JSON and SARIF envelopes are valid and deterministic.

Negative and boundary cases (a broken reference, an empty directory, adjacent
behaviour) are covered per the session-start prompt.
"""

from __future__ import annotations

import json

import pytest

from asdecided.cli import main
from asdecided.output import render_gate_json, render_gate_sarif
from asdecided.services.gate import (
    EMPTY_POLICY,
    ENFORCEMENT_ADVISORY,
    ENFORCEMENT_BLOCKING,
    EnforcementPolicy,
    build_gate,
)
from asdecided.services.init import MalformedRepositoryConfig, load_enforcement_policy
from asdecided.services.relationships import validate_relationships
from asdecided.services.review import build_review
from asdecided.services.validate import validate_directory

# A minimal valid decision + a roadmap that references it by a resolvable
# identifier (the filename-derived alias). This corpus is clean: it passes
# validate, relationships, and review.
_DECISION = """\
---
schema_version: 1
type: decision
---
# Use Markdown

## Status

Accepted

## Context

We need a deterministic, diffable format for product knowledge.

## Decision

We choose Markdown.

## Consequences

It works offline and diffs cleanly.
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

# A roadmap whose only blocking issue is a reference to a *retired* decision
# (relationship-target-superseded — a warning-severity but blocking-by-default
# finding). Pairs with _RETIRED_DECISION below.
_RETIRED_DECISION = """\
---
schema_version: 1
type: decision
---
# Old Choice

## Status

Superseded

## Context

An earlier decision.

## Decision

We chose something we later replaced.

## Consequences

Replaced later.
"""

_ROADMAP_TO_RETIRED = """\
---
schema_version: 1
type: roadmap
---
# v1 Roadmap

## Outcomes

- Another thing ships.

## Initiatives

### Initiative 1 — Do it

Build it.

## Related Decisions

- adr-002-old-choice
"""


def _clean_corpus(tmp_path):
    (tmp_path / "adr-001-use-markdown.md").write_text(_DECISION, encoding="utf-8")
    (tmp_path / "v0-test.md").write_text(_ROADMAP, encoding="utf-8")
    return str(tmp_path)


def _broken_corpus(tmp_path):
    # The decision is present but the roadmap points at a non-existent target,
    # so relationship validation fails (relationship-target-not-found).
    (tmp_path / "adr-001-use-markdown.md").write_text(_DECISION, encoding="utf-8")
    broken = _ROADMAP.replace("- adr-001-use-markdown", "- adr-999-missing")
    (tmp_path / "v0-test.md").write_text(broken, encoding="utf-8")
    return str(tmp_path)


def _superseded_corpus(tmp_path):
    # A live roadmap references a retired decision: the only blocking finding is
    # relationship-target-superseded (a warning-severity, blocking-by-default code).
    (tmp_path / "adr-002-old-choice.md").write_text(_RETIRED_DECISION, encoding="utf-8")
    (tmp_path / "v1-test.md").write_text(_ROADMAP_TO_RETIRED, encoding="utf-8")
    return str(tmp_path)


def _write_config(tmp_path, body: str):
    config_dir = tmp_path / ".decided"
    config_dir.mkdir(exist_ok=True)
    (config_dir / "config.yaml").write_text(body, encoding="utf-8")


# --- default-policy parity ---------------------------------------------------


def test_clean_corpus_passes(tmp_path):
    directory = _clean_corpus(tmp_path)
    report = build_gate(directory)
    assert report.ok
    assert report.blocking == []


def test_default_ok_equals_validate_and_relationships_and_review(tmp_path):
    directory = _clean_corpus(tmp_path)
    report = build_gate(directory)
    expected = (
        validate_directory(directory).ok
        and validate_relationships(directory).ok
        and build_review(directory).ok
    )
    assert report.ok == expected is True


def test_broken_reference_fails_the_gate(tmp_path):
    directory = _broken_corpus(tmp_path)
    report = build_gate(directory)
    assert not report.ok
    assert any(f.source == "relationships" for f in report.blocking)
    # Parity holds on the failing case too.
    expected = (
        validate_directory(directory).ok
        and validate_relationships(directory).ok
        and build_review(directory).ok
    )
    assert report.ok == expected is False


def test_broken_corpus_exit_code_is_one(tmp_path):
    directory = _broken_corpus(tmp_path)
    assert main(["gate", directory]) == 1


def test_clean_corpus_exit_code_is_zero(tmp_path):
    directory = _clean_corpus(tmp_path)
    assert main(["gate", directory]) == 0


# --- policy: advisory downgrade ---------------------------------------------


def test_advisory_policy_downgrades_superseded_so_gate_passes(tmp_path):
    directory = _superseded_corpus(tmp_path)

    # Without policy, the superseded reference is a blocking finding.
    default = build_gate(directory)
    assert not default.ok
    assert any(f.code == "relationship-target-superseded" for f in default.blocking)

    # Downgrade just that finding to advisory: the gate now passes, but the
    # finding still appears — as advisory, not dropped.
    _write_config(tmp_path, "enforcement:\n  advisory:\n    - relationship-target-superseded\n")
    downgraded = build_gate(directory)
    assert downgraded.ok
    superseded = [f for f in downgraded.findings if f.code == "relationship-target-superseded"]
    assert superseded and all(f.enforcement == ENFORCEMENT_ADVISORY for f in superseded)


def test_advisory_finding_still_in_sarif(tmp_path):
    directory = _superseded_corpus(tmp_path)
    _write_config(tmp_path, "enforcement:\n  advisory:\n    - relationship-target-superseded\n")
    report = build_gate(directory)
    sarif = json.loads(render_gate_sarif(report))
    rule_ids = {r["ruleId"] for r in sarif["runs"][0]["results"]}
    assert "relationship-target-superseded" in rule_ids


def test_gate_exit_zero_after_advisory_downgrade(tmp_path):
    directory = _superseded_corpus(tmp_path)
    _write_config(tmp_path, "enforcement:\n  advisory:\n    - relationship-target-superseded\n")
    assert main(["gate", directory]) == 0


# --- policy: off suppression -------------------------------------------------


def test_off_policy_drops_a_finding(tmp_path):
    directory = _superseded_corpus(tmp_path)
    _write_config(tmp_path, "enforcement:\n  off:\n    - relationship-target-superseded\n")
    report = build_gate(directory)
    assert report.ok
    assert all(f.code != "relationship-target-superseded" for f in report.findings)


# --- policy: blocking promotion ---------------------------------------------


def test_blocking_policy_promotes_an_advisory_finding(tmp_path):
    directory = _clean_corpus(tmp_path)
    # missing-recommended-sections is advisory by default (review priority 4);
    # the clean roadmap is missing Assumptions, so this finding exists.
    default = build_gate(directory)
    assert default.ok
    assert any(f.code == "missing-recommended-sections" for f in default.advisory)

    _write_config(tmp_path, "enforcement:\n  blocking:\n    - missing-recommended-sections\n")
    promoted = build_gate(directory)
    assert not promoted.ok
    assert any(f.code == "missing-recommended-sections" for f in promoted.blocking)


# --- malformed policy --------------------------------------------------------


def test_malformed_enforcement_section_raises(tmp_path):
    _clean_corpus(tmp_path)
    _write_config(tmp_path, "enforcement: not-a-mapping\n")
    with pytest.raises(MalformedRepositoryConfig):
        load_enforcement_policy(str(tmp_path))


def test_malformed_enforcement_key_raises(tmp_path):
    _clean_corpus(tmp_path)
    _write_config(tmp_path, "enforcement:\n  blocking: not-a-list\n")
    with pytest.raises(MalformedRepositoryConfig):
        load_enforcement_policy(str(tmp_path))


def test_malformed_enforcement_entry_raises(tmp_path):
    _clean_corpus(tmp_path)
    _write_config(tmp_path, "enforcement:\n  off:\n    - 123\n")
    with pytest.raises(MalformedRepositoryConfig):
        load_enforcement_policy(str(tmp_path))


def test_build_gate_surfaces_malformed_config_via_cli(tmp_path):
    directory = _clean_corpus(tmp_path)
    _write_config(tmp_path, "enforcement: not-a-mapping\n")
    # cmd_gate catches MalformedRepositoryConfig and returns the failure code.
    assert main(["gate", directory]) == 1


# --- policy model precedence -------------------------------------------------


def test_policy_classify_precedence_off_wins():
    policy = EnforcementPolicy(
        blocking=frozenset({"x"}), advisory=frozenset({"x"}), off=frozenset({"x"})
    )
    assert policy.classify("x", ENFORCEMENT_BLOCKING) is None


def test_policy_classify_blocking_beats_advisory():
    policy = EnforcementPolicy(blocking=frozenset({"x"}), advisory=frozenset({"x"}))
    assert policy.classify("x", ENFORCEMENT_ADVISORY) == ENFORCEMENT_BLOCKING


def test_policy_classify_falls_back_to_default():
    assert EMPTY_POLICY.classify("x", ENFORCEMENT_ADVISORY) == ENFORCEMENT_ADVISORY


def test_absent_config_yields_empty_policy(tmp_path):
    _clean_corpus(tmp_path)
    assert load_enforcement_policy(str(tmp_path)) == EMPTY_POLICY


# --- envelopes & determinism -------------------------------------------------


def test_json_envelope_is_valid_and_deterministic(tmp_path):
    directory = _broken_corpus(tmp_path)
    report = build_gate(directory)
    first = render_gate_json(report)
    second = render_gate_json(build_gate(directory))
    assert first == second  # byte-identical across runs (ADR-002)
    payload = json.loads(first)
    assert payload["schema_version"] == "1"
    assert payload["ok"] is False
    assert payload["blocking_count"] >= 1
    assert "findings" in payload


def test_sarif_envelope_is_valid_and_deterministic(tmp_path):
    directory = _broken_corpus(tmp_path)
    report = build_gate(directory)
    first = render_gate_sarif(report)
    second = render_gate_sarif(build_gate(directory))
    assert first == second
    doc = json.loads(first)
    assert doc["version"] == "2.1.0"
    assert doc["runs"][0]["tool"]["driver"]["name"] == "rac"


def test_findings_sorted_deterministically(tmp_path):
    directory = _broken_corpus(tmp_path)
    report = build_gate(directory)
    keys = [(f.path, f.line or 0, f.source, f.code, f.message) for f in report.findings]
    assert keys == sorted(keys)


# --- boundary ---------------------------------------------------------------


def test_empty_directory_passes(tmp_path):
    report = build_gate(str(tmp_path))
    assert report.ok
    assert report.findings == []
    assert main(["gate", str(tmp_path)]) == 0


def test_not_a_directory_is_usage_error(tmp_path):
    missing = tmp_path / "nope"
    with pytest.raises(SystemExit) as exc:
        main(["gate", str(missing)])
    assert exc.value.code == 2
