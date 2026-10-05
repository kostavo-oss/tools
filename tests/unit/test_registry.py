"""Finding the plugin a `uses:` names."""

from pathlib import Path

import pytest

from lely.registry import StepNotFound, find, installed
from lely.steps.bundle import Bundle
from lely.steps.bundle_run import BundleRun
from lely.steps.command import Command
from lely.steps.stevin import Stevin


def test_the_plugins_lely_ships_register_like_anyones() -> None:
    assert {"bundle", "command", "stevin", "bundle.run"} <= set(installed())
    assert find("bundle", Path.cwd()).cls is Bundle
    assert find("stevin", Path.cwd()).cls is Stevin
    assert find("bundle.run", Path.cwd()).cls is BundleRun
    assert find("command", Path.cwd()).source == "built-in"


def test_a_module_and_class() -> None:
    found = find("lely.steps.command:Command", Path.cwd())
    assert found.cls is Command
    assert found.options is Command.Options


def test_a_class_in_a_file_of_the_repo(tmp_path: Path) -> None:
    (tmp_path / "ops").mkdir()
    (tmp_path / "ops" / "steps.py").write_text(
        "from dataclasses import dataclass\n"
        "from lely.model import StepPlan\n"
        "class Warm:\n"
        "    @dataclass(frozen=True)\n"
        "    class Options:\n"
        "        table: str\n"
        "    def plan(self, ctx): return StepPlan()\n"
        "    def apply(self, ctx, plan): return {}\n"
    )
    found = find("./ops/steps.py:Warm", tmp_path)
    assert found.cls.__name__ == "Warm"
    assert found.source == "file ./ops/steps.py"
    assert find("./ops/steps.py:Warm", tmp_path).cls is found.cls  # loaded once


def test_an_unknown_name_lists_what_is_installed() -> None:
    with pytest.raises(
        StepNotFound, match="No plugin named `nope` is installed .*bundle"
    ):
        find("nope", Path.cwd())


def test_a_missing_file_or_class(tmp_path: Path) -> None:
    with pytest.raises(StepNotFound, match="there is no file"):
        find("./nope.py:X", tmp_path)
    (tmp_path / "s.py").write_text("X = 1\n")
    with pytest.raises(StepNotFound, match="there is no class `Y`"):
        find("./s.py:Y", tmp_path)


def test_a_class_that_isnt_a_plugin(tmp_path: Path) -> None:
    (tmp_path / "s.py").write_text("class NotOne:\n    def plan(self, ctx): pass\n")
    with pytest.raises(
        StepNotFound, match="needs an `Options` dataclass and a `apply` method"
    ):
        find("./s.py:NotOne", tmp_path)


def test_destroying_is_planned_first_or_not_at_all(tmp_path: Path) -> None:
    (tmp_path / "s.py").write_text(
        "from dataclasses import dataclass\n"
        "class Half:\n"
        "    @dataclass(frozen=True)\n"
        "    class Options:\n"
        "        pass\n"
        "    def plan(self, ctx): pass\n"
        "    def apply(self, ctx, plan): pass\n"
        "    def destroy(self, ctx, plan): pass\n"
    )
    with pytest.raises(StepNotFound, match="a `plan_destroy` method to go with"):
        find("./s.py:Half", tmp_path)


# -- found in review ---------------------------------------------------------------


@pytest.mark.parametrize("uses", [".foo:Bar", ":Bar", "pkg.mod:"])
def test_a_malformed_module_spelling_says_what_one_looks_like(uses: str) -> None:
    with pytest.raises(StepNotFound, match="a plugin in a package is `package.module:"):
        find(uses, Path.cwd())


def test_a_module_that_raises_on_import_is_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "exploding_plugin.py").write_text("raise RuntimeError('no config')\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    with pytest.raises(StepNotFound, match="can't import `exploding_plugin`: no config"):
        find("exploding_plugin:X", Path.cwd())
