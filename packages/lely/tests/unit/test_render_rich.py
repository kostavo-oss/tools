"""lely in a terminal: snapshots of the shared scenario."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any, cast

from rich.console import Console, RenderableType
from syrupy.assertion import SnapshotAssertion

import project
from fakes import FakeDatabricks, deploy
from lely import planning, running
from lely.config import Config, load
from lely.model import Plan, PlanKind, Source
from lely.render.rich import plan_view, result_view, status_view, wiring_view
from lely.step import NullLog

#: What the scenario's pipeline was deployed with before: another storage.
MOVED = {
    **project.DEPLOYED,
    "pipelines.foo": {
        "id": "42",
        "config": {"name": "pipeline foo", "storage": "dbfs:/old-storage"},
    },
}


def text(view: RenderableType) -> str:
    console = Console(width=100, file=io.StringIO(), record=True, color_system=None)
    console.print(view, highlight=False)
    return console.export_text()


def edges(fake: FakeDatabricks) -> dict[str, Any]:
    return {
        "workspace": project.WORKSPACE,
        "env": {},
        "databricks": fake,
        "log": NullLog(),
        "connect": lambda: cast(Any, None),
    }


def planned(
    config: Config, fake: FakeDatabricks, kind: PlanKind = "apply", **source: Any
) -> Plan:
    return planning.plan(
        config, target="dev", source=Source(**source), kind=kind, **edges(fake)
    )


def test_a_first_deploy(tmp_path: Path, snapshot: SnapshotAssertion) -> None:
    config = load(project.write(tmp_path))
    assert text(plan_view(planned(config, project.databricks(tmp_path)))) == snapshot


def test_a_destructive_change(tmp_path: Path, snapshot: SnapshotAssertion) -> None:
    config = load(project.write(tmp_path))
    fake = FakeDatabricks(project.world(tmp_path, deployed=False))
    deploy(fake.world, MOVED)
    built = planned(config, fake, tree="4b825dc642cb6eb9", dirty=True, root=".")
    assert text(plan_view(built)) == snapshot


def test_a_destroy_plan_runs_from_the_bottom_up(
    tmp_path: Path, snapshot: SnapshotAssertion
) -> None:
    config = load(project.write(tmp_path))
    fake = project.databricks(tmp_path)
    built = planned(config, fake, "destroy", tree="4b825dc6", root=".")
    assert text(plan_view(built)) == snapshot


def test_nothing_to_destroy(tmp_path: Path, snapshot: SnapshotAssertion) -> None:
    config = load(project.write(tmp_path))
    fake = FakeDatabricks(project.world(tmp_path, deployed=False))
    built = planned(config, fake, "destroy", tree="4b82", root=".")
    assert text(plan_view(built)) == snapshot


def test_the_wiring(tmp_path: Path, snapshot: SnapshotAssertion) -> None:
    """003/R8."""
    config = load(project.write(tmp_path))
    assert text(wiring_view(planning.check(config))) == snapshot


def test_an_apply_and_what_exists_after_it(
    tmp_path: Path, snapshot: SnapshotAssertion
) -> None:
    """005/R10, 004/R7a: what each step did, and each line of the overview says
    what happened to it."""
    config = load(project.write(tmp_path))
    fake = project.databricks(tmp_path)
    approved = planned(config, fake)
    result = running.apply(config, approved, at_waiting=lambda step: True, **edges(fake))
    assert text(result_view(result)) == snapshot


def test_a_run_that_failed(tmp_path: Path, snapshot: SnapshotAssertion) -> None:
    """005/R21, R24: three lists, and "nothing was rolled back" in those words."""
    config = load(project.write(tmp_path))
    (tmp_path / "ops" / "notify.sh").write_text(
        "#!/bin/sh\necho 'no route' >&2; exit 7\n"
    )
    fake = project.databricks(tmp_path)
    approved = planned(config, fake)
    result = running.apply(config, approved, at_waiting=lambda step: True, **edges(fake))
    assert text(result_view(result)) == snapshot


def test_status(tmp_path: Path, snapshot: SnapshotAssertion) -> None:
    config = load(project.write(tmp_path))
    found = running.status(config, target="dev", **edges(project.databricks(tmp_path)))
    assert text(status_view(found)) == snapshot


def test_a_step_that_waits_on_every_deploy_says_a_file_never_gets_past_it(
    tmp_path: Path,
) -> None:
    """005/R27: `plan` says so before anyone is surprised."""
    text_ = (
        "steps:\n"
        "  - name: seed\n    uses: ./ops/steps.py:Seed\n"
        "  - name: tell\n    uses: ./ops/steps.py:Notify\n"
        "    with: {job: '${steps.seed.count}'}\n"
    )
    config = load(project.write(tmp_path, text_))
    shown = " ".join(
        text(plan_view(planned(config, project.databricks(tmp_path)))).split()
    )
    assert "⏸ waiting for seed.count — on every deploy" in shown
    assert "Applied from a file, this stops before `tell`" in shown
    assert "a file can never take it further: `lely apply -t <target>` does." in shown


def test_what_a_plan_says_is_shown_never_obeyed(tmp_path: Path) -> None:
    """An escape sequence in a change's summary — from a plan file, or a plan
    command — would move the cursor up and erase the line above it."""
    from lely.model import Change, PlannedStep, StepPlan
    from lely.render.rich import clean, step_view

    hostile = "\x1b[1A\x1b[2Kpipelines.foo"
    step = PlannedStep(
        "app\x07",
        "bundle",
        "h",
        StepPlan(
            (Change("k", "create", hostile, detail=("\x1b[31mred",)),),
            notes=("a note\rover it",),
        ),
    )
    shown = text(step_view(step))
    assert "\x1b" not in shown and "\x07" not in shown and "\r" not in shown
    assert "+ �[1A�[2Kpipelines.foo" in shown
    assert clean("two\nlines\tand a tab") == "two\nlines\tand a tab"
    # what shows nothing and reorders what is read: a name that reads as another
    assert clean("jobs.\u202eelbat\u202c") == "jobs.�elbat�"
    assert clean("a\u200bb\u2066c") == "a�b�c"
    assert clean("ZWJ 👩\u200d💻 stays") == "ZWJ 👩\u200d💻 stays"
    config = load(project.write(tmp_path))
    built = planned(config, project.databricks(tmp_path))
    plan = type(built)(
        built.tool_version,
        built.kind,
        "dev\x1b[2J",
        built.workspace,
        built.source,
        (step,),
    )
    assert "\x1b" not in text(plan_view(plan))


def test_a_plan_says_which_project_of_the_repository_it_is_for(tmp_path: Path) -> None:
    config = load(project.write(tmp_path))
    fake = project.databricks(tmp_path)
    in_a_folder = planned(config, fake, tree="4b825dc6", root="team-a")
    assert "lely plan · project team-a · target dev · " in text(plan_view(in_a_folder))
    at_the_top = planned(config, fake, tree="4b825dc6", root=".")
    assert "lely plan · target dev · " in text(plan_view(at_the_top))


def test_a_plan_that_is_never_saved_says_nothing_about_files(tmp_path: Path) -> None:
    """`lely apply -t dev` plans, shows and runs. What a plan *file* would be
    held to, and where a file would stop, is not its business — and when git
    couldn't be asked, "not in a git repository" would even be false."""
    config = load(project.write(tmp_path))
    built = planned(config, project.databricks(tmp_path))
    saved = text(plan_view(built))
    assert "Applied from a file, this stops before `notify`" in saved
    assert "Not in a git repository" in saved
    unsaved = text(plan_view(built, saved=False))
    assert "from a file" not in unsaved and "git" not in unsaved
    assert "⏸ waiting for app.resources.jobs.bar.id" in unsaved
