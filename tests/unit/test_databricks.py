"""The real CLI runner, against `fake_databricks.py` as a program — so what
lely passes on the command line is what is tested."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

import project
from fakes import bundle_config, fixture
from lely.databricks import CliError, DatabricksCli, answer


def recorded(tmp_path: Path, profile: str | None = None) -> tuple[DatabricksCli, Path]:
    """A CLI whose world answers from recordings."""
    world = tmp_path / "world"
    world.mkdir()
    config = bundle_config(variables={"model_version": None})
    (world / "validate.json").write_text(json.dumps(config))
    (world / "plan.json").write_text(json.dumps(fixture("cli/plan-create.json")))
    runner = DatabricksCli(
        (sys.executable, str(project.FAKE_DATABRICKS), str(world)), profile
    )
    return runner, world


def calls(world: Path) -> list[list[str]]:
    return [json.loads(line) for line in (world / "calls.jsonl").read_text().splitlines()]


def test_runs_the_cli_with_the_profile(tmp_path: Path) -> None:
    runner, world = recorded(tmp_path, profile="dev")
    args = ["bundle", "validate", "--target", "dev", "--var=model_version=14"]
    config = answer(runner, args, tmp_path)
    assert config["variables"] == {"model_version": {"default": None, "value": "14"}}
    assert calls(world) == [[*args, "--output", "json", "--profile", "dev"]]


def test_the_profile_goes_before_what_is_the_jobs(tmp_path: Path) -> None:
    runner, world = recorded(tmp_path, profile="dev")
    runner.run(["bundle", "run", "jobs.x", "--", "--full"], tmp_path)
    assert calls(world) == [
        ["bundle", "run", "jobs.x", "--profile", "dev", "--", "--full"]
    ]


def test_a_failing_run_doesnt_raise(tmp_path: Path) -> None:
    runner, _ = recorded(tmp_path)
    result = runner.run(["bundle", "summary"], tmp_path)
    assert result.returncode == 1
    assert "no recording for `bundle summary`" in result.stderr


def test_a_failure_is_shown_in_the_clis_words(tmp_path: Path) -> None:
    runner, _ = recorded(tmp_path)
    with pytest.raises(
        CliError, match="(?s)`databricks bundle summary` failed.*no recording"
    ):
        answer(runner, ["bundle", "summary"], tmp_path)


def test_output_that_isnt_a_json_object_is_an_error(tmp_path: Path) -> None:
    runner, world = recorded(tmp_path)
    (world / "plan.json").write_text('"just a string"')
    with pytest.raises(CliError, match="printed no JSON object"):
        answer(runner, ["bundle", "plan"], tmp_path)


def test_a_missing_cli_says_how_to_install_it(tmp_path: Path) -> None:
    with pytest.raises(Exception, match="Install the Databricks CLI"):
        DatabricksCli(("no-such-databricks",)).run(["bundle", "summary"], tmp_path)
