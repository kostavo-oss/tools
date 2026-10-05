"""`lely.yml`: read strictly, every problem at its line and column."""

from pathlib import Path

import pytest

from lely.config import ConfigError, Map, Scalar, load, load_text

EXAMPLE = """\
bundle: .

pre:
  - name: model
    uses: ./ops/steps.py:LatestModel
    with:
      model: ${var.catalog}.ml.churn

bundle_vars:
  model_version: ${steps.model.version}

post:
  - uses: stevin
    with: {config: stevin.yml}
  - name: backfill
    uses: bundle.run
    with: {resource: jobs.backfill}
    targets: [dev, prod]
"""


def read(text: str) -> object:
    return load_text(text, Path("lely.yml"))


def problems(text: str) -> list[str]:
    with pytest.raises(ConfigError) as caught:
        read(text)
    return list(caught.value.problems)


def test_reads_steps_in_order_with_their_phase() -> None:
    config = load_text(EXAMPLE, Path("project/lely.yml"))
    assert [(s.name, s.uses, s.phase) for s in config.steps] == [
        ("model", "./ops/steps.py:LatestModel", "pre"),
        ("stevin", "stevin", "post"),
        ("backfill", "bundle.run", "post"),
    ]
    assert config.root == Path("project")
    assert config.bundle_dir == Path("project/.")


def test_a_plain_step_name_doubles_as_the_steps_name() -> None:
    config = load_text(EXAMPLE, Path("lely.yml"))
    assert config.post[0].name == "stevin"


def test_keeps_with_blocks_located() -> None:
    config = load_text(EXAMPLE, Path("lely.yml"))
    block = config.pre[0].options
    assert isinstance(block, Map)
    model = block.get("model")
    assert isinstance(model, Scalar)
    assert model.value == "${var.catalog}.ml.churn"
    assert (model.loc.line, model.loc.column) == (7, 14)


def test_targets_limit_a_step() -> None:
    backfill = load_text(EXAMPLE, Path("lely.yml")).post[1]
    assert backfill.targets == ("dev", "prod")
    assert backfill.runs_for("dev")
    assert not backfill.runs_for("staging")
    assert load_text(EXAMPLE, Path("lely.yml")).post[0].runs_for("anything")


def test_the_digest_follows_the_text() -> None:
    one = load_text(EXAMPLE, Path("lely.yml")).digest
    assert one == load_text(EXAMPLE, Path("lely.yml")).digest
    assert one != load_text(EXAMPLE + "\n# note\n", Path("lely.yml")).digest


def test_an_unknown_key_is_an_error_where_it_was_written() -> None:
    assert problems("post:\n  - uses: stevin\n    wiht: {}\n") == [
        "lely.yml:3:5: unknown key `wiht` in a post step; expected one of "
        "name, uses, with, targets"
    ]


def test_an_unknown_top_level_key_is_an_error() -> None:
    assert problems("steps: []\npost:\n  - uses: stevin\n") == [
        "lely.yml:1:1: unknown key `steps` in lely.yml; expected one of "
        "bundle, pre, bundle_vars, post"
    ]


def test_a_step_needs_uses() -> None:
    assert problems("post:\n  - name: x\n") == ["lely.yml:2:5: `uses` is required"]


def test_a_step_from_a_file_needs_a_name() -> None:
    [problem] = problems("post:\n  - uses: ./ops/steps.py:Warm\n")
    assert problem.startswith("lely.yml:2:5: step `./ops/steps.py:Warm` needs a `name`")


def test_names_are_one_reference_part() -> None:
    [problem] = problems("post:\n  - name: warm.cache\n    uses: command\n")
    assert problem.startswith("lely.yml:2:11: step name `warm.cache` must be")


def test_names_are_unique_across_phases() -> None:
    [problem] = problems("pre:\n  - uses: stevin\npost:\n  - uses: stevin\n")
    assert problem == (
        "lely.yml:4:5: two steps are named `stevin` (the other is at "
        "lely.yml:2:5); give one a `name`"
    )


def test_every_problem_is_reported_at_once() -> None:
    found = problems("post:\n  - uses: stevin\n    wiht: {}\n  - name: y\n")
    assert len(found) == 2


def test_a_duplicate_key_is_an_error() -> None:
    assert problems("post:\n  - uses: stevin\n    uses: command\n") == [
        "lely.yml:3:5: `uses` appears twice"
    ]


def test_bundle_vars_are_single_values() -> None:
    [problem] = problems("post:\n  - uses: stevin\nbundle_vars:\n  tags: [a, b]\n")
    assert problem.startswith(
        "lely.yml:4:9: bundle variable `tags` must be a single value"
    )


def test_no_steps_is_an_error() -> None:
    assert problems("bundle: .\n") == [
        "lely.yml:1:1: no steps: add at least one under pre or post"
    ]


def test_an_empty_file_is_an_error() -> None:
    assert problems("") == [
        "lely.yml: empty; it needs at least one step under pre or post."
    ]


def test_bad_yaml_says_where() -> None:
    [problem] = problems("post:\n  - uses: [stevin\n")
    assert problem.startswith("lely.yml:3:1: not valid YAML")


def test_a_missing_file_says_what_lely_looks_for(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="next to `databricks.yml`"):
        load(tmp_path / "lely.yml")
