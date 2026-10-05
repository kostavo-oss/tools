"""The plan in a terminal: a snapshot of the shared scenario."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any, cast

from rich.console import Console
from syrupy.assertion import SnapshotAssertion

import project
from lely import planning
from lely.config import load
from lely.model import Plan
from lely.render.rich import render_plan
from lely.step import NullLog


def text(plan: Plan) -> str:
    console = Console(width=100, file=io.StringIO(), record=True, color_system=None)
    render_plan(plan, console)
    return console.export_text()


def planned(root: Path, stevin_fixture: str) -> Plan:
    project.write(root, project.lely_yml(stevin_fixture))
    return planning.plan(
        load(root / "lely.yml"),
        target=None,
        databricks=project.databricks(),
        env={},
        log=NullLog(),
        connect=lambda host: cast(Any, None),
    )


def test_a_first_deploy(tmp_path: Path, snapshot: SnapshotAssertion) -> None:
    assert text(planned(tmp_path, "stevin-create.json")) == snapshot


def test_a_destructive_change(tmp_path: Path, snapshot: SnapshotAssertion) -> None:
    assert text(planned(tmp_path, "stevin-destroy.json")) == snapshot
