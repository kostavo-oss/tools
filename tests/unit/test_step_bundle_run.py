"""`bundle.run`: a run of a resource of a bundle step, planned as a `run`."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

import project
from fakes import FakeDatabricks, write_bundle
from lely.errors import LelyError
from lely.model import Change, Linked, Skip
from lely.planning import Session
from lely.step import Context, NullLog, destroys, lists
from lely.steps.bundle import Bundle
from lely.steps.bundle_run import BundleRun
from lely.steps.command import Command
from lely.testing import check_plan, context

APP = Linked(
    "app",
    "bundle",
    Bundle.Options(vars={"model_version": 14}),
    outputs={"resources.jobs.backfill.id": "771"},
    later=("resources.jobs.bar.id",),
)


def ctx(tmp_path: Path, **options: Any) -> Context[BundleRun.Options]:
    write_bundle(tmp_path, project.BUNDLE)
    given: dict[str, Any] = {"bundle": APP, "resource": "jobs.backfill", **options}
    return context(
        BundleRun.Options(**given),
        name="backfill",
        root=tmp_path,
        databricks=project.databricks(tmp_path),
    )


def test_plans_one_run(tmp_path: Path) -> None:
    plan = check_plan(BundleRun(), ctx(tmp_path, args=("--full",)))
    assert plan.changes == (
        Change("jobs.backfill", "run", "runs jobs.backfill", detail=("with --full",)),
    )
    assert not plan.empty  # it runs on every apply: never "nothing to do"


def test_a_resource_this_deploy_creates_can_be_run_too(tmp_path: Path) -> None:
    plan = BundleRun().plan(ctx(tmp_path, resource="jobs.bar"))
    assert plan.changes[0].summary == "runs jobs.bar"


def test_a_resource_the_bundle_doesnt_have_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(LelyError) as caught:
        BundleRun().plan(ctx(tmp_path, resource="jobs.backfil"))
    assert (
        "`jobs.backfil` isn't a resource of bundle step `app` for target `dev` "
        "(it has: jobs.backfill, jobs.bar)"
    ) in str(caught.value)


def test_the_step_it_names_must_be_a_bundle_step(tmp_path: Path) -> None:
    other = Linked("seed", "command", Command.Options(apply=("x",)))
    with pytest.raises(LelyError, match="must name a bundle step; step `seed` uses"):
        BundleRun().plan(ctx(tmp_path, bundle=other))


def test_apply_runs_the_resource_the_way_its_bundle_is_asked(tmp_path: Path) -> None:
    """R11. Same directory, same target, same `--var`s as the bundle step; the
    arguments after a `--`, so they are the job's and not the CLI's."""
    step = ctx(tmp_path, args=("--full", "2024"))
    fake = step.databricks
    assert isinstance(fake, FakeDatabricks)
    assert BundleRun().apply(step, BundleRun().plan(step)) == {}
    assert fake.calls == [
        [
            "bundle",
            "run",
            "jobs.backfill",
            "--target",
            "dev",
            "--var=model_version=14",
            "--",
            "--full",
            "2024",
        ]
    ]
    assert fake.runs == [{"key": "jobs.backfill", "args": ["--full", "2024"]}]


def test_a_failed_run_is_a_failed_step(tmp_path: Path) -> None:
    step = ctx(tmp_path)
    assert isinstance(step.databricks, FakeDatabricks)
    (step.databricks.world / "fail-run").write_text("task `load` failed")
    with pytest.raises(
        LelyError, match="(?s)`databricks bundle run jobs.backfill` failed.*load"
    ):
        BundleRun().apply(step, BundleRun().plan(step))


def test_nothing_to_destroy_and_nothing_to_list(tmp_path: Path) -> None:
    """R13: it deploys nothing. The plugin says so by not having the methods."""
    assert not destroys(BundleRun)
    assert not lists(BundleRun)
    assert BundleRun.__dict__.get("outputs") is None  # R14: it gives nothing


def test_the_core_skips_it_in_a_destroy_and_says_why(tmp_path: Path) -> None:
    from lely.config import load

    config = load(project.write(tmp_path))
    session = Session(
        config,
        "dev",
        project.WORKSPACE,
        {},
        project.databricks(tmp_path),
        NullLog(),
        lambda: cast(Any, None),
    )
    for step in config.steps[:2]:
        session.plan(session.prepare(step))
    backfill = session.prepare(config.steps[3])
    assert session.plan_destroy(backfill) == Skip("`bundle.run` has nothing to destroy")
    assert session.overview(backfill) == Skip("nothing to list")
