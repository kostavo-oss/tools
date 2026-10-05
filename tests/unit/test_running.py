"""Apply, destroy, status: the half that changes a workspace, against the
simulated bundle. Each test names the requirement of
`spec/005-plan-apply-destroy.md` it holds."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, cast

import pytest

import project
from fakes import FakeDatabricks, deploy
from lely import planning, running
from lely.config import Config, load
from lely.errors import Refused
from lely.model import Plan, PlanKind, PlannedStep, Result, Source
from lely.step import NullLog


def edges(fake: FakeDatabricks) -> dict[str, Any]:
    return {
        "workspace": project.WORKSPACE,
        "env": {},
        "databricks": fake,
        "log": NullLog(),
        "connect": lambda: cast(Any, None),
    }


class Project:
    """The scenario on disk, with the workspace beside it."""

    def __init__(self, root: Path, text: str | None = None, *, deployed: bool = True):
        self.root = root
        self.path = project.write(root, text)
        self.fake = FakeDatabricks(project.world(root, deployed=deployed))

    @property
    def config(self) -> Config:
        return load(self.path)

    def plan(self, kind: PlanKind = "apply") -> Plan:
        return planning.plan(
            self.config, target="dev", source=Source(), kind=kind, **edges(self.fake)
        )

    def apply(self, approved: Plan | None = None, **kwargs: Any) -> Result:
        return running.apply(
            self.config, approved or self.plan(), **kwargs, **edges(self.fake)
        )

    def destroy(self, approved: Plan | None = None, **kwargs: Any) -> Result:
        return running.destroy(
            self.config, approved or self.plan("destroy"), **kwargs, **edges(self.fake)
        )

    def notified(self) -> list[str]:
        path = self.root / "notified.txt"
        return path.read_text().split() if path.exists() else []


def outcomes(result: Result) -> dict[str, str]:
    return {step.name: step.outcome for step in result.steps}


def run_it(step: PlannedStep) -> bool:
    return True


#: The scenario without the step that waits on a first deploy.
READY = project.LELY_YML.replace("resources.jobs.bar.id", "resources.jobs.backfill.id")


# -- apply -------------------------------------------------------------------------


def test_apply_runs_the_steps_in_the_order_written(tmp_path: Path) -> None:
    """R4, R6."""
    p = Project(tmp_path, READY)
    result = p.apply()
    assert result.outcome == "done"
    assert outcomes(result) == {
        "model": "nothing",
        "app": "done",
        "notify": "done",
        "backfill": "done",
        "warm": "skipped",
    }
    assert result.steps[-1].detail == "not for target `dev`"
    assert p.fake.verbs.index("deploy") < p.fake.verbs.index("run")
    assert set(p.fake.deployed()) == {"jobs.backfill", "jobs.bar", "pipelines.foo"}
    assert p.notified() == ["771"]
    assert p.fake.runs == [{"key": "jobs.backfill", "args": []}]
    assert not (tmp_path / "warmed.txt").exists()


def test_the_bundle_deploys_a_fresh_plan_not_the_one_that_was_reviewed(
    tmp_path: Path,
) -> None:
    """004/R6: the plan from a file would be stale the moment anything had
    been deployed. What is deployed is planned again and checked."""
    p = Project(tmp_path, READY)
    approved = p.plan()
    assert p.apply(approved).outcome == "done"
    # the same approved plan, again: nothing in it is stale, because nothing in
    # it is what gets deployed
    again = p.apply(approved)
    assert again.outcome == "done"
    assert [c.key for c in again.steps[1].changes] == ["files"]


def test_every_step_is_planned_again_right_before_it_runs(tmp_path: Path) -> None:
    """R7."""
    p = Project(tmp_path, READY)
    approved = p.plan()
    p.fake.clear_calls()
    p.apply(approved)
    verbs = p.fake.verbs
    assert verbs[:3] == ["validate", "plan", "summary"]  # app, planned again
    assert verbs[3] == "deploy"


def test_fewer_changes_than_approved_is_fine(tmp_path: Path) -> None:
    """R7: someone else did part of the work."""
    p = Project(tmp_path, READY)
    approved = p.plan()
    bar = {"name": "job bar", "description": "model 14"}
    deploy(p.fake.world, {**project.DEPLOYED, "jobs.bar": {"id": "5", "config": bar}})
    result = p.apply(approved)
    assert result.outcome == "done"
    assert [c.key for c in result.steps[1].changes] == ["pipelines.foo", "files"]


def test_a_change_that_wasnt_shown_stops_the_run(tmp_path: Path) -> None:
    """R7: a reviewed plan goes stale when the workspace moves under it."""
    p = Project(tmp_path, READY)
    approved = p.plan()
    moved = {"name": "pipeline foo", "storage": "dbfs:/old-storage"}
    deploy(
        p.fake.world, {**project.DEPLOYED, "pipelines.foo": {"id": "42", "config": moved}}
    )
    result = p.apply(approved, allow_destructive=True)
    assert result.outcome == "refused"
    assert outcomes(result) == {
        "model": "nothing",
        "app": "refused",
        "notify": "not started",
        "backfill": "not started",
        "warm": "skipped",
    }
    assert "Step `app` would now replace pipelines.foo" in result.message
    assert "the approved plan showed it would create pipelines.foo" in result.message
    assert result.message.endswith("Plan again.")
    assert "deploy" not in p.fake.verbs


VERSIONED = """\
from dataclasses import dataclass
from pathlib import Path
from lely.model import Output, StepPlan

class Latest:
    @dataclass(frozen=True)
    class Options:
        pass
    outputs = (Output("version"),)
    def plan(self, ctx):
        return StepPlan(outputs={"version": int((ctx.root / "version.txt").read_text())})
    def apply(self, ctx, plan):
        return {}
"""


def test_an_input_that_changed_since_the_plan_stops_the_run(tmp_path: Path) -> None:
    """R5: the plan showed `model_version = 14`. The bundle's own plan would
    read the same with 15 — a job is updated either way — so the changes alone
    wouldn't catch it."""
    (tmp_path / "version.txt").write_text("14")
    text = READY.replace(
        "uses: ./ops/steps.py:LatestModel\n    with:\n      model: dev.ml.churn",
        "uses: ./latest.py:Latest",
    )
    (tmp_path / "latest.py").write_text(VERSIONED)
    p = Project(tmp_path, text)
    approved = p.plan()
    (tmp_path / "version.txt").write_text("15")
    result = p.apply(approved)
    assert result.outcome == "refused"
    assert result.message == (
        "Step `app` takes model.version = 15 now; the plan was approved with 14. "
        "Plan again."
    )
    assert "deploy" not in p.fake.verbs


def test_a_destructive_change_is_refused_before_anything_runs(tmp_path: Path) -> None:
    """R8."""
    p = Project(tmp_path, READY, deployed=False)
    moved = {"name": "pipeline foo", "storage": "dbfs:/old-storage"}
    deploy(
        p.fake.world, {**project.DEPLOYED, "pipelines.foo": {"id": "42", "config": moved}}
    )
    approved = p.plan()
    p.fake.clear_calls()
    with pytest.raises(Refused) as caught:
        p.apply(approved)
    assert "app: pipelines.foo" in str(caught.value)
    assert "Pass --allow-destructive" in str(caught.value)
    assert p.fake.calls == []
    assert p.apply(approved, allow_destructive=True).outcome == "done"
    assert p.fake.deployed()["pipelines.foo"]["id"] != "42"  # replaced


def test_a_plan_with_nothing_to_do_runs_nothing_and_ends_as_done(tmp_path: Path) -> None:
    """R9."""
    text = "steps:\n  - name: model\n    uses: ./ops/steps.py:LatestModel\n"
    text += "    with: {model: dev.ml.churn}\n"
    p = Project(tmp_path, text)
    result = p.apply()
    assert result.outcome == "done"
    assert [(s.outcome, s.detail) for s in result.steps] == [("nothing", "nothing to do")]
    assert p.fake.calls == []


def test_after_an_apply_every_plugin_that_can_says_what_exists(tmp_path: Path) -> None:
    """R10, 004/R7a: each line says what this run did to it."""
    p = Project(tmp_path, READY)
    result = p.apply()
    app = result.steps[1]
    assert app.overview is not None
    assert [(i.key, i.deployed) for i in app.overview.items] == [
        ("jobs.backfill", True),
        ("jobs.bar", True),
        ("pipelines.foo", True),
    ]
    assert app.happened == {"jobs.bar": "created", "pipelines.foo": "created"}
    assert all(step.overview is None for step in result.steps if step.name != "app")
    # nothing is remembered: a second run shows as unchanged what the first created
    assert p.apply().steps[1].happened == {}


def test_a_plugin_that_cant_apply_yet_stops_it_before_anything_runs(
    tmp_path: Path,
) -> None:
    """The `stevin` plugin is parked: it plans, and says so before a deploy."""
    stevin = (
        "  - name: tables\n    uses: stevin\n    with:\n"
        f"      executable: [{sys.executable}, {project.FAKE_STEVIN}, "
        f"{project.FAKE_STEVIN.parent / 'fixtures' / 'stevin-empty.json'}]\n"
    )
    p = Project(tmp_path, READY + stevin)
    approved = p.plan()
    p.fake.clear_calls()
    with pytest.raises(Refused, match="`stevin`, which can plan and can't apply yet"):
        p.apply(approved)
    assert p.fake.calls == []


def test_apply_refuses_a_plan_to_destroy(tmp_path: Path) -> None:
    """R4, R20: a file can't smuggle a destroy."""
    p = Project(tmp_path, READY)
    with pytest.raises(Refused) as caught:
        p.apply(p.plan("destroy"))
    assert "`lely apply` only applies" in str(caught.value)
    assert "`lely destroy <file> -t dev`" in str(caught.value)
    assert p.fake.deployed() == project.DEPLOYED


# -- when something fails ----------------------------------------------------------


def failing(tmp_path: Path) -> Project:
    p = Project(tmp_path, READY)
    (tmp_path / "ops" / "notify.sh").write_text(
        "#!/bin/sh\necho 'no route' >&2; exit 7\n"
    )
    return p


def test_the_first_failing_step_stops_the_run(tmp_path: Path) -> None:
    """R21, R24."""
    p = failing(tmp_path)
    result = p.apply()
    assert result.outcome == "failed"
    assert [s.name for s in result.ran] == ["model", "app"]
    assert [s.name for s in result.failed] == ["notify"]
    assert [s.name for s in result.not_started] == ["backfill"]
    assert "apply command failed (exit 7)" in result.message
    assert "no route" in result.message
    assert p.fake.runs == []
    # nothing was rolled back: what was done, is done
    assert set(p.fake.deployed()) == {"jobs.backfill", "jobs.bar", "pipelines.foo"}


def test_running_it_again_finishes_the_job(tmp_path: Path) -> None:
    """R22, 004/R6a: a step that already did its work plans as nothing left to
    change; the bundle deploys anyway, which only uploads its files."""
    p = failing(tmp_path)
    assert p.apply().outcome == "failed"
    before = p.fake.deployed()
    project.write(tmp_path, READY)  # the script is fixed
    result = p.apply()
    assert result.outcome == "done"
    assert [c.key for c in result.steps[1].changes] == ["files"]
    assert p.fake.deployed() == before
    assert p.notified() == ["771"]
    assert len(p.fake.runs) == 1


def test_from_starts_at_a_named_step(tmp_path: Path) -> None:
    """R23: the steps it passes over are planned, for what they give the
    others; they are not applied."""
    p = Project(tmp_path, READY)
    result = p.apply(from_step="notify")
    assert outcomes(result) == {
        "model": "passed",
        "app": "passed",
        "notify": "done",
        "backfill": "done",
        "warm": "skipped",
    }
    assert "deploy" not in p.fake.verbs
    assert p.notified() == ["771"]  # it still got the bundle's output
    with pytest.raises(Refused, match="`--from nope`: no step `nope`"):
        p.apply(from_step="nope")


# -- a step that can't be planned yet ----------------------------------------------


def test_a_reviewed_file_stops_at_a_waiting_step(tmp_path: Path) -> None:
    """R27: it runs what was reviewed. R30: never out of order."""
    p = Project(tmp_path)
    result = p.apply(at_waiting=None)
    assert result.outcome == "refused"
    assert outcomes(result) == {
        "model": "nothing",
        "app": "done",
        "notify": "refused",
        "backfill": "not started",
        "warm": "skipped",
    }
    assert result.message == (
        "Step `notify` was waiting for app.resources.jobs.bar.id when this plan was "
        "made, so nobody has seen what it will do. Plan again: the next plan shows it."
    )
    assert p.notified() == []
    assert p.fake.runs == []


def test_the_next_plan_shows_the_step_ready_and_one_round_finishes(
    tmp_path: Path,
) -> None:
    """R27: a first deploy through a reviewed file can take two rounds."""
    p = Project(tmp_path)
    p.apply(at_waiting=None)
    second = p.plan()
    assert second.waiting == ()
    notify = second.step("notify")
    assert notify is not None
    bar = p.fake.deployed()["jobs.bar"]["id"]
    assert notify.plan.changes[0].summary == f"runs ./ops/notify.sh {bar}"
    assert p.apply(second, at_waiting=None).outcome == "done"
    assert p.notified() == [bar]


def test_without_a_file_the_step_is_planned_when_it_gets_there(tmp_path: Path) -> None:
    """R28, R29: `--yes` runs it; a terminal is shown the step and asked again."""
    p = Project(tmp_path)
    seen: list[PlannedStep] = []

    def asked(step: PlannedStep) -> bool:
        seen.append(step)
        return True

    result = p.apply(at_waiting=asked)
    assert result.outcome == "done"
    bar = p.fake.deployed()["jobs.bar"]["id"]
    [shown] = seen
    assert (shown.name, shown.state) == ("notify", "ready")
    assert shown.plan.changes[0].summary == f"runs ./ops/notify.sh {bar}"
    assert p.notified() == [bar]


def test_saying_no_at_a_waiting_step_stops_there(tmp_path: Path) -> None:
    """R29."""
    p = Project(tmp_path)
    result = p.apply(at_waiting=lambda step: False)
    assert result.outcome == "refused"
    assert result.message == "Step `notify` wasn't approved. Nothing more was run."
    assert p.notified() == []
    assert outcomes(result)["backfill"] == "not started"


def test_a_waiting_step_doesnt_get_past_the_other_rules(tmp_path: Path) -> None:
    """R30: a destructive change in a step that was waiting needs the flag."""
    drops = {
        "changes": [{"key": "cache", "action": "delete", "summary": "drops the cache"}]
    }
    plan_command = json.dumps([sys.executable, "-c", f"print({json.dumps(drops)!r})"])
    text = project.LELY_YML.replace(
        'apply: [./ops/notify.sh, "${steps.app.resources.jobs.bar.id}"]',
        'apply: [./ops/notify.sh, "${steps.app.resources.jobs.bar.id}"]\n'
        f"      plan: {plan_command}",
    )
    p = Project(tmp_path, text)
    result = p.apply(at_waiting=run_it)
    assert result.outcome == "refused"
    assert "Step `notify` holds destructive changes — drops the cache" in result.message
    assert p.notified() == []
    assert p.apply(at_waiting=run_it, allow_destructive=True).outcome == "done"


def test_a_step_that_takes_an_output_of_a_run_gets_it_at_apply(tmp_path: Path) -> None:
    """R26, 010/R5: what the apply command writes is known after the run."""
    (tmp_path / "ops").mkdir()
    seed = tmp_path / "ops" / "seed.sh"
    seed.write_text('#!/bin/sh\necho "count=3" >> "$LELY_OUTPUTS"\n')
    seed.chmod(0o755)
    text = (
        "steps:\n"
        "  - name: seed\n    uses: command\n"
        "    with: {apply: [./ops/seed.sh], outputs: [count]}\n"
        "  - name: notify\n    uses: command\n"
        "    with: {apply: [./ops/notify.sh, '${steps.seed.count}']}\n"
    )
    p = Project(tmp_path, text)
    approved = p.plan()
    assert [s.state for s in approved.steps] == ["ready", "waiting"]
    assert p.apply(approved, at_waiting=None).outcome == "refused"  # every deploy
    assert p.apply(approved, at_waiting=run_it).outcome == "done"
    assert p.notified() == ["3"]


# -- destroy -----------------------------------------------------------------------

DROP = (
    "  - name: drop\n    uses: command\n    with:\n"
    "      apply: [./ops/warm.sh]\n"
    '      destroy: [./ops/notify.sh, "${steps.app.resources.jobs.backfill.id}"]\n'
)


def test_destroy_goes_from_the_bottom_up(tmp_path: Path) -> None:
    """R11, R12, 002/R21: a step below the bundle is destroyed while the
    bundle, and the id it needed, still exist."""
    p = Project(tmp_path, READY + DROP)
    result = p.destroy()
    assert result.outcome == "done"
    assert [(s.name, s.outcome) for s in result.steps] == [
        ("drop", "done"),
        ("warm", "skipped"),
        ("backfill", "skipped"),
        ("notify", "skipped"),
        ("app", "done"),
        ("model", "skipped"),
    ]
    assert p.notified() == ["771"]  # the destroy command got the job's id
    assert p.fake.deployed() == {}
    assert p.fake.state["destroyed"][0]["resources"] == ["jobs.backfill"]


def test_a_step_with_nothing_to_destroy_is_skipped_and_says_why(tmp_path: Path) -> None:
    """R13."""
    p = Project(tmp_path)
    reasons = {s.name: s.detail for s in p.destroy().steps}
    assert reasons == {
        "warm": "not for target `dev`",
        "backfill": "`bundle.run` has nothing to destroy",
        "notify": "it needs app.resources.jobs.bar.id, which isn't there",
        "app": "",
        "model": "`./ops/steps.py:LatestModel` has nothing to destroy",
    }


def test_a_destroy_is_checked_against_what_was_approved(tmp_path: Path) -> None:
    """R15: anything that wasn't in the approved plan stops the run."""
    p = Project(tmp_path, READY)
    approved = p.plan("destroy")
    p.apply(at_waiting=run_it)  # two more resources since the destroy was approved
    result = p.destroy(approved)
    assert result.outcome == "refused"
    assert "Step `app` would now also delete jobs.bar" in result.message
    assert set(p.fake.deployed()) == {"jobs.backfill", "jobs.bar", "pipelines.foo"}


def test_destroying_what_isnt_deployed_does_nothing_and_ends_as_done(
    tmp_path: Path,
) -> None:
    """R16."""
    p = Project(tmp_path, deployed=False)
    result = p.destroy()
    assert result.outcome == "done"
    assert outcomes(result)["app"] == "nothing"
    assert "destroy" not in p.fake.verbs


def test_from_names_where_a_destroy_starts_going_up(tmp_path: Path) -> None:
    """R23."""
    p = Project(tmp_path, READY + DROP)
    result = p.destroy(from_step="app")
    assert [(s.name, s.outcome) for s in result.steps][:2] == [
        ("drop", "passed"),
        ("warm", "skipped"),
    ]
    assert outcomes(result)["app"] == "done"
    assert p.notified() == []


def test_a_failing_destroy_stops_and_leaves_the_rest(tmp_path: Path) -> None:
    """R21."""
    p = Project(tmp_path, READY + DROP)
    (tmp_path / "ops" / "notify.sh").write_text("#!/bin/sh\nexit 3\n")
    result = p.destroy()
    assert result.outcome == "failed"
    assert [s.name for s in result.failed] == ["drop"]
    assert [s.name for s in result.not_started] == ["backfill", "notify", "app", "model"]
    assert p.fake.deployed() == project.DEPLOYED


def test_destroy_refuses_a_plan_to_apply(tmp_path: Path) -> None:
    p = Project(tmp_path, READY)
    with pytest.raises(Refused, match="`lely destroy` only destroys"):
        p.destroy(p.plan("apply"))


# -- status ------------------------------------------------------------------------


def test_status_shows_every_step_and_changes_nothing(tmp_path: Path) -> None:
    """R32."""
    p = Project(tmp_path)
    before = p.fake.state
    found = running.status(p.config, target="dev", **edges(p.fake))
    assert p.fake.state == before
    assert set(p.fake.verbs) <= {"validate", "plan", "summary"}
    notes = {s.name: s.note for s in found.steps}
    assert notes == {
        "model": "nothing to list",
        "app": "",
        "notify": (
            "can't be listed: it needs app.resources.jobs.bar.id, which isn't there"
        ),
        "backfill": "nothing to list",
        "warm": "skipped: not for target `dev`",
    }
    app = found.steps[1].overview
    assert app is not None
    assert [(i.key, i.deployed, i.id) for i in app.items] == [
        ("jobs.backfill", True, "771"),
        ("jobs.bar", False, None),
        ("pipelines.foo", False, None),
    ]
    assert app.notes[0].startswith("as seen by jane@example.com under ")
    assert (found.target, found.workspace) == ("dev", project.WORKSPACE)
