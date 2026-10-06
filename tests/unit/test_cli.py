"""The `lely` command, end to end, against the fake Databricks CLI as a program.

Consent, exit codes and plan files are the command line's own: each test names
the requirement of `spec/005-plan-apply-destroy.md` it holds.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
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


def test_apply_without_a_file_needs_a_target(ready: Lely) -> None:
    """R37."""
    result = ready("apply", "--yes")
    assert result.exit_code == 2
    assert "Give the target: `lely apply -t <target>`." in said(result)


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
