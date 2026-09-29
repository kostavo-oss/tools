"""The plan in a terminal: a snapshot of the shared scenario."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any, cast

from rich.console import Console
from syrupy.assertion import SnapshotAssertion

import project
from sluis import planning
from sluis.config import load
from sluis.model import Plan
from sluis.render.rich import render_plan
from sluis.step import NullLog


def text(plan: Plan) -> str:
    console = Console(width=100, file=io.StringIO(), record=True, color_system=None)
    render_plan(plan, console)
    return console.export_text()


def planned(root: Path, deltaplan_fixture: str) -> Plan:
    project.write(root, project.sluis_yml(deltaplan_fixture))
    return planning.plan(
        load(root / "sluis.yml"),
        target=None,
        databricks=project.databricks(),
        env={},
        log=NullLog(),
        connect=lambda host: cast(Any, None),
    )


def test_a_first_deploy(tmp_path: Path, snapshot: SnapshotAssertion) -> None:
    assert text(planned(tmp_path, "deltaplan-create.json")) == snapshot


def test_a_destructive_change(tmp_path: Path, snapshot: SnapshotAssertion) -> None:
    assert text(planned(tmp_path, "deltaplan-destroy.json")) == snapshot
