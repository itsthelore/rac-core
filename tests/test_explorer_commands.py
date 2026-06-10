"""Tests for the Explorer command registry and routing (v0.8.1).

Pure unit tests — no Textual, no repository. The `/` surface's contract:
one registry, search as the fallback route, teaching examples for empty
input (DESIGN-command-surface).
"""

from __future__ import annotations

from rac.explorer.commands import EXAMPLES, REGISTRY, SEARCH, parse, suggestions


def test_registry_is_the_v082_contract():
    assert [spec.name for spec in REGISTRY] == [
        "open",
        "find",
        "browse",
        "health",
        "home",
        "help",
        "quit",
    ]
    assert all(spec.usage and spec.summary for spec in REGISTRY)


def test_health_is_discoverable():
    assert "health" in {spec.name for spec in REGISTRY}
    assert parse("health").command == "health"
    assert parse("/health").command == "health"


def test_registered_command_routes_with_args():
    invocation = parse("open req-001")
    assert invocation.command == "open"
    assert invocation.args == "req-001"


def test_leading_slash_and_case_are_tolerated():
    assert parse("/Open REQ-001").command == "open"
    assert parse("/Open REQ-001").args == "REQ-001"


def test_unregistered_input_is_a_search():
    invocation = parse("payments retry logic")
    assert invocation.command == SEARCH
    assert invocation.args == "payments retry logic"


def test_command_name_inside_text_does_not_route():
    # Only the first word routes; "the open question" is a search.
    assert parse("the open question").command == SEARCH


def test_empty_input_is_an_empty_search():
    invocation = parse("   ")
    assert invocation.command == SEARCH
    assert invocation.args == ""


def test_suggestions_prefix_match_on_first_word():
    assert [s.name for s in suggestions("o")] == ["open"]
    assert [s.name for s in suggestions("h")] == ["health", "home", "help"]
    assert [s.name for s in suggestions("he")] == ["health", "help"]
    assert suggestions("zzz") == ()
    assert [s.name for s in suggestions("")] == [s.name for s in REGISTRY]


def test_examples_teach_registered_workflows():
    assert EXAMPLES
    for example in EXAMPLES:
        routed = parse(example)
        assert routed.command in {spec.name for spec in REGISTRY} | {SEARCH}
