"""Characterization pins for exit codes and error-path messages (rebuild).

RAC's exit code is part of its automation contract: 0 = clean, 1 = a
recognized-but-failing corpus, 2 = a usage/IO error (argparse or a missing
file). Several of these paths are exercised by no golden. The rebuild could
easily collapse a "return 1" into a "raise SystemExit(2)" (or vice versa) or
reword a stderr message without any byte-golden noticing.

These tests pin, per invocation: whether ``main`` returns the code or raises
``SystemExit`` with it, and the exact stderr text of the human-facing error
paths. One notable pinned behavior: ``validate --json`` on a missing file still
prints a plain error to stderr and exits 2 — it does *not* emit a JSON error
envelope.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from rac.cli import main

REPO_ROOT = Path(__file__).parent.parent


def _invoke(argv, capsys, monkeypatch):
    """Run ``main`` and normalize both exit conventions to (kind, code, out, err)."""
    monkeypatch.chdir(REPO_ROOT)
    monkeypatch.setattr("rac.output.human._USE_COLOR", False)
    try:
        code = main(argv)
        kind = "return"
    except SystemExit as exc:  # argparse and hard IO errors exit(2)
        code = exc.code
        kind = "exit"
    captured = capsys.readouterr()
    return kind, code, captured.out, captured.err


# --- exit-code map -----------------------------------------------------------

# (argv, kind, code). "return" means main returned the code; "exit" means it
# raised SystemExit(code).
EXIT_CASES = [
    (["gate", "tests/fixtures/valid"], "return", 0),
    (["gate", "tests/fixtures/portfolio"], "return", 1),
    (["gate", "tests/fixtures/portfolio", "--sarif"], "return", 1),
    (["coverage", "tests/fixtures/portfolio_summary/all_types"], "return", 0),
    (["index", "tests/fixtures/portfolio_summary/all_types"], "return", 0),
    (["portfolio", "tests/fixtures/portfolio_summary/all_types"], "return", 0),
    (["resolve", "RAC-ZZZZZZZZZZZZ", "tests/fixtures/resolve"], "return", 1),
    (["validate", "/nope/does-not-exist.md"], "exit", 2),
    (["validate", "/nope/does-not-exist.md", "--json"], "exit", 2),
    (["not-a-command"], "exit", 2),
    ([], "exit", 2),
]


@pytest.mark.parametrize(
    "argv,kind,code",
    EXIT_CASES,
    ids=["/".join(c[0]) or "<no-args>" for c in EXIT_CASES],
)
def test_exit_code_and_convention(argv, kind, code, capsys, monkeypatch):
    got_kind, got_code, _out, _err = _invoke(argv, capsys, monkeypatch)
    assert (got_kind, got_code) == (kind, code)


# --- empty-corpus exit codes (a rebuild edge that must stay non-failing) ------


def test_empty_corpus_commands_exit_zero(tmp_path, capsys, monkeypatch):
    empty = tmp_path / "empty"
    empty.mkdir()
    for argv in (
        ["index", str(empty), "--json"],
        ["stats", str(empty)],
        ["portfolio", str(empty), "--json"],
        ["coverage", str(empty), "--json"],
    ):
        kind, code, _out, _err = _invoke(argv, capsys, monkeypatch)
        assert (kind, code) == ("return", 0), argv


# --- error-path stderr messages ----------------------------------------------


def test_missing_file_error_message(capsys, monkeypatch):
    _kind, _code, out, err = _invoke(["validate", "/nope/does-not-exist.md"], capsys, monkeypatch)
    assert out == ""
    assert err == "rac: file not found: /nope/does-not-exist.md\n"


def test_missing_file_json_flag_still_plain_error(capsys, monkeypatch):
    # --json does NOT convert a missing-file failure into a JSON envelope.
    _kind, _code, out, err = _invoke(
        ["validate", "/nope/does-not-exist.md", "--json"], capsys, monkeypatch
    )
    assert out == ""
    assert err == "rac: file not found: /nope/does-not-exist.md\n"


def test_resolve_not_found_error_message(capsys, monkeypatch):
    _kind, _code, out, err = _invoke(
        ["resolve", "RAC-ZZZZZZZZZZZZ", "tests/fixtures/resolve"], capsys, monkeypatch
    )
    assert out == ""
    assert err == "rac: artifact not found: RAC-ZZZZZZZZZZZZ\n"


def test_unknown_subcommand_reports_invalid_choice(capsys, monkeypatch):
    _kind, _code, _out, err = _invoke(["not-a-command"], capsys, monkeypatch)
    assert "invalid choice: 'not-a-command'" in err
