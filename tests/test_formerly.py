"""What still answers to the name caland had before: isolinear.

The rename changed what people type and read. It could not change what was
already on somebody's machine — a settings file, a theme they picked, a command
in their fingers — and this is where that is pinned.
"""

from __future__ import annotations

import importlib
import json
import sys
import tomllib
from importlib.metadata import entry_points, version
from pathlib import Path

import pytest

import caland
from caland import formerly
from caland.domain import Settings
from caland.infrastructure import JsonSettingsStore
from caland.interface.theme import CALAND_THEMES


def test_only_formerly_spells_the_old_name():
    package = Path(caland.__file__).parent
    spelling_it = sorted(
        path.relative_to(package).as_posix()
        for path in package.rglob("*")
        if path.suffix in {".py", ".tcss"}
        and "isolinear" in path.read_text(encoding="utf-8").lower()
    )
    assert spelling_it == ["formerly.py"]


# -- the settings file --------------------------------------------------------


@pytest.fixture
def config_home(tmp_path, monkeypatch):
    """An empty config home, the way a machine has one."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    return tmp_path


def _write(path: Path, **settings: object) -> Path:
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(settings))
    return path


def test_settings_kept_under_the_old_name_are_still_read(config_home):
    _write(
        config_home / "isolinear" / "settings.json",
        theme="isolinear-violet",
        show_all_scopes=True,
        audit_threshold=180,
    )
    assert JsonSettingsStore().load() == Settings(
        theme="caland-violet", show_all_scopes=True, audit_threshold=180
    )


def test_a_change_is_saved_under_the_new_name_and_the_old_file_is_left_alone(
    config_home,
):
    old = _write(config_home / "isolinear" / "settings.json", theme="isolinear-amber")
    before = old.read_text()

    store = JsonSettingsStore()
    settings = store.load()
    settings.show_all_scopes = True
    store.save(settings)

    new = config_home / "caland" / "settings.json"
    assert json.loads(new.read_text())["theme"] == "caland-amber"
    assert old.read_text() == before
    assert JsonSettingsStore().load() == Settings(
        theme="caland-amber", show_all_scopes=True
    )


def test_the_new_file_wins_where_both_are_there(config_home):
    _write(config_home / "isolinear" / "settings.json", theme="isolinear-amber")
    _write(config_home / "caland" / "settings.json", theme="caland-phosphor")
    assert JsonSettingsStore().load().theme == "caland-phosphor"


def test_a_settings_file_that_was_asked_for_has_no_former_one(config_home):
    _write(config_home / "isolinear" / "settings.json", theme="isolinear-amber")
    assert JsonSettingsStore(config_home / "elsewhere.json").load() == Settings()


# -- the themes ---------------------------------------------------------------


def test_every_theme_is_still_found_under_the_name_it_was_saved_with():
    for theme in CALAND_THEMES:
        saved_as = theme.name.replace("caland", "isolinear", 1)
        assert formerly.theme(saved_as) == theme.name


@pytest.mark.parametrize("name", ["caland-violet", "textual-dark", "isolinearish", ""])
def test_any_other_theme_name_is_left_as_it_is(name):
    assert formerly.theme(name) == name


# -- the commands -------------------------------------------------------------


def test_the_old_commands_are_installed_beside_the_new_one():
    scripts = {
        script.name: script.value
        for script in entry_points(group="console_scripts")
        if script.value.startswith("caland.")
    }
    assert scripts == {
        "caland": "caland.app:main",
        "isolinear": "caland.formerly:main",
        "iso": "caland.formerly:main",
    }


@pytest.mark.parametrize("command", formerly.COMMANDS)
def test_an_old_command_says_the_new_name_and_then_is_caland(
    command, monkeypatch, capsys
):
    monkeypatch.setattr(sys, "argv", [command, "--version"])
    formerly.main()
    said = capsys.readouterr()
    # said beside the output, never in it
    assert said.out == f"caland {version('caland')}\n"
    assert "isolinear is now caland" in said.err


def test_its_help_is_calands_and_never_mentions_the_old_name(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["iso", "--help"])
    formerly.main()
    out = capsys.readouterr().out
    assert "usage: caland" in out
    assert "isolinear" not in out


# -- the last release under the old name --------------------------------------

SHIM = Path(__file__).parents[1] / "isolinear-shim"


def test_the_last_isolinear_release_installs_caland_and_its_old_commands():
    project = tomllib.loads((SHIM / "pyproject.toml").read_text())["project"]
    assert project["name"] == "isolinear"
    assert [d.split(">=")[0] for d in project["dependencies"]] == ["caland"]
    assert project["scripts"] == {
        "isolinear": "caland.formerly:main",
        "iso": "caland.formerly:main",
    }


def test_importing_it_warns_and_points_at_caland(monkeypatch):
    monkeypatch.syspath_prepend(str(SHIM / "src"))
    monkeypatch.delitem(sys.modules, "isolinear", raising=False)
    with pytest.warns(DeprecationWarning, match="isolinear is now caland"):
        importlib.import_module("isolinear")
    monkeypatch.delitem(sys.modules, "isolinear")


def test_caland_does_not_ship_it():
    """One wheel must not carry both names: the old one is a release of its own."""
    root = SHIM.parent
    build = tomllib.loads((root / "pyproject.toml").read_text())["tool"]["hatch"]["build"]
    assert build["targets"]["wheel"]["packages"] == ["src/caland"]
    assert SHIM.name in build["targets"]["sdist"]["exclude"]
