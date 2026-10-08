"""Finding the plugin a `uses:` names."""

from pathlib import Path

import pytest

from lely.registry import StepNotFound, find, installed
from lely.steps.bundle import Bundle
from lely.steps.bundle_run import BundleRun
from lely.steps.stevin import Stevin


def test_the_plugins_lely_ships_register_like_anyones() -> None:
    assert {"bundle", "stevin", "bundle.run"} <= set(installed())
    assert find("bundle", Path.cwd()).cls is Bundle
    assert find("stevin", Path.cwd()).cls is Stevin
    assert find("bundle.run", Path.cwd()).cls is BundleRun
    assert find("bundle.run", Path.cwd()).source == "built-in"


def test_command_is_no_plugin_any_more() -> None:
    """011/R12: a config that still names it is told there is no such plugin."""
    assert "command" not in installed()
    with pytest.raises(StepNotFound, match="No plugin named `command`"):
        find("command", Path.cwd())


def test_a_module_and_class() -> None:
    found = find("lely.steps.bundle_run:BundleRun", Path.cwd())
    assert found.cls is BundleRun
    assert found.options is BundleRun.Options


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


def test_options_whose_types_cant_be_read_are_named(tmp_path: Path) -> None:
    """A type hint naming something the plugin's module doesn't have used to
    end every command in a `NameError`."""
    (tmp_path / "s.py").write_text(
        "from __future__ import annotations\n"
        "from dataclasses import dataclass\n"
        "class Odd:\n"
        "    @dataclass(frozen=True)\n"
        "    class Options:\n"
        "        size: Missing = None\n"
        "    def plan(self, ctx): pass\n"
        "    def apply(self, ctx, plan): pass\n"
    )
    with pytest.raises(StepNotFound, match="the types of its `Options` can't be read"):
        find("./s.py:Odd", tmp_path)


def test_an_option_keeps_the_words_of_the_class_it_came_from(tmp_path: Path) -> None:
    from lely.registry import option_docs

    (tmp_path / "s.py").write_text(
        "from dataclasses import dataclass\n"
        "@dataclass(frozen=True)\n"
        "class Base:\n"
        "    #: Where it is.\n"
        "    path: str = '.'\n"
        "    #: Said by the base.\n"
        "    size: int = 1\n"
        "class Step:\n"
        "    @dataclass(frozen=True)\n"
        "    class Options(Base):\n"
        "        #: Said again, by the one that\n"
        "        #: inherits it.\n"
        "        size: int = 2\n"
        "    def plan(self, ctx): pass\n"
        "    def apply(self, ctx, plan): pass\n"
    )
    assert option_docs(find("./s.py:Step", tmp_path).options) == {
        "path": "Where it is.",
        "size": "Said again, by the one that inherits it.",
    }


def test_only_the_classs_own_body_describes_its_options(tmp_path: Path) -> None:
    from lely.registry import option_docs

    (tmp_path / "s.py").write_text(
        "from dataclasses import dataclass\n"
        "class Step:\n"
        "    @dataclass(frozen=True)\n"
        "    class Options:\n"
        "        #: How many.\n"
        "        size: int = 1\n"
        "        def __post_init__(self):\n"
        "            #: Not about an option at all.\n"
        "            size: int = 2\n"
        "    def plan(self, ctx): pass\n"
        "    def apply(self, ctx, plan): pass\n"
    )
    assert option_docs(find("./s.py:Step", tmp_path).options) == {"size": "How many."}


def test_what_a_plugin_prints_doesnt_land_in_lelys_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """stdout is lely's: a plan as JSON, a schema. A `print` left in a plugin
    goes to stderr."""
    from lely.step import declared

    (tmp_path / "loud.py").write_text(
        "from dataclasses import dataclass\n"
        "print('imported!')\n"
        "class Loud:\n"
        "    @dataclass(frozen=True)\n"
        "    class Options:\n"
        "        pass\n"
        "    @staticmethod\n"
        "    def outputs(written):\n"
        "        print('asked what it gives!')\n"
        "        return ()\n"
        "    def plan(self, ctx): pass\n"
        "    def apply(self, ctx, plan): pass\n"
    )
    found = find("./loud.py:Loud", tmp_path)
    assert declared(found.cls, {}) == ()
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "imported!" in captured.err and "asked what it gives!" in captured.err
    with pytest.raises(
        Exception, match="`outputs` must be a tuple of `Output`s, not int"
    ):
        declared(type("Wrong", (), {"outputs": 5}), {})
