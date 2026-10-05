"""The `lely` command, end to end, against the recorded CLI and stevin."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

import project
from lely import cli, planfile

runner = CliRunner()


@pytest.fixture
def workdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    project.write(tmp_path)
    answers = project.answers(tmp_path)
    monkeypatch.setattr(
        cli, "DATABRICKS", (sys.executable, str(project.FAKE_DATABRICKS), str(answers))
    )
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_validate(workdir: Path) -> None:
    result = runner.invoke(cli.app, ["validate"])
    assert result.exit_code == 0, result.output
    assert "lely.yml: 1 pre, 4 post steps, 1 bundle variable(s)" in result.output


def test_validate_fails_with_located_problems(workdir: Path) -> None:
    (workdir / "lely.yml").write_text("post:\n  - uses: stevin\n    with: {confg: x}\n")
    result = runner.invoke(cli.app, ["validate"])
    assert result.exit_code == 1
    assert "lely.yml:3:12: unknown option `confg`" in result.output


def test_plan_shows_and_writes_the_plan(workdir: Path) -> None:
    result = runner.invoke(cli.app, ["plan", "-o", "plan.json"])
    assert result.exit_code == 0, result.output
    assert "lely plan · shop · target dev" in result.output
    assert "Plan: 5 changes · 1 run · 0 destructive · 1 decided at apply" in result.output
    written = planfile.loads((workdir / "plan.json").read_text())
    assert written.deploy.variables == (("model_version", "14"),)


def test_show_renders_a_saved_plan(workdir: Path) -> None:
    runner.invoke(cli.app, ["plan", "-o", "plan.json"])
    result = runner.invoke(cli.app, ["show", "plan.json"])
    assert result.exit_code == 0, result.output
    assert "▶ runs jobs.backfill" in result.output


def test_plan_as_json(workdir: Path) -> None:
    result = runner.invoke(cli.app, ["plan", "-f", "json"])
    assert result.exit_code == 0, result.output
    document = json.loads(result.stdout)
    assert [s["name"] for s in document["post"]] == ["tables", "notify", "backfill"]


def test_a_failing_cli_fails_the_plan(workdir: Path) -> None:
    (workdir / "answers" / "plan.json").unlink()
    result = runner.invoke(cli.app, ["plan"])
    assert result.exit_code == 1
    assert "`databricks bundle plan` failed" in result.output


def test_steps_lists_the_built_ins() -> None:
    result = runner.invoke(cli.app, ["steps"])
    assert result.exit_code == 0, result.output
    assert "bundle.run  built-in" in result.output
    assert "resource: a string  required" in result.output
    assert "executable: list of strings  default ('stevin',)" in result.output


def test_version() -> None:
    result = runner.invoke(cli.app, ["--version"])
    assert result.output.startswith("lely ")
