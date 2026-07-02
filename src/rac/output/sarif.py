"""SARIF 2.1.0 rendering for RAC's CI code-scanning surface (ADR-054).

GitHub Code Scanning ingests SARIF to annotate a pull request inline. Each
``rac <command> --sarif`` invocation emits one SARIF *run* covering that
command's findings, so a CI job can upload it and surface RAC's findings on the
diff.

The document is a derived machine contract, parallel to the JSON export
(ADR-007), and deterministic and offline (ADR-002): the tool version comes from
the installed package, results are ordered by ``(uri, line, ruleId, message)``,
and no timestamps are emitted — the same corpus state yields byte-identical
output.
"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote

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
_INFORMATION_URI = "https://github.com/itsthelore/rac-core"

# SARIF ``level`` is a closed set that RAC severities project onto. Suppressed
# (``off``) findings never reach here — they are dropped before rendering. Review
# adds an advisory "info" severity, which projects to SARIF "note".
_LEVEL = {"error": "error", "warning": "warning", "info": "note"}


def _result(rule_id: str, level: str, message: str, uri: str, line: int | None) -> dict[str, Any]:
    # A SARIF artifactLocation.uri is an RFC 3986 URI, not a raw path: a filename
    # carrying a space or non-ASCII character must be percent-encoded or Code
    # Scanning may reject or mislocate the finding. Path separators stay literal.
    location: dict[str, Any] = {
        "physicalLocation": {"artifactLocation": {"uri": quote(uri, safe="/")}}
    }
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
    results = [
        _result(issue.code, issue.severity, issue.message, file.path, issue.line)
        for file in result.files
        for issue in file.issues
    ]
    if result.okf is not None:
        # OKF conformance findings are file-level (no line anchor).
        results += [
            _result(finding.code, finding.severity, finding.message, finding.path, None)
            for finding in result.okf.findings
        ]
    return _document(results)


def render_review_sarif(report: ReviewReport) -> str:
    """Render a ``rac review`` report as a SARIF 2.1.0 document (ADR-054).

    Review findings are file-level; the message carries the suggested action so
    the fix is visible inline. Deterministic and offline, like every renderer
    here (ADR-002).
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


# Relationship-validation findings project onto SARIF levels via the canonical
# intrinsic severity the relationships service owns (``RELATIONSHIP_SEVERITY``),
# so the SARIF annotation level and the ``rac gate`` enforcement layer read one
# source and can never disagree. The gate blocks on any non-zero exit, so a
# warning-level retired-decision reference still fails the check — the level only
# sets the annotation severity, never the enforcement class.
_RELATIONSHIP_LEVEL = RELATIONSHIP_SEVERITY

# Human-readable reason per reference-style finding, keyed by code. Repository-
# level findings (duplicate identifier, cycle, unsupported edge) format their own
# shape below and never consult this table.
_RELATIONSHIP_REASON = {
    ISSUE_TARGET_NOT_FOUND: "target not found",
    ISSUE_TARGET_AMBIGUOUS: "target is ambiguous",
    ISSUE_SELF_REFERENCE: "self-reference",
    ISSUE_TARGET_SUPERSEDED: "target is superseded",
    ISSUE_TARGET_TYPE_MISMATCH: "target is the wrong artifact type",
}


def _relationship_result(issue: RelationshipIssue) -> dict[str, Any]:
    """One SARIF result for a relationship-validation finding.

    Also the shared formatting source for ``rac gate``: ``services.gate`` imports
    this function (lazily, to break an import cycle) so gate findings and
    ``rac relationships --sarif`` can never drift in message or anchor. This
    coupling makes the name a cross-module contract.

    Duplicate-identifier and cycle findings carry a ``paths`` list rather than a
    single ``source_path``; the first path anchors the annotation and the message
    names every involved file so the finding is actionable inline.
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
    """Render ``rac relationships --validate`` as a SARIF 2.1.0 document (ADR-054).

    This is the renderer the PR pipeline gate uploads to surface broken and
    retired cross-artifact references inline on the diff. Deterministic and
    offline (ADR-002).
    """
    return _document([_relationship_result(issue) for issue in validation.issues])


def render_gate_sarif(report: GateReport) -> str:
    """Render a ``rac gate`` report as one SARIF 2.1.0 document (v0.21.14).

    A single combined run over *all* gate findings — blocking and advisory alike
    — so the PR gate uploads one SARIF under one Code Scanning category instead of
    three. Each finding's intrinsic ``severity`` drives its annotation level (an
    advisory finding still annotates at its own severity); the enforcement class
    lives in the gate's exit code, not the SARIF level. Deterministic and offline
    (ADR-002).
    """
    return _document(
        [_result(f.code, f.severity, f.message, f.path, f.line) for f in report.findings]
    )


def _sort_key(result: dict[str, Any]) -> tuple[str, int, str, str]:
    # Deterministic ordering (ADR-002): a missing region sorts as line 0, placing
    # file-level findings ahead of line-anchored ones for the same file, then by
    # rule id, then message text.
    location = result["locations"][0]["physicalLocation"]
    return (
        location["artifactLocation"]["uri"],
        location.get("region", {}).get("startLine", 0),
        result["ruleId"],
        result["message"]["text"],
    )


def _document(results: list[dict[str, Any]]) -> str:
    # ``sorted`` (not an in-place sort) so a caller's list is never mutated.
    ordered = sorted(results, key=_sort_key)
    rules = [{"id": code} for code in sorted({r["ruleId"] for r in ordered})]
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
                "results": ordered,
            }
        ],
    }
    return json.dumps(document, indent=2)
