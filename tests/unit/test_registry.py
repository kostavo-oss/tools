"""Finding the step a `uses:` names."""

from pathlib import Path

import pytest

from sluis.registry import StepNotFound, find, installed
from sluis.steps.bundle_run import BundleRun
from sluis.steps.command import Command
from sluis.steps.deltaplan import Deltaplan


def test_the_built_ins_register_like_plugins() -> None:
    assert {"command", "deltaplan", "bundle.run"} <= set(installed())
    assert find("deltaplan", Path.cwd()).cls is Deltaplan
    assert find("bundle.run", Path.cwd()).cls is BundleRun
    assert find("command", Path.cwd()).source == "built-in"


def test_a_module_and_class() -> None:
    found = find("sluis.steps.command:Command", Path.cwd())
    assert found.cls is Command
    assert found.options is Command.Options


def test_a_class_in_a_file_of_the_repo(tmp_path: Path) -> None:
    (tmp_path / "ops").mkdir()
    (tmp_path / "ops" / "steps.py").write_text(
        "from dataclasses import dataclass\n"
        "from sluis.model import StepPlan\n"
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
        StepNotFound, match="No step named `nope` is installed .*deltaplan"
    ):
        find("nope", Path.cwd())


def test_a_missing_file_or_class(tmp_path: Path) -> None:
    with pytest.raises(StepNotFound, match="there is no file"):
        find("./nope.py:X", tmp_path)
    (tmp_path / "s.py").write_text("X = 1\n")
    with pytest.raises(StepNotFound, match="there is no class `Y`"):
        find("./s.py:Y", tmp_path)


def test_a_class_that_isnt_a_step(tmp_path: Path) -> None:
    (tmp_path / "s.py").write_text("class NotAStep:\n    def plan(self, ctx): pass\n")
    with pytest.raises(
        StepNotFound, match="needs an `Options` dataclass and a `apply` method"
    ):
        find("./s.py:NotAStep", tmp_path)
