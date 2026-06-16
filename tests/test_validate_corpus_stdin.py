"""Tests for corpus-aware stdin validation — `rac validate - --corpus DIR`.

The engine seam behind the generated Claude Code `PreToolUse` pre-edit hook
(v0.21.17, ADR-067): a proposed document piped on stdin is validated
structurally *and* has its outbound references resolved against the live corpus,
so a reference to a retired (superseded) or missing decision is blocked
pre-write. Structural-only enforcement, deterministic and offline — no semantic
verdict (ADR-067).

Each corpus is built in ``tmp_path`` so the cases are self-contained and the
boundary behaviour (usage errors, identifier collision, no-regression) is pinned.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

from rac.cli import main
from rac.core.markdown import parse
from rac.services.validate import validate_stdin_against_corpus

# --- corpus + document builders ----------------------------------------------

# Decisions are identified by their filename stem (legacy identity, no
# frontmatter id) so references resolve as the canonical human-readable form
# (e.g. ``adr-001-live``) without depending on Crockford-base32 ID generation.
_LIVE_DECISION = """\
---
schema_version: 1
type: decision
---
# A Live Decision

## Context

Context for the decision.

## Decision

We decide a thing.

## Consequences

Consequences follow.

## Status

Accepted

## Category

Architecture
"""

_RETIRED_DECISION = """\
---
schema_version: 1
type: decision
---
# A Retired Decision

## Context

Context for the retired decision.

## Decision

We decided a thing, since superseded.

## Consequences

History.

## Status

Superseded

## Category

Architecture
"""

_ROADMAP = """\
---
schema_version: 1
type: roadmap
---
# A Proposed Roadmap

## Status

Planned

## Context

We plan work.

## Outcomes

- A good outcome.

## Initiatives

### Initiative 1

Do the thing.

## Related Decisions

- {ref}
"""


def _build_corpus(tmp_path: Path) -> str:
    """A minimal corpus: one live decision and one retired one.

    Each decision is identified by its filename stem (``adr-001-live``,
    ``adr-002-retired``), so a proposed document references them by that name.
    """
    decisions = tmp_path / "decisions"
    decisions.mkdir()
    (decisions / "adr-001-live.md").write_text(_LIVE_DECISION, encoding="utf-8")
    (decisions / "adr-002-retired.md").write_text(_RETIRED_DECISION, encoding="utf-8")
    return str(tmp_path)


def _run(argv: list[str], stdin: str = "", monkeypatch=None) -> tuple[int, str, str]:
    """Run ``rac`` with ``stdin`` piped, returning ``(exit_code, stdout, stderr)``.

    Usage-error paths raise ``SystemExit`` rather than returning their code, so
    the exit status is normalised here whichever way the CLI signals it.
    """
    out, err = io.StringIO(), io.StringIO()
    monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
    monkeypatch.setattr("sys.stdout", out)
    monkeypatch.setattr("sys.stderr", err)
    try:
        code = main(argv)
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
    return code, out.getvalue(), err.getvalue()


# --- the engine service ------------------------------------------------------


def test_clean_reference_to_live_decision_passes(tmp_path):
    corpus = _build_corpus(tmp_path)
    product = parse(_ROADMAP.format(ref="adr-001-live"), source_path="-")
    result = validate_stdin_against_corpus(product, corpus)
    assert result.ok
    assert result.relationship_issues == []


def test_reference_to_retired_decision_is_blocked(tmp_path):
    corpus = _build_corpus(tmp_path)
    product = parse(_ROADMAP.format(ref="adr-002-retired"), source_path="-")
    result = validate_stdin_against_corpus(product, corpus)
    assert not result.ok
    codes = {i.code for i in result.relationship_issues}
    assert "relationship-target-superseded" in codes


def test_reference_to_missing_decision_is_blocked(tmp_path):
    corpus = _build_corpus(tmp_path)
    product = parse(_ROADMAP.format(ref="adr-999-missing"), source_path="-")
    result = validate_stdin_against_corpus(product, corpus)
    assert not result.ok
    codes = {i.code for i in result.relationship_issues}
    assert "relationship-target-not-found" in codes


def test_only_proposed_documents_own_findings_surface(tmp_path):
    """Pre-existing corpus issues are not the pre-edit hook's concern.

    The retired decision in the corpus is itself a danging-retirement the corpus
    may flag, but a *clean* proposed document referencing only the live decision
    must report nothing — the result is scoped to what the edit introduces.
    """
    corpus = _build_corpus(tmp_path)
    product = parse(_ROADMAP.format(ref="adr-001-live"), source_path="-")
    result = validate_stdin_against_corpus(product, corpus)
    assert all(i.source_path == "-" for i in result.relationship_issues)
    assert result.relationship_issues == []


# --- the CLI surface ---------------------------------------------------------


def test_cli_retired_reference_exits_one_with_finding(tmp_path, monkeypatch):
    corpus = _build_corpus(tmp_path)
    doc = _ROADMAP.format(ref="adr-002-retired")
    code, out, _ = _run(["validate", "-", "--corpus", corpus, "--json"], doc, monkeypatch)
    assert code == 1
    payload = json.loads(out)
    assert payload["valid"] is False
    codes = {i["code"] for i in payload["relationship_issues"]}
    assert "relationship-target-superseded" in codes


def test_cli_missing_reference_exits_one(tmp_path, monkeypatch):
    corpus = _build_corpus(tmp_path)
    doc = _ROADMAP.format(ref="adr-999-missing")
    code, out, _ = _run(["validate", "-", "--corpus", corpus, "--json"], doc, monkeypatch)
    assert code == 1
    codes = {i["code"] for i in json.loads(out)["relationship_issues"]}
    assert "relationship-target-not-found" in codes


def test_cli_clean_document_exits_zero(tmp_path, monkeypatch):
    corpus = _build_corpus(tmp_path)
    doc = _ROADMAP.format(ref="adr-001-live")
    code, out, _ = _run(["validate", "-", "--corpus", corpus, "--json"], doc, monkeypatch)
    assert code == 0
    payload = json.loads(out)
    assert payload["valid"] is True
    assert payload["relationship_issues"] == []


def test_cli_structurally_invalid_blocks_even_without_finding(tmp_path, monkeypatch):
    """A structurally broken proposed document fails the corpus run too.

    The structural and relationship finding sets are combined: a missing required
    section is an error regardless of whether any reference is broken.
    """
    corpus = _build_corpus(tmp_path)
    # A well-shaped roadmap with a second top-level title — a type-agnostic
    # structural error (multiple-titles) that does not change classification —
    # referencing a live decision, so the *only* failure is structural. Proves
    # the structural set blocks independently of the reference set.
    doc = _ROADMAP.format(ref="adr-001-live") + "\n# A Second Title\n"
    code, out, _ = _run(["validate", "-", "--corpus", corpus, "--json"], doc, monkeypatch)
    assert code == 1
    payload = json.loads(out)
    assert payload["valid"] is False
    assert any(e["code"] == "multiple-titles" for e in payload["errors"])
    # The reference itself is clean: the failure is purely structural.
    assert payload["relationship_issues"] == []


def test_structurally_invalid_blocks_without_corpus_flag(monkeypatch):
    """No regression: plain `rac validate -` still exits 1 on a structural error."""
    doc = "# Just a title with no required sections\n"
    code, _, _ = _run(["validate", "-"], doc, monkeypatch)
    assert code == 1


def test_clean_document_without_corpus_flag_unchanged(tmp_path, monkeypatch):
    """No regression: without --corpus, references are not resolved at all.

    The same document that fails against the corpus (retired reference) passes
    plain single-file validation, proving --corpus is purely additive.
    """
    doc = _ROADMAP.format(ref="adr-002-retired")
    code, _, _ = _run(["validate", "-"], doc, monkeypatch)
    assert code == 0


# --- boundary / usage --------------------------------------------------------


def test_corpus_with_directory_target_is_usage_error(tmp_path, monkeypatch):
    corpus = _build_corpus(tmp_path)
    code, _, err = _run(["validate", corpus, "--corpus", corpus], "", monkeypatch)
    assert code == 2
    assert "--corpus applies to stdin" in err


def test_corpus_pointing_at_non_directory_is_usage_error(tmp_path, monkeypatch):
    corpus = _build_corpus(tmp_path)
    not_a_dir = str(Path(corpus) / "decisions" / "adr-001-live.md")
    code, _, err = _run(["validate", "-", "--corpus", not_a_dir], "x", monkeypatch)
    assert code == 2
    assert "not a directory" in err


# --- identifier collision (editing an existing artifact) ---------------------


def test_editing_existing_artifact_excludes_on_disk_counterpart(tmp_path, monkeypatch):
    """An edited artifact (matching identity) replaces its on-disk version.

    Documented rule: an identity-bearing proposed document whose canonical
    identifier matches an on-disk artifact has that on-disk counterpart excluded
    from the corpus index, so the edit is validated as a *replacement*. This
    avoids a spurious ``duplicate-artifact-identifier`` and a spurious
    ``relationship-self-reference`` — only the references the edit introduces are
    reported. The edited document carries a ``## ID`` matching the on-disk
    ``adr-001-live`` (filename) identity; under stdin the ``## ID`` is what gives
    the proposed document a stable identity (the path is ``-``). Here it adds a
    reference to the retired decision, which must surface as the one finding.
    """
    corpus = _build_corpus(tmp_path)
    edited = (
        "---\nschema_version: 1\ntype: decision\n---\n"
        "# A Live Decision\n\n"
        "## ID\n\nadr-001-live\n\n"
        "## Context\n\nctx\n\n## Decision\n\ndec\n\n## Consequences\n\ncons\n\n"
        "## Status\n\nAccepted\n\n## Category\n\nArchitecture\n\n"
        "## Related Decisions\n\n- adr-002-retired\n"
    )
    product = parse(edited, source_path="-")
    result = validate_stdin_against_corpus(product, corpus)
    codes = {i.code for i in result.relationship_issues}
    assert "duplicate-artifact-identifier" not in codes
    assert "relationship-self-reference" not in codes
    assert "relationship-target-superseded" in codes


def test_editing_existing_artifact_no_self_reference(tmp_path, monkeypatch):
    """The edited artifact is not flagged against its own excluded counterpart.

    With the on-disk counterpart (``adr-001-live``) excluded and the proposed
    document standing in for it, referencing a *live peer* must be clean: no
    duplicate-identity against the file being edited, no self-reference, no broken
    reference.
    """
    corpus = _build_corpus(tmp_path)
    # Add a second live decision to reference.
    (Path(corpus) / "decisions" / "adr-003-live.md").write_text(_LIVE_DECISION, encoding="utf-8")
    edited = (
        "---\nschema_version: 1\ntype: decision\n---\n"
        "# A Live Decision\n\n"
        "## ID\n\nadr-001-live\n\n"
        "## Context\n\nctx\n\n## Decision\n\ndec\n\n## Consequences\n\ncons\n\n"
        "## Status\n\nAccepted\n\n## Category\n\nArchitecture\n\n"
        "## Related Decisions\n\n- adr-003-live\n"
    )
    product = parse(edited, source_path="-")
    result = validate_stdin_against_corpus(product, corpus)
    assert result.relationship_issues == []
    assert result.ok


def test_new_artifact_no_identity_match_validates_against_full_corpus(tmp_path):
    """A brand-new document matches no on-disk identity; the corpus is unchanged.

    A new roadmap (no frontmatter id, stdin identity ``-``) referencing the
    retired decision is still blocked — exclusion only removes an existing
    counterpart, never a peer the new document points at.
    """
    corpus = _build_corpus(tmp_path)
    product = parse(_ROADMAP.format(ref="adr-002-retired"), source_path="-")
    result = validate_stdin_against_corpus(product, corpus)
    codes = {i.code for i in result.relationship_issues}
    assert "relationship-target-superseded" in codes
