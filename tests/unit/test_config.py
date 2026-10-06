"""The config: one list of steps, read strictly, every problem at its line and
column — from `lely.yml` and from `pyproject.toml` alike."""

from pathlib import Path

import pytest

import project
from lely.config import ConfigError, Map, Scalar, find, load, load_text, written

EXAMPLE = """\
steps:
  - name: model
    uses: ./ops/steps.py:LatestModel
    with:
      model: main.ml.churn

  - uses: bundle
    with:
      path: .
      vars:
        model_version: ${steps.model.version}

  - name: backfill
    uses: bundle.run
    with: {bundle: bundle, resource: jobs.backfill}
    targets: [dev, prod]
"""


def read(text: str) -> object:
    return load_text(text, Path("lely.yml"))


def problems(text: str, name: str = "lely.yml") -> list[str]:
    with pytest.raises(ConfigError) as caught:
        load_text(text, Path(name))
    return list(caught.value.problems)


def test_reads_steps_in_the_order_written() -> None:
    config = load_text(EXAMPLE, Path("project/lely.yml"))
    assert [(s.name, s.uses) for s in config.steps] == [
        ("model", "./ops/steps.py:LatestModel"),
        ("bundle", "bundle"),
        ("backfill", "bundle.run"),
    ]
    assert config.root == Path("project")
    assert config.step("backfill") is config.steps[2]
    assert config.step("nope") is None


def test_a_plain_plugin_name_doubles_as_the_steps_name() -> None:
    config = load_text(EXAMPLE, Path("lely.yml"))
    assert config.steps[1].name == "bundle"


def test_keeps_with_blocks_located() -> None:
    config = load_text(EXAMPLE, Path("lely.yml"))
    block = config.steps[0].options
    assert isinstance(block, Map)
    model = block.get("model")
    assert isinstance(model, Scalar)
    assert model.value == "main.ml.churn"
    assert (model.loc.line, model.loc.column) == (5, 14)


def test_a_with_block_as_written_keeps_its_references() -> None:
    config = load_text(EXAMPLE, Path("lely.yml"))
    assert written(config.steps[1].options) == {
        "path": ".",
        "vars": {"model_version": "${steps.model.version}"},
    }
    assert written(None) is None


def test_targets_limit_a_step() -> None:
    backfill = load_text(EXAMPLE, Path("lely.yml")).steps[2]
    assert backfill.targets == ("dev", "prod")
    assert backfill.runs_for("dev")
    assert not backfill.runs_for("staging")
    assert load_text(EXAMPLE, Path("lely.yml")).steps[0].runs_for("anything")


def test_an_unknown_key_is_an_error_where_it_was_written() -> None:
    assert problems("steps:\n  - uses: bundle\n    wiht: {}\n") == [
        "lely.yml:3:5: unknown key `wiht` in a step; expected one of "
        "name, uses, with, targets"
    ]


def test_the_keys_from_before_the_one_list_are_unknown() -> None:
    assert problems("pre: []\nsteps:\n  - uses: bundle\n") == [
        "lely.yml:1:1: unknown key `pre` in lely.yml; expected steps"
    ]


def test_a_step_needs_uses() -> None:
    assert problems("steps:\n  - name: x\n") == ["lely.yml:2:5: `uses` is required"]


def test_a_plugin_from_a_file_needs_a_name() -> None:
    [problem] = problems("steps:\n  - uses: ./ops/steps.py:Warm\n")
    assert problem.startswith("lely.yml:2:5: step `./ops/steps.py:Warm` needs a `name`")


def test_names_are_one_reference_part() -> None:
    [problem] = problems("steps:\n  - name: warm.cache\n    uses: command\n")
    assert problem.startswith("lely.yml:2:11: step name `warm.cache` must be")


def test_names_are_unique() -> None:
    [problem] = problems("steps:\n  - uses: bundle\n  - uses: bundle\n")
    assert problem == (
        "lely.yml:3:5: two steps are named `bundle` (the other is at "
        "lely.yml:2:5); give one a `name`"
    )


def test_every_problem_is_reported_at_once() -> None:
    found = problems("steps:\n  - uses: bundle\n    wiht: {}\n  - name: y\n")
    assert len(found) == 2


def test_a_duplicate_key_is_an_error() -> None:
    assert problems("steps:\n  - uses: bundle\n    uses: command\n") == [
        "lely.yml:3:5: `uses` appears twice"
    ]


def test_no_steps_is_an_error() -> None:
    assert problems("steps: []\n") == [
        "lely.yml:1:1: no steps: add at least one under `steps`"
    ]


def test_an_empty_file_is_an_error() -> None:
    assert problems("") == ["lely.yml: empty; it needs a `steps:` list."]


def test_bad_yaml_says_where() -> None:
    [problem] = problems("steps:\n  - uses: [bundle\n")
    assert problem.startswith("lely.yml:3:1: not valid YAML")


def test_a_missing_file_says_what_lely_reads(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match=r"`lely.yml`, or `\[tool.lely\]`"):
        load(tmp_path / "lely.yml")


# -- pyproject.toml -------------------------------------------------------------


def test_pyproject_says_the_same_as_lely_yml(tmp_path: Path) -> None:
    yml = load_text(project.LELY_YML, tmp_path / "lely.yml")
    toml = load_text(project.PYPROJECT_TOML, tmp_path / "pyproject.toml")
    assert [(s.name, s.uses, s.targets) for s in toml.steps] == [
        (s.name, s.uses, s.targets) for s in yml.steps
    ]
    assert [written(s.options) for s in toml.steps] == [
        written(s.options) for s in yml.steps
    ]
    assert toml.root == yml.root


def test_pyproject_keeps_positions() -> None:
    config = load_text(project.PYPROJECT_TOML, Path("pyproject.toml"))
    model, app, notify, backfill, warm = config.steps
    # `[[tool.lely.steps]]` headers
    assert [s.loc.line for s in config.steps] == [5, 10, 15, 22, 27]
    block = app.options
    assert isinstance(block, Map)
    variables = block.get("vars")
    assert isinstance(variables, Map)
    version = variables.get("model_version")
    assert isinstance(version, Scalar)
    line = project.PYPROJECT_TOML.splitlines()[version.loc.line - 1]
    assert line[version.loc.column - 1 :].startswith('"${steps.model.version}"')
    # a `with` written as its own table, and an item of a list in it
    command = notify.options
    assert isinstance(command, Map)
    assert command.entries[0].key_loc.line == 20
    assert project.PYPROJECT_TOML.splitlines()[19][
        command.entries[0].key_loc.column - 1 :
    ].startswith("apply")


def test_pyproject_problems_have_a_position() -> None:
    text = (
        '[project]\nname = "x"\n\n[[tool.lely.steps]]\nuses = "bundle"\nwiht = {}\n'
        '\n[[tool.lely.steps]]\nname = "y"\n'
    )
    assert problems(text, "pyproject.toml") == [
        "pyproject.toml:6:1: unknown key `wiht` in a step; expected one of "
        "name, uses, with, targets",
        "pyproject.toml:8:1: `uses` is required",
    ]


def test_pyproject_unknown_top_key() -> None:
    text = '[tool.lely]\nbundle = "."\n\n[[tool.lely.steps]]\nuses = "bundle"\n'
    assert problems(text, "pyproject.toml") == [
        "pyproject.toml:2:1: unknown key `bundle` in [tool.lely]; expected steps"
    ]


def test_pyproject_steps_written_inline() -> None:
    text = '[tool.lely]\nsteps = [\n  { uses = "bundle" },\n  { name = "x" },\n]\n'
    assert problems(text, "pyproject.toml") == ["pyproject.toml:4:3: `uses` is required"]


def test_pyproject_without_a_section_or_broken() -> None:
    assert problems('[project]\nname = "x"\n', "pyproject.toml") == [
        "pyproject.toml: it has no `[tool.lely]` section."
    ]
    [problem] = problems("[tool.lely\n", "pyproject.toml")
    assert problem.startswith("pyproject.toml: not valid TOML")


# -- finding it -----------------------------------------------------------------


def test_the_config_is_found_from_a_subfolder(tmp_path: Path) -> None:
    project.write(tmp_path)
    deep = tmp_path / "src" / "pkg"
    deep.mkdir(parents=True)
    assert find(deep) == tmp_path / "lely.yml"
    assert find(tmp_path) == tmp_path / "lely.yml"


def test_a_pyproject_counts_only_with_a_lely_section(tmp_path: Path) -> None:
    project.write(tmp_path, toml=True)
    inner = tmp_path / "service"
    inner.mkdir()
    (inner / "pyproject.toml").write_text('[project]\nname = "service"\n')
    assert find(inner) == tmp_path / "pyproject.toml"


def test_both_in_one_folder_is_an_error_that_names_them(tmp_path: Path) -> None:
    project.write(tmp_path)
    project.write(tmp_path, toml=True)
    with pytest.raises(ConfigError) as caught:
        find(tmp_path)
    message = str(caught.value)
    assert str(tmp_path / "lely.yml") in message
    assert str(tmp_path / "pyproject.toml") in message
    assert "doesn't merge them and doesn't pick" in message


def test_no_config_anywhere_says_what_was_looked_for(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="No `lely.yml`, and no `pyproject.toml`"):
        find(tmp_path)


# -- found in review: a file lely can't read is a message, never a traceback ---------


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("base: &b {uses: bundle}\nsteps:\n  - <<: *b\n", "not valid YAML"),
        ("steps:\n  - uses: !foo bar\n", "not valid YAML"),
        (
            "steps:\n  - uses: bundle\n    with: {when: 2024-02-30}\n",
            "lely.yml:3:18: `2024-02-30` can't be read as YAML's `timestamp`; quote",
        ),
        (
            "steps:\n  - uses: bundle\n    with: {n: !!int abc}\n",
            "lely.yml:3:15: `abc` can't be read as YAML's `int`",
        ),
        # found in the fourth review: each of these was a traceback
        ("steps:\n  - uses: bundle\n    with: {n: !!bool maybe}\n", "YAML's `bool`"),
        ("steps:\n  - uses: bundle\n    with: {n: !!int ''}\n", "YAML's `int`"),
        ("steps:\n  - uses: bundle\n    with: {n: !!float ''}\n", "YAML's `float`"),
        ("steps:\n  - uses: bundle\n    with: {n: !!timestamp x}\n", "`timestamp`"),
        ("steps: &a\n  - uses: bundle\n  - *a\n", "refers to itself"),
        ("steps:\n  - uses: \x01\n", "not valid YAML"),
    ],
)
def test_yaml_lely_cant_read_is_a_config_error(text: str, message: str) -> None:
    [problem] = problems(text)
    assert message in problem
    assert problem.startswith("lely.yml")


def test_a_config_that_isnt_a_readable_file_is_a_config_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="directory"):
        load(tmp_path)
    binary = tmp_path / "lely.yml"
    binary.write_bytes(b"steps: \xff\xfe\n")
    with pytest.raises(ConfigError, match="not a text file lely can read"):
        load(binary)


def test_a_config_named_lely_yaml_says_what_lely_reads(tmp_path: Path) -> None:
    (tmp_path / "lely.yaml").write_text("steps: []\n")
    with pytest.raises(ConfigError) as caught:
        find(tmp_path)
    assert "lely reads `lely.yml`. Rename it" in str(caught.value)


def test_a_broken_pyproject_that_is_about_lely_isnt_passed_over(tmp_path: Path) -> None:
    project.write(tmp_path)  # a `lely.yml` in the folder above
    inner = tmp_path / "service"
    inner.mkdir()
    (inner / "pyproject.toml").write_text('tool.lely.steps = [\n  { uses = "bundle" \n')
    assert find(inner) == inner / "pyproject.toml"
    with pytest.raises(ConfigError, match="not valid TOML"):
        load(find(inner))


# -- found in the third review -------------------------------------------------------


def test_a_toml_value_is_what_toml_parsed_never_what_a_scan_found() -> None:
    """Where a value was written is found again by scanning the text, which is
    good enough for a position in a message. For a moment the *value* a text
    option was handed came from there too — and a commented-out line, or the
    key above, supplied it."""
    text = (
        "[[tool.lely.steps]]\n"
        'uses = "bundle"\n'
        "# with.vars.model_version = 13\n"
        "with.vars.model_version = 14  # not 15\n"
        "with.vars.a = 1.10\n"
        "with.vars.b = 2.20\n"
    )
    config = load_text(text, Path("pyproject.toml"))
    block = config.steps[0].options
    assert written(block) == {"vars": {"model_version": 14, "a": 1.1, "b": 2.2}}
    variables = block.get("vars") if block else None
    assert isinstance(variables, Map)
    assert all(
        isinstance(entry.value, Scalar) and entry.value.raw is None
        for entry in variables.entries
    )


def test_a_yaml_number_keeps_the_text_it_was_written_as() -> None:
    config = load_text(
        "steps:\n  - uses: bundle\n    with: {vars: {a: 1.10, b: 0123, c: yes, d: x}}\n",
        Path("lely.yml"),
    )
    block = config.steps[0].options
    variables = block.get("vars") if block else None
    assert isinstance(variables, Map)
    raws = {e.key: e.value.raw for e in variables.entries if isinstance(e.value, Scalar)}
    assert raws == {"a": "1.10", "b": "0123", "c": "yes", "d": None}


def test_what_a_step_is_made_from_is_what_was_spelled() -> None:
    """005/R5: options *as written*. `1.10` edited to `1.1` hands a text option
    another text, so it is another step — while `5` is `5` in YAML and in TOML."""
    from lely.config import spelled

    def of(yaml_value: str) -> object:
        config = load_text(
            f"steps:\n  - uses: bundle\n    with: {{v: {yaml_value}}}\n", Path("lely.yml")
        )
        return spelled(config.steps[0].options)

    assert of("1.10") != of("1.1")
    assert of("0123") != of("83")
    assert of("yes") != of("true")
    assert of("1.10") == {"v": {"$written": "1.10"}}
    assert of("5") == {"v": 5} and of("1.5") == {"v": 1.5} and of("true") == {"v": True}
    toml = load_text(
        '[[tool.lely.steps]]\nuses = "bundle"\nwith = { v = 5 }\n', Path("pyproject.toml")
    )
    assert spelled(toml.steps[0].options) == of("5")


def test_no_config_is_told_apart_from_one_that_cant_be_read(tmp_path: Path) -> None:
    from lely.config import NoConfig

    with pytest.raises(NoConfig):
        find(tmp_path)
    (tmp_path / "lely.yml").write_text("stps: []\n")
    with pytest.raises(ConfigError) as caught:
        load(find(tmp_path))
    assert not isinstance(caught.value, NoConfig)
