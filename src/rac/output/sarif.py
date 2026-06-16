"""SARIF rendering for `rac validate` — CI code scanning (ADR-054).

SARIF 2.1.0 is the format GitHub Code Scanning ingests to annotate a pull
request inline. `rac validate <dir> --sarif` emits one SARIF run covering both
core validation findings and OKF conformance findings, so a CI job can upload it
and surface RAC's findings on the diff.

The output is a *derived* machine contract, parallel to the JSON export (ADR-007),
and fully deterministic and offline (ADR-002): the tool version comes from the
installed package, results are sorted by ``(uri, line, ruleId)``, and no
timestamps are emitted, so the same corpus state yields a byte-identical document.
"""

from __future__ import annotations

import json

from rac import __version__
from rac.services.gate import GateReport
from rac.services.relationships import (
    ISSUE_DUPLICATE_IDENTIFIER,
    ISSUE_EDGE_UNSUPPORTED,
    ISSUE_RELATIONSHIP_CYCLE,
    ISSUE_SELF_REFERENCE,
    ISSUE_TARGET_AMBIGUOUS,
    ISSUE_TARGET_NOT_FOUND,
    ISSUE_TARGET_SUPERSEDED,
    ISSUE_TARGET_TYPE_MISMATCH,
    RELATIONSHIP_SEVERITY,
    RelationshipIssue,
    RelationshipValidation,
)
from rac.services.review import ReviewReport
from rac.services.validate import DirectoryValidation

_SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"
_INFORMATION_URI = "https://github.com/tcballard/requirements-as-code"

# SARIF `level` is a closed set; RAC severities map onto it. Suppressed
# (``off``) findings never reach here — they are dropped before rendering.
# Review adds an advisory "info" severity, which maps to SARIF "note".
_LEVEL = {"error": "error", "warning": "warning", "info": "note"}


def _result(rule_id: str, level: str, message: str, uri: str, line: int | None) -> dict:
    location: dict = {"physicalLocation": {"artifactLocation": {"uri": uri}}}
    if line is not None:
        location["physicalLocation"]["region"] = {"startLine": line}
    return {
        "ruleId": rule_id,
        "level": _LEVEL.get(level, "warning"),
        "message": {"text": message},
        "locations": [location],
    }


def render_validate_sarif(result: DirectoryValidation) -> str:
    """Render a directory validation result as a SARIF 2.1.0 document."""
    results: list[dict] = []
    for file in result.files:
        for issue in file.issues:
            results.append(
                _result(issue.code, issue.severity, issue.message, file.path, issue.line)
            )
    if result.okf is not None:
        for finding in result.okf.findings:
            results.append(
                _result(finding.code, finding.severity, finding.message, finding.path, None)
            )

    return _document(results)


def render_review_sarif(report: ReviewReport) -> str:
    """Render a `rac review` report as a SARIF 2.1.0 document (ADR-054).

    Review findings are file-level (no line anchor); the message carries the
    suggested action so the fix is visible inline. Like the validate renderer,
    the output is deterministic and offline (ADR-002).
    """
    results = [
        _result(
            issue.code,
            issue.severity,
            f"{issue.message} — {issue.action}" if issue.action else issue.message,
            issue.path,
            None,
        )
        for issue in report.issues
    ]
    return _document(results)


# Relationship-validation findings map onto SARIF levels (ADR-054) via the
# canonical intrinsic severity owned by the relationships service
# (``RELATIONSHIP_SEVERITY``), so the SARIF annotation level and the `rac gate`
# enforcement layer read one source and can never disagree. The PR gate blocks on
# any non-zero exit, so a warning-level retired-decision reference still fails the
# check — the level only sets the annotation severity, not the enforcement class.
_RELATIONSHIP_LEVEL = RELATIONSHIP_SEVERITY

# Human-readable message per finding, keyed by code. Reference-style findings
# format the relationship, target, and reason; repository-level findings
# (duplicate identifier, cycle) format their own shape.
_RELATIONSHIP_REASON = {
    ISSUE_TARGET_NOT_FOUND: "target not found",
    ISSUE_TARGET_AMBIGUOUS: "target is ambiguous",
    ISSUE_SELF_REFERENCE: "self-reference",
    ISSUE_TARGET_SUPERSEDED: "target is superseded",
    ISSUE_TARGET_TYPE_MISMATCH: "target is the wrong artifact type",
}


def _relationship_result(issue: RelationshipIssue) -> dict:
    """One SARIF result for a relationship-validation finding.

    Duplicate-identifier and cycle findings carry a ``paths`` list rather than a
    single ``source_path``; the first path anchors the annotation and the
    message names every involved file so the finding is actionable inline.
    """
    label = (issue.relationship or "").replace("_", " ")
    if issue.code == ISSUE_DUPLICATE_IDENTIFIER:
        paths = issue.paths or []
        message = f"Duplicate artifact identifier '{issue.identifier}' in: {', '.join(paths)}"
        uri = paths[0] if paths else issue.identifier or ""
    elif issue.code == ISSUE_RELATIONSHIP_CYCLE:
        paths = issue.paths or []
        message = f"{label} relationship cycle: {' -> '.join(paths)}"
        uri = paths[0] if paths else ""
    elif issue.code == ISSUE_EDGE_UNSUPPORTED:
        message = f"{label} not supported for this artifact type"
        uri = issue.source_path or ""
    else:
        reason = _RELATIONSHIP_REASON.get(issue.code, issue.code)
        message = f"{label}: {issue.target} — {reason}"
        uri = issue.source_path or ""
    return _result(issue.code, _RELATIONSHIP_LEVEL.get(issue.code, "warning"), message, uri, None)


def render_relationships_sarif(validation: RelationshipValidation) -> str:
    """Render `rac relationships --validate` as a SARIF 2.1.0 document (ADR-054).

    This is the renderer the PR pipeline gate uploads to surface broken and
    retired cross-artifact references inline on the diff. Like the validate and
    review renderers, the output is deterministic and offline (ADR-002).
    """
    results = [_relationship_result(issue) for issue in validation.issues]
    return _document(results)


def render_gate_sarif(report: GateReport) -> str:
    """Render a `rac gate` report as a single SARIF 2.1.0 document (v0.21.14).

    One combined run over *all* gate findings — blocking and advisory alike — so
    the PR gate uploads a single SARIF under one Code Scanning category instead of
    three. The finding's intrinsic ``severity`` drives the annotation level (an
    advisory finding still annotates at its own severity); the enforcement class is
    carried in the gate's exit code, not the SARIF level. Deterministic and offline
    (ADR-002): results are sorted by ``_document`` and no timestamps are emitted.
    """
    results = [_result(f.code, f.severity, f.message, f.path, f.line) for f in report.findings]
    return _document(results)


def _document(results: list[dict]) -> str:
    # Deterministic ordering (ADR-002): a line of 0 sorts file-level findings
    # ahead of line-anchored ones for the same file, then by rule then message.
    results.sort(
        key=lambda r: (
            r["locations"][0]["physicalLocation"]["artifactLocation"]["uri"],
            r["locations"][0]["physicalLocation"].get("region", {}).get("startLine", 0),
            r["ruleId"],
            r["message"]["text"],
        )
    )

    rules = [{"id": code} for code in sorted({r["ruleId"] for r in results})]
    document = {
        "version": "2.1.0",
        "$schema": _SCHEMA,
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "rac",
                        "informationUri": _INFORMATION_URI,
                        "version": __version__,
                        "rules": rules,
                    }
                },
                "results": results,
            }
        ],
    }
    return json.dumps(document, indent=2)
