"""The Python package exposes only a native AsDecided launcher."""

from __future__ import annotations

import sys

import pytest

from asdecided import dispatch


def test_decided_execs_native_binary(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[tuple[str, list[str]]] = []
    monkeypatch.setattr(sys, "argv", ["decided", "validate", "decisions/"])
    monkeypatch.setattr(dispatch, "_binary_path", lambda name: f"/bin/{name}")
    monkeypatch.setattr(dispatch, "_exec", lambda binary, argv: called.append((binary, argv)))

    dispatch.main()

    assert called == [("/bin/decided", ["validate", "decisions/"])]


def test_mcp_routes_directly_to_native_server(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[tuple[str, list[str]]] = []
    monkeypatch.setattr(sys, "argv", ["decided", "mcp", "--root", "."])
    monkeypatch.setattr(dispatch, "_binary_path", lambda name: f"/bin/{name}")
    monkeypatch.setattr(dispatch, "_exec", lambda binary, argv: called.append((binary, argv)))

    dispatch.main()

    assert called == [("/bin/decided-mcp", ["--root", "."])]


def test_missing_native_binary_has_no_python_fallback(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["decided", "validate", "decisions/"])
    monkeypatch.setattr(dispatch, "_binary_path", lambda _name: None)

    with pytest.raises(SystemExit) as raised:
        dispatch.main()

    assert raised.value.code == 2
    assert "no bundled 'decided' binary" in capsys.readouterr().err
