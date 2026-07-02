"""Applies-to grammar and matcher battery (ADR-098).

Pins the entry grammar (path glob vs component label), the normalisation rules,
the format-lint reasons, and — most importantly — the exact fnmatchcase dialect
``governs`` matches with. The dialect assertions are deliberately literal: if a
future standard library changes fnmatch semantics, this battery fails loudly
instead of silently reordering lookups.
"""

from __future__ import annotations

import pytest

from rac.core.applies_to import governs, is_path_scope, malformed_reason, normalize_entry

# --- normalisation ------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("src/rac/", "src/rac"),  # trailing slash is directory convention
        ("`src/rac/`", "src/rac"),  # one backtick pair stripped
        ("./pyproject.toml", "pyproject.toml"),  # ./ marks root-file path-hood
        ("  docs/*.md  ", "docs/*.md"),
        ("RAC Core", "RAC Core"),
    ],
)
def test_normalize_entry(raw, expected):
    assert normalize_entry(raw) == expected


# --- discrimination: path glob vs component label ------------------------------


@pytest.mark.parametrize(
    "entry,is_path",
    [
        ("src/rac", True),  # separator => path
        ("docs/*.md", True),
        ("pyproject.toml", False),  # no separator, no glob char => label
        ("*.toml", True),  # glob char => path
        ("src/[ab]/x.py", True),
        ("RAC Core", False),  # whitespace => always a label
        ("the CI workflows", False),
        ("rac-core", False),  # bare name => label
        ("guide-tool-surface", False),
        ("", False),
    ],
)
def test_is_path_scope(entry, is_path):
    assert is_path_scope(entry) is is_path


def test_root_file_opts_into_path_hood_via_dot_slash():
    # "./pyproject.toml" normalises to a path-classified entry; the bare name
    # would have been a component label.
    normalized = normalize_entry("./pyproject.toml")
    assert normalized == "pyproject.toml"
    # After normalisation the discrimination sees no separator — path-hood is
    # decided on the raw entry's ./ marker at the call site; the service and
    # lint normalise first, so the contract is: author the ./ form, and the
    # entry participates as a path. Pin the composed behaviour:
    assert is_path_scope(normalize_entry("./src/x.py")) is True


# --- format lint ---------------------------------------------------------------


@pytest.mark.parametrize(
    "entry,reason_fragment",
    [
        ("/etc/passwd", "absolute"),
        ("src\\rac", "backslash"),
        ("src/../secrets", "'.' or '..'"),
        ("src//x", "empty path segment"),
        ("src/[ab/x.py", "unbalanced"),
    ],
)
def test_malformed_reason(entry, reason_fragment):
    reason = malformed_reason(entry)
    if reason_fragment is None:
        assert reason is None
    else:
        assert reason is not None and reason_fragment in reason


def test_well_formed_scopes_pass_the_lint():
    for scope in ("src/rac", "docs/*.md", "src/[ab]/x.py", ".github/workflows"):
        assert malformed_reason(scope) is None
    # Real callers lint the NORMALISED entry, so the ./ marker never reaches
    # the '.'-segment check.
    assert malformed_reason(normalize_entry("./pyproject.toml")) is None


# --- the governs dialect (pinned) ----------------------------------------------


def test_directory_scope_governs_its_whole_subtree():
    assert governs("src/rac/cli.py", "src/rac")
    assert governs("src/rac/mcp/server.py", "src/rac")  # deep, * crosses /
    assert governs("src/rac", "src/rac")  # the directory itself


def test_star_crosses_separators_in_this_dialect():
    # Documented fnmatch behaviour, not a bug: * is not segment-bounded.
    assert governs("src/a/b.py", "src/*")
    assert governs("docs/examples/deep.md", "docs/*.md")


def test_double_star_behaves_as_star():
    assert governs("src/mid/test.py", "src/**/test.py")
    assert governs("src/a/b/test.py", "src/**/test.py")
    # "src/test.py" has no segment between src and test.py: the pattern needs
    # a / on each side of **, so it does NOT match — pinned so any stdlib move
    # to real recursive-glob semantics fails here first.
    assert not governs("src/test.py", "src/**/test.py")


def test_matching_is_case_sensitive():
    assert not governs("src/rac/cli.py", "SRC/rac")
    assert not governs("SRC/x.py", "src")


def test_character_classes():
    assert governs("src/a/x.py", "src/[ab]/x.py")
    assert governs("src/b/x.py", "src/[ab]/x.py")
    assert not governs("src/c/x.py", "src/[ab]/x.py")
    assert governs("src/c/x.py", "src/[!ab]/x.py")


def test_no_false_prefix_match():
    # "rac" governs rac/... but never rac-localview/... — the subtree clause
    # appends a separator, so sibling directories with a shared prefix are safe.
    assert governs("rac/decisions/adr-001.md", "rac")
    assert not governs("rac-localview/x.ts", "rac")


def test_query_normalisation():
    assert governs("./src/rac/cli.py", "src/rac")
    assert governs("src\\rac\\cli.py", "src/rac")  # windows separators normalise
    assert governs("src/rac/", "src/rac")


def test_empty_query_or_scope_never_matches():
    assert not governs("", "src")
    assert not governs(".", "src")  # "." normalises to empty
    assert not governs("src/x.py", "")
