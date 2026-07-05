"""Characterization tests for the author cluster (inspect / improve / schema /
templates / new / init / quickstart / profiles).

These characterization tests were added before the rebuild-scale examiner
freeze. They pin CURRENT observable behavior exactly — human-readable stdout
wording, generated-file bytes, and template bodies that existing tests assert
only structurally (substring / ``json.loads`` / spec-derived render). Nothing
here is a desired-behavior assertion: if the product output changes, these are
expected to fail and be re-pinned, not "fixed".

Byte-anchor constants (the four non-requirement template bodies) embed the
current packaged bytes inline, giving each type the independent anchor the
requirement template already has via ``tests/golden``.
"""

from __future__ import annotations

import pytest
from conftest import fixture_path

from rac.cli import main
from rac.core.schema import schema_reference
from rac.core.templates import load_template
from rac.output.templates import render_schema_template
from rac.services.init import init_repository, load_enforcement_policy


def _parse_id(stdout: str) -> str:
    """The system-assigned ID from a `rac new` / `rac quickstart` `ID:` line."""
    for line in stdout.splitlines():
        if line.startswith("ID: "):
            return line[len("ID: ") :]
    raise AssertionError(f"no ID line in output: {stdout!r}")


# --- Finding 1 (HIGH): `rac new` human next-step framing ----------------------


def test_cli_new_human_exact(tmp_path, capsys):
    init_repository(str(tmp_path), key="RAC")
    out = tmp_path / "req.md"
    assert main(["new", "requirement", str(out)]) == 0
    captured = capsys.readouterr().out
    artifact_id = _parse_id(captured)
    assert captured == (
        f"Created requirement artifact: {out}\n"
        f"ID: {artifact_id}\n"
        f"\n"
        f"Edit the TODO placeholders, then check it with: rac validate {out}\n"
    )


# --- Finding 2 (HIGH): `rac quickstart` human body + Initialized/Using verbs ---


def test_cli_quickstart_human_initialized_exact(tmp_path, capsys, monkeypatch):
    # Fresh directory: identity is created, so the verb is "Initialized".
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    monkeypatch.setattr("sys.stdout.isatty", lambda: False)
    assert main(["quickstart", str(tmp_path), "--key", "RAC"]) == 0
    captured = capsys.readouterr().out
    artifact_id = _parse_id(captured)
    starter = tmp_path / "rac" / "requirements" / "first-requirement.md"
    assert captured == (
        f"Initialized repository key RAC\n"
        f"Created requirement artifact: {starter}\n"
        f"ID: {artifact_id}\n"
        f"\n"
        f"Next: edit the TODO placeholders, then run: rac validate {starter}\n"
    )


def test_cli_quickstart_human_using_verb_exact(tmp_path, capsys, monkeypatch):
    # Identity already established but the corpus holds no recognized artifact:
    # init_repository returns created=False, so the verb is "Using" — the
    # otherwise-untested branch of render_quickstart_human.
    init_repository(str(tmp_path), key="RAC")
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    monkeypatch.setattr("sys.stdout.isatty", lambda: False)
    assert main(["quickstart", str(tmp_path)]) == 0
    captured = capsys.readouterr().out
    artifact_id = _parse_id(captured)
    starter = tmp_path / "rac" / "requirements" / "first-requirement.md"
    assert captured == (
        f"Using repository key RAC\n"
        f"Created requirement artifact: {starter}\n"
        f"ID: {artifact_id}\n"
        f"\n"
        f"Next: edit the TODO placeholders, then run: rac validate {starter}\n"
    )


# --- Finding 3 (MEDIUM): `rac init` Config:/Wrote: human lines -----------------


def test_cli_init_profile_default_human_exact(tmp_path, capsys):
    # Plain init has no Profile:/Wrote: lines; a profile init reports the config
    # path and every written client file in _MCP_TARGETS order.
    assert main(["init", str(tmp_path), "--key", "ACME", "--profile", "default"]) == 0
    captured = capsys.readouterr().out
    assert captured == (
        f"Initialized repository key ACME\n"
        f"Config: {tmp_path / '.rac' / 'config.yaml'}\n"
        f"Profile: default\n"
        f"Wrote: {tmp_path / '.mcp.json'}\n"
        f"Wrote: {tmp_path / '.cursor' / 'mcp.json'}\n"
    )


def test_cli_init_plain_human_exact(tmp_path, capsys):
    # No profile: Config: line present, no Profile:/Wrote: lines.
    assert main(["init", str(tmp_path), "--key", "PROJ"]) == 0
    captured = capsys.readouterr().out
    assert captured == (
        f"Initialized repository key PROJ\nConfig: {tmp_path / '.rac' / 'config.yaml'}\n"
    )


# --- Finding 4 (MEDIUM): enterprise profile blocking codes + config bytes ------


def test_enterprise_blocking_code_set_is_exact(tmp_path):
    init_repository(str(tmp_path), key="ACME", profile="enterprise")
    policy = load_enforcement_policy(str(tmp_path))
    assert policy.blocking == frozenset(
        {
            "relationship-target-not-found",
            "relationship-target-ambiguous",
            "relationship-self-reference",
            "relationship-target-type-mismatch",
            "relationship-target-superseded",
            "relationship-cycle",
            "relationship-edge-unsupported",
            "duplicate-artifact-identifier",
        }
    )


def test_enterprise_config_bytes_exact(tmp_path):
    # The full committed .rac/config.yaml: repository key, both comment lines,
    # and the eight blocking codes in their exact order.
    init_repository(str(tmp_path), key="ACME", profile="enterprise")
    config = (tmp_path / ".rac" / "config.yaml").read_text(encoding="utf-8")
    assert config == (
        "repository_key: ACME\n"
        "# Enterprise profile (ADR-088): relationship-integrity findings block "
        "`rac gate`,\n"
        "# committed explicitly so the enforcement policy is auditable (ADR-049).\n"
        "enforcement:\n"
        "  blocking:\n"
        "    - relationship-target-not-found\n"
        "    - relationship-target-ambiguous\n"
        "    - relationship-self-reference\n"
        "    - relationship-target-type-mismatch\n"
        "    - relationship-target-superseded\n"
        "    - relationship-cycle\n"
        "    - relationship-edge-unsupported\n"
        "    - duplicate-artifact-identifier\n"
    )


# --- Finding 5 (MEDIUM): generated .mcp.json / .cursor/mcp.json byte format ----

_MCP_JSON_BYTES = (
    "{\n"
    '  "mcpServers": {\n'
    '    "lore": {\n'
    '      "command": "rac",\n'
    '      "args": ["mcp", "--root", "."]\n'
    "    }\n"
    "  }\n"
    "}\n"
)


def test_mcp_json_exact_bytes(tmp_path):
    init_repository(str(tmp_path), key="ACME", profile="default")
    assert (tmp_path / ".mcp.json").read_text(encoding="utf-8") == _MCP_JSON_BYTES
    assert (tmp_path / ".cursor" / "mcp.json").read_text(encoding="utf-8") == _MCP_JSON_BYTES


# --- Finding 6 (MEDIUM): independent byte anchors for the 4 non-requirement ----
# templates. Existing tests only assert packaged-file == spec-derived render, so
# a coordinated edit of both sources passes silently. These literals are the
# independent anchor: the packaged .md AND the schema-derived render must both
# equal the exact current bytes.

_DECISION_TEMPLATE = (
    "# Title\n\n"
    "## Context\n\n"
    "TODO: describe the situation, constraints, and background.\n\n"
    "<!-- What forces, constraints, or problems led to this decision? -->\n"
    "<!-- What background does a reader need? -->\n\n"
    "## Decision\n\n"
    "TODO: describe the decision that has been made.\n\n"
    "<!-- What was decided? -->\n"
    "<!-- State it as a clear, active choice. -->\n\n"
    "## Consequences\n\n"
    "TODO: describe the expected positive and negative consequences.\n\n"
    "<!-- What becomes easier or harder as a result? -->\n"
    "<!-- What trade-offs are you accepting? -->\n\n"
    "## Status\n\n"
    "Proposed\n\n"
    "<!-- Choose one: Proposed | Accepted | Superseded | Deprecated -->\n"
    "<!-- Is this Proposed, Accepted, Superseded, or Deprecated? -->\n\n"
    "## Category\n\n"
    "Other\n\n"
    "<!-- Choose one: Architecture | Product | Process | Technical | Other -->\n"
    "<!-- Which area: Architecture, Product, Process, Technical, or Other? -->\n\n"
    "## Alternatives Considered\n\n"
    "TODO: describe the options that were considered and why they were not chosen.\n\n"
    "<!-- What other options were weighed? -->\n"
    "<!-- Why were they not chosen? -->\n"
)

_ROADMAP_TEMPLATE = (
    "# Title\n\n"
    "## Outcomes\n\n"
    "TODO: describe the outcomes this roadmap is intended to achieve.\n\n"
    "<!-- What user, business, or operational outcomes matter? -->\n"
    "<!-- Why are these outcomes important now? -->\n\n"
    "## Initiatives\n\n"
    "TODO: describe the major initiatives that support the outcomes.\n\n"
    "<!-- What major bodies of work support these outcomes? -->\n"
    "<!-- How does each initiative connect to an outcome? -->\n\n"
    "## Success Measures\n\n"
    "TODO: describe how progress or success will be measured.\n\n"
    "<!-- How will the team know the roadmap is succeeding? -->\n"
    "<!-- What observable signals would show progress? -->\n\n"
    "## Assumptions\n\n"
    "TODO: describe conditions assumed to be true.\n\n"
    "<!-- What must be true for this roadmap to remain valid? -->\n\n"
    "## Risks\n\n"
    "TODO: describe implementation, delivery, operational, or adoption risks.\n\n"
    "<!-- What could prevent these outcomes from being achieved? -->\n"
)

_PROMPT_TEMPLATE = (
    "# Title\n\n"
    "## Objective\n\n"
    "TODO: describe what this prompt is intended to achieve.\n\n"
    "<!-- What task should this prompt help complete? -->\n"
    "<!-- What outcome should the model produce? -->\n\n"
    "## Input\n\n"
    "TODO: describe the information, context, or source material the prompt expects.\n\n"
    "<!-- What context or source material does the prompt require? -->\n"
    "<!-- What assumptions should the model make about the input? -->\n\n"
    "## Instructions\n\n"
    "TODO: describe the steps, rules, or approach the model should follow.\n\n"
    "<!-- What should the model do first? -->\n"
    "<!-- What process should it follow? -->\n\n"
    "## Output\n\n"
    "TODO: describe the expected response format or result.\n\n"
    "<!-- What should the output contain? -->\n"
    "<!-- Should the response be structured as bullets, JSON, Markdown, or prose? -->\n\n"
    "## Constraints\n\n"
    "TODO: describe any boundaries or restrictions.\n\n"
    "<!-- What should the model avoid? -->\n"
    "<!-- Are there tone, format, safety, or scope constraints? -->\n\n"
    "## Examples\n\n"
    "TODO: provide example inputs and outputs if useful.\n\n"
    "<!-- What examples would make the desired behavior clearer? -->\n\n"
    "## Evaluation\n\n"
    "TODO: describe how the output should be judged.\n\n"
    "<!-- What makes a good response? -->\n"
    "<!-- How can the user tell whether the prompt worked? -->\n"
)

_DESIGN_TEMPLATE = (
    "# Title\n\n"
    "## Context\n\n"
    "TODO: describe the design context and why this design exists.\n\n"
    "<!-- What situation, product area, or user experience does this design address? -->\n"
    "<!-- Why is this design needed now? -->\n\n"
    "## User Need\n\n"
    "TODO: describe who this design is for and what they need to accomplish.\n\n"
    "<!-- Who is the user or audience? -->\n"
    "<!-- What task, pain point, or goal does this design support? -->\n\n"
    "## Design\n\n"
    "TODO: describe the proposed experience, interaction, layout, flow, or system behavior.\n\n"
    "<!-- What is the proposed design? -->\n"
    "<!-- How should the experience work? -->\n\n"
    "## Constraints\n\n"
    "TODO: describe technical, product, accessibility, platform, or implementation constraints.\n\n"
    "<!-- What constraints shape this design? -->\n"
    "<!-- What must the design respect or avoid? -->\n\n"
    "## Rationale\n\n"
    "TODO: explain why this design approach was chosen.\n\n"
    "<!-- Why is this the preferred approach? -->\n"
    "<!-- What trade-offs does this design make? -->\n\n"
    "## Alternatives\n\n"
    "TODO: describe alternatives that were considered.\n\n"
    "<!-- What other approaches were considered? -->\n"
    "<!-- Why were they not chosen? -->\n\n"
    "## Accessibility\n\n"
    "TODO: describe accessibility considerations.\n\n"
    "<!-- What accessibility needs should this design support? -->\n"
    "<!-- Are there keyboard, contrast, readability, or screen-reader considerations? -->\n\n"
    "## Style Guidance\n\n"
    "TODO: describe visual, tone, layout, or interaction style guidance.\n\n"
    "<!-- What visual or interaction style should be followed? -->\n"
    "<!-- What patterns should remain consistent? -->\n\n"
    "## Open Questions\n\n"
    "TODO: list unresolved design questions.\n\n"
    "<!-- What still needs to be decided? -->\n"
    "<!-- What should be validated or explored further? -->\n"
)

_TEMPLATE_BYTES = {
    "decision": _DECISION_TEMPLATE,
    "roadmap": _ROADMAP_TEMPLATE,
    "prompt": _PROMPT_TEMPLATE,
    "design": _DESIGN_TEMPLATE,
}


@pytest.mark.parametrize("name", sorted(_TEMPLATE_BYTES))
def test_packaged_template_bytes_are_independently_anchored(name):
    assert load_template(name) == _TEMPLATE_BYTES[name]


@pytest.mark.parametrize("name", sorted(_TEMPLATE_BYTES))
def test_schema_derived_template_render_bytes_are_independently_anchored(name):
    ref = schema_reference(name)
    assert ref is not None
    assert render_schema_template(ref) == _TEMPLATE_BYTES[name]


# --- Finding 7 (MEDIUM): `rac inspect <file>` human layout --------------------


def test_cli_inspect_single_file_human_exact(capsys, monkeypatch):
    # Plain output (no ANSI): pins the Confidence line format, the Present/
    # Missing Sections headers, the ✓/✗ markers, and Title-case section names.
    monkeypatch.setattr("rac.output.human._USE_COLOR", False)
    assert main(["inspect", fixture_path("inspect", "requirement.md")]) == 0
    assert capsys.readouterr().out == (
        "Artifact Type: Requirement\n"
        "Confidence: 71%\n"
        "\n"
        "Present Sections:\n"
        "  ✓ Problem\n"
        "  ✓ Requirements\n"
        "  ✓ Success Metrics\n"
        "\n"
        "Missing Sections:\n"
        "  ✗ Risks\n"
        "  ✗ Assumptions\n"
    )


# --- Finding 8 (LOW): `rac inspect <dir>` lists every type, even at zero -------


def test_cli_inspect_directory_human_exact(capsys, monkeypatch):
    monkeypatch.setattr("rac.output.human._USE_COLOR", False)
    assert main(["inspect", fixture_path("inspect")]) == 0
    assert capsys.readouterr().out == (
        "Files Inspected: 4\n"
        "\n"
        "Requirements: 2\n"
        "Decisions: 1\n"
        "Roadmaps: 0\n"
        "Prompts: 0\n"
        "Designs: 0\n"
        "Unknown: 1\n"
    )
