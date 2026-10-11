"""Apply, destroy, status: the half that changes a workspace, against the
simulated bundle. Each test names the rule of `RULES.md` it
holds."""

from __future__ import annotations

import dataclasses
import json
import os
from pathlib import Path
from typing import Any, cast

import pytest

import project
from fakes import FakeDatabricks, FakeStevin, deploy, write_bundle
from lely import planfile, planning, running
from lely.config import Config, load
from lely.errors import LelyError, Refused
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
    """APL-1, APL-2."""
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
    """BDL-8: the plan from a file would be stale the moment anything had
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
    """APL-3."""
    p = Project(tmp_path, READY)
    approved = p.plan()
    p.fake.clear_calls()
    p.apply(approved)
    verbs = p.fake.verbs
    assert verbs[:2] == ["summary", "plan"]  # app, planned again
    assert verbs[2] == "deploy"


def test_fewer_changes_than_approved_is_fine(tmp_path: Path) -> None:
    """APL-3: someone else did part of the work."""
    p = Project(tmp_path, READY)
    approved = p.plan()
    bar = {"name": "job bar", "description": "model 14"}
    deploy(p.fake.world, {**project.DEPLOYED, "jobs.bar": {"id": "5", "config": bar}})
    result = p.apply(approved)
    assert result.outcome == "done"
    assert [c.key for c in result.steps[1].changes] == ["pipelines.foo", "files"]


def test_a_change_that_wasnt_shown_stops_the_run(tmp_path: Path) -> None:
    """APL-3: a reviewed plan goes stale when the workspace moves under it."""
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
    """PLAN-4: the plan showed `model_version = 14`. The bundle's own plan would
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
    """APL-4."""
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
    """APL-5."""
    text = "steps:\n  - name: model\n    uses: ./ops/steps.py:LatestModel\n"
    text += "    with: {model: dev.ml.churn}\n"
    p = Project(tmp_path, text)
    result = p.apply()
    assert result.outcome == "done"
    assert [(s.outcome, s.detail) for s in result.steps] == [("nothing", "nothing to do")]
    assert p.fake.calls == []


def test_after_an_apply_every_plugin_that_can_says_what_exists(tmp_path: Path) -> None:
    """APL-6, APL-7: each line says what this run did to it."""
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


PLAN_ONLY = '''
from dataclasses import dataclass

from lely.model import Change, StepPlan


class Parked:
    """Plans, and can't apply yet."""

    plan_only = True

    @dataclass(frozen=True, slots=True)
    class Options:
        pass

    def plan(self, ctx):
        return StepPlan(changes=(Change("thing", "create", "thing"),))

    def apply(self, ctx, plan):
        raise AssertionError("a plugin that can't apply was asked to")
'''


def test_a_plugin_that_cant_apply_yet_stops_it_before_anything_runs(
    tmp_path: Path,
) -> None:
    """PLG-11: it plans, and says so before a deploy."""
    parked = "  - name: later\n    uses: ./ops/parked.py:Parked\n"
    p = Project(tmp_path, READY + parked)
    (tmp_path / "ops" / "parked.py").write_text(PLAN_ONLY)
    approved = p.plan()
    p.fake.clear_calls()
    with pytest.raises(
        Refused, match="`./ops/parked.py:Parked`, which can plan and can't apply yet"
    ):
        p.apply(approved)
    assert p.fake.calls == []


# -- the `stevin` step: apply, destroy, status -----------------------------------------

REMEMBERS = '''
import json
from dataclasses import dataclass
from pathlib import Path

from lely.model import Change, StepPlan


class Remembers:
    """Writes down what `apply` was handed: the plan, and the approved one."""

    @dataclass(frozen=True, slots=True)
    class Options:
        pass

    def plan(self, ctx):
        assert ctx.approved is None, "only `apply` is handed the approved plan"
        made = len(list(Path(ctx.root).glob("planned-*")))
        (Path(ctx.root) / f"planned-{made}").touch()
        run = Change("thing", "run", "thing")
        return StepPlan(changes=(run,), payload={"made": made})

    def apply(self, ctx, plan):
        approved = None if ctx.approved is None else ctx.approved.payload
        seen = {"fresh": plan.payload, "approved": approved}
        (Path(ctx.root) / "seen.json").write_text(json.dumps(seen))
        return {}
'''


def test_apply_is_handed_the_plan_that_was_approved_beside_the_fresh_one(
    tmp_path: Path,
) -> None:
    """PLG-14: also when the approved plan came from a file."""
    p = Project(
        tmp_path, "steps:\n  - name: one\n    uses: ./ops/remembers.py:Remembers\n"
    )
    (tmp_path / "ops" / "remembers.py").write_text(REMEMBERS)
    approved = planfile.loads(planfile.dumps(p.plan()))
    assert p.apply(approved).outcome == "done"
    seen = json.loads((tmp_path / "seen.json").read_text())
    assert seen == {"fresh": {"made": 1}, "approved": {"made": 0}}


def test_a_step_that_was_waiting_is_handed_no_approved_plan(tmp_path: Path) -> None:
    """PLG-14: nobody approved a plan of it before it was reached."""
    # a step waits through an option: this one takes what only a run gives
    waiting = REMEMBERS.replace("        pass\n", "        count: int\n")
    p = Project(
        tmp_path,
        "steps:\n  - name: seed\n    uses: ./ops/steps.py:Seed\n"
        "  - name: one\n    uses: ./ops/remembers.py:Remembers\n"
        "    with: {count: '${steps.seed.count}'}\n",
    )
    (tmp_path / "ops" / "remembers.py").write_text(waiting)
    approved = p.plan()
    assert approved.steps[1].state == "waiting"
    assert p.apply(approved, at_waiting=run_it).outcome == "done"
    seen = json.loads((tmp_path / "seen.json").read_text())
    assert seen == {"fresh": {"made": 0}, "approved": None}


def tables(
    tmp_path: Path, recording: str = "stevin-create.json", then: str = ""
) -> tuple[Project, FakeStevin]:
    """A project whose first step is stevin's, over a world of its own."""
    stevin = FakeStevin.planning(tmp_path / "stevin-world", recording)
    program = ", ".join(stevin.executable)
    p = Project(
        tmp_path,
        f"steps:\n  - name: tables\n    uses: stevin\n"
        f"    with:\n      executable: [{program}]\n{then}",
    )
    return p, stevin


#: A step below the tables, which leaves a file when it has run.
WARM = "  - name: warm\n    uses: ./ops/steps.py:Warm\n"


def test_the_stevin_step_applies_the_plan_file_that_was_approved(tmp_path: Path) -> None:
    """STV-4: through lely's own plan file, as a pull request's plan reaches
    the merge. stevin plans once more, for lely's check, and applies the file
    that was approved."""
    p, stevin = tables(tmp_path, then=WARM)
    approved = planfile.loads(planfile.dumps(p.plan()))
    reviewed = approved.steps[0].plan.payload
    stevin.clear_calls()
    result = p.apply(approved)
    assert result.outcome == "done", result.message
    assert outcomes(result) == {"tables": "done", "warm": "done"}
    # the overview after an apply is a `stevin list`: no plan is made for it
    assert stevin.verbs == ["plan", "apply", "list"]
    assert stevin.handed == reviewed
    assert len(stevin.applied) == 5
    assert (tmp_path / "warmed.txt").exists()
    tables_ = result.steps[0]
    assert tables_.overview is not None
    assert tables_.happened == {
        "dev.sales.customers": "created",
        "dev.sales.orders": "created",
        "dev.sales.big_orders": "created",
    }
    # the same plan again finds nothing left, and stevin is not asked to apply
    stevin.clear_calls()
    assert outcomes(p.apply(approved))["tables"] == "nothing"
    assert "apply" not in stevin.verbs


def test_a_stale_stevin_plan_stops_the_run_and_nothing_after_it_starts(
    tmp_path: Path,
) -> None:
    """STV-6: stevin refuses the approved file, in its own words; lely plans
    nothing again for it, and the step below never starts."""
    p, stevin = tables(tmp_path, then=WARM)
    approved = p.plan()
    stevin.told("moved", "a column was added by hand")
    result = p.apply(approved)
    assert result.outcome == "refused"
    assert outcomes(result) == {"tables": "refused", "warm": "not started"}
    assert "the live tables have changed since this plan was made" in result.message
    assert "Plan again with `lely plan`" in result.message
    assert stevin.applied == []
    assert not (tmp_path / "warmed.txt").exists()
    # the same file is refused again; a new plan is what runs
    assert p.apply(approved).outcome == "refused"
    assert p.apply(p.plan()).outcome == "done"


def test_a_destructive_stevin_step_needs_allow_destructive(tmp_path: Path) -> None:
    """STV-8: refused without lely's own permission, before stevin is asked
    to apply; with it, stevin is told too."""
    p, stevin = tables(tmp_path, "stevin-destroy.json")
    approved = p.plan()
    stevin.clear_calls()
    with pytest.raises(
        Refused, match="tables: dev.sales.orders. Pass --allow-destructive"
    ):
        p.apply(approved)
    assert stevin.calls == []
    result = p.apply(approved, allow_destructive=True)
    assert result.outcome == "done", result.message
    [apply] = [call for call in stevin.calls if call[0] == "apply"]
    assert apply[-1] == "--allow-destructive"
    assert stevin.applied == ["dev.sales.orders|DROP COLUMN|address"]


def test_a_risk_class_lely_doesnt_know_needs_allow_destructive(tmp_path: Path) -> None:
    """STV-3: what lely can't read is asked about, not waved through."""
    p, stevin = tables(tmp_path)
    stevin.told("risk", "irreversible")
    approved = p.plan()
    assert approved.summary.destructive == 3
    with pytest.raises(Refused, match="Pass --allow-destructive"):
        p.apply(approved)
    assert stevin.applied == []
    assert p.apply(approved, allow_destructive=True).outcome == "done"
    assert len(stevin.applied) == 5


def test_a_stevin_plan_that_was_applied_in_part_is_not_resumed(tmp_path: Path) -> None:
    """STV-5: the approved file holds steps that ran; what stevin would run
    now is less, so the file is refused and stevin is not asked."""
    p, stevin = tables(tmp_path)
    approved = p.plan()
    stevin.told("fail-step", "3")
    first = p.apply(approved)
    assert first.outcome == "failed"
    assert "Failed at step 3 of 5" in first.message
    assert len(stevin.applied) == 2  # the first table, whole
    stevin.told("fail-step", "")
    stevin.clear_calls()
    second = p.apply(approved)
    assert second.outcome == "refused"
    assert "5 step(s) then, 3 now" in second.message
    assert "apply" not in stevin.verbs
    assert p.apply(p.plan()).outcome == "done"
    assert len(stevin.applied) == 5


def test_a_destroy_leaves_stevins_tables_alone_and_says_so(tmp_path: Path) -> None:
    """STV-10, PLG-15: one line in the destroy plan, and stevin is never run."""
    p, stevin = tables(tmp_path, then=WARM)
    assert p.apply().outcome == "done"
    stevin.clear_calls()
    plan = p.plan("destroy")
    said = (
        "stevin drops nothing on a destroy: a dropped table is its rows. The tables stay."
    )
    assert (plan.steps[0].state, plan.steps[0].skipped) == ("skipped", said)
    assert plan.steps[0].plan.changes == ()
    result = p.destroy(plan)
    assert result.outcome == "done"
    assert {s.name: (s.outcome, s.detail) for s in result.steps}["tables"] == (
        "skipped",
        said,
    )
    assert stevin.calls == []
    assert len(stevin.applied) == 5


def test_status_lists_what_stevins_specs_describe(tmp_path: Path) -> None:
    """STV-13: a status asks `stevin list`, and makes no plan."""
    p, stevin = tables(tmp_path)
    found = running.status(p.config, target="dev", **edges(p.fake))
    overview = found.steps[0].overview
    assert overview is not None
    assert [(i.kind, i.key, i.deployed) for i in overview.items] == [
        ("view", "dev.sales.big_orders", False),
        ("table", "dev.sales.customers", False),
        ("table", "dev.sales.orders", False),
    ]
    assert stevin.verbs == ["list"]
    assert stevin.applied == []


def test_apply_refuses_a_plan_to_destroy(tmp_path: Path) -> None:
    """APL-1, ASK-4: a file can't smuggle a destroy."""
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
    """APL-8, APL-11."""
    p = failing(tmp_path)
    result = p.apply()
    assert result.outcome == "failed"
    assert [s.name for s in result.ran] == ["app"]
    assert [s.name for s in result.failed] == ["notify"]
    assert result.refused == ()
    assert [s.name for s in result.not_started] == ["backfill"]
    assert "`./ops/notify.sh 771` failed (exit 7)" in result.message
    assert "no route" in result.message
    assert p.fake.runs == []
    # nothing was rolled back: what was done, is done
    assert set(p.fake.deployed()) == {"jobs.backfill", "jobs.bar", "pipelines.foo"}


def test_running_it_again_finishes_the_job(tmp_path: Path) -> None:
    """APL-9, BDL-9: a step that already did its work plans as nothing left to
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
    """APL-10: the steps it passes over are planned, for what they give the
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


# -- a step whose plugin says it is waiting -------------------------------------------

LATER = '''
from dataclasses import dataclass
from pathlib import Path

from lely.model import Change, StepPlan


class Later:
    """Can plan its table only once `there.txt` exists. Until then it says it
    is waiting, and shows the one change it can already see."""

    @dataclass(frozen=True, slots=True)
    class Options:
        pass

    def plan(self, ctx):
        early = Change("early", "create", "early")
        if not (Path(ctx.root) / "there.txt").exists():
            return StepPlan((early,), waiting="there.txt is not there yet")
        return StepPlan((early, Change("late", "create", "late")))

    def apply(self, ctx, plan):
        (Path(ctx.root) / "applied.txt").write_text(
            ",".join(change.key for change in plan.changes)
        )
        return {}


class Makes:
    @dataclass(frozen=True, slots=True)
    class Options:
        pass

    def plan(self, ctx):
        return StepPlan((Change("there", "run", "makes there.txt"),))

    def apply(self, ctx, plan):
        (Path(ctx.root) / "there.txt").touch()
        return {}
'''


def later(tmp_path: Path, *, makes: bool = True) -> Project:
    above = "  - name: makes\n    uses: ./ops/later.py:Makes\n" if makes else ""
    p = Project(
        tmp_path, f"steps:\n{above}  - name: later\n    uses: ./ops/later.py:Later\n"
    )
    (tmp_path / "ops" / "later.py").write_text(LATER)
    return p


def test_a_step_whose_plugin_says_it_waits_is_held_like_any_waiting_step(
    tmp_path: Path,
) -> None:
    """WAIT-7: a plugin's own `waiting` makes the step waiting, with its
    reason. From a file the run stops there and runs none of it, not even the
    change the plan did show; in one go it is planned at its turn, shown whole
    and asked about; the next plan shows it ready."""
    p = later(tmp_path)
    approved = planfile.loads(planfile.dumps(p.plan()))
    step = approved.steps[1]
    assert (step.state, step.waiting) == (
        "waiting",
        "waiting: there.txt is not there yet",
    )
    assert [change.key for change in step.plan.changes] == ["early"]

    stopped = p.apply(approved, at_waiting=None)
    assert stopped.outcome == "refused"
    assert outcomes(stopped) == {"makes": "done", "later": "refused"}
    assert stopped.message == (
        "Step `later` was waiting when this plan was made (there.txt is not there "
        "yet), so nobody has seen what it will do. Plan again: the next plan shows it."
    )
    assert not (tmp_path / "applied.txt").exists()

    seen: list[PlannedStep] = []
    no = p.apply(approved, at_waiting=lambda step: bool(seen.append(step)))
    assert no.outcome == "refused"  # the answer was no
    assert not (tmp_path / "applied.txt").exists()
    assert p.apply(approved, at_waiting=run_it).outcome == "done"
    assert [change.key for change in seen[0].plan.changes] == ["early", "late"]
    assert (tmp_path / "applied.txt").read_text() == "early,late"

    (tmp_path / "applied.txt").unlink()
    ready = planfile.loads(planfile.dumps(p.plan()))
    assert ready.steps[1].state == "ready"
    assert p.apply(ready, at_waiting=None).outcome == "done"
    assert (tmp_path / "applied.txt").read_text() == "early,late"


def test_a_step_that_still_waits_at_its_turn_runs_nothing_whoever_is_asked(
    tmp_path: Path,
) -> None:
    """WAIT-7: nothing above it makes what it waits for, so the plan made at
    its turn is still not whole. Refused, with a file and without, and nobody
    is asked about a plan that can't be shown in full."""
    p = later(tmp_path, makes=False)
    asked: list[PlannedStep] = []
    for at_waiting in (None, lambda step: asked.append(step) is None):
        result = p.apply(at_waiting=at_waiting)
        assert result.outcome == "refused"
        assert result.message == (
            "Step `later` still can't be planned in full: there.txt is not there "
            "yet. No step above it brought that about in this run, so a new plan "
            "alone shows the same. Nothing of the step was run."
        )
    assert asked == []
    assert not (tmp_path / "applied.txt").exists()


# -- a first deploy: the tables' schema is the bundle's, and not there yet -----------

#: A bundle that declares the schema stevin's tables are in.
SALES = {
    "name": "shop",
    "variables": {},
    "resources": {"schemas": {"sales": {"name": "sales", "catalog_name": "dev"}}},
}


def first_deploy(tmp_path: Path) -> tuple[Project, FakeStevin]:
    """A data product on a target that was never deployed: the bundle, then
    stevin's tables in the bundle's schema, then a step below them."""
    stevin = FakeStevin.planning(tmp_path / "stevin-world")
    p = Project(
        tmp_path,
        "steps:\n  - name: app\n    uses: bundle\n"
        "  - name: tables\n    uses: stevin\n"
        f"    with:\n      executable: [{', '.join(stevin.executable)}]\n{WARM}",
        deployed=False,
    )
    write_bundle(tmp_path, SALES)
    stevin.in_a_schema_of(p.fake, "schemas.sales")
    return p, stevin


def test_on_a_first_deploy_the_bundle_is_ready_and_the_tables_wait(
    tmp_path: Path,
) -> None:
    """The plan is made, with the tables waiting and why. It reads back from
    a plan file as it was made."""
    p, stevin = first_deploy(tmp_path)
    plan = p.plan()
    assert [(s.name, s.state) for s in plan.steps] == [
        ("app", "ready"),
        ("tables", "waiting"),
        ("warm", "ready"),
    ]
    tables_ = plan.steps[1]
    assert tables_.waiting == (
        "waiting: a schema of these tables is the bundle's and is not deployed "
        "yet; the tables are planned once it is"
    )
    assert tables_.waits_for == ()
    assert tables_.plan.notes == (
        "stevin: dev.sales is the bundle's schema 'sales', and isn't there yet "
        "\u2014 run `databricks bundle deploy` first; stevin won't create it",
    )
    assert (tables_.plan.changes, tables_.plan.payload) == ((), None)
    assert plan.summary.waiting == 1
    assert [s.name for s in plan.waiting] == ["tables"]
    assert planfile.loads(planfile.dumps(plan)) == plan
    assert stevin.verbs == ["plan"]
    assert p.fake.deployed() == {}  # a plan changes nothing


def test_a_file_that_showed_the_tables_waiting_applies_none_of_them(
    tmp_path: Path,
) -> None:
    """STV-18: the bundle runs, since it was reviewed. The tables were never
    shown: stevin plans them, for lely to see they are ready, and is not asked
    to apply. Nothing below them starts. The next plan shows them."""
    p, stevin = first_deploy(tmp_path)
    approved = planfile.loads(planfile.dumps(p.plan()))
    stevin.clear_calls()
    result = p.apply(approved, at_waiting=None)
    assert result.outcome == "refused"
    assert outcomes(result) == {
        "app": "done",
        "tables": "refused",
        "warm": "not started",
    }
    assert result.message == (
        "Step `tables` was waiting when this plan was made (a schema of these "
        "tables is the bundle's and is not deployed yet; the tables are planned "
        "once it is), so nobody has seen what it will do. Plan again: the next "
        "plan shows it."
    )
    assert "schemas.sales" in p.fake.deployed()
    assert stevin.verbs == ["plan"]
    assert stevin.applied == []
    assert not (tmp_path / "warmed.txt").exists()
    # the same file again, and with `--from`: still nothing of the tables
    for kwargs in ({}, {"from_step": "tables"}, {"allow_destructive": True}):
        again = p.apply(approved, at_waiting=None, **kwargs)
        assert (again.outcome, outcomes(again)["tables"]) == ("refused", "refused")
    assert stevin.applied == []
    # `--from` a step below goes past the tables, as it goes past any step:
    # they are planned for what they give, and not applied
    below = p.apply(approved, at_waiting=None, from_step="warm")
    assert outcomes(below) == {"app": "passed", "tables": "passed", "warm": "done"}
    assert "apply" not in stevin.verbs
    assert stevin.applied == []
    (tmp_path / "warmed.txt").unlink()

    second = planfile.loads(planfile.dumps(p.plan()))
    assert [(s.name, s.state) for s in second.steps][1] == ("tables", "ready")
    assert [c.action for c in second.steps[1].plan.changes] == ["create"] * 3
    # no step creates the schema: it is the bundle's
    assert "CREATE SCHEMA" not in json.dumps(second.steps[1].plan.payload)
    assert "CREATE TABLE" in json.dumps(second.steps[1].plan.payload)
    stevin.clear_calls()
    done = p.apply(second, at_waiting=None)
    assert done.outcome == "done", done.message
    assert stevin.handed == second.steps[1].plan.payload  # the file that was reviewed
    assert len(stevin.applied) == 4
    assert (tmp_path / "warmed.txt").exists()


def test_in_one_go_the_tables_are_planned_shown_and_asked_about_after_the_bundle(
    tmp_path: Path,
) -> None:
    """STV-19: the bundle is deployed first; then stevin plans, the plan is
    shown, and what was shown is what stevin is handed. An answer that is not
    yes applies none of it."""
    p, stevin = first_deploy(tmp_path)
    approved = p.plan()
    seen: list[PlannedStep] = []

    def no(step: PlannedStep) -> bool:
        seen.append(step)
        assert "schemas.sales" in p.fake.deployed()  # the bundle ran first
        return False

    refused = p.apply(approved, at_waiting=no)
    assert refused.outcome == "refused"
    assert refused.message == "Step `tables` wasn't approved. Nothing more was run."
    assert stevin.applied == []
    assert "apply" not in stevin.verbs
    assert not (tmp_path / "warmed.txt").exists()

    def yes(step: PlannedStep) -> bool:
        seen.append(step)
        return True

    stevin.clear_calls()
    result = p.apply(approved, at_waiting=yes)
    assert result.outcome == "done", result.message
    assert outcomes(result) == {"app": "done", "tables": "done", "warm": "done"}
    for shown in seen:
        assert (shown.name, shown.state) == ("tables", "ready")
        assert [c.key for c in shown.plan.changes] == [
            "dev.sales.customers",
            "dev.sales.orders",
            "dev.sales.big_orders",
        ]
    assert stevin.verbs == ["plan", "apply", "list"]
    assert stevin.handed == seen[-1].plan.payload
    assert len(stevin.applied) == 4


def test_tables_that_still_wait_when_their_turn_comes_are_not_applied(
    tmp_path: Path,
) -> None:
    """STV-19: the bundle ran and the schema is still not there, because this
    bundle deploys another one. The run stops as refused, with or without a
    file, and whatever is answered: nobody could be shown a plan."""
    p, stevin = first_deploy(tmp_path)
    stevin.in_a_schema_of(p.fake, "schemas.other")
    asked: list[PlannedStep] = []
    for at_waiting in (None, lambda step: asked.append(step) is None):
        result = p.apply(p.plan(), at_waiting=at_waiting)
        assert result.outcome == "refused"
        assert result.message == (
            "Step `tables` still can't be planned in full: a schema of these "
            "tables is the bundle's and is not deployed yet; the tables are "
            "planned once it is. No step above it brought that about in this run, "
            "so a new plan alone shows the same. Nothing of the step was run."
        )
        assert outcomes(result)["warm"] == "not started"
    assert asked == []
    assert "apply" not in stevin.verbs
    assert stevin.applied == []


def test_another_failure_of_stevin_plan_still_fails_the_plan(tmp_path: Path) -> None:
    """STV-16: only exit 5 waits. A plan that fails is no plan, on a first
    deploy as on any other; and one that fails when the run reaches the step
    fails the run."""
    p, stevin = first_deploy(tmp_path)
    approved = p.plan()
    stevin.told("fail-plan", "tables/orders.yml: unknown key `colums`")
    with pytest.raises(LelyError, match=r"(?s)`stevin plan` failed \(exit 1\).*colums"):
        p.plan()
    result = p.apply(approved, at_waiting=run_it)
    assert (result.outcome, outcomes(result)["tables"]) == ("failed", "failed")
    assert stevin.applied == []


def test_a_destroy_and_a_status_before_the_bundle_is_deployed(tmp_path: Path) -> None:
    """STV-17: neither fails on a target never deployed. A destroy skips the
    tables and stevin is not run; a status lists them, each not there."""
    p, stevin = first_deploy(tmp_path)
    plan = p.plan("destroy")
    assert plan.steps[1].skipped == (
        "stevin drops nothing on a destroy: a dropped table is its rows. The tables stay."
    )
    result = p.destroy(plan)
    assert result.outcome == "done", result.message
    assert outcomes(result)["tables"] == "skipped"
    assert stevin.calls == []

    status = running.status(p.config, target="dev", **edges(p.fake))
    listed = status.steps[1].overview
    assert listed is not None
    assert [(item.name, item.deployed) for item in listed.items] == [
        ("big_orders", False),
        ("customers", False),
        ("orders", False),
    ]
    assert stevin.verbs == ["list"]


# -- a step that can't be planned yet ----------------------------------------------


def test_a_reviewed_file_stops_at_a_waiting_step(tmp_path: Path) -> None:
    """WAIT-3: it runs what was reviewed. WAIT-6: never out of order."""
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
    """WAIT-3: a first deploy through a reviewed file can take two rounds."""
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
    """WAIT-4, WAIT-5: `--yes` runs it; a terminal is shown the step and asked again."""
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
    """WAIT-5."""
    p = Project(tmp_path)
    result = p.apply(at_waiting=lambda step: False)
    assert result.outcome == "refused"
    assert result.message == "Step `notify` wasn't approved. Nothing more was run."
    assert p.notified() == []
    assert outcomes(result)["backfill"] == "not started"


def test_a_waiting_step_doesnt_get_past_the_other_rules(tmp_path: Path) -> None:
    """WAIT-6: a destructive change in a step that was waiting needs the flag."""
    (tmp_path / "drops.py").write_text(
        "from dataclasses import dataclass\n"
        "from lely.model import Change, StepPlan\n"
        "class DropsCache:\n"
        "    '''Takes the job's id, and plans to drop a cache.'''\n"
        "    @dataclass(frozen=True)\n"
        "    class Options:\n"
        "        job: str\n"
        "    def plan(self, ctx):\n"
        "        drop = Change('cache', 'delete', 'drops the cache', destructive=True)\n"
        "        return StepPlan((drop,))\n"
        "    def apply(self, ctx, plan):\n"
        "        return {}\n"
    )
    text = project.LELY_YML.replace(
        "uses: ./ops/steps.py:Notify", "uses: ./drops.py:DropsCache"
    )
    p = Project(tmp_path, text)
    result = p.apply(at_waiting=run_it)
    assert result.outcome == "refused"
    assert "Step `notify` holds destructive changes — drops the cache" in result.message
    assert p.apply(at_waiting=run_it, allow_destructive=True).outcome == "done"


def test_a_step_that_takes_an_output_of_a_run_gets_it_at_apply(tmp_path: Path) -> None:
    """WAIT-2: what a program gives by running is known after the run."""
    text = (
        "steps:\n"
        "  - name: seed\n    uses: ./ops/steps.py:Seed\n"
        "  - name: notify\n    uses: ./ops/steps.py:Notify\n"
        "    with: {job: '${steps.seed.count}'}\n"
    )
    p = Project(tmp_path, text)
    approved = p.plan()
    assert [s.state for s in approved.steps] == ["ready", "waiting"]
    assert p.apply(approved, at_waiting=None).outcome == "refused"  # every deploy
    assert p.apply(approved, at_waiting=run_it).outcome == "done"
    assert p.notified() == ["3"]


# -- destroy -----------------------------------------------------------------------

DROP_PY = """\
import subprocess
from dataclasses import dataclass
from lely.model import Change, StepPlan

class Drop:
    '''Nothing at apply; at destroy, tells notify.sh the job id it was given.'''
    @dataclass(frozen=True)
    class Options:
        job: str
    def plan(self, ctx):
        return StepPlan()
    def apply(self, ctx, plan):
        return {}
    def plan_destroy(self, ctx):
        run = f"runs ./ops/notify.sh {ctx.options.job}"
        return StepPlan((Change("drop", "run", run, destructive=True),))
    def destroy(self, ctx, plan):
        subprocess.run(["./ops/notify.sh", ctx.options.job], cwd=ctx.root, check=True)
"""

DROP = (
    "  - name: drop\n    uses: ./drop.py:Drop\n"
    "    with: {job: '${steps.app.resources.jobs.backfill.id}'}\n"
)


def with_drop(tmp_path: Path, text: str = READY) -> str:
    """`text` with a `drop` step below it, whose plugin is in the folder."""
    (tmp_path / "drop.py").write_text(DROP_PY)
    return text + DROP


def test_destroy_goes_from_the_bottom_up(tmp_path: Path) -> None:
    """DST-1, DST-2, REF-9: a step below the bundle is destroyed while the
    bundle, and the id it needed, still exist."""
    p = Project(tmp_path, with_drop(tmp_path))
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
    """DST-3."""
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
    """DST-5: anything that wasn't in the approved plan stops the run."""
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
    """DST-6."""
    p = Project(tmp_path, deployed=False)
    result = p.destroy()
    assert result.outcome == "done"
    assert outcomes(result)["app"] == "nothing"
    assert "destroy" not in p.fake.verbs


def test_from_names_where_a_destroy_starts_going_up(tmp_path: Path) -> None:
    """APL-10."""
    p = Project(tmp_path, with_drop(tmp_path))
    result = p.destroy(from_step="app")
    assert [(s.name, s.outcome) for s in result.steps][:2] == [
        ("drop", "passed"),
        ("warm", "skipped"),
    ]
    assert outcomes(result)["app"] == "done"
    assert p.notified() == []


def test_a_failing_destroy_stops_and_leaves_the_rest(tmp_path: Path) -> None:
    """APL-8."""
    p = Project(tmp_path, with_drop(tmp_path))
    (tmp_path / "ops" / "notify.sh").write_text("#!/bin/sh\nexit 3\n")
    result = p.destroy()
    assert result.outcome == "failed"
    assert [s.name for s in result.failed] == ["drop"]
    assert [s.name for s in result.not_started] == ["backfill", "notify", "app", "model"]
    assert p.fake.deployed() == project.DEPLOYED


def test_destroy_refuses_a_plan_to_apply(tmp_path: Path) -> None:
    p = Project(tmp_path, READY)
    with pytest.raises(Refused, match="`lely destroy` only destroys") as caught:
        p.destroy(p.plan("apply"))
    assert "Run it with `lely apply <file>`." in str(caught.value)


# -- status ------------------------------------------------------------------------


def test_status_shows_every_step_and_changes_nothing(tmp_path: Path) -> None:
    """CLI-3."""
    p = Project(tmp_path)
    before = p.fake.state
    found = running.status(p.config, target="dev", **edges(p.fake))
    assert p.fake.state == before
    assert set(p.fake.verbs) <= {"summary", "plan"}
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


# -- found in review ---------------------------------------------------------------


def test_a_destroy_holds_a_skipped_step_to_having_shown_nothing(tmp_path: Path) -> None:
    """A step the approved plan showed as skipped showed nothing it would
    remove: whatever it would remove now was never approved."""
    p = Project(tmp_path)
    approved = p.plan("destroy")
    hidden = dataclasses.replace(
        approved,
        steps=tuple(
            dataclasses.replace(step, skipped="nothing deployed")
            if step.name == "app"
            else step
            for step in approved.steps
        ),
    )
    result = p.destroy(hidden)
    assert result.outcome == "refused"
    assert "Step `app` would now also delete jobs.backfill" in result.message
    assert p.fake.deployed() == project.DEPLOYED


def versioned(tmp_path: Path, text: str) -> Project:
    (tmp_path / "version.txt").write_text("14")
    (tmp_path / "latest.py").write_text(VERSIONED)
    return Project(
        tmp_path,
        text.replace(
            "uses: ./ops/steps.py:LatestModel\n    with:\n      model: dev.ml.churn",
            "uses: ./latest.py:Latest",
        ),
    )


def test_a_destroy_is_held_to_the_inputs_the_plan_showed(tmp_path: Path) -> None:
    """DST-5, PLAN-4: a destroy acts on the values it is handed — `bundle destroy`
    with other variables, a destroy command with another id — so they have to
    be the ones that were shown. Checked before anything is removed."""
    p = versioned(tmp_path, with_drop(tmp_path))
    approved = p.plan("destroy")
    (tmp_path / "version.txt").write_text("1500")
    with pytest.raises(Refused) as caught:
        p.destroy(approved)
    assert str(caught.value) == (
        "Step `app` takes model.version = 1500 now; the plan was approved with 14. "
        "Plan again."
    )
    assert p.fake.deployed() == project.DEPLOYED
    assert p.notified() == []  # the destroy command below the bundle didn't run


def test_from_doesnt_pass_over_the_check_on_what_a_step_takes(tmp_path: Path) -> None:
    """APL-10. A step `--from` passes over is planned for what it gives the steps
    below. What it gives was approved with these values."""
    p = versioned(tmp_path, READY)
    approved = p.plan()
    (tmp_path / "version.txt").write_text("1500")
    result = p.apply(approved, from_step="backfill")
    assert result.outcome == "refused"
    assert "Step `app` takes model.version = 1500 now" in result.message
    assert p.fake.runs == []  # `bundle run` would have gone out with the new value


def test_a_destroy_that_finds_nothing_says_whose_view_that_is(tmp_path: Path) -> None:
    """BDL-13: never a bare "nothing there". The plan listed a job; run as
    another identity (V7), it isn't there to destroy."""
    project.write(tmp_path)
    world = project.world(tmp_path)
    write_bundle(tmp_path, {**project.BUNDLE, "profiles": {"ci": "ci@example.com"}})
    config = load(tmp_path / "lely.yml")
    approved = planning.plan(
        config,
        target="dev",
        source=Source(),
        kind="destroy",
        **edges(FakeDatabricks(world)),
    )
    assert [c.key for c in approved.steps[1].plan.changes] == ["jobs.backfill"]
    other = FakeDatabricks(world, profile="ci")
    result = running.destroy(config, approved, **edges(other))
    assert result.outcome == "done"
    app = next(step for step in result.steps if step.name == "app")
    assert app.outcome == "nothing"
    assert app.detail == (
        "nothing the plan listed is there to destroy; not deployed, as far as "
        "ci@example.com can see under /Workspace/Users/ci@example.com/.bundle/shop/dev"
    )
    assert FakeDatabricks(world).deployed() == project.DEPLOYED


IDLE = """\
from dataclasses import dataclass
from lely.model import Item, Output, Overview, StepPlan

class Idle:
    '''Declares an id it would give by running, and never plans a run.'''
    @dataclass(frozen=True)
    class Options:
        pass
    outputs = (Output("id", "exists"),)
    def plan(self, ctx):
        return StepPlan(later=("id",))
    def apply(self, ctx, plan):
        return {"id": "1"}

class Numbered(Idle):
    '''An overview line whose id isn't text.'''
    outputs = ()
    def plan(self, ctx):
        return StepPlan()
    def overview(self, ctx):
        return Overview((Item("thing", "a", "a", True, id=123),))
"""


def test_a_plugin_that_never_ran_is_named_when_what_it_gives_is_missed(
    tmp_path: Path,
) -> None:
    (tmp_path / "idle.py").write_text(IDLE)
    text = (
        "steps:\n"
        "  - name: made\n    uses: ./idle.py:Idle\n"
        "  - name: report\n    uses: ./ops/steps.py:Notify\n"
        "    with: {job: '${steps.made.id}'}\n"
    )
    p = Project(tmp_path, text)
    result = p.apply(at_waiting=run_it)
    assert result.outcome == "failed"
    assert "Step `report`: it needs made.id, which isn't there" in result.message
    assert "Step `made` had nothing to do, so it didn't run" in result.message


def test_an_overview_line_that_isnt_text_is_a_message_not_a_crash(
    tmp_path: Path,
) -> None:
    (tmp_path / "idle.py").write_text(IDLE)
    p = Project(tmp_path, "steps:\n  - name: odd\n    uses: ./idle.py:Numbered\n")
    with pytest.raises(LelyError, match="id and url are text or nothing"):
        running.status(p.config, target="dev", **edges(p.fake))
    # after an apply, that it can't be listed doesn't undo the run
    result = p.apply()
    assert result.outcome == "done"
    assert result.steps[0].detail.startswith("couldn't be listed: ")


def test_from_is_checked_before_anything_is_planned(tmp_path: Path) -> None:
    p = Project(tmp_path, READY)
    with pytest.raises(Refused, match="no step `nope` runs for target `dev`"):
        running.check_from(p.config, "dev", "nope")
    with pytest.raises(Refused, match="no step `warm` runs for target `dev`"):
        running.check_from(p.config, "dev", "warm")  # it is for prod only
    running.check_from(p.config, "dev", "app")
    running.check_from(p.config, "dev", None)


# -- found in the second review ------------------------------------------------------

SEEDS = """\
from dataclasses import dataclass
from lely.model import Change, Output, StepPlan

class Tables:
    '''Says part of its destroy plan has to wait, and shows the rest.'''
    @dataclass(frozen=True)
    class Options:
        pass
    def plan(self, ctx):
        return StepPlan()
    def apply(self, ctx, plan):
        return {}
    def plan_destroy(self, ctx):
        dropped = (ctx.root / "dropped.txt").exists()
        changes = () if dropped else (Change("t1", "delete", "drops table t1"),)
        return StepPlan(changes, waiting="t2 is still being written to")
    def destroy(self, ctx, plan):
        (ctx.root / "dropped.txt").write_text("t1")

class Names:
    '''Gives a tuple, and a change with no summary: what a plan file reads
    back as a list, and as the change's key.'''
    @dataclass(frozen=True)
    class Options:
        pass
    outputs = (Output("names"),)
    def plan(self, ctx):
        return StepPlan((Change("k", "run", ""),), {"names": ("a", "b")})
    def apply(self, ctx, plan):
        return {"names": ("a", "b")}

class Takes:
    @dataclass(frozen=True)
    class Options:
        names: object = None
    def plan(self, ctx):
        return StepPlan((Change("took", "run", f"takes {ctx.options.names}"),))
    def apply(self, ctx, plan):
        return {}

class Dated(Names):
    outputs = (Output("when", "run"),)
    def plan(self, ctx):
        return StepPlan((Change("k", "run", "k"),))
    def apply(self, ctx, plan):
        import datetime
        return {"when": datetime.date(2026, 10, 5)}
"""


def test_a_destroy_step_that_says_part_has_to_wait_destroys_what_it_showed(
    tmp_path: Path,
) -> None:
    """A plugin's own "part of this has to wait" is not the same as a step
    lely skipped: what it showed was approved."""
    (tmp_path / "seeds.py").write_text(SEEDS)
    p = Project(tmp_path, "steps:\n  - name: tables\n    uses: ./seeds.py:Tables\n")
    approved = p.plan("destroy")
    assert approved.steps[0].state == "waiting"
    assert [c.summary for c in approved.steps[0].plan.changes] == ["drops table t1"]
    result = p.destroy(approved)
    assert result.outcome == "done", result.message
    assert (tmp_path / "dropped.txt").read_text() == "t1"


def test_a_plan_is_the_same_whether_or_not_it_went_through_a_file(
    tmp_path: Path,
) -> None:
    """A tuple a plugin gave reads back from a file as a list; a change with no
    summary reads back named by its key. Planning hands on the plain form, so
    what was approved and what is planned again compare equal either way."""
    from lely import planfile

    (tmp_path / "seeds.py").write_text(SEEDS)
    text = (
        "steps:\n  - name: tables\n    uses: ./seeds.py:Names\n"
        "  - name: after\n    uses: ./seeds.py:Takes\n"
        "    with: {names: '${steps.tables.names}'}\n"
    )
    p = Project(tmp_path, text)
    approved = p.plan()
    assert approved.steps[0].plan.outputs == {"names": ["a", "b"]}
    assert approved.steps[0].plan.changes[0].summary == "k"
    assert planfile.loads(planfile.dumps(approved)) == approved
    assert p.apply(approved).outcome == "done"  # without a file
    through_a_file = planfile.loads(planfile.dumps(p.plan()))
    assert p.apply(through_a_file).outcome == "done"


def test_what_apply_gives_has_to_be_json_and_says_so(tmp_path: Path) -> None:
    (tmp_path / "seeds.py").write_text(SEEDS)
    p = Project(tmp_path, "steps:\n  - name: stamp\n    uses: ./seeds.py:Dated\n")
    result = p.apply()
    assert result.outcome == "failed"
    assert "`apply`: an output holds a date, which isn't JSON" in result.message


def test_a_target_no_step_runs_for_is_refused(tmp_path: Path) -> None:
    """CLI-2. lely keeps no list of targets, so a mistyped one is caught by a
    plugin that checks it — unless every step's `targets` leave it out, and no
    plugin is asked. That used to end "Nothing to do", exit 0."""
    text = (
        "steps:\n  - name: app\n    uses: bundle\n    targets: [dev, prod]\n"
        "    with: {vars: {model_version: 1}}\n"
    )
    p = Project(tmp_path, text)
    for call in (
        lambda: planning.plan(p.config, target="prd", source=Source(), **edges(p.fake)),
        lambda: running.status(p.config, target="prd", **edges(p.fake)),
        lambda: running.check_applies(p.config, "prd"),
    ):
        with pytest.raises(Refused) as caught:
            call()
        assert str(caught.value) == (
            "No step runs for target `prd`: every step's `targets` leave it out "
            "(dev, prod)."
        )
    assert p.fake.calls == []
    planning.runs_for(p.config, "prod")


def test_an_overview_line_says_whether_it_is_deployed_in_one_word(tmp_path: Path) -> None:
    """Found in the sixth review: `deployed=Decimal(1)` went through, and
    ended `apply -o` in a traceback once the steps had run. A run is not
    undone by a list lely can't take: it says so beside the step."""
    (tmp_path / "odd.py").write_text(
        "from dataclasses import dataclass\n"
        "from decimal import Decimal\n"
        "from lely.model import Change, Item, Overview, StepPlan\n"
        "class Odd:\n"
        "    @dataclass(frozen=True)\n"
        "    class Options:\n"
        "        pass\n"
        "    def plan(self, ctx):\n"
        "        return StepPlan((Change('k', 'run', 'runs'),))\n"
        "    def apply(self, ctx, plan):\n"
        "        return {}\n"
        "    def overview(self, ctx):\n"
        "        return Overview((Item('job', 'k', 'n', Decimal(1)),))\n"
    )
    config = load(
        project.write(tmp_path, "steps:\n  - name: x\n    uses: ./odd.py:Odd\n")
    )
    fake = project.databricks(tmp_path)
    approved = planning.plan(config, target="dev", source=Source(), **edges(fake))
    result = running.apply(config, approved, **edges(fake))
    assert result.outcome == "done"
    [step] = result.steps
    assert step.overview is None
    assert "an overview line's `deployed` is true or false" in step.detail
    json.dumps(planfile.result_to_json(result))


def test_a_literal_dollar_brace_reaches_the_program_as_it_is_meant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """REF-3: `$${…}` is a literal `${…}`, for the shell to read — no reference."""
    monkeypatch.setenv("LELY_TEST_HOME", "/home/jane")
    (tmp_path / "shell.py").write_text(
        "from dataclasses import dataclass\n"
        "from lely.step import Program\n"
        "class Shell(Program):\n"
        "    '''Runs a line of shell.'''\n"
        "    @dataclass(frozen=True)\n"
        "    class Options:\n"
        "        script: str\n"
        "    def command(self, ctx):\n"
        "        return ['sh', '-c', ctx.options.script]\n"
    )
    p = Project(
        tmp_path,
        "steps:\n  - name: seed\n    uses: ./shell.py:Shell\n    with:\n"
        "      script: 'echo \"$${LELY_TEST_HOME}\" > home.txt'\n",
    )
    given: dict[str, Any] = {**edges(p.fake), "env": dict(os.environ)}
    result = running.apply(p.config, p.plan(), **given)
    assert result.outcome == "done", result.message
    assert (tmp_path / "home.txt").read_text() == "/home/jane\n"


# -- an output that holds a secret option ------------------------------------------

ECHO = """\
from dataclasses import dataclass
from pathlib import Path
from lely.model import Change, Output, Secret, StepPlan

class Echo:
    # hands its secret option back as plain text, after a run: a plugin's mistake
    @dataclass(frozen=True)
    class Options:
        token: Secret
    outputs = (Output("url", known="run"),)
    def plan(self, ctx):
        return StepPlan(changes=(Change("url", "run", "asks for the url"),))
    def apply(self, ctx, plan):
        return {"url": f"https://user:{ctx.options.token.reveal()}@host"}

class Takes:
    @dataclass(frozen=True)
    class Options:
        url: Secret
    def plan(self, ctx):
        return StepPlan(changes=(Change("taken", "run", "takes the url"),))
    def apply(self, ctx, plan):
        Path(ctx.root, "taken.txt").write_text(ctx.options.url.reveal())
        return {}
"""


def test_an_output_a_run_gives_that_holds_a_secret_option_is_a_secret(
    tmp_path: Path,
) -> None:
    """SEC-5: also for what `apply` returns, through a plan file. The step
    below is handed it whole, and the run's record holds a marker."""
    (tmp_path / "echo.py").write_text(ECHO)
    text = (
        "steps:\n  - name: echo\n    uses: ./echo.py:Echo\n"
        "    with: {token: t0p-s3cret}\n"
        "  - name: takes\n    uses: ./echo.py:Takes\n"
        "    with: {url: '${steps.echo.url}'}\n"
    )
    p = Project(tmp_path, text)
    written = planfile.dumps(p.plan())
    assert "t0p-s3cret" not in written
    result = p.apply(planfile.loads(written), at_waiting=run_it)
    assert outcomes(result) == {"echo": "done", "takes": "done"}, result.message
    assert (tmp_path / "taken.txt").read_text() == "https://user:t0p-s3cret@host"
    assert "t0p-s3cret" not in json.dumps(planfile.result_to_json(result))
