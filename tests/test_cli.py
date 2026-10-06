"""The command: the page by default, the terminal version when asked for."""

from __future__ import annotations

import sys

import pytest

from caland import app


@pytest.fixture
def started(monkeypatch):
    """What `caland …` starts, without starting it."""
    seen: list[tuple] = []

    def page(profile, args):
        seen.append(("page", profile, sorted(a for a in args if a.startswith("--"))))
        return 0

    class Terminal:
        def __init__(self, **kwargs):
            seen.append(("tui", kwargs["profile"], kwargs["read_only"]))

        def run(self):
            seen.append(("ran",))

    monkeypatch.setattr(app, "_page", page)
    monkeypatch.setattr(app, "CalandApp", Terminal)

    def run(*args: str) -> list[tuple]:
        monkeypatch.setattr(sys, "argv", ["caland", *args])
        try:
            app.main()
        except SystemExit as stop:
            seen.append(("exit", stop.code))
        return seen

    return run


def test_caland_is_the_page(started):
    assert started() == [("page", None, []), ("exit", 0)]


def test_a_workspace_by_name_or_as_a_profile(started):
    assert started("prod")[0] == ("page", "prod", [])


def test_a_profile_by_its_flag(started):
    assert started("--profile", "prod", "--read-only")[0] == (
        "page",
        "prod",
        ["--profile", "--read-only"],
    )


def test_the_flags_of_the_page_reach_it(started):
    assert started("--read-only", "--no-open")[0] == (
        "page",
        None,
        ["--no-open", "--read-only"],
    )


def test_page_still_says_the_page_from_when_it_was_not_the_default(started):
    assert started("--page", "prod")[0] == ("page", "prod", ["--page"])


def test_tui_is_the_terminal_version_and_nothing_else_is(started):
    assert started("--tui") == [("tui", None, False), ("ran",)]


def test_the_terminal_version_takes_a_workspace_and_read_only(started):
    assert started("--tui", "prod", "--read-only") == [("tui", "prod", True), ("ran",)]


def test_a_profile_with_no_name_is_said_and_nothing_starts(started, capsys):
    assert started("--profile") == [("exit", 2)]
    assert "needs a workspace name" in capsys.readouterr().err


def test_help_says_what_caland_is_now(started, capsys):
    assert started("--help") == []
    out = capsys.readouterr().out
    assert "usage: caland [WORKSPACE]" in out and "--tui" in out and "page" in out
    assert "TUI" not in out
