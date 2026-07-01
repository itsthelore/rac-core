"""Tests for the CLI: exit codes and JSON output."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import fixture_path

from rac import __version__
from rac.cli import main

REPO_ROOT = Path(__file__).parent.parent


@pytest.mark.parametrize(
    "argv",
    [
        ["--version"],
        ["validate", "x", "--version"],
        ["diff", "a", "b", "--version"],
        ["stats", "d", "--version"],
        ["ingest", "foo.docx", "--version"],
        ["ingest", "--version"],  # short-circuits before the required `file`
        ["schema", "--version"],
    ],
)
def test_version_flag_on_root_and_subcommands(argv, capsys):
    # --version prints and exits 0 from the root parser and every subcommand,
    # even when other args are present and even when required positionals aren't.
    with pytest.raises(SystemExit) as exc:
        main(argv)
    assert exc.value.code == 0
    assert capsys.readouterr().out.strip() == f"rac {__version__}"


def test_validate_valid_exits_zero(capsys):
    rc = main(["validate", fixture_path("valid", "feature.md")])
    assert rc == 0
    assert "PASS" in capsys.readouterr().out


def test_validate_invalid_exits_one(capsys):
    rc = main(["validate", fixture_path("invalid", "duplicate_ids.md")])
    assert rc == 1
    out = capsys.readouterr().out
    assert "FAIL" in out
    assert "duplicate-req-id" in out


def test_validate_missing_file_exits_two():
    with pytest.raises(SystemExit) as exc:
        main(["validate", fixture_path("valid", "does_not_exist.md")])
    assert exc.value.code == 2


def test_validate_json_shape(capsys):
    rc = main(["validate", fixture_path("invalid", "malformed_id.md"), "--json"])
    assert rc == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["valid"] is False
    assert {"file", "valid", "errors", "warnings"} <= payload.keys()
    assert any(e["code"] == "malformed-req-id" for e in payload["errors"])


def test_diff_exits_zero_and_reports(capsys):
    rc = main(["diff", fixture_path("diff", "old.md"), fixture_path("diff", "new.md")])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Added Requirements" in out
    assert "REQ-004" in out
    assert "Before:" in out and "After:" in out  # modified-requirement format


def test_diff_json_shape(capsys):
    rc = main(
        [
            "diff",
            fixture_path("diff", "old.md"),
            fixture_path("diff", "new.md"),
            "--json",
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert [r["id"] for r in payload["added_requirements"]] == ["REQ-004"]
    assert [r["id"] for r in payload["removed_requirements"]] == ["REQ-003"]
    assert [c["id"] for c in payload["modified_requirements"]] == ["REQ-002"]


def test_broken_pipe_exits_quietly():
    # A downstream consumer closing the pipe early (`rac export … | head`) must
    # not dump a BrokenPipeError traceback: stderr stays clean, the process
    # exits non-zero without "Exception ignored" shutdown noise. Runs in a
    # subprocess because EPIPE only occurs on a real OS pipe.
    proc = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "from rac.cli import main; raise SystemExit(main(['export', 'rac', '--json']))",
        ],
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert proc.stdout is not None and proc.stderr is not None
    proc.stdout.read(1024)  # consume a little, like `head`
    proc.stdout.close()  # then hang up
    stderr = proc.stderr.read().decode(errors="replace")
    proc.stderr.close()
    rc = proc.wait()
    assert rc == 1
    assert "Traceback" not in stderr
    assert "BrokenPipeError" not in stderr
