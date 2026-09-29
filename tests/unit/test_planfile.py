"""The plan file: written and read back whole, and never with a secret."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest

import project
from sluis import planfile, planning
from sluis.config import load
from sluis.model import Change, Secret, StepPlan
from sluis.planfile import PlanFileError
from sluis.step import NullLog


def test_a_plan_survives_the_round_trip(tmp_path: Path) -> None:
    project.write(tmp_path)
    built = planning.plan(
        load(tmp_path / "sluis.yml"),
        target=None,
        databricks=project.databricks(),
        env={},
        log=NullLog(),
        connect=lambda host: cast(Any, None),
    )
    assert planfile.loads(planfile.dumps(built)) == built


def test_a_secret_output_is_never_written() -> None:
    step = StepPlan(outputs={"token": Secret("t0k"), "user": "jane"})
    written = json.dumps(planfile.step_plan_to_json(step))
    assert "t0k" not in written
    back = planfile.step_plan_from_json(json.loads(written))
    token = back.outputs["token"]
    assert isinstance(token, Secret)
    with pytest.raises(Exception, match="never keeps one"):
        token.reveal()


def test_a_payload_with_a_secret_is_refused() -> None:
    with pytest.raises(PlanFileError, match="its payload holds a secret"):
        planfile.step_plan_to_json(StepPlan(payload=cast(Any, {"auth": [Secret("x")]})))


def test_another_format_is_refused() -> None:
    with pytest.raises(PlanFileError, match="format 9; this sluis reads format 1"):
        planfile.loads(json.dumps({"format_version": 9}))


@pytest.mark.parametrize(
    ("document", "message"),
    [
        ({"changes": [{"key": "a", "action": "zap"}]}, "action must be one of"),
        (
            {"changes": [{"key": "a", "action": "run"}, {"key": "a", "action": "run"}]},
            "share a key",
        ),
        ({"chnages": []}, "unknown keys chnages"),
        ({"deferred": 3}, "`deferred` must be a string or null"),
        ([], "must be a JSON object"),
    ],
)
def test_a_steps_plan_is_read_strictly(document: Any, message: str) -> None:
    with pytest.raises(PlanFileError, match=message):
        planfile.step_plan_from_json(document)


def test_delete_and_replace_are_destructive_whatever_was_written() -> None:
    change = planfile.step_plan_from_json(
        {"changes": [{"key": "t", "action": "delete", "destructive": False}]}
    ).changes[0]
    assert change == Change("t", "delete", "t", destructive=True)
