"""Tests for rac.core.hooks, rac.services.hook, and the `rac hook` CLI (v0.13.4).

Pins the bundled git-hook contract: each hook ships as a package resource,
`rac hook install` writes the selected style into `.git/hooks/<style>`
(executable) without ever overwriting, `rac hook list` enumerates the bundle,
and exit codes follow the standard convention (0 installed/listed, 1 refused
or operational error, 2 bad path or no .git directory). One functional test
exercises the installed post-commit hook end to end.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path

import pytest

from rac.cli import main
from rac.core.hooks import (
    BUNDLED_HOOKS,
    DEFAULT_STYLE,
    HookNotFound,
    HookResourceMissing,
    available_hooks,
    hook_specs,
    load_hook,
)
from rac.services.hook import HookFileExists, NotAGitWorkTree, install_hook

HOOK_STYLES = ["post-commit", "pre-commit"]


def _git(repo: Path, *args: str, when: str | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    if when is not None:
        env["GIT_AUTHOR_DATE"] = when
        env["GIT_COMMITTER_DATE"] = when
    return subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "--quiet", "--initial-branch=main")
    return tmp_path


# --- registry ----------------------------------------------------------------


def test_registry_lists_bundled_hooks_in_order():
    assert available_hooks() == HOOK_STYLES
    assert DEFAULT_STYLE == "post-commit"


def test_every_bundled_hook_has_a_one_line_description():
    for spec in hook_specs():
        assert spec.description
        assert "\n" not in spec.description


def test_unknown_style_raises_hook_not_found():
    with pytest.raises(HookNotFound, match="unknown hook style: nope"):
        load_hook("nope")


def test_missing_resource_raises_hook_resource_missing(monkeypatch):
    from rac.core import hooks as core_hooks

    ghost = core_hooks.HookSpec(style="ghost-commit", description="No resource ships.")
    monkeypatch.setattr(core_hooks, "BUNDLED_HOOKS", (*BUNDLED_HOOKS, ghost))
    with pytest.raises(HookResourceMissing, match="packaged hook missing: ghost-commit"):
        core_hooks.load_hook("ghost-commit")


@pytest.mark.parametrize("style", HOOK_STYLES)
def test_packaged_hook_loads_and_is_a_shell_script(style):
    content = load_hook(style)
    assert content == load_hook(style)  # deterministic
    assert content.decode("utf-8").startswith("#!/bin/sh")


# --- service -----------------------------------------------------------------


def test_install_writes_executable_hook(repo):
    installed = install_hook(str(repo))
    dest = repo / ".git" / "hooks" / "post-commit"
    assert dest.read_bytes() == load_hook("post-commit")
    assert installed.path == str(dest)
    assert installed.bytes_written == len(dest.read_bytes())
    assert dest.stat().st_mode & stat.S_IXUSR  # executable


def test_install_pre_commit_style(repo):
    installed = install_hook(str(repo), "pre-commit")
    assert installed.style == "pre-commit"
    assert (repo / ".git" / "hooks" / "pre-commit").read_bytes() == load_hook("pre-commit")


def test_install_never_overwrites(repo):
    dest = repo / ".git" / "hooks" / "post-commit"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("existing hook", encoding="utf-8")
    with pytest.raises(HookFileExists, match="never overwrites"):
        install_hook(str(repo))
    assert dest.read_text(encoding="utf-8") == "existing hook"


def test_install_outside_git_repo_raises(tmp_path):
    with pytest.raises(NotAGitWorkTree, match="no .git directory"):
        install_hook(str(tmp_path))


def test_install_unknown_style_raises(repo):
    with pytest.raises(HookNotFound):
        install_hook(str(repo), "nope")


def test_installation_json_contract(repo):
    installed = install_hook(str(repo))
    assert installed.to_dict() == {
        "schema_version": "1",
        "installed": True,
        "hook": {"style": "post-commit", "path": str(repo / ".git" / "hooks" / "post-commit")},
    }


# --- CLI ----------------------------------------------------------------------


def test_cli_install_default_post_commit(repo, capsys):
    rc = main(["hook", "install", "--dir", str(repo)])
    assert rc == 0
    assert (repo / ".git" / "hooks" / "post-commit").is_file()
    assert "Installed post-commit git hook" in capsys.readouterr().out


def test_cli_install_json(repo, capsys):
    rc = main(["hook", "install", "--dir", str(repo), "--style", "pre-commit", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["installed"] is True
    assert payload["hook"]["style"] == "pre-commit"


def test_cli_second_install_exits_1_untouched(repo, capsys):
    assert main(["hook", "install", "--dir", str(repo)]) == 0
    before = (repo / ".git" / "hooks" / "post-commit").read_bytes()
    rc = main(["hook", "install", "--dir", str(repo)])
    assert rc == 1
    assert "never overwrites" in capsys.readouterr().err
    assert (repo / ".git" / "hooks" / "post-commit").read_bytes() == before


def test_cli_install_outside_git_exits_2(tmp_path, capsys):
    rc_exc = None
    with pytest.raises(SystemExit) as exc:
        main(["hook", "install", "--dir", str(tmp_path)])
    rc_exc = exc.value.code
    assert rc_exc == 2
    assert "no .git directory" in capsys.readouterr().err


def test_cli_install_bad_dir_exits_2(tmp_path, capsys):
    with pytest.raises(SystemExit) as exc:
        main(["hook", "install", "--dir", str(tmp_path / "nope")])
    assert exc.value.code == 2
    assert "not a directory" in capsys.readouterr().err


def test_cli_unknown_style_exits_2(repo, capsys):
    # argparse rejects an unregistered --style before the handler runs.
    with pytest.raises(SystemExit) as exc:
        main(["hook", "install", "--dir", str(repo), "--style", "nope"])
    assert exc.value.code == 2


def test_cli_hook_list_human(capsys):
    rc = main(["hook", "list"])
    assert rc == 0
    out = capsys.readouterr().out
    for spec in hook_specs():
        assert spec.style in out
        assert spec.description in out


def test_cli_hook_list_json(capsys):
    rc = main(["hook", "list", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "schema_version": "1",
        "hooks": [{"style": spec.style, "description": spec.description} for spec in hook_specs()],
    }


# --- functional: the installed post-commit hook nudges, never blocks ---------


def test_post_commit_hook_is_advisory_and_runs(repo):
    # A corpus committed long ago, then the hook installed; a later commit must
    # succeed (advisory) and print the cadence nudge.
    corpus = repo / "rac" / "requirements"
    corpus.mkdir(parents=True)
    (corpus / "a.md").write_text(
        "# A\n\n## Problem\n\np\n\n## Requirements\n\n[REQ-001] x\n", encoding="utf-8"
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "--quiet", "-m", "old corpus", when="2020-01-01T00:00:00+00:00")

    install_hook(str(repo))

    (repo / "note.txt").write_text("trigger a commit\n", encoding="utf-8")
    _git(repo, "add", ".")
    # The commit must succeed despite the stale corpus (post-commit is advisory).
    result = _git(repo, "commit", "--quiet", "-m", "another commit")
    assert "No product knowledge recorded" in (result.stdout + result.stderr)
