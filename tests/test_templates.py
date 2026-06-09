"""Tests for rac.core.templates — the canonical template registry (v0.7.10).

Bundled templates are part of RAC's compatibility contract (ADR-021): every
supported artifact type must have a packaged template that classifies as its
type, passes structural validation, and stays aligned with the spec-derived
`rac schema --template` render so the two sources cannot drift.
"""

from __future__ import annotations

import pytest

from rac.core.artifacts import ARTIFACT_SPECS
from rac.core.classification import classify
from rac.core.markdown import parse
from rac.core.schema import schema_reference
from rac.core.templates import (
    TemplateNotFound,
    available_templates,
    load_template,
)
from rac.core.validation import has_errors, validate
from rac.output.templates import render_schema_template

SPEC_NAMES = [spec.name for spec in ARTIFACT_SPECS]


# --- registry ----------------------------------------------------------------


def test_registry_matches_artifact_specs():
    # One canonical registry: the template set is the spec set, in spec order.
    assert available_templates() == SPEC_NAMES


def test_unknown_type_raises_template_not_found():
    with pytest.raises(TemplateNotFound, match="unsupported artifact type: meeting"):
        load_template("meeting")


# --- content contract ---------------------------------------------------------


@pytest.mark.parametrize("name", SPEC_NAMES)
def test_template_loads_from_package(name):
    text = load_template(name)
    assert text.startswith("# Title")


@pytest.mark.parametrize("name", SPEC_NAMES)
def test_template_is_deterministic(name):
    assert load_template(name) == load_template(name)


@pytest.mark.parametrize("name", SPEC_NAMES)
def test_template_classifies_as_its_type(name):
    result = classify(parse(load_template(name)))
    assert result.type == name


@pytest.mark.parametrize("name", SPEC_NAMES)
def test_template_passes_structural_validation(name):
    issues = validate(parse(load_template(name)))
    assert not has_errors(issues)


@pytest.mark.parametrize("name", SPEC_NAMES)
def test_template_matches_spec_derived_render(name):
    # Drift guard: the bundled file must equal the spec-derived render, so the
    # creation template and `rac schema --template` stay one source of truth.
    assert load_template(name) == render_schema_template(schema_reference(name))
