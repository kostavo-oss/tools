"""The `lely` command, end to end, against the fake Databricks CLI as a program.

Consent, exit codes and plan files are the command line's own: each test names
the requirement of `spec/005-plan-apply-destroy.md` it holds.
"""

from __future__ import annotations

import json
import os
import re
import stat
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import typer
from typer.testing import CliRunner, Result

import fake_github
import project
from fake_github import FakeGitHub
from fakes import FakeDatabricks
from lely import cli, planfile
from lely.model import Workspace

runner = CliRunner()

_ANSI = re.compile(r"\x1b\[[0-9;]*m")

#: The scenario without the step that waits on a first deploy.
READY = project.LELY_YML.replace("resources.jobs.bar.id", "resources.jobs.backfill.id")


class Lely:
    """`lely`, run in a project folder, with a terminal or without one."""

    def __init__(self, root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.root = root
        self.fake = project.databricks(root)
        self._monkeypatch = monkeypatch
        self.terminal(False)

    def terminal(self, there: bool) -> None:
        self._monkeypatch.setattr(cli, "_interactive", lambda: there)

    def __call__(self, *args: str, typed: str | None = None) -> Result:
        result = runner.invoke(cli.app, list(args), input=typed)
        if result.exception and not isinstance(result.exception, SystemExit):
            raise result.exception
        return result

    def notified(self) -> list[str]:
        path = self.root / "notified.txt"
        return path.read_text().split() if path.exists() else []


def said(result: Result) -> str:
    return _ANSI.sub("", result.output)


@pytest.fixture
def lely(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Lely:
    project.write(tmp_path)
    run = Lely(tmp_path, monkeypatch)
    fake = (sys.executable, str(project.FAKE_DATABRICKS), str(run.fake.world))
    monkeypatch.setattr(cli, "DATABRICKS", fake)
    monkeypatch.setattr(cli, "WHOAMI", lambda profile: project.WORKSPACE)
    monkeypatch.setattr(cli, "CONNECT", lambda profile: None)
    monkeypatch.setattr(cli, "POWERS", lambda profile: "not a workspace admin")
    monkeypatch.setenv("COLUMNS", "200")
    monkeypatch.chdir(tmp_path)
    return run


@pytest.fixture
def ready(lely: Lely) -> Lely:
    project.write(lely.root, READY)
    return lely


# -- validate, steps ---------------------------------------------------------------


def test_validate_prints_the_wiring(lely: Lely) -> None:
    """003/R8."""
    result = lely("validate")
    assert result.exit_code == 0, said(result)
    assert "lely.yml: 5 steps" in said(result)
    assert "app       takes  model_version ← model.version" in said(result)
    assert "notify    takes  ← app.resources.jobs.bar.id" in said(result)
    assert "model     gives  version (at plan)" in said(result)
    assert lely.fake.calls == []  # offline


def test_validate_fails_with_located_problems(lely: Lely) -> None:
    (lely.root / "lely.yml").write_text("steps:\n  - uses: bundle\n    with: {paht: x}\n")
    result = lely("validate")
    assert result.exit_code == 1
    assert "lely.yml:3:12: unknown option `paht`" in said(result)


def test_the_config_is_found_from_a_subfolder(
    lely: Lely, monkeypatch: pytest.MonkeyPatch
) -> None:
    """003/R5a: and a step's paths stay relative to the config."""
    deep = lely.root / "src" / "pkg"
    deep.mkdir(parents=True)
    monkeypatch.chdir(deep)
    assert "lely.yml: 5 steps" in said(lely("validate"))
    result = lely("plan", "-t", "dev")
    assert result.exit_code == 0, said(result)
    assert "→ version = 14" in said(result)  # ./ops/steps.py, from the config


def test_a_project_in_pyproject(lely: Lely) -> None:
    """003/R5."""
    (lely.root / "lely.yml").unlink()
    project.write(lely.root, toml=True)
    assert "pyproject.toml: 5 steps" in said(lely("validate"))
    assert lely("plan", "-t", "dev").exit_code == 0


def test_a_plugin_whose_default_cant_be_made_is_said_and_the_rest_listed(
    lely: Lely,
) -> None:
    """Found in the fourth review: `lely steps` and `lely schema` ended in a
    traceback, and what a default's function printed landed in the schema."""
    (lely.root / "ops" / "odd.py").write_text(
        "from dataclasses import dataclass, field\n"
        "def loud():\n    print('LOUD'); return ['a']\n"
        "def broken():\n    raise RuntimeError('no default today')\n"
        "class Loud:\n"
        "    @dataclass(frozen=True)\n"
        "    class Options:\n        names: list = field(default_factory=loud)\n"
        "    def plan(self, ctx): pass\n    def apply(self, ctx, plan): pass\n"
        "class Broken(Loud):\n"
        "    @dataclass(frozen=True)\n"
        "    class Options:\n        names: list = field(default_factory=broken)\n"
    )
    project.write(
        lely.root,
        "steps:\n  - name: a\n    uses: ./ops/odd.py:Loud\n"
        "  - name: b\n    uses: ./ops/odd.py:Broken\n",
    )
    listed = lely("steps")
    assert listed.exit_code == 0
    shown = " ".join(said(listed).split())
    assert "names: list default ['a']" in shown
    assert "the default of its option `names` can't be made: RuntimeError" in shown
    assert "bundle.run" in shown
    failed = lely("schema")
    assert failed.exit_code == 1
    assert "can't be made: RuntimeError" in " ".join(said(failed).split())
    project.write(lely.root, "steps:\n  - name: a\n    uses: ./ops/odd.py:Loud\n")
    schema = lely("schema")
    assert schema.exit_code == 0
    assert json.loads(schema.stdout)["title"] == "lely"


def test_steps_lists_plugins_with_what_they_take_give_and_can_do(lely: Lely) -> None:
    """002, done when: options, outputs and when each is known, and whether it
    has an overview and a destroy."""
    result = lely("steps")
    assert result.exit_code == 0, said(result)
    text = said(result)
    assert "bundle  built-in" in text
    assert "path: a string  default '.'" in text
    assert (
        "gives  resources.<type>.<key>.id, resources.<type>.<key>.url (once it exists)"
    ) in text
    assert "can    plan, apply, list, destroy\n" in text  # bundle
    assert "can    plan, apply, destroy\n" in text  # command: nothing to list
    assert "bundle.run  built-in" in text
    assert "bundle: the name of a step  required" in text
    assert "can    plan, apply\n" in text
    assert "gives  what a step lists, by its options" in text  # command
    assert "can    plan\n" in text  # stevin: parked
    # and the plugin this project names
    assert "./ops/steps.py:LatestModel  file ./ops/steps.py" in text
    assert "gives  version (at plan)" in text


def _commands() -> dict[str, Any]:
    group: Any = typer.main.get_command(cli.app)
    return dict(group.commands)


@pytest.mark.parametrize("name", sorted(_commands()))
def test_help_shows_every_bracket_it_was_written_with(
    name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Help is read as Rich markup, where `[tool.lely]` is a style nobody
    defined: it was dropped, and every `--help` said "a pyproject.toml with .
    Found from here up". Nor is what stops that shown: a typer that didn't
    read help as markup (before 0.20.1) showed the backslash."""
    monkeypatch.setenv("COLUMNS", "200")
    result = runner.invoke(cli.app, [name, "--help"])
    assert result.exit_code == 0, result.output
    shown = " ".join(_ANSI.sub("", result.output).split())
    command = _commands()[name]
    written = [command.help or ""]
    written += [getattr(param, "help", None) or "" for param in command.params]
    for text in written:
        for bracket in re.findall(r"\[[^\[\]]*\]", text.replace("\\[", "[")):
            assert bracket in shown, f"`lely {name} --help` lost {bracket}"
    assert "\\[" not in shown
    if any(param.name == "path" for param in command.params):
        assert "a pyproject.toml with [tool.lely]. Found from here up" in shown


def test_what_schema_says_of_a_pyproject_names_its_section(lely: Lely) -> None:
    """The same bracket, lost the same way: "a `` section in pyproject.toml"."""
    (lely.root / "lely.yml").unlink()
    project.write(lely.root, toml=True)
    result = lely("schema", "-o", "lely.schema.json")
    assert result.exit_code == 0, said(result)
    assert (
        "a `[tool.lely]` section in pyproject.toml has no schema of its own"
    ) in " ".join(said(result).split())


def test_the_commands_help_is_read_for_are_all_of_them() -> None:
    assert sorted(_commands()) == [
        "apply",
        "destroy",
        "doctor",
        "plan",
        "schema",
        "show",
        "status",
        "steps",
        "ui",
        "validate",
    ]
    with_a_config = [
        name
        for name, command in _commands().items()
        if any(param.name == "path" for param in command.params)
    ]
    assert len(with_a_config) == 8  # all but `show` and `ui`: they read a file


def test_version() -> None:
    result = runner.invoke(cli.app, ["--version"])
    assert result.output.startswith("lely ")


# -- plan, show --------------------------------------------------------------------


def test_plan_always_needs_a_target(lely: Lely) -> None:
    """R37: there is no default target."""
    result = lely("plan")
    assert result.exit_code == 2
    assert lely.fake.calls == []


def test_plan_shows_the_plan_and_names_the_workspace(lely: Lely) -> None:
    """R1, R35."""
    result = lely("plan", "-t", "dev")
    assert result.exit_code == 0, said(result)
    assert (
        "lely plan · target dev · https://dbc-example.cloud.databricks.com as "
        "jane@example.com"
    ) in said(result)
    assert "Plan: 2 changes · 2 runs · 0 destructive · 1 waiting" in said(result)
    assert "Applied from a file, this stops before `notify`" in said(result)  # R27
    assert set(lely.fake.verbs) == {"summary", "plan"}


def test_plan_writes_a_file_and_show_renders_it(lely: Lely) -> None:
    """R1, 001/R5."""
    result = lely("plan", "-t", "dev", "-o", "plan.json")
    assert result.exit_code == 0, said(result)
    assert "Wrote plan.json" in said(result)
    written = planfile.loads((lely.root / "plan.json").read_text())
    assert (written.kind, written.target) == ("apply", "dev")
    lely.fake.clear_calls()
    shown = lely("show", "plan.json")
    assert shown.exit_code == 0, said(shown)
    assert "▶ runs jobs.backfill" in said(shown)
    assert lely.fake.calls == []  # no workspace


def test_plan_as_json(lely: Lely) -> None:
    result = lely("plan", "-t", "dev", "-f", "json")
    assert result.exit_code == 0, said(result)
    document = json.loads(result.stdout)
    assert [s["name"] for s in document["steps"]] == [
        "model",
        "app",
        "notify",
        "backfill",
        "warm",
    ]


def test_a_failing_cli_fails_the_plan(lely: Lely) -> None:
    (lely.fake.world / "fail-plan").write_text("workspace unreachable")
    result = lely("plan", "-t", "dev")
    assert result.exit_code == 1
    assert "`databricks bundle plan` failed" in said(result)
    assert "workspace unreachable" in said(result)


def test_a_plan_file_this_lely_doesnt_read_is_refused(lely: Lely) -> None:
    """R3."""
    (lely.root / "old.json").write_text(json.dumps({"format_version": 1}))
    result = lely("show", "old.json")
    assert result.exit_code == 1
    assert "format 1; this lely reads format 4. Run `lely plan` again." in said(result)
    assert lely("show", "nope.json").exit_code == 1


# -- apply: consent ----------------------------------------------------------------


def test_with_no_terminal_and_no_yes_apply_refuses(ready: Lely) -> None:
    """R17: a forgotten flag is a failed job, never an unreviewed deploy."""
    result = ready("apply", "-t", "dev")
    assert result.exit_code == 2
    assert "Pass --yes to run without asking." in said(result)
    assert "deploy" not in ready.fake.verbs


def test_yes_in_the_command_runs_without_asking(ready: Lely) -> None:
    """R17."""
    result = ready("apply", "-t", "dev", "--yes")
    assert result.exit_code == 0, said(result)
    assert "Applied: 3 steps." in said(result)
    assert set(ready.fake.deployed()) == {"jobs.backfill", "jobs.bar", "pipelines.foo"}
    assert ready.notified() == ["771"]
    # R10: what now exists, and what this run did to it
    assert re.search(r"job\s+jobs\.bar\s+job bar\s+\d+\s+created", said(result))
    assert re.search(r"job\s+jobs\.backfill\s+backfill\s+771\s+unchanged", said(result))


def test_at_a_terminal_apply_shows_the_plan_and_asks(ready: Lely) -> None:
    """R4, R35: the question names the workspace and the identity."""
    ready.terminal(True)
    result = ready("apply", "-t", "dev", typed="n\n")
    assert result.exit_code == 2
    assert "Plan: 2 changes · 3 runs · 0 destructive" in said(result)
    assert (
        "Apply this plan to target `dev` on https://dbc-example.cloud.databricks.com "
        "as jane@example.com?"
    ) in said(result)
    assert "Not approved. Nothing was run." in said(result)
    assert "deploy" not in ready.fake.verbs
    assert ready("apply", "-t", "dev", typed="y\n").exit_code == 0
    assert "deploy" in ready.fake.verbs


def test_apply_without_a_file_needs_a_target(
    ready: Lely, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R37 — and it is refused before anything is reached: the workspace was
    asked who is running first, so the refusal waited on a sign-in, and
    without credentials the command failed with 1 instead."""

    def reached(profile: str | None) -> Workspace:
        raise AssertionError("the workspace was reached")

    monkeypatch.setattr(cli, "WHOAMI", reached)
    (ready.root / "lely.yml").write_text("not: [a config")  # not read either
    result = ready("apply", "--yes")
    assert result.exit_code == 2
    assert "Give the target: `lely apply -t <target>`." in said(result)
    assert ready.fake.calls == []


def test_a_destructive_change_is_refused_without_the_flag(ready: Lely) -> None:
    """R8: before anything runs — and before anything is asked. Here the bundle
    no longer declares a job that is deployed, so the deploy would delete it."""
    bundle = {**project.BUNDLE, "resources": {"jobs": {"bar": {"name": "job bar"}}}}
    (ready.root / "fake-bundle.json").write_text(json.dumps(bundle))
    (ready.root / "lely.yml").write_text(
        "steps:\n  - name: app\n    uses: bundle\n    with: {vars: {model_version: 1}}\n"
    )
    result = ready("apply", "-t", "dev", "--yes")
    assert result.exit_code == 2
    assert "app: jobs.backfill" in said(result)  # it would be deleted
    assert "Pass --allow-destructive to apply them." in said(result)
    assert "deploy" not in ready.fake.verbs
    assert ready("apply", "-t", "dev", "--yes", "--allow-destructive").exit_code == 0
    assert set(ready.fake.deployed()) == {"jobs.bar"}


# -- apply: a step that was waiting -------------------------------------------------


def test_yes_without_a_file_runs_a_waiting_step_when_it_gets_there(lely: Lely) -> None:
    """R28: lely's unreviewed way of running."""
    result = lely("apply", "-t", "dev", "--yes")
    assert result.exit_code == 0, said(result)
    bar = lely.fake.deployed()["jobs.bar"]["id"]
    assert lely.notified() == [bar]
    assert f"▶ runs ./ops/notify.sh {bar}" in said(result)


def test_at_a_terminal_lely_asks_again_at_a_waiting_step(lely: Lely) -> None:
    """R29: the same consent, given at the moment it can be."""
    lely.terminal(True)
    result = lely("apply", "-t", "dev", typed="y\nn\n")
    assert result.exit_code == 2
    assert "Run step `notify` on target `dev`" in said(result)
    assert "Step `notify` wasn't approved. Nothing more was run." in said(result)
    assert "jobs.bar" in lely.fake.deployed()  # the bundle ran: it was approved
    assert lely.notified() == []
    assert lely.fake.runs == []  # R30: never out of order
    assert lely("apply", "-t", "dev", typed="y\ny\n").exit_code == 0
    assert len(lely.notified()) == 1


def test_a_reviewed_file_stops_at_a_waiting_step_and_takes_a_second_round(
    lely: Lely,
) -> None:
    """R27, R31: 2 says "plan again", and the next plan shows the step ready."""
    assert lely("plan", "-t", "dev", "-o", "plan.json").exit_code == 0
    first = lely("apply", "plan.json", "--yes")
    assert first.exit_code == 2
    assert "Plan again: the next plan shows it." in said(first)
    assert "ran: app" in said(first)  # `model` had nothing to do: it didn't run
    assert "refused: notify" in said(first)  # a refusal isn't a failure
    assert "never started: backfill" in said(first)
    assert "Nothing was rolled back." in said(first)
    # R22: after a refusal, the same file is refused again
    assert lely("apply", "plan.json", "--yes").exit_code == 2
    assert lely("plan", "-t", "dev", "-o", "plan.json").exit_code == 0
    second = lely("apply", "plan.json", "--yes")
    assert second.exit_code == 0, said(second)
    assert len(lely.notified()) == 1
    # 004/R7a: nothing is remembered — what the first round created shows as
    # unchanged in the round that finishes it
    assert re.search(r"jobs\.bar\s+job bar\s+\d+\s+unchanged", said(second))


# -- apply: a plan file ------------------------------------------------------------


def planned(lely: Lely, *args: str) -> None:
    result = lely("plan", "-t", "dev", "-o", "plan.json", *args)
    assert result.exit_code == 0, said(result)
    lely.fake.clear_calls()


def test_a_file_is_asked_about_too(ready: Lely) -> None:
    """R20."""
    planned(ready)
    assert ready("apply", "plan.json").exit_code == 2  # no terminal, no --yes
    ready.terminal(True)
    result = ready("apply", "plan.json", typed="y\n")
    assert result.exit_code == 0, said(result)
    assert "Apply this plan to target `dev`" in said(result)
    assert "+ jobs.bar" in said(result)  # it shows what is in it


def test_a_file_for_another_target_than_the_command_says_is_refused(ready: Lely) -> None:
    planned(ready)
    result = ready("apply", "plan.json", "-t", "prod", "--yes")
    assert result.exit_code == 2
    assert "made for target `dev`, and the command says `prod`" in said(result)
    assert ready.fake.calls == []


def test_a_file_is_refused_when_a_steps_options_changed(ready: Lely) -> None:
    """R5: what is compared is the config as lely reads it."""
    planned(ready)
    text = (ready.root / "lely.yml").read_text()
    (ready.root / "lely.yml").write_text(text + "\n# an unrelated note\n")
    assert ready("apply", "plan.json", "--yes").exit_code == 0  # not the text
    planned(ready)
    (ready.root / "lely.yml").write_text(text.replace("jobs.backfill}", "jobs.bar}"))
    result = ready("apply", "plan.json", "--yes")
    assert result.exit_code == 2
    assert "Step `backfill` is configured differently" in said(result)
    assert ready.fake.calls == []


def test_a_file_made_against_one_workspace_is_refused_on_another(
    ready: Lely, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R35."""
    planned(ready)
    other = Workspace("https://prod.cloud.databricks.com", "jane@example.com")
    monkeypatch.setattr(cli, "WHOAMI", lambda profile: other)
    result = ready("apply", "plan.json", "--yes")
    assert result.exit_code == 2
    assert "this run talks to https://prod.cloud.databricks.com" in said(result)
    assert ready.fake.calls == []


def test_a_file_is_refused_on_another_git_tree(ready: Lely) -> None:
    """R36: what was reviewed is what is deployed."""

    def git(*args: str) -> None:
        identity = ["-c", "user.name=t", "-c", "user.email=t@example.com"]
        subprocess.run(["git", *identity, *args], cwd=ready.root, check=True)

    (ready.root / ".gitignore").write_text(".world/\nplan.json\nnotified.txt\n")
    git("init", "-q")
    git("add", ".")
    git("commit", "-q", "-m", "first")
    planned(ready)
    assert planfile.loads((ready.root / "plan.json").read_text()).source.tree
    (ready.root / "ops" / "notify.sh").write_text("#!/bin/sh\necho changed\n")
    dirty = ready("apply", "plan.json", "--yes")
    assert dirty.exit_code == 2
    assert "uncommitted changes that the plan was made without" in said(dirty)
    git("commit", "-q", "-am", "second")
    moved = ready("apply", "plan.json", "--yes")
    assert moved.exit_code == 2
    assert "The plan was made on git tree" in said(moved)
    assert ready.fake.calls == []


def test_outside_git_the_plan_says_it_couldnt_be_recorded(lely: Lely) -> None:
    """R36."""
    assert "Not in a git repository" in said(lely("plan", "-t", "dev"))


def test_apply_cant_be_handed_a_destroy(ready: Lely) -> None:
    """R20: as first written, `lely apply destroy.json --yes` would have
    destroyed a target with neither "destroy" nor its name in the command."""
    planned(ready, "--destroy")
    result = ready("apply", "plan.json", "--yes")
    assert result.exit_code == 2
    assert "`lely apply` only applies" in said(result)
    assert "lely destroy plan.json -t dev" in said(result)
    assert ready.fake.deployed() == project.DEPLOYED


# -- apply: how it ends ------------------------------------------------------------


def test_a_failed_step_ends_with_1_and_three_lists(ready: Lely) -> None:
    """R21, R24, R31."""
    (ready.root / "ops" / "notify.sh").write_text(
        "#!/bin/sh\necho 'no route' >&2\nexit 7\n"
    )
    result = ready("apply", "-t", "dev", "--yes")
    assert result.exit_code == 1
    assert "ran: app" in said(result)
    assert "failed: notify" in said(result)
    assert "never started: backfill" in said(result)
    assert "Nothing was rolled back." in said(result)
    assert "no route" in said(result)


def test_the_result_as_json(ready: Lely) -> None:
    """R21."""
    result = ready("apply", "-t", "dev", "--yes", "-f", "json")
    assert result.exit_code == 0, said(result)
    document = json.loads(result.stdout)
    assert document["outcome"] == "done"
    assert document["ran"] == ["app", "notify", "backfill"]
    assert document["failed"] == document["refused"] == document["not_started"] == []
    items = document["steps"][1]["overview"]["items"]
    assert {item["key"]: item["happened"] for item in items} == {
        "jobs.backfill": "unchanged",
        "jobs.bar": "created",
        "pipelines.foo": "created",
    }


def test_from_resumes_at_a_step(ready: Lely) -> None:
    """R23."""
    result = ready("apply", "-t", "dev", "--yes", "--from", "backfill")
    assert result.exit_code == 0, said(result)
    assert "deploy" not in ready.fake.verbs
    assert ready.notified() == []
    assert len(ready.fake.runs) == 1


# -- destroy -----------------------------------------------------------------------


def test_destroy_always_needs_a_target(lely: Lely) -> None:
    """R19, R37: there is no default target to destroy."""
    assert lely("destroy", "--yes").exit_code == 2
    assert lely.fake.calls == []


def test_to_destroy_at_a_terminal_the_answer_is_the_targets_name(lely: Lely) -> None:
    """R18: not `y`, so that `prod` is never destroyed by a reflex."""
    lely.terminal(True)
    wrong = lely("destroy", "-t", "dev", typed="y\n")
    assert wrong.exit_code == 2
    assert "Destroy plan: 1 change · 0 runs · 1 destructive" in said(wrong)
    assert (
        "This destroys target `dev` on https://dbc-example.cloud.databricks.com as "
        "jane@example.com."
    ) in said(wrong)
    assert "That isn't the target's name. Nothing was destroyed." in said(wrong)
    assert lely.fake.deployed() == project.DEPLOYED
    right = lely("destroy", "-t", "dev", typed="dev\n")
    assert right.exit_code == 0, said(right)
    assert "Destroyed: 1 step." in said(right)
    assert lely.fake.deployed() == {}


def test_without_a_terminal_consent_to_destroy_is_given_in_the_command(
    lely: Lely,
) -> None:
    """R17, R19."""
    refused = lely("destroy", "-t", "dev")
    assert refused.exit_code == 2
    assert "Pass --yes to destroy target `dev` without asking." in said(refused)
    assert lely.fake.deployed() == project.DEPLOYED
    assert lely("destroy", "-t", "dev", "--yes").exit_code == 0
    assert lely.fake.deployed() == {}


def test_a_destroy_can_be_saved_reviewed_and_run_as_a_file(lely: Lely) -> None:
    """R14: one file format for both; the target is said again."""
    assert lely("plan", "-t", "dev", "--destroy", "-o", "destroy.json").exit_code == 0
    shown = lely("show", "destroy.json")
    assert "lely destroy plan · target dev" in said(shown)
    assert "- jobs.backfill  destructive" in said(shown)
    wrong = lely("destroy", "destroy.json", "-t", "prod", "--yes")
    assert wrong.exit_code == 2
    assert "made for target `dev`, and the command says `prod`" in said(wrong)
    assert lely.fake.deployed() == project.DEPLOYED
    assert lely("destroy", "destroy.json", "-t", "dev", "--yes").exit_code == 0
    assert lely.fake.deployed() == {}


def test_a_destroy_file_is_asked_about_with_the_targets_name(lely: Lely) -> None:
    """R20."""
    lely("plan", "-t", "dev", "--destroy", "-o", "destroy.json")
    lely.terminal(True)
    assert lely("destroy", "destroy.json", "-t", "dev", typed="yes\n").exit_code == 2
    assert lely("destroy", "destroy.json", "-t", "dev", typed="dev\n").exit_code == 0


def test_destroy_cant_be_handed_a_plan_to_apply(lely: Lely) -> None:
    lely("plan", "-t", "dev", "-o", "plan.json")
    result = lely("destroy", "plan.json", "-t", "dev", "--yes")
    assert result.exit_code == 2
    assert "`lely destroy` only destroys" in said(result)


def test_destroying_what_isnt_deployed_says_so_and_ends_as_done(
    tmp_path: Path, lely: Lely
) -> None:
    """R16: and there is nothing to ask about."""
    lely.fake.world.joinpath("state.json").unlink()
    result = lely("destroy", "-t", "dev")
    assert result.exit_code == 0, said(result)
    assert "Nothing to destroy." in said(result)
    assert "destroy" not in FakeDatabricks(lely.fake.world).verbs


# -- status, doctor ----------------------------------------------------------------


def test_status_shows_what_is_deployed_and_whose_view_it_is(lely: Lely) -> None:
    """R32, 004/R9b."""
    result = lely("status", "-t", "dev")
    assert result.exit_code == 0, said(result)
    text = said(result)
    assert "lely status · target dev · https://dbc-example.cloud.databricks.com" in text
    assert re.search(r"job\s+jobs\.backfill\s+backfill\s+771", text)
    assert re.search(r"job\s+jobs\.bar\s+job bar\s+not deployed", text)
    assert "as seen by jane@example.com under /Workspace/Users/jane@example.com" in text
    assert "nothing to list" in text
    assert "skipped: not for target `dev`" in text
    assert set(lely.fake.verbs) <= {"summary", "plan"}
    assert lely("status").exit_code == 2  # R37


def test_status_as_json(lely: Lely) -> None:
    document: Any = json.loads(lely("status", "-t", "dev", "-f", "json").stdout)
    assert [s["name"] for s in document["steps"]][:2] == ["model", "app"]
    assert document["steps"][1]["overview"]["items"][0]["id"] == "771"


def test_doctor_reports_the_tools_the_workspace_and_the_identity(lely: Lely) -> None:
    """R33, 002/R13a."""
    result = lely("doctor")
    assert result.exit_code == 0, said(result)
    text = said(result)
    assert "the Databricks CLI: Databricks CLI v1.18.0" in text
    assert "the workspace: https://dbc-example.cloud.databricks.com as jane" in text
    assert "not a workspace admin" in text
    assert "credentials that can read and nothing more" in text
    assert "step `notify` runs `./ops/notify.sh`" in text
    assert "step `app` runs `databricks`" in text
    assert lely.fake.verbs == []  # it changes nothing, and plans nothing


def test_doctor_fails_when_a_tool_is_missing(
    lely: Lely, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "DATABRICKS", ("no-such-databricks",))
    (lely.root / "ops" / "notify.sh").unlink()
    result = lely("doctor")
    assert result.exit_code == 1
    assert "`no-such-databricks` isn't on PATH" in said(result)
    assert "step `notify` runs `./ops/notify.sh`: not found" in said(result)


# -- found in review ---------------------------------------------------------------


@pytest.mark.parametrize(
    "command",
    [
        ("plan",),
        ("status",),
        ("apply", "--yes"),
        ("destroy", "--yes"),
    ],
)
def test_an_empty_target_is_no_target(lely: Lely, command: tuple[str, ...]) -> None:
    """R37. `-t "$TARGET"` with the variable unset: the Databricks CLI would
    read an empty target as "the default one", and there is none."""
    for empty in ("", "  "):
        result = lely(*command, "-t", empty)
        assert result.exit_code == 2, said(result)
        assert "there is no default target" in said(result)
    assert lely.fake.calls == []
    assert lely.fake.deployed() == project.DEPLOYED


def test_pressing_enter_doesnt_destroy(lely: Lely) -> None:
    """R18."""
    lely.terminal(True)
    result = lely("destroy", "-t", "dev", typed="\n")
    assert result.exit_code == 2
    assert lely.fake.deployed() == project.DEPLOYED


def test_a_destroy_file_edited_to_hide_what_it_removes_is_refused(lely: Lely) -> None:
    """R17, R20. One field of a real destroy plan changed by hand: the step is
    marked skipped, its changes left in. As first built this showed "Nothing to
    destroy", asked nothing, and destroyed."""
    lely("plan", "-t", "dev", "--destroy", "-o", "destroy.json")
    path = lely.root / "destroy.json"
    document = json.loads(path.read_text())
    document["steps"][1]["skipped"] = "nothing deployed"
    path.write_text(json.dumps(document))
    lely.fake.clear_calls()
    for command in (("show", "destroy.json"), ("destroy", "destroy.json", "-t", "dev")):
        result = lely(*command)
        assert result.exit_code == (1 if command[0] == "show" else 2), said(result)
        assert "step `app` is skipped and holds changes" in said(result)
    assert lely.fake.deployed() == project.DEPLOYED
    assert "destroy" not in lely.fake.verbs


def test_a_file_lely_cant_read_is_a_refusal_when_it_would_be_run(lely: Lely) -> None:
    """R3, R31: "plan again" ends with 2. `show` changes nothing: 1."""
    old = lely.root / "old.json"
    old.write_text(json.dumps({"format_version": 1}))
    for command in (("apply", "old.json", "--yes"), ("destroy", "old.json", "-t", "dev")):
        result = lely(*command)
        assert result.exit_code == 2, said(result)
        assert "Run `lely plan` again." in said(result)
    assert lely("show", "old.json").exit_code == 1
    old.write_bytes(b"\xff\xfe\x00not text")
    assert lely("apply", "old.json", "--yes").exit_code == 2
    assert "it isn't text" in said(lely("show", "old.json"))
    assert lely.fake.calls == []


def test_a_from_that_names_no_step_is_refused_before_anything_is_planned(
    ready: Lely,
) -> None:
    ready.terminal(True)
    result = ready("apply", "-t", "dev", "--from", "nope", typed="y\n")
    assert result.exit_code == 2
    assert "`--from nope`: no step `nope` runs for target `dev`" in said(result)
    assert "Apply this plan" not in said(result)  # nothing was asked
    assert ready.fake.calls == []
    assert ready("destroy", "-t", "dev", "--yes", "--from", "nope").exit_code == 2
    assert ready.fake.calls == []


def test_a_refusal_before_the_first_step_is_said_as_json_too(ready: Lely) -> None:
    """With `-f json`, whatever reads stdout reads something."""
    result = ready("apply", "-t", "dev", "-f", "json")  # no terminal, no --yes
    assert result.exit_code == 2
    document = json.loads(result.stdout)
    assert (document["kind"], document["target"]) == ("apply", "dev")
    assert document["outcome"] == "refused"
    assert "Pass --yes" in document["message"]
    assert document["steps"] == []


def test_the_question_names_who_runs_not_who_planned(
    ready: Lely, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R35: with a file, the two need not be the same — a plan is made with
    credentials that can read, and run with ones that can write."""
    planned(ready)
    deployer = Workspace(project.WORKSPACE.host, "deployer-sp@example.com")
    monkeypatch.setattr(cli, "WHOAMI", lambda profile: deployer)
    ready.terminal(True)
    result = ready("apply", "plan.json", typed="n\n")
    assert (
        "Apply this plan to target `dev` on https://dbc-example.cloud.databricks.com "
        "as deployer-sp@example.com (the plan was made as jane@example.com)?"
    ) in said(result)


def test_a_plan_that_cant_be_written_is_a_message(lely: Lely) -> None:
    result = lely("plan", "-t", "dev", "-o", "missing/plan.json")
    assert result.exit_code == 1
    assert "Can't write the plan to missing/plan.json" in said(result)


def test_a_destroy_plan_committed_for_review_doesnt_refuse_itself(lely: Lely) -> None:
    """R14 and R36 together: a destroy can go through a pull request, and the
    plan is still held to the tree it was made on — the tree without itself."""

    def git(*args: str) -> None:
        identity = ["-c", "user.name=t", "-c", "user.email=t@example.com"]
        subprocess.run(["git", *identity, *args], cwd=lely.root, check=True)

    (lely.root / ".gitignore").write_text(".world/\nnotified.txt\n")
    git("init", "-q")
    git("add", ".")
    git("commit", "-q", "-m", "first")
    assert lely("plan", "-t", "dev", "--destroy", "-o", "destroy.json").exit_code == 0
    git("add", "destroy.json")
    git("commit", "-q", "-m", "destroy dev, for review")
    result = lely("destroy", "destroy.json", "-t", "dev", "--yes")
    assert result.exit_code == 0, said(result)
    assert lely.fake.deployed() == {}


def test_a_reviewed_file_covers_a_bundle_outside_the_configs_folder(
    tmp_path: Path, lely: Lely, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R36: the bundle's files are in no plan, so the tree that is recorded has
    to reach as far as a step can — here `path: ../bundle`."""

    def git(*args: str) -> None:
        identity = ["-c", "user.name=t", "-c", "user.email=t@example.com"]
        subprocess.run(["git", *identity, *args], cwd=tmp_path, check=True)

    deploy = tmp_path / "deploy"
    deploy.mkdir()
    (tmp_path / "lely.yml").unlink()
    (tmp_path / "bundle").mkdir()
    (tmp_path / "fake-bundle.json").rename(tmp_path / "bundle" / "fake-bundle.json")
    (deploy / "lely.yml").write_text(
        "steps:\n  - name: app\n    uses: bundle\n"
        "    with: {path: ../bundle, vars: {model_version: 1}}\n"
    )
    (tmp_path / ".gitignore").write_text(".world/\nplan.json\n")
    git("init", "-q")
    git("add", ".")
    git("commit", "-q", "-m", "first")
    monkeypatch.chdir(deploy)
    assert lely("plan", "-t", "dev", "-o", "plan.json").exit_code == 0
    (tmp_path / "bundle" / "notebook.py").write_text("# v2, unreviewed\n")
    git("add", ".")
    git("commit", "-q", "-m", "a notebook nobody reviewed")
    lely.fake.clear_calls()
    result = lely("apply", "plan.json", "--yes")
    assert result.exit_code == 2
    assert "The plan was made on git tree" in said(result)
    assert lely.fake.calls == []


# -- found in the second review ------------------------------------------------------

TEAM = """\
steps:
  - name: app
    uses: bundle
  - name: migrate
    uses: command
    with:
      apply: [./ops/migrate.sh]
      destroy: [./ops/migrate.sh, --drop]
"""


def two_teams(lely: Lely) -> None:
    """Two projects in one repository, started from the same template."""
    from fakes import write_bundle

    for path in ("lely.yml", "fake-bundle.json"):
        (lely.root / path).unlink()
    for name in ("team-a", "team-b"):
        folder = lely.root / name
        (folder / "ops").mkdir(parents=True)
        (folder / "lely.yml").write_text(TEAM)
        script = folder / "ops" / "migrate.sh"
        script.write_text(f'#!/bin/sh\necho "{name} $1" >> ../migrated.txt\n')
        script.chmod(0o755)
        resources = {"jobs": {"etl": {"name": f"etl of {name}"}}}
        write_bundle(folder, {"name": name, "resources": resources})
    (lely.root / ".gitignore").write_text(
        ".world/\nmigrated.txt\n*.json\n!fake-bundle.json\n"
    )
    identity = ["-c", "user.name=t", "-c", "user.email=t@example.com"]
    for args in (["init", "-q"], ["add", "."], ["commit", "-q", "-m", "two teams"]):
        subprocess.run(["git", *identity, *args], cwd=lely.root, check=True)


def test_a_plan_for_one_project_isnt_run_on_another_in_the_same_repository(
    lely: Lely,
) -> None:
    """R5, R36. Both projects share the repository's tree and, as written,
    their steps. The plan says which project it is for, and is held to it."""
    two_teams(lely)
    planned_ = lely("plan", "-t", "dev", "-c", "team-a/lely.yml", "-o", "plan.json")
    assert planned_.exit_code == 0, said(planned_)
    assert "lely plan · project team-a · target dev" in said(planned_)
    other = lely("apply", "plan.json", "-c", "team-b/lely.yml", "--yes")
    assert other.exit_code == 2
    assert (
        "The plan was made for the project in `team-a`, and this is the one in `team-b`."
    ) in said(other)
    assert lely.fake.deployed("team-b") == {}
    assert not (lely.root / "migrated.txt").exists()
    own = lely("apply", "plan.json", "-c", "team-a/lely.yml", "--yes")
    assert own.exit_code == 0, said(own)
    assert (lely.root / "migrated.txt").read_text() == "team-a \n"

    # and the same for a destroy
    assert (
        lely(
            "plan",
            "-t",
            "dev",
            "--destroy",
            "-c",
            "team-a/lely.yml",
            "-o",
            "destroy.json",
        ).exit_code
        == 0
    )
    wrong = lely("destroy", "destroy.json", "-t", "dev", "-c", "team-b/lely.yml", "--yes")
    assert wrong.exit_code == 2
    assert "team-a --drop" not in (lely.root / "migrated.txt").read_text()
    assert set(lely.fake.deployed("team-a")) == {"jobs.etl"}


def test_a_plan_file_is_for_a_clean_checkout(ready: Lely) -> None:
    """R36. A plan made with uncommitted changes used to be held to nothing:
    any later commit could be applied with it. Now it says so, and is not run
    from a file. Nor is a clean plan run on a checkout where something was
    staged since — which leaves every tracked file as it was."""

    def git(*args: str) -> None:
        identity = ["-c", "user.name=t", "-c", "user.email=t@example.com"]
        subprocess.run(["git", *identity, *args], cwd=ready.root, check=True)

    (ready.root / ".gitignore").write_text(".world/\nplan.json\nnotified.txt\n")
    git("init", "-q")
    git("add", ".")
    git("commit", "-q", "-m", "first")
    script = ready.root / "ops" / "notify.sh"
    script.write_text('#!/bin/sh\necho "v2 $1" >> notified.txt\n')
    made_dirty = ready("plan", "-t", "dev", "-o", "plan.json")
    assert "Planned with uncommitted changes" in said(made_dirty)
    assert "won't run it from a file" in said(made_dirty)
    git("commit", "-q", "-am", "v2")
    refused = ready("apply", "plan.json", "--yes")
    assert refused.exit_code == 2
    assert "The plan was made with uncommitted changes" in said(refused)
    assert ready.fake.verbs.count("deploy") == 0

    planned(ready)  # on the clean checkout
    (ready.root / "ops" / "new.sh").write_text("#!/bin/sh\n")
    git("add", "ops/new.sh")  # staged since: no tracked file changed
    staged = ready("apply", "plan.json", "--yes")
    assert staged.exit_code == 2
    assert "uncommitted changes that the plan was made without" in said(staged)
    git("reset", "-q", "--", "ops/new.sh")
    assert ready("apply", "plan.json", "--yes").exit_code == 0
    assert ready.notified() == ["v2", "771"]
    # without a file there is nothing to hold a plan to, and nothing stops it
    script.write_text('#!/bin/sh\necho "v3 $1" >> notified.txt\n')
    assert ready("apply", "-t", "dev", "--yes").exit_code == 0


def test_before_the_first_commit_the_plan_says_so(ready: Lely) -> None:
    """Not "not in a git repository", which would be false."""
    subprocess.run(["git", "init", "-q"], cwd=ready.root, check=True)
    subprocess.run(["git", "add", "lely.yml"], cwd=ready.root, check=True)
    result = ready("plan", "-t", "dev", "-o", "plan.json")
    assert result.exit_code == 0, said(result)
    assert "This repository has no commit yet" in said(result)
    assert "Not in a git repository" not in said(result)
    assert ready("apply", "-t", "dev", "--yes").exit_code == 0


def test_git_refusing_fails_a_plan_and_doesnt_stop_an_unsaved_run(
    ready: Lely, git_refuses: Callable[[], None]
) -> None:
    """R36. In a container the checkout is often someone else's, and git
    refuses it. That used to read as "not in a git repository", and the plan
    file was then held to nothing."""
    subprocess.run(["git", "init", "-q"], cwd=ready.root, check=True)
    git_refuses()
    result = ready("plan", "-t", "dev", "-o", "plan.json")
    assert result.exit_code == 1
    assert "dubious ownership" in said(result)
    assert not (ready.root / "plan.json").exists()
    # a plan that is run now and not saved is held to nothing anyway
    assert ready("apply", "-t", "dev", "--yes").exit_code == 0


def test_an_empty_target_in_a_plan_file_is_refused(ready: Lely) -> None:
    planned(ready)
    path = ready.root / "plan.json"
    document = json.loads(path.read_text())
    document["target"] = ""
    path.write_text(json.dumps(document))
    result = ready("apply", "plan.json", "--yes")
    assert result.exit_code == 2
    assert "`target` is empty" in said(result)
    assert ready.fake.calls == []


def test_a_target_no_step_runs_for_isnt_nothing_to_do(lely: Lely) -> None:
    """R37."""
    (lely.root / "lely.yml").write_text(
        "steps:\n  - name: app\n    uses: bundle\n    targets: [dev, prod]\n"
        "    with: {vars: {model_version: 1}}\n"
    )
    for command, code in (
        (("plan", "-t", "prd"), 1),
        (("status", "-t", "prd"), 1),
        (("apply", "-t", "prd", "--yes"), 2),
        (("destroy", "-t", "prd", "--yes"), 2),
    ):
        result = lely(*command)
        assert result.exit_code == code, said(result)
        assert "No step runs for target `prd`" in said(result)
    assert lely.fake.calls == []


def test_a_project_that_cant_be_applied_is_refused_before_the_question(
    ready: Lely,
) -> None:
    empty = project.FAKE_STEVIN.parent / "fixtures" / "stevin-empty.json"
    stevin = (
        "  - name: tables\n    uses: stevin\n    with:\n"
        f"      executable: [{sys.executable}, {project.FAKE_STEVIN}, {empty}]\n"
    )
    (ready.root / "lely.yml").write_text(READY + stevin)
    ready.terminal(True)
    result = ready("apply", "-t", "dev", typed="y\n")
    assert result.exit_code == 2
    assert "`stevin`, which can plan and can't apply yet" in said(result)
    assert "Apply this plan" not in said(result)
    assert ready.fake.calls == []


def test_with_json_stdout_holds_json_and_nothing_else(ready: Lely) -> None:
    written = ready("plan", "-t", "dev", "-f", "json", "-o", "plan.json")
    assert written.exit_code == 0
    assert written.stdout == ""  # the plan is in the file; "Wrote …" is on stderr
    assert "Wrote plan.json" in written.stderr
    # a run that ends before its first step says which run it was
    refused = ready("apply", "plan.json", "-f", "json")  # no terminal, no --yes
    document = json.loads(refused.stdout)
    assert (document["kind"], document["target"], document["outcome"]) == (
        "apply",
        "dev",
        "refused",
    )
    assert document["workspace"] == {
        "host": project.WORKSPACE.host,
        "identity": project.WORKSPACE.identity,
    }


def test_what_a_program_says_while_a_step_runs_is_shown_never_obeyed(
    ready: Lely,
) -> None:
    """A warning the Databricks CLI or a step's command writes on stderr while
    it succeeds was never shown. It is a line of the step's progress now — on
    lely's stderr, so stdout still holds the result and nothing else — and
    what it holds for a terminal to obey is made visible."""
    (ready.fake.world / "warn-deploy").write_text(
        "Warning: jobs.bar has no owner\n\x1b[2Kgone\n"
    )
    (ready.fake.world / "warn-run").write_text("Run URL: https://x/run/1\n")
    (ready.root / "ops" / "notify.sh").write_text(
        "#!/bin/sh\necho 'WARNING: 3 rows were rejected' >&2\n"
    )
    result = ready("apply", "-t", "dev", "--yes", "-f", "json")
    assert result.exit_code == 0, said(result)
    assert json.loads(result.stdout)["outcome"] == "done"
    progress = _ANSI.sub("", result.stderr)
    for line in (
        "… app: Deployment complete!",
        "… app: Warning: jobs.bar has no owner",
        "… app: �[2Kgone",
        "… notify: WARNING: 3 rows were rejected",
        "… backfill: Run of jobs.backfill finished: SUCCESS",
        "… backfill: Run URL: https://x/run/1",
    ):
        assert line in progress
    assert "\x1b[2K" not in result.stderr


def test_escape_sequences_in_a_plan_file_dont_reach_the_terminal(ready: Lely) -> None:
    planned(ready)
    path = ready.root / "plan.json"
    document = json.loads(path.read_text())
    document["steps"][1]["plan"]["changes"][0]["summary"] = "\x1b[1A\x1b[2Kjobs.bar"
    path.write_text(json.dumps(document))
    shown = ready("show", "plan.json")
    assert "\x1b[1A" not in shown.output
    assert "�[1A�[2Kjobs.bar" in shown.output


def test_a_stream_that_cant_write_a_checkmark_doesnt_end_in_a_traceback(
    lely: Lely,
) -> None:
    """A redirected stdout on Windows is cp1252: `✓` and `←` aren't in it."""
    done = subprocess.run(
        [sys.executable, "-m", "lely", "validate"],
        cwd=lely.root,
        env={**__import__("os").environ, "PYTHONIOENCODING": "cp1252"},
        capture_output=True,
    )
    assert done.returncode == 0, done.stderr.decode("cp1252", "replace")
    assert b"lely.yml: 5 steps" in done.stdout
    assert b"Traceback" not in done.stderr


# -- found in the third review -------------------------------------------------------


def test_a_question_doesnt_obey_what_a_plan_file_says(
    ready: Lely, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R35. The plan above the question was cleaned; the question itself, which
    names who made the plan, was not."""
    asked: list[str] = []
    monkeypatch.setattr(cli, "_confirm", lambda question: asked.append(question) or False)
    planned(ready)
    path = ready.root / "plan.json"
    document = json.loads(path.read_text())
    document["workspace"]["identity"] = "eve\x1b[1A\x1b[2Kjane@example.com"
    path.write_text(json.dumps(document))
    ready.terminal(True)
    assert ready("apply", "plan.json").exit_code == 2
    [question] = asked
    assert "\x1b" not in question
    assert "(the plan was made as eve�[1A�[2Kjane@example.com)" in question


def test_what_a_program_prints_is_logged_without_its_control_characters(
    ready: Lely,
) -> None:
    (ready.root / "ops" / "notify.sh").write_text(
        "#!/bin/sh\nprintf 'done \\033[2J\\033[1;1H and more\\n'\n"
    )
    result = ready("apply", "-t", "dev", "--yes")
    assert result.exit_code == 0, result.output
    assert "\x1b" not in result.output
    assert "notify: done �[2J�[1;1H and more" in result.output


# -- Markdown (008/R1) ----------------------------------------------------------------


def test_a_plan_as_markdown_is_the_plan_the_file_holds(ready: Lely) -> None:
    """`plan -f md`, `plan --destroy -f md` and `show -f md`: stdout holds the
    Markdown and nothing else."""
    planned = ready("plan", "-t", "dev", "-f", "md", "-o", "plan.json")
    assert planned.exit_code == 0
    assert planned.stdout.startswith(
        "<!-- lely:plan:dev -->\n### lely plan · target `dev`"
    )
    assert "\n+     create   jobs.bar\n" in planned.stdout
    assert "Wrote" not in planned.stdout and "Wrote plan.json" in planned.stderr
    shown = ready("show", "plan.json", "-f", "md")
    assert shown.stdout == planned.stdout
    destroy = ready("plan", "-t", "dev", "--destroy", "-f", "md")
    assert destroy.stdout.startswith(
        "<!-- lely:destroy:dev -->\n### lely destroy plan · "
    )
    assert "\n-     delete   jobs.backfill  destructive\n" in destroy.stdout


def test_a_run_and_what_exists_as_markdown(ready: Lely) -> None:
    refused = ready("apply", "-t", "dev", "-f", "md")  # no terminal, no --yes
    assert refused.exit_code == 2
    assert refused.stdout.startswith(
        "### lely apply · target `dev` · refused\n\n**Nothing was run.**\n\n```text\n"
    )
    applied = ready("apply", "-t", "dev", "--yes", "-f", "md")
    assert applied.exit_code == 0
    assert applied.stdout.startswith("### lely apply · target `dev`\n")
    assert "#### What exists now" in applied.stdout
    assert "| `created` | [open](<" in applied.stdout
    status = ready("status", "-t", "dev", "-f", "md")
    assert status.stdout.startswith("### lely status · target `dev`\n")
    assert "| `app` | `job` | `jobs.bar` | `job bar` | `1001` | [open](<" in status.stdout


# -- GitHub (008) ---------------------------------------------------------------------


@pytest.fixture
def hub(ready: Lely, monkeypatch: pytest.MonkeyPatch) -> FakeGitHub:
    """A GitHub Actions run for a pull request, and a fake GitHub behind it."""
    fake = FakeGitHub()
    monkeypatch.setattr(cli, "GITHUB", fake.connect)
    fake_github.inside(monkeypatch, ready.root)
    return fake


def page(ready: Lely) -> str:
    summary = ready.root / "summary.md"
    return summary.read_text() if summary.exists() else ""


def test_github_is_never_on_because_of_where_a_command_runs(
    ready: Lely, hub: FakeGitHub
) -> None:
    """008/R4: in a run, with a token and a pull request — and no `--github`."""
    assert ready("plan", "-t", "dev").exit_code == 0
    assert ready("apply", "-t", "dev", "--yes").exit_code == 0
    assert hub.calls == [] and page(ready) == ""


def test_outside_a_run_github_says_so_and_the_plan_stands(
    ready: Lely, monkeypatch: pytest.MonkeyPatch
) -> None:
    """008/R5."""
    fake_github.outside(monkeypatch)
    result = ready("plan", "-t", "dev", "--github")
    assert result.exit_code == 0
    assert "+ jobs.bar" in result.stdout
    assert "--github: this isn't a GitHub Actions run" in " ".join(result.stderr.split())


def test_the_plan_is_put_on_the_pull_request_and_kept_current(
    ready: Lely, hub: FakeGitHub
) -> None:
    """008/R2, R3: one comment, updated by the next plan; the run's page too."""
    first = ready("plan", "-t", "dev", "--github", "-o", "plan.json")
    assert first.exit_code == 0
    assert "… github: created the comment on pull request #12" in first.stderr
    [body] = hub.bodies
    assert body.startswith("<!-- lely:plan:dev -->\n### lely plan · target `dev`\n")
    assert "\n+     create   jobs.bar\n" in body
    assert "commit `0123456789ab`" in body and "[the run](<" in body
    assert page(ready).startswith("<!-- lely:plan:dev -->\n### lely plan")

    # the workspace moves on, so the next plan is another
    assert ready("apply", "-t", "dev", "--yes").exit_code == 0
    second = ready("plan", "-t", "dev", "--github")
    assert "… github: updated the comment on pull request #12" in second.stderr
    [body] = hub.bodies
    assert "create   jobs.bar" not in body
    # a saved plan is shown the same way, and it is the same comment
    shown = ready("show", "plan.json", "--github")
    assert shown.exit_code == 0 and len(hub.comments) == 1
    assert "create   jobs.bar" in hub.bodies[0]
    # a plan to destroy is another plan, with a comment of its own
    ready("plan", "-t", "dev", "--destroy", "--github")
    assert [body.split("\n", 1)[0] for body in hub.bodies] == [
        "<!-- lely:plan:dev -->",
        "<!-- lely:destroy:dev -->",
    ]


def test_a_plan_that_fails_says_so_where_the_last_plan_stood(
    ready: Lely, hub: FakeGitHub
) -> None:
    ready("plan", "-t", "dev", "--github")
    (ready.root / "lely.yml").write_text("steps:\n  - uses: nothing-like-it\n")
    failed = ready("plan", "-t", "dev", "--github")
    assert failed.exit_code == 1
    [body] = hub.bodies
    assert body.startswith(
        "<!-- lely:plan:dev -->\n### lely plan · target `dev` · failed"
    )
    assert "**The plan could not be made, so there is none to review.**" in body
    assert "nothing-like-it" not in body  # what went wrong is on the run's page
    assert "nothing-like-it" in page(ready)


def test_a_comment_that_cant_be_written_doesnt_fail_the_plan(
    ready: Lely, hub: FakeGitHub
) -> None:
    """008/R5: the job has no permission to comment."""
    hub.refused = {"POST"}
    result = ready("plan", "-t", "dev", "--github")
    assert result.exit_code == 0 and hub.comments == []
    said = " ".join(result.stderr.split())
    assert "--github: couldn't comment on pull request #12: 403" in said
    assert "the job needs `permissions: pull-requests: write`" in said
    assert "### lely plan · target `dev`" in page(ready)


def test_a_pull_request_from_a_fork_gets_no_plan_and_is_told_so(
    ready: Lely, hub: FakeGitHub, monkeypatch: pytest.MonkeyPatch
) -> None:
    """008/R4a: nothing of the project is loaded, and no workspace is asked."""

    def never(profile: str | None) -> Workspace:
        raise AssertionError("a fork's plan reached for the workspace")

    monkeypatch.setattr(cli, "WHOAMI", never)
    (ready.root / "ops" / "steps.py").write_text("raise SystemExit('ran its code')\n")
    fake_github.inside(monkeypatch, ready.root, head="someone/shop")
    result = ready("plan", "-t", "dev", "--github", "-o", "plan.json")
    assert result.exit_code == 0
    assert "comes from a fork (someone/shop): no plan is made" in result.stderr
    assert not (ready.root / "plan.json").exists()
    assert hub.calls == []
    assert "### lely plan · target `dev` · skipped" in page(ready)
    # … and nothing is applied or destroyed for one
    for command in (("apply", "-t", "dev", "--yes"), ("destroy", "-t", "dev", "--yes")):
        refused = ready(*command, "--github")
        assert refused.exit_code == 2
        assert "This pull request comes from a fork (someone/shop)" in " ".join(
            refused.stderr.split()
        )
    assert page(ready).count("· refused\n\n**Nothing was run.**") == 2


def test_a_run_and_what_it_left_go_on_its_page(ready: Lely, hub: FakeGitHub) -> None:
    """008/R3: what each step did, and what exists now, with links."""
    refused = ready("apply", "-t", "dev", "--github")  # no terminal, no --yes
    assert refused.exit_code == 2
    assert "### lely apply · target `dev` · refused\n\n**Nothing was run.**" in page(
        ready
    )
    applied = ready("apply", "-t", "dev", "--yes", "--github")
    assert applied.exit_code == 0
    assert "… github: wrote the run's summary" in applied.stderr
    written = page(ready)
    assert "### lely apply · target `dev`\n" in written
    assert "#### What exists now" in written
    assert f"| `created` | [open](<{project.WORKSPACE.host}/jobs/1001>) |" in written
    assert hub.calls == []  # a run's result is on its page; the comment is the plan's
    destroyed = ready("destroy", "-t", "dev", "--yes", "--github")
    assert destroyed.exit_code == 0
    assert "### lely destroy · target `dev`\n" in page(ready)


# -- found in the fifth review ---------------------------------------------------------


def test_a_saved_plan_is_not_posted_for_a_fork(
    ready: Lely, hub: FakeGitHub, monkeypatch: pytest.MonkeyPatch
) -> None:
    """008/R4a: a plan file out of a fork's checkout is not "the plan"."""
    assert ready("plan", "-t", "dev", "-o", "plan.json").exit_code == 0
    fake_github.inside(monkeypatch, ready.root, head="someone/shop")
    shown = ready("show", "plan.json", "--github")
    assert shown.exit_code == 0 and "+ jobs.bar" in shown.stdout
    assert "comes from a fork (someone/shop): its plan is not posted" in " ".join(
        shown.stderr.split()
    )
    assert hub.calls == []
    assert "### lely plan · target `dev` · skipped" in page(ready)


def test_a_plan_that_holds_the_runs_token_is_not_written(
    ready: Lely, hub: FakeGitHub
) -> None:
    """008/R6. A plan command that prints its environment puts the token in
    the plan: in the file, which is kept as an artifact, and on stdout."""
    ready("plan", "-t", "dev", "--github")
    printing = (
        "import json, os\n"
        "print(json.dumps({'changes': [{'key': 'k', 'action': 'run',"
        " 'summary': 'with ' + os.environ['GITHUB_TOKEN']}]}))\n"
    )
    (ready.root / "ops" / "leak.py").write_text(printing)
    leaking = READY + (
        "  - name: seed\n    uses: command\n    with:\n"
        f"      apply: ['true']\n      plan: [{sys.executable}, ops/leak.py]\n"
    )
    (ready.root / "lely.yml").write_text(leaking)
    for extra in ((), ("-f", "md"), ("-f", "json")):
        result = ready("plan", "-t", "dev", "--github", "-o", "plan.json", *extra)
        assert result.exit_code == 1
        assert fake_github.TOKEN not in result.stdout + result.stderr
        assert "The plan of step `seed` holds this run's GitHub token" in " ".join(
            result.stderr.split()
        )
        assert not (ready.root / "plan.json").exists()
    [body] = hub.bodies
    assert "· failed\n" in body and fake_github.TOKEN not in body + page(ready)


def test_a_failing_plan_of_a_project_whose_folder_is_gone_is_still_that_projects(
    ready: Lely, hub: FakeGitHub
) -> None:
    """A pull request that renames `team-a/` while the workflow still plans
    `-c team-a/lely.yml`: the failure was filed as the top project's."""
    subprocess.run(["git", "init", "-q"], cwd=ready.root, check=True)
    failed = ready("plan", "-t", "dev", "--github", "-c", "team-a/deploy/lely.yml")
    assert failed.exit_code == 1
    [body] = hub.bodies
    assert body.startswith("<!-- lely:plan:dev:team-a/deploy -->\n")
    # and a project at the top stays the top's
    (ready.root / "lely.yml").write_text("steps: 5\n")
    ready("plan", "-t", "dev", "--github")
    assert hub.bodies[1].startswith(
        "<!-- lely:plan:dev -->\n### lely plan · target `dev` · f"
    )


def test_whatever_goes_wrong_while_posting_the_token_is_not_said(
    ready: Lely, hub: FakeGitHub, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An error may quote what it choked on."""

    def choking(*args: Any, **kwargs: Any) -> Any:
        raise ValueError(f"Invalid header value b'Bearer {fake_github.TOKEN}\\n'")

    monkeypatch.setattr(cli.github, "post_plan", choking)
    result = ready("plan", "-t", "dev", "--github")
    assert result.exit_code == 0 and fake_github.TOKEN not in result.stderr
    assert (
        "--github: couldn't be done: ValueError: Invalid header value b'Bearer ***"
        in (" ".join(result.stderr.split()))
    )


# -- the page (007) -------------------------------------------------------------------


@pytest.fixture
def browser(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    opened: list[str] = []
    monkeypatch.setattr(cli, "BROWSER", lambda address: opened.append(address) or True)
    return opened


def test_a_plan_file_is_made_into_a_page_beside_it(
    ready: Lely, browser: list[str]
) -> None:
    """007/R1, R4: from the file alone, and not opened where there is nobody
    to look."""
    assert ready("plan", "-t", "dev", "-o", "plan.json").exit_code == 0
    result = ready("ui", "plan.json")
    assert result.exit_code == 0 and "Wrote plan.html" in result.stdout
    page = (ready.root / "plan.html").read_text()
    assert page.startswith("<!doctype html>") and "<title>lely plan · dev</title>" in page
    assert '<td class="what">jobs.bar</td>' in page
    assert browser == []  # no terminal: nobody to open it for
    ready.terminal(True)
    ready("ui", "plan.json")
    assert browser == [(ready.root / "plan.html").resolve().as_uri()]
    ready("ui", "plan.json", "--no-open", "-o", "pages/dev.html")
    assert len(browser) == 1 and not (ready.root / "pages").exists()


def test_the_page_can_go_anywhere(ready: Lely, browser: list[str]) -> None:
    ready("plan", "-t", "dev", "--destroy", "-o", "destroy.json")
    (ready.root / "pages").mkdir()
    written = ready("ui", "destroy.json", "-o", "pages/gone.html", "--open")
    assert written.exit_code == 0
    assert "lely destroy plan" in (ready.root / "pages" / "gone.html").read_text()
    assert browser == [(ready.root / "pages" / "gone.html").resolve().as_uri()]
    piped = ready("ui", "destroy.json", "-o", "-", "--open")
    assert piped.stdout.startswith("<!doctype html>") and "Wrote" not in piped.stdout
    assert len(browser) == 1  # what went to stdout is not a file to open
    same = ready("ui", "destroy.json", "-o", "destroy.json")
    assert same.exit_code == 1 and "the page needs another name" in same.stderr
    assert json.loads((ready.root / "destroy.json").read_text())["kind"] == "destroy"


def test_making_a_page_runs_nothing_of_the_project(
    ready: Lely,
    browser: list[str],
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """007/R4, R8: no workspace, no credentials, no plugin — a plan file from
    anywhere is safe to open, and the page is the same on any machine."""
    ready("plan", "-t", "dev", "-o", "plan.json")
    here = ready("ui", "plan.json", "-o", "-").stdout
    elsewhere = tmp_path_factory.mktemp("elsewhere")
    (elsewhere / "plan.json").write_text((ready.root / "plan.json").read_text())
    (ready.root / "ops" / "steps.py").write_text("raise SystemExit('ran its code')\n")
    (ready.root / "lely.yml").write_text("not: [a config")

    def never(profile: str | None) -> Workspace:
        raise AssertionError("a page reached for the workspace")

    monkeypatch.setattr(cli, "WHOAMI", never)
    monkeypatch.chdir(elsewhere)
    assert ready("ui", "plan.json", "-o", "-").stdout == here


def test_a_file_that_is_no_plan_and_no_result_is_said(ready: Lely) -> None:
    (ready.root / "notes.json").write_text('{"hello": 1}')
    (ready.root / "broken.json").write_text("{not json")
    for name, said_ in (
        ("notes.json", "This plan file is format None"),
        ("broken.json", "broken.json: not a plan or a result"),
        ("missing.json", "missing.json: No such file"),
    ):
        result = ready("ui", name)
        assert result.exit_code == 1 and said_ in " ".join(result.stderr.split())
        assert not (ready.root / name).with_suffix(".html").exists()


def test_a_run_can_write_its_record_and_the_record_becomes_a_page(
    ready: Lely, browser: list[str]
) -> None:
    """007/R6: what each step did and what exists now, from a file the run
    wrote when asked to. Nothing reads it back but the page."""
    applied = ready("apply", "-t", "dev", "--yes", "-o", "result.json")
    assert applied.exit_code == 0 and "Wrote result.json" in applied.stderr
    record = json.loads((ready.root / "result.json").read_text())
    assert (record["result_format"], record["outcome"]) == (1, "done")
    assert ready("ui", "result.json").exit_code == 0
    page = (ready.root / "result.html").read_text()
    assert "<title>lely apply · dev</title>" in page
    assert '<p class="outcome done">Applied: 3 steps.</p>' in page
    assert f'<a href="{project.WORKSPACE.host}/jobs/1001"' in page
    destroyed = ready("destroy", "-t", "dev", "--yes", "-o", "gone.json")
    assert destroyed.exit_code == 0
    assert "lely destroy" in ready("ui", "gone.json", "-o", "-").stdout


def test_a_run_that_never_started_leaves_a_record_of_that(ready: Lely) -> None:
    refused = ready("apply", "-t", "dev", "-o", "result.json")  # no --yes, no terminal
    assert refused.exit_code == 2
    record = json.loads((ready.root / "result.json").read_text())
    assert (record["outcome"], record["steps"]) == ("refused", [])
    page = ready("ui", "result.json", "-o", "-").stdout
    assert '<strong class="refused">Refused.</strong> Nothing was rolled back.' in page
    assert "Pass --yes to run without asking." in page


def test_a_record_that_cant_be_written_changes_nothing_about_the_run(ready: Lely) -> None:
    applied = ready("apply", "-t", "dev", "--yes", "-o", "no/such/folder/result.json")
    assert applied.exit_code == 0
    assert "Can't write the result to no/such/folder/result.json" in " ".join(
        applied.stderr.split()
    )
    assert ready.fake.deployed()  # … and the run happened


# -- found in the sixth review ---------------------------------------------------------


def test_a_page_is_never_written_through_a_link_or_over_someone_elses_file(
    ready: Lely, browser: list[str], tmp_path_factory: pytest.TempPathFactory
) -> None:
    """A plan file can come from anywhere, and so can what lies beside it: a
    `plan.html` that is a link to a file of the reader's own was written
    through, and an unrelated `plan.html` written over."""
    ready("plan", "-t", "dev", "-o", "plan.json")
    theirs = tmp_path_factory.mktemp("home") / "authorized_keys"
    theirs.write_text("ssh-ed25519 the owner's key\n")
    (ready.root / "plan.html").symlink_to(theirs)
    planted = ready("ui", "plan.json")
    assert planted.exit_code == 1
    assert "plan.html is there already, and it isn't a page lely made" in " ".join(
        planted.stderr.split()
    )
    assert theirs.read_text() == "ssh-ed25519 the owner's key\n"
    # named outright, the link is replaced by the page — still not followed
    assert ready("ui", "plan.json", "-o", "plan.html").exit_code == 0
    assert theirs.read_text() == "ssh-ed25519 the owner's key\n"
    assert not (ready.root / "plan.html").is_symlink()
    assert (ready.root / "plan.html").read_text().startswith("<!doctype html>")
    # a page lely made is its own to write again; anything else is not
    assert ready("ui", "plan.json").exit_code == 0
    (ready.root / "plan.html").write_text("<h1>our team's own page</h1>")
    assert ready("ui", "plan.json").exit_code == 1
    assert (ready.root / "plan.html").read_text() == "<h1>our team's own page</h1>"


def test_the_file_to_read_is_never_the_file_written_however_it_is_spelled(
    ready: Lely, browser: list[str]
) -> None:
    ready("plan", "-t", "dev", "-o", "plan.json")
    plan = (ready.root / "plan.json").read_text()
    os.link(ready.root / "plan.json", ready.root / "second-name.html")
    (ready.root / "link.html").symlink_to("plan.json")
    for spelled in ("plan.json", "./plan.json", "second-name.html", "link.html"):
        refused = ready("ui", "plan.json", "-o", spelled)
        assert refused.exit_code == 1, spelled
        assert "is the file to read: the page needs another name" in refused.stderr
        assert (ready.root / "plan.json").read_text() == plan


def test_a_file_is_whole_or_as_it_was(
    ready: Lely, browser: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Written beside its place first and then moved there, so a write that
    fails leaves no half of a plan behind — and nothing lying about."""
    ready("plan", "-t", "dev", "-o", "plan.json")
    before = (ready.root / "plan.json").read_text()

    def full(*args: Any, **kwargs: Any) -> None:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(os, "replace", full)
    failed = ready("plan", "-t", "dev", "-o", "plan.json")
    assert failed.exit_code == 1 and "No space left on device" in failed.stderr
    assert (ready.root / "plan.json").read_text() == before
    assert sorted(path.name for path in ready.root.glob(".plan.json*")) == []


def test_a_runs_record_never_holds_the_runs_token(ready: Lely, hub: FakeGitHub) -> None:
    """007/R7. A step that fails may print it. What goes on the run's page is
    searched for it; the record, which is kept and made into a page, was not."""
    (ready.root / "ops" / "notify.sh").write_text(
        '#!/bin/sh\necho "auth failed for $GITHUB_TOKEN" >&2; exit 1\n'
    )
    for extra in ((), ("-f", "json"), ("-f", "md")):
        failed = ready(
            "apply", "-t", "dev", "--yes", "--github", "-o", "result.json", *extra
        )
        assert failed.exit_code == 1
        record = (ready.root / "result.json").read_text()
        assert fake_github.TOKEN not in record and "auth failed for ***" in record
        assert fake_github.TOKEN not in failed.stdout
    assert fake_github.TOKEN not in ready("ui", "result.json", "-o", "-").stdout


def test_a_file_made_again_is_readable_by_whoever_could_read_it_before(
    ready: Lely, browser: list[str]
) -> None:
    """Written beside its place and moved there, a file is a new file: one
    kept to oneself must not come back readable by everyone."""
    assert ready("plan", "-t", "dev", "-o", "plan.json").exit_code == 0
    plan = ready.root / "plan.json"
    fresh = plan.stat().st_mode & 0o777
    assert fresh & 0o600 == 0o600  # as any new file here
    plan.chmod(0o600)
    assert ready("plan", "-t", "dev", "-o", "plan.json").exit_code == 0
    assert plan.stat().st_mode & 0o777 == 0o600
    # a link standing there is replaced by a new file: nothing of its target's
    theirs = ready.root / "theirs.txt"
    theirs.write_text("x")
    theirs.chmod(0o640)
    (ready.root / "page.html").symlink_to(theirs)
    assert ready("ui", "plan.json", "-o", "page.html").exit_code == 0
    assert (ready.root / "page.html").stat().st_mode & 0o777 == fresh
    assert theirs.read_text() == "x"


# -- found when the sixth review's fixes were reviewed ---------------------------------


LEAKING = (
    "import json, os, sys\n"
    "token = os.environ['GITHUB_TOKEN']\n"
    "how = sys.argv[1]\n"
    "if how == 'plan':\n"
    "    print(json.dumps({'changes': [{'key': 'k', 'action': 'run',"
    " 'summary': 'job with ' + token}]}))\n"
    "elif how == 'plan-fails':\n"
    "    sys.exit('auth failed for ' + token)\n"
    "else:\n"
    "    print('signed in with ' + token)\n"
    "    print('and on stderr ' + token, file=sys.stderr)\n"
    "    sys.exit(1 if how.endswith('fails') else 0)\n"
)


def leaking(ready: Lely, **commands: str) -> None:
    """The scenario with a `seed` step whose commands print the run's token."""
    (ready.root / "ops" / "leak.py").write_text(LEAKING)
    lines = "".join(
        f"      {verb}: [{sys.executable}, ops/leak.py, {how}]\n"
        for verb, how in commands.items()
    )
    (ready.root / "lely.yml").write_text(
        READY + "  - name: seed\n    uses: command\n    with:\n" + lines
    )


def nowhere(ready: Lely, hub: FakeGitHub, *results: Result) -> None:
    """The token is in nothing lely said or wrote."""
    said_ = "".join(result.stdout + result.stderr for result in results)
    kept = "".join(
        path.read_text()
        for path in ready.root.iterdir()
        if path.suffix in (".json", ".md", ".html")
    )
    assert fake_github.TOKEN not in said_ + kept + "".join(hub.bodies)
    assert "***" in said_ + kept  # … and it was there to be searched for


@pytest.mark.parametrize("extra", [(), ("-f", "json"), ("-f", "md")])
def test_with_github_no_line_lely_says_holds_the_token(
    ready: Lely, hub: FakeGitHub, extra: tuple[str, ...]
) -> None:
    """008/R6. Searching the result was not enough: a command that prints the
    token and succeeds put it in lely's own progress lines; a plan command
    that fails with it put it in the error."""
    leaking(ready, apply="apply", destroy="destroy")
    # the Databricks CLI can print it too, while it deploys
    (ready.fake.world / "warn-deploy").write_text(f"auth: {fake_github.TOKEN}\n")
    applied = ready("apply", "-t", "dev", "--yes", "--github", "-o", "r.json", *extra)
    assert applied.exit_code == 0
    destroyed = ready("destroy", "-t", "dev", "--yes", "--github", *extra)
    assert destroyed.exit_code == 0
    nowhere(ready, hub, applied, destroyed)
    # what each program wrote was passed on, on both streams: hidden, not dropped
    for line in ("seed: signed in with ***", "seed: and on stderr ***", "app: auth: ***"):
        assert f"… {line}" in _ANSI.sub("", applied.stderr)

    leaking(ready, apply="apply-fails")
    failed = ready("apply", "-t", "dev", "--yes", "--github", "-o", "r.json", *extra)
    assert failed.exit_code == 1
    nowhere(ready, hub, failed)

    leaking(ready, apply="apply", plan="plan-fails")
    for command in (("plan", "-t", "dev"), ("apply", "-t", "dev", "--yes")):
        stopped = ready(*command, "--github", *extra)
        assert stopped.exit_code == 1
        nowhere(ready, hub, stopped)


def test_a_plan_that_holds_the_token_is_shown_by_no_command(
    ready: Lely, hub: FakeGitHub, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`plan`, `apply` and `destroy` refused one; `show --github` showed and
    posted it, and so did `apply` for a step it could only plan mid-run."""
    leaking(ready, apply="apply", plan="plan")
    fake_github.outside(monkeypatch)  # a plan made without --github, earlier in the job
    monkeypatch.setenv("GITHUB_TOKEN", fake_github.TOKEN)
    assert ready("plan", "-t", "dev", "-o", "plan.json").exit_code == 0
    assert fake_github.TOKEN in (ready.root / "plan.json").read_text()
    (ready.root / "plan.json").rename(ready.root / "plan.kept")
    fake_github.inside(monkeypatch, ready.root)
    (ready.root / "plan.json").write_text((ready.root / "plan.kept").read_text())
    (ready.root / "plan.kept").unlink()
    for extra in ((), ("-f", "json"), ("-f", "md")):
        shown = ready("show", "plan.json", "--github", *extra)
        assert shown.exit_code == 1
        assert fake_github.TOKEN not in shown.stdout + shown.stderr
        assert "The plan of step `seed` holds this run's GitHub token" in " ".join(
            shown.stderr.split()
        )
    assert hub.bodies == []
    (ready.root / "plan.json").unlink()

    # a step that waits is planned only when the run gets to it — and shown then
    waiting = project.LELY_YML.replace(
        'apply: [./ops/notify.sh, "${steps.app.resources.jobs.bar.id}"]',
        f'apply: ["true"]\n      plan: [{sys.executable}, ops/leak.py, plan, '
        '"${steps.app.resources.jobs.bar.id}"]',
    )
    (ready.root / "lely.yml").write_text(waiting)
    stopped = ready("apply", "-t", "dev", "--yes", "--github")
    assert stopped.exit_code == 1
    assert fake_github.TOKEN not in stopped.stdout + stopped.stderr
    assert "The plan of step `notify` holds this run's GitHub token" in " ".join(
        stopped.stdout.split() + stopped.stderr.split()
    )


def test_a_result_that_cant_be_searched_is_not_shown_as_it_is(
    ready: Lely, hub: FakeGitHub, monkeypatch: pytest.MonkeyPatch
) -> None:
    """It fell back to the result as it was, token and all."""
    leaking(ready, apply="apply-fails")

    def broken(document: Any) -> Any:
        raise TypeError("Object of type PosixPath is not JSON serializable")

    monkeypatch.setattr(cli.planfile, "result_from_json", broken)
    failed = ready("apply", "-t", "dev", "--yes", "--github")
    assert failed.exit_code == 1
    assert fake_github.TOKEN not in failed.stdout + failed.stderr + page(ready)
    assert "What this run said is left out" in " ".join(failed.stdout.split())
    assert "✗ seed" in failed.stdout  # how each step ended is still said


def test_what_is_no_file_is_written_to_as_it_is(ready: Lely, browser: list[str]) -> None:
    """`-o /dev/null` worked, and stopped working when files came to be
    written beside their place and moved there. A device is written to; and
    under `/dev` nothing is ever replaced."""
    assert ready("plan", "-t", "dev", "-o", "/dev/null").exit_code == 0
    assert ready("apply", "-t", "dev", "--yes", "-o", "/dev/null").exit_code == 0
    assert ready("schema", "-o", "/dev/null").exit_code == 0
    assert Path("/dev/null").is_char_device()
    pipe = ready.root / "pipe"
    os.mkfifo(pipe)
    reader = os.open(pipe, os.O_RDONLY | os.O_NONBLOCK)
    try:
        cli._write(pipe, "through the pipe\n")
        assert os.read(reader, 100) == b"through the pipe\n"
    finally:
        os.close(reader)
    assert stat.S_ISFIFO(pipe.stat().st_mode)


def test_a_file_in_a_folder_that_cant_be_written_to(
    ready: Lely, browser: list[str]
) -> None:
    """There is no room beside it for a second file: the file itself is
    written, as it used to be. One marked read-only is left alone."""
    kept = ready.root / "kept"
    kept.mkdir()
    (kept / "plan.json").write_text("old")
    (kept / "locked.json").write_text("old")
    (kept / "locked.json").chmod(0o444)
    kept.chmod(0o555)
    try:
        cli._write(kept / "plan.json", "new")
        assert (kept / "plan.json").read_text() == "new"
        with pytest.raises(PermissionError):
            cli._write(kept / "locked.json", "new")
        with pytest.raises(PermissionError):  # … and no new file can be made there
            cli._write(kept / "another.json", "new")
        assert sorted(path.name for path in kept.iterdir()) == [
            "locked.json",
            "plan.json",
        ]
    finally:
        kept.chmod(0o755)
    (ready.root / "locked.json").write_text("old")
    (ready.root / "locked.json").chmod(0o444)
    with pytest.raises(PermissionError):  # in a folder that can be written to, too
        cli._write(ready.root / "locked.json", "new")
    assert (ready.root / "locked.json").read_text() == "old"


def test_a_long_name_is_no_longer_for_being_written_beside(ready: Lely) -> None:
    name = "p" * 245 + ".json"
    cli._write(ready.root / name, "x")
    assert (ready.root / name).read_text() == "x"


def test_a_file_made_again_is_for_the_same_group_or_for_nobody_else(
    ready: Lely, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The mode was kept and the group was not: a file for one group to read
    came back readable by another."""
    plan = ready.root / "plan.json"
    plan.write_text("old")
    plan.chmod(0o640)
    given: list[tuple[int, int]] = []
    real_stat = os.stat

    class Elsewhere:
        """A new file here belongs to another group than the old one."""

        def __init__(self, inner: os.stat_result) -> None:
            self.st_gid = inner.st_gid + 1

    def stat_(path: Any, *args: Any, **kwargs: Any) -> Any:
        found = real_stat(path, *args, **kwargs)
        return Elsewhere(found) if str(path).endswith(".tmp") else found

    monkeypatch.setattr(os, "stat", stat_)
    monkeypatch.setattr(os, "chown", lambda path, uid, gid: given.append((uid, gid)))
    cli._write(plan, "new")
    assert given == [(-1, plan.stat().st_gid)] and plan.stat().st_mode & 0o777 == 0o640

    def refused(path: Any, uid: int, gid: int) -> None:
        raise PermissionError(1, "Operation not permitted")

    monkeypatch.setattr(os, "chown", refused)
    cli._write(plan, "newer")
    assert plan.read_text() == "newer" and plan.stat().st_mode & 0o777 == 0o600
    # … and what a mode says beyond who may read and write is not carried over
    monkeypatch.undo()
    plan.chmod(0o4755)
    cli._write(plan, "newest")
    assert plan.stat().st_mode & 0o7777 == 0o755
