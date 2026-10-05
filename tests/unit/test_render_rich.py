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
    built = planned(config, fake, tree="4b825dc642cb6eb9", dirty=True)
    assert text(plan_view(built)) == snapshot


def test_a_destroy_plan_runs_from_the_bottom_up(
    tmp_path: Path, snapshot: SnapshotAssertion
) -> None:
    config = load(project.write(tmp_path))
    built = planned(config, project.databricks(tmp_path), "destroy", tree="4b825dc6")
    assert text(plan_view(built)) == snapshot


def test_nothing_to_destroy(tmp_path: Path, snapshot: SnapshotAssertion) -> None:
    config = load(project.write(tmp_path))
    fake = FakeDatabricks(project.world(tmp_path, deployed=False))
    assert text(plan_view(planned(config, fake, "destroy", tree="4b82"))) == snapshot


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
        "  - name: seed\n    uses: command\n"
        "    with: {apply: [./ops/warm.sh], outputs: [count]}\n"
        "  - name: tell\n    uses: command\n"
        "    with: {apply: [./ops/notify.sh, '${steps.seed.count}']}\n"
    )
    config = load(project.write(tmp_path, text_))
    shown = " ".join(
        text(plan_view(planned(config, project.databricks(tmp_path)))).split()
    )
    assert "⏸ waiting for seed.count — on every deploy" in shown
    assert "Applied from a file, this stops before `tell`" in shown
    assert "a file can never take it further: `lely apply -t <target>` does." in shown
