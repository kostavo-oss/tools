"""What may run: consent covers what was shown. Each rule, on its own."""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest

import project
from lely import approval
from lely.errors import Refused
from lely.model import (
    Change,
    Input,
    Plan,
    PlannedStep,
    Secret,
    Source,
    StepPlan,
    Workspace,
)

CREATE = Change("jobs.bar", "create", "jobs.bar")
UPDATE = Change("jobs.foo", "update", "jobs.foo", detail=("description",))
SHOWN = StepPlan(changes=(CREATE, UPDATE))


def plan(*steps: PlannedStep, **source: Any) -> Plan:
    return Plan("0.0.1", "apply", "dev", project.WORKSPACE, Source(**source), steps)


# -- the approval check (005/R7) ---------------------------------------------------


def test_the_same_changes_are_approved() -> None:
    approval.approved_changes(SHOWN, SHOWN, "app")


def test_fewer_changes_is_fine() -> None:
    """Someone else did part of the work, or an earlier run did."""
    approval.approved_changes(SHOWN, StepPlan(changes=(UPDATE,)), "app")
    approval.approved_changes(SHOWN, StepPlan(), "app")


def test_anything_new_stops_the_run() -> None:
    fresh = StepPlan(changes=(CREATE, Change("jobs.new", "delete", "jobs.new")))
    with pytest.raises(Refused) as caught:
        approval.approved_changes(SHOWN, fresh, "app")
    assert str(caught.value) == (
        "Step `app` would now also delete jobs.new, which the approved plan didn't "
        "show. Plan again."
    )


@pytest.mark.parametrize(
    "now",
    [
        dataclasses.replace(UPDATE, action="replace"),  # another kind of change
        dataclasses.replace(UPDATE, destructive=True),
        dataclasses.replace(UPDATE, detail=("description", "tasks")),  # other lines
        dataclasses.replace(UPDATE, summary="jobs.foo (renamed)"),
    ],
)
def test_anything_that_reads_differently_stops_the_run(now: Change) -> None:
    """Made stricter on 2026-10-05: the design matched a change by its name alone."""
    with pytest.raises(
        Refused, match="the approved plan showed it would update jobs.foo"
    ):
        approval.approved_changes(SHOWN, StepPlan(changes=(now,)), "app")


# -- destructive (005/R8) ----------------------------------------------------------


def test_a_destructive_change_needs_the_flag() -> None:
    drop = Change("pipelines.foo", "replace", "pipelines.foo")
    steps = (PlannedStep("app", "bundle", "h", StepPlan(changes=(CREATE, drop))),)
    with pytest.raises(Refused) as caught:
        approval.destructive_allowed(steps, allow=False)
    assert "app: pipelines.foo" in str(caught.value)
    assert "--allow-destructive" in str(caught.value)
    approval.destructive_allowed(steps, allow=True)
    approval.destructive_allowed(steps[:0], allow=False)


def test_a_skipped_step_holds_nothing_to_allow() -> None:
    drop = StepPlan(changes=(Change("t", "delete", "t"),))
    skipped = PlannedStep("x", "y", "h", drop, skipped="not for target `dev`")
    approval.destructive_allowed((skipped,), allow=False)


# -- the plan file against the project (005/R5) -------------------------------------

STEPS = (PlannedStep("model", "lookup", "aaa"), PlannedStep("app", "bundle", "bbb"))


def test_the_same_steps_with_the_same_options_are_the_same_project() -> None:
    approval.same_project(
        plan(*STEPS), [("model", "lookup", "aaa"), ("app", "bundle", "bbb")]
    )


def test_a_step_added_removed_or_moved_makes_the_plan_stale() -> None:
    with pytest.raises(Refused) as caught:
        approval.same_project(plan(*STEPS), [("app", "bundle", "bbb")])
    assert str(caught.value) == (
        "The plan was made for the steps model, app; the project now has app. Plan again."
    )
    with pytest.raises(Refused, match="the project now has app, model"):
        approval.same_project(
            plan(*STEPS), [("app", "bundle", "bbb"), ("model", "lookup", "aaa")]
        )


def test_a_reconfigured_step_makes_the_plan_stale_and_is_named() -> None:
    with pytest.raises(Refused, match="Step `app` is configured differently"):
        approval.same_project(
            plan(*STEPS), [("model", "lookup", "aaa"), ("app", "bundle", "ccc")]
        )
    with pytest.raises(Refused, match="Step `model` is configured differently"):
        approval.same_project(
            plan(*STEPS), [("model", "other", "aaa"), ("app", "bundle", "bbb")]
        )


def test_an_input_that_changed_since_the_plan_was_never_approved() -> None:
    """The plan showed `model_version = 14`; 15 is another deploy."""
    was = PlannedStep(
        "app", "bundle", "h", inputs=(Input("model_version", "model.version", 14),)
    )
    approval.same_inputs(was, [Input("model_version", "model.version", 14)])
    with pytest.raises(Refused) as caught:
        approval.same_inputs(was, [Input("model_version", "model.version", 15)])
    assert str(caught.value) == (
        "Step `app` takes model.version = 15 now; the plan was approved with 14. "
        "Plan again."
    )


def test_what_wasnt_known_at_plan_and_what_is_secret_isnt_compared() -> None:
    was = PlannedStep(
        "notify",
        "command",
        "h",
        inputs=(
            Input("", "app.resources.jobs.bar.id", None, known=False),
            Input("token", "login.token", Secret()),
        ),
    )
    approval.same_inputs(
        was,
        [
            Input("", "app.resources.jobs.bar.id", "1001"),
            Input("token", "login.token", Secret("t0k")),
        ],
    )


# -- the workspace (005/R35) and the tree (005/R36) ---------------------------------


def test_a_plan_made_against_one_workspace_is_refused_on_another() -> None:
    approval.same_workspace(
        plan(), Workspace(project.WORKSPACE.host + "/", "ci@example.com")
    )
    with pytest.raises(Refused) as caught:
        approval.same_workspace(plan(), Workspace("https://prod.example.com", "jane"))
    assert "this run talks to https://prod.example.com" in str(caught.value)


def test_a_plan_is_refused_on_another_tree() -> None:
    approved = plan(tree="aaaaaaaaaaaaaaaa")
    approval.same_source(approved, Source("aaaaaaaaaaaaaaaa"))
    with pytest.raises(
        Refused, match="made on git tree aaaaaaaaaaaa.*now on bbbbbbbbbbbb"
    ):
        approval.same_source(approved, Source("bbbbbbbbbbbbbbbb"))
    with pytest.raises(
        Refused, match="uncommitted changes that the plan was made without"
    ):
        approval.same_source(approved, Source("aaaaaaaaaaaaaaaa", dirty=True))
    with pytest.raises(Refused, match="this isn't one"):
        approval.same_source(approved, Source())


def test_a_plan_that_recorded_nothing_can_be_held_to_nothing() -> None:
    """Outside a git repository, or with uncommitted changes: it said so when
    it was made."""
    approval.same_source(plan(), Source("bbbb"))
    approval.same_source(plan(tree="aaaa", dirty=True), Source("bbbb", dirty=True))
