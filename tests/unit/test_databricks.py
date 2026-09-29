"""The real CLI runner, against `fake_databricks.py` — a program that answers
from recordings, so what sluis passes on the command line is what is tested."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

import project
from sluis.databricks import CliError, DatabricksCli


def cli(tmp_path: Path, profile: str | None = None) -> tuple[DatabricksCli, Path]:
    answers = project.answers(tmp_path)
    runner = DatabricksCli(
        tmp_path, (sys.executable, str(project.FAKE_DATABRICKS), str(answers)), profile
    )
    return runner, answers


def calls(answers: Path) -> list[list[str]]:
    return [
        json.loads(line) for line in (answers / "calls.jsonl").read_text().splitlines()
    ]


def test_validate_passes_the_target_and_variables(tmp_path: Path) -> None:
    runner, answers = cli(tmp_path, profile="dev")
    config: Any = runner.validate("dev", {"model_version": "14"})
    assert config["variables"]["model_version"]["value"] == "14"
    assert calls(answers) == [
        [
            "bundle",
            "validate",
            "--output",
            "json",
            "--target",
            "dev",
            "--var=model_version=14",
            "--profile",
            "dev",
        ]
    ]


def test_plan_and_summary(tmp_path: Path) -> None:
    runner, answers = cli(tmp_path)
    assert runner.plan("dev", {})["plan_version"] == 2
    assert "resources" in runner.summary("dev")
    assert [c[1] for c in calls(answers)] == ["plan", "summary"]


def test_without_a_target_the_cli_picks_the_default(tmp_path: Path) -> None:
    runner, answers = cli(tmp_path)
    runner.validate(None, {})
    assert "--target" not in calls(answers)[0]


def test_a_failure_is_shown_in_the_clis_words(tmp_path: Path) -> None:
    runner, answers = cli(tmp_path)
    (answers / "plan.json").unlink()
    with pytest.raises(
        CliError, match="(?s)`databricks bundle plan` failed.*no recording"
    ):
        runner.plan("dev", {})


def test_output_that_isnt_json_is_an_error(tmp_path: Path) -> None:
    runner, answers = cli(tmp_path)
    (answers / "summary.json").write_text('"just a string"')
    with pytest.raises(CliError, match="printed no JSON object"):
        runner.summary("dev")


def test_a_missing_cli_says_how_to_install_it(tmp_path: Path) -> None:
    with pytest.raises(Exception, match="Install the Databricks CLI"):
        DatabricksCli(tmp_path, ("no-such-databricks",)).summary("dev")
