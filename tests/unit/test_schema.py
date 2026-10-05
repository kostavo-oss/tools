"""The editors' schema: what `lely validate` says about a config's shape, as a
JSON Schema built from the plugins themselves (003/R9).

Held to two things: a real validator reads it the way an editor would, and it
agrees with lely — a config lely reads fits the schema, and a shape lely
refuses doesn't.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import pytest
import yaml
from jsonschema import Draft7Validator
from typer.testing import CliRunner

import project
from lely import cli, planning, registry, schema
from lely.config import ConfigError, load
from lely.model import Linked, Secret
from lely.steps.bundle import Bundle


def schema_for(root: Path) -> dict[str, Any]:
    """The schema `lely schema` writes for the project at `root`."""
    if not (root / "ops" / "steps.py").exists():
        root.mkdir(parents=True, exist_ok=True)
        project.write(root)
    names = [*sorted(registry.installed()), "./ops/steps.py:LatestModel"]
    plugins = [registry.find(name, root) for name in names]
    docs = {found.uses: registry.option_docs(found.options) for found in plugins}
    return schema.build(plugins, docs)


def errors(document: object, built: Mapping[str, Any]) -> list[str]:
    Draft7Validator.check_schema(built)
    return [error.message for error in Draft7Validator(built).iter_errors(document)]


def lely_reads(root: Path, text: str) -> bool:
    project.write(root, text)
    try:
        planning.check(load(root / "lely.yml"))
    except ConfigError:
        return False
    return True


# -- it agrees with lely ------------------------------------------------------------

TWO_BUNDLES = (
    "steps:\n"
    "  - name: data\n    uses: bundle\n    with: {vars: {model_version: 1}}\n"
    "  - name: api\n    uses: bundle\n    targets: [dev, prod]\n    with:\n"
    "      path: .\n      vars: {job: '${steps.data.resources.jobs.backfill.id}'}\n"
)
COMMANDS = (
    "steps:\n"
    "  - name: seed\n    uses: command\n    with:\n      plan: [./p.sh, --plan]\n"
    "      apply: [./a.sh]\n      destroy: [./d.sh]\n      outputs: [count]\n"
    "      env: {TOKEN: '${env.TOKEN}', PORT: 8080}\n"
    "  - uses: stevin\n"
    "    with: {config: stevin.yml, target: null, select: ['sales.*']}\n"
)


@pytest.mark.parametrize("text", [project.LELY_YML, TWO_BUNDLES, COMMANDS])
def test_a_config_lely_reads_fits_the_schema(tmp_path: Path, text: str) -> None:
    assert lely_reads(tmp_path, text)
    assert errors(yaml.safe_load(text), schema_for(tmp_path)) == []


@pytest.mark.parametrize(
    ("text", "said"),
    [
        ("pre: []\nsteps:\n  - uses: bundle\n", "'pre' was unexpected"),
        ("steps: []\n", "[] should be non-empty"),
        ("steps:\n  - name: x\n", "'uses' is a required property"),
        ("steps:\n  - uses: bundle\n    wiht: {}\n", "'wiht' was unexpected"),
        ("steps:\n  - uses: bundle\n    with: {paht: x}\n", "'paht' was unexpected"),
        ("steps:\n  - uses: bundle\n    with: {path: [x]}\n", "is not of type"),
        ("steps:\n  - uses: bundle\n    targets: dev\n", "'dev' is not of type 'array'"),
        (
            "steps:\n  - uses: bundle\n  - name: run\n    uses: bundle.run\n"
            "    with: {bundle: bundle}\n",
            "'resource' is a required property",
        ),
        (
            "steps:\n  - uses: bundle\n  - name: run\n    uses: bundle.run\n",
            "'with' is a required property",
        ),
        (
            "steps:\n  - uses: bundle\n  - uses: bundle.run\n"
            "    with: {bundle: bundle, resource: jobs.x}\n",
            "'name' is a required property",
        ),
        (
            "steps:\n  - uses: ./ops/steps.py:LatestModel\n    with: {model: m}\n",
            "'name' is a required property",
        ),
        (
            "steps:\n  - name: a.b\n    uses: command\n    with: {apply: [x]}\n",
            "'a.b' does not match",
        ),
        (
            "steps:\n  - name: s\n    uses: command\n    with: {apply: ./x.sh}\n",
            "'./x.sh' is not of type 'array'",
        ),
        (
            "steps:\n  - name: m\n    uses: ./ops/steps.py:LatestModel\n"
            "    with: {model: m, alais: x}\n",
            "'alais' was unexpected",
        ),
    ],
)
def test_a_shape_lely_refuses_doesnt_fit_the_schema(
    tmp_path: Path, text: str, said: str
) -> None:
    assert not lely_reads(tmp_path, text)
    found = errors(yaml.safe_load(text), schema_for(tmp_path))
    assert any(said in message for message in found), found


def test_a_mistake_is_reported_against_the_plugin_that_was_named(tmp_path: Path) -> None:
    """One `if` per plugin rather than a choice between all of them: an editor
    then says what is wrong, not that nothing matched."""
    text = "steps:\n  - uses: bundle\n    with: {paht: x}\n"
    found = errors(yaml.safe_load(text), schema_for(tmp_path / "x"))
    assert found == ["Additional properties are not allowed ('paht' was unexpected)"]


def test_what_only_validate_can_see_is_left_to_validate(tmp_path: Path) -> None:
    """A schema can't see one step from another: a reference to a step that
    isn't there fits the shape, and `lely validate` refuses it."""
    text = project.LELY_YML.replace("${steps.model.version}", "${steps.nope.version}")
    assert errors(yaml.safe_load(text), schema_for(tmp_path)) == []
    assert not lely_reads(tmp_path, text)


def test_a_plugin_the_schema_doesnt_know_is_left_alone(tmp_path: Path) -> None:
    text = "steps:\n  - name: x\n    uses: some.package:Plugin\n    with: {any: thing}\n"
    assert errors(yaml.safe_load(text), schema_for(tmp_path / "x")) == []


# -- every type an option can have ---------------------------------------------------


@dataclass(frozen=True, slots=True)
class Options:
    model: str
    retries: int = 3
    ratio: float = 0.5
    enabled: bool = True
    mode: Literal["fast", "safe"] = "safe"
    tags: tuple[str, ...] = ()
    env: Mapping[str, Secret] = field(default_factory=dict)
    note: str | None = None
    extra: object = None
    after: Linked | None = None


class Typed:
    """Has one option of every kind."""

    Options = Options


def typed(with_: dict[str, Any]) -> list[str]:
    found = registry.Found("typed", Typed, "test", Options)
    document = {"steps": [{"uses": "typed", "with": with_}]}
    return errors(document, schema.build([found]))


def test_every_supported_type_is_let_through() -> None:
    assert (
        typed(
            {
                "model": "main.ml.churn",
                "retries": 5,
                "ratio": 1,
                "enabled": False,
                "mode": "fast",
                "tags": ["a", "b"],
                "env": {"A": "1", "PORT": 8080},
                "note": None,
                "extra": {"any": [1, "two"]},
                "after": "app",
            }
        )
        == []
    )
    assert typed({"model": 14}) == []  # a number is taken as text


def test_a_reference_is_let_through_where_a_number_is_wanted() -> None:
    """`retries: ${steps.model.version}` is a string in the file and a number
    once resolved."""
    refs = {
        "model": "m",
        "retries": "${steps.model.version}",
        "ratio": "${steps.model.ratio}",
        "enabled": "${steps.model.on}",
        "mode": "${steps.model.mode}",
    }
    assert typed(refs) == []


@pytest.mark.parametrize(
    "with_",
    [
        {},  # `model` is required
        {"model": "m", "retries": "many"},
        {"model": "m", "ratio": "half"},
        {"model": "m", "enabled": "yes"},
        {"model": "m", "mode": "slow"},
        {"model": "m", "tags": "a"},
        {"model": "m", "tags": [["a"]]},
        {"model": "m", "env": ["A"]},
        {"model": ["m"]},
        {"model": "m", "after": "not a name"},
    ],
)
def test_a_wrong_type_doesnt_fit(with_: dict[str, Any]) -> None:
    assert typed(with_) != []


def test_defaults_are_given_where_a_config_could_write_them() -> None:
    found = registry.Found("typed", Typed, "test", Options)
    options = schema.build([found])["definitions"]["step"]["allOf"][0]["then"][
        "properties"
    ]["with"]
    assert options["required"] == ["model"]
    properties = options["properties"]
    assert properties["retries"]["default"] == 3
    assert properties["mode"]["default"] == "safe"
    assert properties["tags"]["default"] == []
    assert "default" not in properties["note"]  # `None`: nothing to write
    assert "default" not in properties["env"]


# -- in the plugins' own words --------------------------------------------------------


def test_an_options_comments_are_its_description() -> None:
    assert registry.option_docs(Bundle.Options) == {
        "path": "The directory holding `databricks.yml`, relative to the config.",
        "vars": "Passed to the bundle as `--var`, on every call. Single values only.",
    }
    assert registry.option_docs(int) == {}  # no source to read: no words


def test_the_schema_says_what_a_plugin_does_and_gives(tmp_path: Path) -> None:
    project.write(tmp_path)
    step = schema_for(tmp_path)["definitions"]["step"]
    described = {
        choice["const"]: choice["description"]
        for choice in step["properties"]["uses"]["anyOf"]
        if "const" in choice
    }
    assert described["bundle"] == (
        "Deploys an Asset Bundle with the Databricks CLI.\n"
        "Gives at plan: target, name, workspace.<field>, var.<name>, "
        "resources.<type>.<key>.<field>.\n"
        "Gives once it exists: resources.<type>.<key>.id, resources.<type>.<key>.url."
    )
    assert described["command"].endswith("Gives: what the step lists, by its options.")
    assert described["./ops/steps.py:LatestModel"].endswith("Gives at plan: version.")
    bundle = next(
        when["then"]["properties"]["with"]["properties"]
        for when in step["allOf"]
        if when["if"]["properties"]["uses"]["const"] == "bundle"
    )
    assert bundle["path"]["description"].startswith("The directory holding")


# -- the command ----------------------------------------------------------------------

runner = CliRunner()


def test_lely_schema_prints_the_schema_for_this_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project.write(tmp_path)
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(cli.app, ["schema"])
    assert result.exit_code == 0, result.output
    printed = json.loads(result.stdout)
    assert printed == schema_for(tmp_path)
    assert errors(yaml.safe_load(project.LELY_YML), printed) == []


def test_lely_schema_writes_a_file_and_says_how_to_use_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project.write(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("COLUMNS", "200")
    result = runner.invoke(cli.app, ["schema", "-o", "lely.schema.json"])
    assert result.exit_code == 0, result.output
    assert "Wrote lely.schema.json" in result.output
    assert "# yaml-language-server: $schema=lely.schema.json" in result.output
    written = json.loads((tmp_path / "lely.schema.json").read_text())
    assert written["$schema"] == "http://json-schema.org/draft-07/schema#"
    missing = runner.invoke(cli.app, ["schema", "-o", "nope/lely.schema.json"])
    assert missing.exit_code == 1
    assert "Can't write the schema to nope/lely.schema.json" in missing.output


def test_lely_schema_works_without_a_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Before there is a config to read: the installed plugins."""
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(cli.app, ["schema"])
    assert result.exit_code == 0, result.output
    step = json.loads(result.stdout)["definitions"]["step"]
    known = [c["const"] for c in step["properties"]["uses"]["anyOf"] if "const" in c]
    assert known == ["bundle", "bundle.run", "command", "stevin"]
