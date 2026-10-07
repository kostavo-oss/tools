"""The command: what it is asked, and what it starts."""

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

    monkeypatch.setattr(app, "_page", page)

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
        ["--read-only"],
    )
    assert started("--profile=prod")[-2] == ("page", "prod", [])


def test_the_flags_of_the_page_reach_it(started):
    assert started("--read-only", "--no-open")[0] == (
        "page",
        None,
        ["--no-open", "--read-only"],
    )


def test_page_still_says_the_page_from_when_it_was_not_the_default(started):
    assert started("--page", "prod")[0] == ("page", "prod", ["--page"])


def test_the_terminal_version_is_not_in_caland_and_it_says_where_it_is(started, capsys):
    assert started("--tui") == [("exit", 2)]
    said = capsys.readouterr().err
    assert "no terminal version in caland" in said and "uvx isolinear" in said
    assert started("--tui", "prod", "--read-only")[-1] == ("exit", 2)


def test_caland_installs_one_command_and_none_under_another_name():
    from importlib.metadata import entry_points

    scripts = {
        script.name: script.value
        for script in entry_points(group="console_scripts")
        if script.value.startswith("caland.")
    }
    assert scripts == {"caland": "caland.app:main"}


def test_nothing_of_the_terminal_version_is_left_to_import():
    import importlib.util

    for gone in ("textual", "caland.formerly", "caland.interface.screens"):
        if gone == "textual":
            import importlib.metadata as metadata

            needs = " ".join(metadata.requires("caland") or [])
            assert "textual" not in needs
        else:
            assert importlib.util.find_spec(gone) is None


def test_a_profile_with_no_name_is_said_and_nothing_starts(started, capsys):
    assert started("--profile") == [("exit", 2)]
    assert "needs a workspace name" in capsys.readouterr().err
    assert started("--profile", "--read-only")[-1] == ("exit", 2)
    assert started("--profile=")[-1] == ("exit", 2)


@pytest.mark.parametrize(
    "args",
    [
        ["--readonly", "prod"],  # meant: change nothing. Must not open prod to change
        ["--read_only"],
        ["-r"],
        ["--page", "--readonly"],
        ["--no-browser"],
        ["--profile", "prod", "--bogus"],
    ],
)
def test_an_option_that_is_not_one_is_refused_and_nothing_starts(started, capsys, args):
    assert started(*args) == [("exit", 2)]
    assert "there is no option" in capsys.readouterr().err


@pytest.mark.parametrize("args", [["dev", "prod"], ["prod", "--profile", "dev"]])
def test_one_workspace_at_a_time(started, capsys, args):
    assert started(*args) == [("exit", 2)]
    assert "one workspace at a time" in capsys.readouterr().err


def test_help_says_what_caland_is_now(started, capsys):
    assert started("--help") == []
    out = capsys.readouterr().out
    assert "usage: caland [WORKSPACE]" in out and "page" in out
    assert "TUI" not in out and "--tui" not in out


def test_help_lists_every_option_there_is_but_the_one_kept_for_old_command_lines(
    started, capsys
):
    assert started("-h") == []
    out = capsys.readouterr().out
    for option in ("--profile NAME", "--read-only", "--no-open"):
        assert option in out
    assert "  -V, --version  " in out and "  -h, --help  " in out
    # `--page` is taken, and does nothing: it is from before the page was all there is
    assert "--page" not in out
    # read-only is about the workspace: settings and a profile may still be written here
    assert "change nothing in the workspace" in out


def test_the_short_options_do_what_the_long_ones_do(started, capsys):
    from importlib.metadata import version

    assert started("-V") == []
    assert capsys.readouterr().out == f"caland {version('caland')}\n"
    assert started("--version") == []
    assert capsys.readouterr().out == f"caland {version('caland')}\n"
