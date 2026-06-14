"""Tests for validation severity overrides — warnings-first onboarding (ADR-053).

Covers the pure model (`resolve_severity`/`apply_overrides`), the config loader
(`load_overrides` over `.rac/config.yaml`, including the YAML `off`->False
coercion and malformed-config errors), and end-to-end behaviour through
`rac validate`: a corpus that fails by default goes green once a type or rule is
downgraded, precedence (rule beats the type ceiling), suppression, and that an
absent `validation` section is a pure no-op.
"""

from __future__ import annotations

import pytest

from rac.cli import main
from rac.core.models import Issue
from rac.core.overrides import EMPTY, SeverityOverrides, apply_overrides, resolve_severity
from rac.services.init import MalformedRepositoryConfig, load_overrides

# A decision that classifies (context/decision/consequences/status) but carries an
# out-of-enum status, so it fails with `invalid-decision-status` by default.
BAD_DECISION = """\
---
schema_version: 1
id: RAC-KTQ63DPSMF19
type: decision
---
# A Decision With A Bad Status

## Context
c

## Decision
d

## Consequences
x

## Status
Bogus
"""


def _repo(tmp_path, config: str, artifact: str = BAD_DECISION):
    (tmp_path / ".rac").mkdir()
    (tmp_path / ".rac" / "config.yaml").write_text(config, encoding="utf-8")
    (tmp_path / "d.md").write_text(artifact, encoding="utf-8")
    return str(tmp_path)


# --- pure model --------------------------------------------------------------


def test_resolve_severity_precedence():
    ov = SeverityOverrides(rules={"x": "error"}, types={"decision": "warning"})
    # Type ceiling downgrades, but the per-rule entry is more specific and wins.
    assert resolve_severity("error", "x", "decision", ov) == "error"
    assert resolve_severity("error", "y", "decision", ov) == "warning"
    assert resolve_severity("error", "y", "requirement", ov) == "error"


def test_apply_overrides_empty_is_noop():
    issues = [Issue("error", "a", "m"), Issue("warning", "b", "m")]
    assert apply_overrides(issues, "decision", EMPTY) is issues


def test_apply_overrides_downgrades_and_suppresses():
    issues = [Issue("error", "a", "m", 3), Issue("error", "b", "m")]
    ov = SeverityOverrides(rules={"a": "warning", "b": "off"})
    out = apply_overrides(issues, "decision", ov)
    assert [(i.code, i.severity) for i in out] == [("a", "warning")]
    assert out[0].line == 3  # other fields preserved


# --- loader ------------------------------------------------------------------


def test_load_overrides_absent_config_is_empty(tmp_path):
    assert load_overrides(str(tmp_path)).is_empty


def test_load_overrides_no_validation_section_is_empty(tmp_path):
    repo = _repo(tmp_path, "repository_key: RAC\n")
    assert load_overrides(repo).is_empty


def test_load_overrides_parses_rules_and_types(tmp_path):
    cfg = (
        "repository_key: RAC\nvalidation:\n"
        "  rules:\n    ambiguous-verb: off\n"
        "  types:\n    roadmap: warning\n"
    )
    repo = _repo(tmp_path, cfg)
    ov = load_overrides(repo)
    assert ov.rules == {"ambiguous-verb": "off"}  # YAML `off` coerced from False
    assert ov.types == {"roadmap": "warning"}


def test_load_overrides_rejects_unknown_severity(tmp_path):
    repo = _repo(tmp_path, "repository_key: RAC\nvalidation:\n  rules:\n    x: loud\n")
    with pytest.raises(MalformedRepositoryConfig, match="error, warning, off"):
        load_overrides(repo)


def test_load_overrides_rejects_off_for_whole_type(tmp_path):
    # `off` is not allowed for a whole type (only error|warning).
    repo = _repo(tmp_path, "repository_key: RAC\nvalidation:\n  types:\n    decision: off\n")
    with pytest.raises(MalformedRepositoryConfig, match="error, warning"):
        load_overrides(repo)


# --- end to end through `rac validate` ---------------------------------------


def test_validate_fails_without_overrides(tmp_path, capsys):
    repo = _repo(tmp_path, "repository_key: RAC\n")
    assert main(["validate", repo]) == 1
    assert "1 invalid" in capsys.readouterr().out


def test_type_downgrade_keeps_ci_green(tmp_path, capsys):
    repo = _repo(tmp_path, "repository_key: RAC\nvalidation:\n  types:\n    decision: warning\n")
    assert main(["validate", repo]) == 0
    assert "1 valid, 0 invalid" in capsys.readouterr().out


def test_rule_suppression_keeps_ci_green(tmp_path):
    repo = _repo(
        tmp_path, "repository_key: RAC\nvalidation:\n  rules:\n    invalid-decision-status: off\n"
    )
    assert main(["validate", repo]) == 0


def test_rule_overrides_type_ceiling(tmp_path):
    cfg = (
        "repository_key: RAC\nvalidation:\n  types:\n    decision: warning\n"
        "  rules:\n    invalid-decision-status: error\n"
    )
    repo = _repo(tmp_path, cfg)
    assert main(["validate", repo]) == 1  # rule forces error back, type cap loses


def test_okf_finding_is_downgradable(tmp_path):
    # A typed artifact named index.md triggers okf-reserved-filename-collision.
    (tmp_path / ".rac").mkdir()
    (tmp_path / "index.md").write_text(BAD_DECISION.replace("Bogus", "Accepted"), encoding="utf-8")
    cfg_path = tmp_path / ".rac" / "config.yaml"
    cfg_path.write_text("repository_key: RAC\n", encoding="utf-8")
    assert main(["validate", str(tmp_path)]) == 1  # collision fails by default
    cfg_path.write_text(
        "repository_key: RAC\nvalidation:\n  rules:\n"
        "    okf-reserved-filename-collision: warning\n",
        encoding="utf-8",
    )
    assert main(["validate", str(tmp_path)]) == 0  # downgraded -> conformant
