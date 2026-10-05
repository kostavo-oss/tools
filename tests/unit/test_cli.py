"""The `lely` command, end to end, against the fake Databricks CLI as a program.

Consent, exit codes and plan files are the command line's own: each test names
the requirement of `spec/005-plan-apply-destroy.md` it holds.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner, Result

import project
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
    assert set(lely.fake.verbs) == {"validate", "plan", "summary"}


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
    assert "format 1; this lely reads format 2. Run `lely plan` again." in said(result)
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
    assert "ran: model, app" in said(first)
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
    assert "ran: model, app" in said(result)
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
    assert document["ran"] == ["model", "app", "notify", "backfill"]
    assert document["failed"] == document["not_started"] == []
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
    assert set(lely.fake.verbs) <= {"validate", "plan", "summary"}
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
