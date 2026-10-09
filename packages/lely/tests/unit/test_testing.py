"""The contract kit: each rule is something that can fail.

A check that never fails checks nothing, so every one is run here against a
plugin that breaks its rule — and against the plugins lely ships, which pass
the ones that apply to them (002/R25).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

import project
from fakes import FakeDatabricks, write_bundle
from lely.model import (
    Change,
    Item,
    Linked,
    Output,
    Overview,
    Secret,
    StepPlan,
)
from lely.step import Context
from lely.steps.bundle import Bundle
from lely.steps.bundle_run import BundleRun
from lely.testing import (
    NoDatabricks,
    ReadOnly,
    check_apply,
    check_destroy,
    check_overview,
    check_plan,
    context,
)


@dataclass(frozen=True, slots=True)
class Options:
    pass


class Good:
    """A plugin that keeps a list of things in memory, by the rules."""

    Options = Options
    outputs = (Output("count"), Output("id", "exists"), Output("ran", "run"))
    made: list[str]

    def __init__(self) -> None:
        self.made = []

    def plan(self, ctx: Context[Options]) -> StepPlan:
        changes = () if self.made else (Change("thing", "create", "thing"),)
        outputs: dict[str, Any] = {"count": len(self.made)}
        if self.made:
            outputs["id"] = "1"
        return StepPlan(changes, outputs, later=() if self.made else ("id",))

    def apply(self, ctx: Context[Options], plan: StepPlan) -> dict[str, Any]:
        self.made.append("thing")
        return {"id": "1", "ran": True}

    def overview(self, ctx: Context[Options]) -> Overview:
        return Overview(tuple(Item("thing", m, m, True, "1") for m in self.made))

    def plan_destroy(self, ctx: Context[Options]) -> StepPlan:
        return StepPlan(tuple(Change(m, "delete", m) for m in self.made))

    def destroy(self, ctx: Context[Options], plan: StepPlan) -> None:
        self.made.clear()


CTX = context(Options())


def test_a_plugin_that_follows_the_rules_passes_all_of_it() -> None:
    assert check_plan(Good(), CTX).outputs == {"count": 0}
    assert check_apply(Good(), CTX) == {"id": "1", "ran": True}
    assert [c.key for c in check_destroy(Good(), CTX).changes] == ["thing"]
    assert check_overview(Good(), CTX) == Overview()


# -- each rule, broken -------------------------------------------------------------


class WritesWhilePlanning(Good):
    def plan(self, ctx: Context[Options]) -> StepPlan:
        ctx.databricks.run(["bundle", "deploy"], ctx.root)
        return super().plan(ctx)


def test_plan_changes_nothing(tmp_path: Path) -> None:
    ctx = context(Options(), databricks=FakeDatabricks(tmp_path / "world"))
    with pytest.raises(AssertionError, match="`databricks bundle deploy` isn't a read"):
        check_plan(WritesWhilePlanning(), ctx)


def test_a_read_is_let_through(tmp_path: Path) -> None:
    write_bundle(tmp_path, project.BUNDLE)
    fake = project.databricks(tmp_path)
    reading = ReadOnly(fake)
    done = reading.run(
        ["bundle", "summary", "--target", "dev", "--var=model_version=1"], tmp_path
    )
    assert done.returncode == 0
    with pytest.raises(AssertionError, match="isn't a read"):
        reading.run(["bundle", "destroy", "--auto-approve"], tmp_path)


def test_a_plugin_that_reaches_for_a_cli_it_wasnt_given_fails_loudly() -> None:
    with pytest.raises(AssertionError, match="give the context a `databricks=` fake"):
        NoDatabricks().run(["bundle", "validate"], Path.cwd())
    with pytest.raises(AssertionError, match="give the context `connect=`"):
        _ = CTX.workspace


class DoesntConverge(Good):
    def apply(self, ctx: Context[Options], plan: StepPlan) -> dict[str, Any]:
        return {"ran": True}


def test_apply_does_what_the_plan_said() -> None:
    with pytest.raises(
        AssertionError, match=r"after apply, the plan still shows: \['thing'\]"
    ):
        check_apply(DoesntConverge(), CTX)


class LeavesSomething(Good):
    def destroy(self, ctx: Context[Options], plan: StepPlan) -> None:
        pass


def test_destroy_undoes_it() -> None:
    with pytest.raises(AssertionError, match="doesn't show what the first plan showed"):
        check_destroy(LeavesSomething(), CTX)


class NothingToRemove(Good):
    def plan_destroy(self, ctx: Context[Options]) -> StepPlan:
        return StepPlan()


def test_a_destroy_plan_after_apply_shows_something() -> None:
    with pytest.raises(AssertionError, match="shows nothing to remove"):
        check_destroy(NothingToRemove(), CTX)


class HalfALine(Good):
    def overview(self, ctx: Context[Options]) -> Overview:
        return Overview((Item("thing", "key", "", True),))


class ListsByDeploying(Good):
    def overview(self, ctx: Context[Options]) -> Overview:
        ctx.databricks.run(["bundle", "deploy"], ctx.root)
        return Overview()


def test_an_overview_changes_nothing_and_every_line_is_whole(tmp_path: Path) -> None:
    with pytest.raises(AssertionError, match="an incomplete line"):
        check_overview(HalfALine(), CTX)
    ctx = context(Options(), databricks=FakeDatabricks(tmp_path / "world"))
    with pytest.raises(AssertionError, match="isn't a read"):
        check_overview(ListsByDeploying(), ctx)


class GivesMore(Good):
    def plan(self, ctx: Context[Options]) -> StepPlan:
        return StepPlan(outputs={"count": 0, "surprise": 1})


class GivesLess(Good):
    def plan(self, ctx: Context[Options]) -> StepPlan:
        return StepPlan()


class GivesTooEarly(Good):
    def plan(self, ctx: Context[Options]) -> StepPlan:
        return StepPlan(outputs={"count": 0, "ran": True})


class AppliesMore(Good):
    def apply(self, ctx: Context[Options], plan: StepPlan) -> dict[str, Any]:
        self.made.append("thing")
        return {"surprise": 1}


def test_outputs_are_as_declared() -> None:
    with pytest.raises(AssertionError, match="plan gave an output `surprise`"):
        check_plan(GivesMore(), CTX)
    with pytest.raises(AssertionError, match="`count` is declared as known at plan"):
        check_plan(GivesLess(), CTX)
    with pytest.raises(
        AssertionError, match="`ran` is declared as known after every run"
    ):
        check_plan(GivesTooEarly(), CTX)
    with pytest.raises(AssertionError, match="apply gave an output `surprise`"):
        check_apply(AppliesMore(), CTX)


class Leaks(Good):
    def plan(self, ctx: Context[Options]) -> StepPlan:
        payload: Any = {"token": Secret("t0k")}
        return StepPlan(outputs={"count": 0}, payload=payload)


class Repeats(Good):
    def plan(self, ctx: Context[Options]) -> StepPlan:
        change = Change("a", "create", "a")
        return StepPlan((change, change), {"count": 0})


def test_no_secret_reaches_a_file_and_keys_are_unique() -> None:
    with pytest.raises(Exception, match="holds a secret; a plan file never does"):
        check_plan(Leaks(), CTX)
    with pytest.raises(AssertionError, match="change keys repeat"):
        check_plan(Repeats(), CTX)


# -- the plugins lely ships pass what applies to them -------------------------------


def test_the_bundle_plugin_passes_the_whole_kit(tmp_path: Path) -> None:
    """004, done when."""
    write_bundle(tmp_path, project.BUNDLE)

    def ctx(folder: str) -> Context[Bundle.Options]:
        world = tmp_path / folder
        return context(
            Bundle.Options(vars={"model_version": "14"}),
            root=tmp_path,
            databricks=FakeDatabricks(world),
        )

    check_plan(Bundle(), ctx("one"))
    check_apply(Bundle(), ctx("two"))
    check_destroy(Bundle(), ctx("three"))
    assert isinstance(check_overview(Bundle(), ctx("four")), Overview)


def test_bundle_run_passes_the_parts_that_apply(tmp_path: Path) -> None:
    """010, done when. It doesn't converge — it is a run — and doesn't list."""
    write_bundle(tmp_path, project.BUNDLE)
    fake = project.databricks(tmp_path)
    app = Linked(
        "app",
        "bundle",
        Bundle.Options(vars={"model_version": "14"}),
        outputs={"resources.jobs.backfill.id": "771"},
    )
    run = context(
        BundleRun.Options(bundle=app, resource="jobs.backfill"),
        root=tmp_path,
        databricks=fake,
    )
    check_plan(BundleRun(), run)
    # a `run` may remain after apply: it happens every time
    assert check_apply(BundleRun(), run) == {}
    assert fake.runs == [{"key": "jobs.backfill", "args": []}]


class GivesATuple(Good):
    def plan(self, ctx: Context[Options]) -> StepPlan:
        names: Any = ("a", "b")
        return StepPlan(outputs={"count": names})


def test_the_kit_takes_a_plan_the_way_lely_does() -> None:
    """A tuple a plugin gives is a list once lely has taken it: the kit used to
    fail a plan the core accepts."""
    assert check_plan(GivesATuple(), CTX).outputs == {"count": ("a", "b")}
