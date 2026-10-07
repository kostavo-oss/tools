"""The real CLI runner, against `fake_databricks.py` as a program — so what
lely passes on the command line is what is tested."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

import project
from fakes import FakeDatabricks, bundle_config, fixture
from lely.databricks import CliError, DatabricksCli, answer, heard


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


def test_the_cli_is_heard_while_it_runs(tmp_path: Path) -> None:
    """A deploy or a job run takes minutes: what the CLI writes is passed on as
    it comes, not when it is done. This stand-in for it goes on only once its
    first line has been heard."""
    script = (
        "import pathlib, sys, time\n"
        "print('Uploading…', file=sys.stderr, flush=True)\n"
        "for _ in range(400):\n"
        "    if pathlib.Path('heard').exists():\n"
        "        break\n"
        "    time.sleep(0.05)\n"
        "else:\n"
        "    sys.exit('nobody heard the first line while this ran')\n"
        "print('done:', *sys.argv[1:])\n"
    )
    lines: list[str] = []

    def said(line: str) -> None:
        lines.append(line)
        (tmp_path / "heard").touch()

    runner = DatabricksCli((sys.executable, "-c", script), profile="dev")
    result = heard(runner, ["bundle", "deploy"], tmp_path, said)
    assert result.returncode == 0, result.stderr
    assert lines == ["Uploading…", "done: bundle deploy --profile dev"]
    assert (result.stdout, result.stderr) == (
        "done: bundle deploy --profile dev\n",
        "Uploading…\n",
    )


def test_a_stand_in_for_the_cli_is_heard_when_it_is_done(tmp_path: Path) -> None:
    """The contract is `run(args, cwd)`, which answers when the program has
    ended: whatever keeps to that and no more is still heard, on both streams."""
    world = tmp_path / "world"
    world.mkdir()
    (world / "plan.json").write_text(json.dumps(fixture("cli/plan-create.json")))
    (world / "warn-plan").write_text("Warning: one\nWarning: two\n")
    lines: list[str] = []
    result = heard(FakeDatabricks(world), ["bundle", "plan"], tmp_path, lines.append)
    assert result.returncode == 0
    assert lines == [result.stdout.strip(), "Warning: one", "Warning: two"]
