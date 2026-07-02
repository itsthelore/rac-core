"""Path→decisions lookup: service and CLI (ADR-098).

Mirrors ``tests/test_find_decisions.py``: fixture corpus on ``tmp_path``, the
service contract first (liveness filter, scope matching, determinism), then the
``rac decisions`` CLI face (exit codes, JSON shape, byte-determinism). No
``.rac/config.yaml`` is written, so the advisory tree pass never runs here —
the lookup itself needs no repository root.
"""

from __future__ import annotations

import json

import pytest

from rac.cli import main
from rac.services.resolve import decisions_for_path

LIVE_AUTH = """---
schema_version: 1
id: RAC-AVTH00000001
type: decision
---
# Auth module boundaries

## Context

c

## Decision

d

## Consequences

q

## Status

Accepted

## Applies To

- src/auth/
- the login surface
"""

LIVE_DOCS_GLOB = """---
schema_version: 1
id: RAC-D0CS00000001
type: decision
---
# Docs style

## Context

c

## Decision

d

## Consequences

q

## Status

Accepted

## Applies To

- docs/*.md
"""

RETIRED_AUTH = """---
schema_version: 1
id: RAC-RETD00000001
type: decision
---
# Old auth decision

## Context

c

## Decision

d

## Consequences

q

## Status

Superseded

## Applies To

- src/auth/
"""

UNSCOPED = """---
schema_version: 1
id: RAC-VNSC00000001
type: decision
---
# Unscoped decision

## Context

c

## Decision

d

## Consequences

q

## Status

Accepted
"""


@pytest.fixture
def repo(tmp_path):
    d = tmp_path / "rac"
    (d / "decisions").mkdir(parents=True)
    (d / "decisions" / "live-auth.md").write_text(LIVE_AUTH, encoding="utf-8")
    (d / "decisions" / "live-docs.md").write_text(LIVE_DOCS_GLOB, encoding="utf-8")
    (d / "decisions" / "retired-auth.md").write_text(RETIRED_AUTH, encoding="utf-8")
    (d / "decisions" / "unscoped.md").write_text(UNSCOPED, encoding="utf-8")
    return d


# --- service -------------------------------------------------------------------


def test_live_decision_governing_the_path_is_returned(repo):
    result = decisions_for_path(str(repo), "src/auth/login.py")
    assert [m.artifact_id for m in result.matches] == ["RAC-AVTH00000001"]
    match = result.matches[0]
    assert match.status == "Accepted"
    assert match.scopes == ["src/auth/"]  # the declared entry, verbatim evidence
    assert match.title == "Auth module boundaries"


def test_retired_decisions_never_match(repo):
    # RETIRED_AUTH declares the same scope but is Superseded — liveness reuses
    # the agent-rules predicate, so it is filtered out.
    result = decisions_for_path(str(repo), "src/auth/login.py")
    assert "RAC-RETD00000001" not in [m.artifact_id for m in result.matches]


def test_glob_scope_matches(repo):
    result = decisions_for_path(str(repo), "docs/examples/deep.md")
    assert [m.artifact_id for m in result.matches] == ["RAC-D0CS00000001"]


def test_component_labels_never_match(repo):
    # "the login surface" is a component label; a path query never matches it.
    result = decisions_for_path(str(repo), "the login surface")
    assert result.matches == []


def test_unrelated_path_returns_empty(repo):
    result = decisions_for_path(str(repo), "src/billing/invoice.py")
    assert result.matches == []
    assert result.match_count == 0


def test_query_normalisation(repo):
    for query in ("./src/auth/login.py", "src\\auth\\login.py", "src/auth/"):
        result = decisions_for_path(str(repo), query)
        assert [m.artifact_id for m in result.matches] == ["RAC-AVTH00000001"], query


def test_empty_query_matches_nothing(repo):
    assert decisions_for_path(str(repo), "").matches == []
    assert decisions_for_path(str(repo), ".").matches == []


def test_result_is_deterministic(repo):
    first = decisions_for_path(str(repo), "src/auth/login.py").to_dict()
    second = decisions_for_path(str(repo), "src/auth/login.py").to_dict()
    assert first == second


# --- CLI face --------------------------------------------------------------------


def test_cli_human_output_and_exit_zero(repo, capsys):
    rc = main(["decisions", "src/auth/login.py", str(repo)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "RAC-AVTH00000001" in out
    assert "Accepted" in out
    assert "src/auth/" in out


def test_cli_empty_result_is_valid_and_exit_zero(repo, capsys):
    rc = main(["decisions", "src/billing/x.py", str(repo)])
    assert rc == 0
    assert "No live decisions" in capsys.readouterr().out


def test_cli_json_contract(repo, capsys):
    rc = main(["decisions", "src/auth/login.py", str(repo), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == "1"
    assert payload["path"] == "src/auth/login.py"
    assert payload["type"] == "decision"
    assert payload["match_count"] == 1
    match = payload["matches"][0]
    assert match["id"] == "RAC-AVTH00000001"
    assert match["status"] == "Accepted"
    assert match["scopes"] == ["src/auth/"]
    assert set(match) == {"id", "type", "title", "status", "path", "scopes"}


def test_cli_not_a_directory_is_usage_error(tmp_path):
    with pytest.raises(SystemExit) as exc:
        main(["decisions", "src/x.py", str(tmp_path / "nope")])
    assert exc.value.code == 2


def test_cli_empty_path_is_usage_error(repo):
    with pytest.raises(SystemExit) as exc:
        main(["decisions", "", str(repo)])
    assert exc.value.code == 2


def test_cli_output_is_byte_deterministic(repo, capsys):
    main(["decisions", "src/auth/login.py", str(repo), "--json"])
    first = capsys.readouterr().out
    main(["decisions", "src/auth/login.py", str(repo), "--json"])
    assert capsys.readouterr().out == first
