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
from rac.services.validate import DirectoryValidation

_SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"
_INFORMATION_URI = "https://github.com/tcballard/requirements-as-code"

# SARIF `level` is a closed set; RAC severities map one-to-one. Suppressed
# (``off``) findings never reach here — they are dropped before rendering.
_LEVEL = {"error": "error", "warning": "warning"}


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
