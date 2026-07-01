"""Tests for SARIF validation output — CI code scanning (ADR-054).

Structural and determinism checks rather than a committed byte-golden (the tool
version is build-derived). Covers the SARIF 2.1.0 envelope, that core validation
and OKF findings both appear, the severity->level mapping, region presence only
for line-anchored findings, and that suppressed (`off`) findings never render.
"""

from __future__ import annotations

import json

import pytest

from rac.cli import main
from rac.output import (
    render_relationships_sarif,
    render_review_sarif,
    render_validate_sarif,
)
from rac.services.relationships import validate_relationships
from rac.services.review import build_review
from rac.services.validate import validate_directory

BAD_DECISION = """\
---
schema_version: 1
id: RAC-KTQ63DPSMF19
type: decision
---
# Bad Status

## Context
c

## Decision
d

## Consequences
x

## Status
Bogus
"""


def _sarif_for(tmp_path) -> dict:
    (tmp_path / "d.md").write_text(BAD_DECISION, encoding="utf-8")
    # index.md (typed) also yields an OKF reserved-filename finding.
    (tmp_path / "index.md").write_text(BAD_DECISION.replace("Bogus", "Accepted"), encoding="utf-8")
    result = validate_directory(str(tmp_path))
    return json.loads(render_validate_sarif(result))


def test_sarif_envelope(tmp_path):
    doc = _sarif_for(tmp_path)
    assert doc["version"] == "2.1.0"
    assert "$schema" in doc
    driver = doc["runs"][0]["tool"]["driver"]
    assert driver["name"] == "rac"
    assert isinstance(driver["version"], str) and driver["version"]


def test_sarif_covers_core_and_okf_findings(tmp_path):
    doc = _sarif_for(tmp_path)
    rule_ids = {r["ruleId"] for r in doc["runs"][0]["results"]}
    assert "invalid-decision-status" in rule_ids  # core validation
    assert "okf-reserved-filename-collision" in rule_ids  # OKF conformance
    # Declared rules mirror the observed codes.
    declared = {r["id"] for r in doc["runs"][0]["tool"]["driver"]["rules"]}
    assert rule_ids <= declared


def test_sarif_levels_and_regions(tmp_path):
    doc = _sarif_for(tmp_path)
    for r in doc["runs"][0]["results"]:
        assert r["level"] in ("error", "warning")
        loc = r["locations"][0]["physicalLocation"]
        assert loc["artifactLocation"]["uri"]
        # OKF findings are file-level (no region); core findings may carry a line.
        if "region" in loc:
            assert loc["region"]["startLine"] >= 1


def test_sarif_deterministic(tmp_path):
    (tmp_path / "d.md").write_text(BAD_DECISION, encoding="utf-8")
    result = validate_directory(str(tmp_path))
    assert render_validate_sarif(result) == render_validate_sarif(result)


def test_sarif_uris_are_percent_encoded(tmp_path):
    # artifactLocation.uri is an RFC 3986 URI, not a raw path: a filename with
    # a space (or non-ASCII) must be percent-encoded or Code Scanning may
    # reject or mislocate the finding. Path separators stay literal.
    (tmp_path / "bad decision.md").write_text(BAD_DECISION, encoding="utf-8")
    doc = json.loads(render_validate_sarif(validate_directory(str(tmp_path))))
    uris = {
        r["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]
        for r in doc["runs"][0]["results"]
    }
    assert uris, "expected at least one finding for the invalid decision"
    assert all(" " not in uri for uri in uris)
    assert any(uri.endswith("bad%20decision.md") for uri in uris)
    assert all("/" in uri for uri in uris)  # separators are not encoded


def test_sarif_omits_suppressed_findings(tmp_path):
    (tmp_path / ".rac").mkdir()
    (tmp_path / ".rac" / "config.yaml").write_text(
        "repository_key: RAC\nvalidation:\n  rules:\n    invalid-decision-status: off\n",
        encoding="utf-8",
    )
    (tmp_path / "d.md").write_text(BAD_DECISION, encoding="utf-8")
    doc = json.loads(render_validate_sarif(validate_directory(str(tmp_path))))
    rule_ids = {r["ruleId"] for r in doc["runs"][0]["results"]}
    assert "invalid-decision-status" not in rule_ids


def test_cli_sarif_directory(tmp_path, capsys):
    (tmp_path / "d.md").write_text(BAD_DECISION, encoding="utf-8")
    rc = main(["validate", str(tmp_path), "--sarif"])
    assert rc == 1
    doc = json.loads(capsys.readouterr().out)
    assert doc["version"] == "2.1.0"


def test_cli_sarif_rejected_for_single_file(tmp_path, capsys):
    f = tmp_path / "d.md"
    f.write_text(BAD_DECISION, encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        main(["validate", str(f), "--sarif"])
    assert exc.value.code == 2  # EXIT_USAGE
    assert "directory validation" in capsys.readouterr().err


def test_cli_json_and_sarif_mutually_exclusive(tmp_path):
    with pytest.raises(SystemExit):
        main(["validate", str(tmp_path), "--json", "--sarif"])


# --- relationships --validate --sarif (v0.21.13) -----------------------------
#
# The PR-gate contract: a broken reference and a retired-decision reference both
# reach SARIF, so the merge gate annotates them inline (Success Measure).

ACCEPTED_DECISION = """\
---
schema_version: 1
id: RAC-AAAA00000001
type: decision
---
# ADR-001: Foo

## Context
c

## Decision
d

## Consequences
x

## Status
Accepted

## Category
Architecture
"""

SUPERSEDED_DECISION = """\
---
schema_version: 1
id: RAC-AAAA00000002
type: decision
---
# ADR-002: Bar

## Context
c

## Decision
d

## Consequences
x

## Status
Superseded

## Category
Architecture
"""

# A live roadmap referencing an accepted decision (resolves), a superseded one
# (retired), and a missing one (broken).
ROADMAP_WITH_BROKEN_AND_RETIRED = """\
---
schema_version: 1
id: RAC-AAAA00000003
type: roadmap
---
# Sample Roadmap

## Status
Planned

## Context
c

## Outcomes
- o

## Initiatives
### Initiative 1 — Do
Do.

## Success Measures
- m

## Assumptions
- a

## Risks
- r

## Related Decisions
- RAC-AAAA00000001
- RAC-AAAA00000002
- adr-404-missing
"""


def _gate_corpus(tmp_path):
    (tmp_path / "adr-001-foo.md").write_text(ACCEPTED_DECISION, encoding="utf-8")
    (tmp_path / "adr-002-bar.md").write_text(SUPERSEDED_DECISION, encoding="utf-8")
    (tmp_path / "roadmap.md").write_text(ROADMAP_WITH_BROKEN_AND_RETIRED, encoding="utf-8")
    return tmp_path


def test_relationships_sarif_covers_broken_and_retired(tmp_path):
    result = validate_relationships(str(_gate_corpus(tmp_path)))
    doc = json.loads(render_relationships_sarif(result))
    by_rule = {r["ruleId"]: r for r in doc["runs"][0]["results"]}
    assert "relationship-target-not-found" in by_rule  # broken reference
    assert "relationship-target-superseded" in by_rule  # retired-decision reference
    # Referential integrity is an error; the retired-target reference is advisory.
    assert by_rule["relationship-target-not-found"]["level"] == "error"
    assert by_rule["relationship-target-superseded"]["level"] == "warning"
    # Both anchor to the referencing roadmap so the annotation lands on the diff.
    for issue in by_rule.values():
        assert issue["locations"][0]["physicalLocation"]["artifactLocation"]["uri"].endswith(
            "roadmap.md"
        )


def test_relationships_sarif_deterministic(tmp_path):
    result = validate_relationships(str(_gate_corpus(tmp_path)))
    assert render_relationships_sarif(result) == render_relationships_sarif(result)


def test_relationships_sarif_clean_corpus_has_no_results(tmp_path):
    (tmp_path / "adr-001-foo.md").write_text(ACCEPTED_DECISION, encoding="utf-8")
    doc = json.loads(render_relationships_sarif(validate_relationships(str(tmp_path))))
    assert doc["runs"][0]["results"] == []


def test_cli_relationships_sarif_exit_and_envelope(tmp_path, capsys):
    rc = main(["relationships", str(_gate_corpus(tmp_path)), "--validate", "--sarif"])
    assert rc == 1
    doc = json.loads(capsys.readouterr().out)
    assert doc["version"] == "2.1.0"


def test_cli_relationships_sarif_requires_validate(tmp_path, capsys):
    with pytest.raises(SystemExit) as exc:
        main(["relationships", str(_gate_corpus(tmp_path)), "--sarif"])
    assert exc.value.code == 2  # EXIT_USAGE
    assert "requires --validate" in capsys.readouterr().err


# --- review --sarif (v0.21.13) -----------------------------------------------


def test_review_sarif_envelope_and_levels(tmp_path):
    doc = json.loads(render_review_sarif(build_review(str(_gate_corpus(tmp_path)))))
    results = doc["runs"][0]["results"]
    assert results, "the broken-reference corpus should yield review findings"
    assert doc["version"] == "2.1.0"
    for r in results:
        # Review adds advisory "info", which maps onto SARIF "note".
        assert r["level"] in ("error", "warning", "note")
        assert r["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]


def test_cli_review_sarif_exit(tmp_path, capsys):
    rc = main(["review", str(_gate_corpus(tmp_path)), "--sarif"])
    assert rc == 1  # priority 1-2 findings present
    doc = json.loads(capsys.readouterr().out)
    assert doc["version"] == "2.1.0"
