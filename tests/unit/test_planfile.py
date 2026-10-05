"""The plan file: written and read back whole, and never with a secret."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any, cast

import pytest

import project
from lely import planfile, planning
from lely.config import load
from lely.model import (
    Change,
    Input,
    Item,
    Overview,
    Plan,
    PlanKind,
    PlannedStep,
    Result,
    Secret,
    Source,
    Status,
    StepPlan,
    StepResult,
    StepStatus,
)
from lely.planfile import PlanFileError
from lely.step import NullLog


def planned(root: Path, kind: PlanKind = "apply") -> Plan:
    project.write(root)
    return planning.plan(
        load(root / "lely.yml"),
        target="dev",
        workspace=project.WORKSPACE,
        source=Source(tree="4b825dc642cb6eb9a060e54bf8d69288fbee4904", dirty=True),
        env={},
        databricks=project.databricks(root),
        log=NullLog(),
        connect=lambda: cast(Any, None),
        kind=kind,
    )


def test_a_plan_survives_the_round_trip(tmp_path: Path) -> None:
    built = planned(tmp_path)
    assert planfile.loads(planfile.dumps(built)) == built


def test_a_destroy_plan_survives_it_too(tmp_path: Path) -> None:
    built = planned(tmp_path, "destroy")
    back = planfile.loads(planfile.dumps(built))
    assert back == built
    assert back.kind == "destroy"


def test_the_file_says_what_it_is_and_holds_what_was_shown(tmp_path: Path) -> None:
    """005/R2."""
    document = planfile.plan_to_json(planned(tmp_path))
    assert {k: v for k, v in document.items() if k != "steps"} == {
        "format_version": 2,
        "tool_version": document["tool_version"],
        "kind": "apply",
        "target": "dev",
        "workspace": {
            "host": "https://dbc-example.cloud.databricks.com",
            "identity": "jane@example.com",
        },
        "source": {"tree": "4b825dc642cb6eb9a060e54bf8d69288fbee4904", "dirty": True},
    }
    model, app, notify, _, warm = document["steps"]
    assert (app["name"], app["uses"], app["state"]) == ("app", "bundle", "ready")
    assert app["inputs"] == [
        {"label": "model_version", "from": "model.version", "known": True, "value": 14}
    ]
    assert app["plan"]["changes"][0] == {
        "key": "jobs.bar",
        "action": "create",
        "summary": "jobs.bar",
        "destructive": False,
        "detail": [],
    }
    assert app["plan"]["payload"]["plan_version"] == 2  # the plugin's own data
    assert model["plan"]["outputs"] == {"version": 14}
    assert (notify["state"], notify["waits_for"]) == (
        "waiting",
        ["app.resources.jobs.bar.id"],
    )
    assert (warm["state"], warm["skipped"]) == ("skipped", "not for target `dev`")


def test_a_secret_output_is_never_written() -> None:
    step = StepPlan(outputs={"token": Secret("t0k"), "user": "jane"})
    written = json.dumps(planfile.step_plan_to_json(step))
    assert "t0k" not in written
    back = planfile.step_plan_from_json(json.loads(written))
    token = back.outputs["token"]
    assert isinstance(token, Secret)
    with pytest.raises(Exception, match="never keeps one"):
        token.reveal()


def test_a_secret_a_step_takes_is_never_written(tmp_path: Path) -> None:
    built = planned(tmp_path)
    step = PlannedStep(
        "login", "x", "hash", inputs=(Input("token", "auth.token", Secret("t0k")),)
    )
    written = planfile.dumps(dataclasses.replace(built, steps=(step,)))
    assert "t0k" not in written
    assert json.loads(written)["steps"][0]["inputs"][0]["value"] == {"$secret": True}


def test_a_payload_with_a_secret_is_refused() -> None:
    with pytest.raises(PlanFileError, match="its payload holds a secret"):
        planfile.step_plan_to_json(StepPlan(payload=cast(Any, {"auth": [Secret("x")]})))


def test_another_format_is_refused_and_says_to_plan_again() -> None:
    """005/R3: the message names both versions."""
    with pytest.raises(PlanFileError) as caught:
        planfile.loads(json.dumps({"format_version": 1}))
    assert str(caught.value) == (
        "This plan file is format 1; this lely reads format 2. Run `lely plan` again."
    )
    with pytest.raises(PlanFileError, match="Not a plan file"):
        planfile.loads("not json")


def test_a_plan_file_says_whether_it_applies_or_destroys(tmp_path: Path) -> None:
    document = planfile.plan_to_json(planned(tmp_path))
    document["kind"] = "obliterate"
    with pytest.raises(PlanFileError, match="`kind` must be apply or destroy"):
        planfile.plan_from_json(document)


@pytest.mark.parametrize(
    ("document", "message"),
    [
        ({"changes": [{"key": "a", "action": "zap"}]}, "action must be one of"),
        (
            {"changes": [{"key": "a", "action": "run"}, {"key": "a", "action": "run"}]},
            "share a key",
        ),
        ({"chnages": []}, "unknown keys chnages"),
        ({"deferred": "x"}, "unknown keys deferred"),
        ({"waiting": 3}, "`waiting` must be a string or null"),
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


# -- what a run leaves behind ------------------------------------------------------


def test_a_result_has_its_three_lists() -> None:
    """005/R21."""
    result = Result(
        "apply",
        "dev",
        project.WORKSPACE,
        (
            StepResult("model", "x", "nothing", "nothing to do"),
            StepResult(
                "app",
                "bundle",
                "done",
                changes=(Change("jobs.bar", "create", "jobs.bar"),),
                overview=Overview(
                    (Item("job", "jobs.bar", "job bar", True, "1001", "https://x/1"),),
                    ("as seen by jane",),
                ),
                happened={"jobs.bar": "created"},
            ),
            StepResult("notify", "command", "failed", "boom"),
            StepResult("backfill", "bundle.run", "not started"),
            StepResult("warm", "command", "skipped", "not for target `dev`"),
        ),
        "failed",
        "boom",
    )
    document = planfile.result_to_json(result)
    assert (document["ran"], document["failed"], document["not_started"]) == (
        ["model", "app"],
        ["notify"],
        ["backfill"],
    )
    assert document["rolled_back"] == []
    assert (document["outcome"], document["message"]) == ("failed", "boom")
    app = document["steps"][1]
    assert app["overview"]["items"] == [
        {
            "kind": "job",
            "key": "jobs.bar",
            "name": "job bar",
            "deployed": True,
            "id": "1001",
            "url": "https://x/1",
            "happened": "created",
        }
    ]
    assert json.dumps(document)


def test_a_status_as_json() -> None:
    status = Status(
        "dev",
        project.WORKSPACE,
        (
            StepStatus("app", "bundle", Overview((Item("job", "jobs.b", "b", False),))),
            StepStatus("seed", "command", note="runs a command; nothing to list"),
        ),
    )
    document = planfile.status_to_json(status)
    assert document["steps"][0]["overview"]["items"][0] == {
        "kind": "job",
        "key": "jobs.b",
        "name": "b",
        "deployed": False,
        "id": None,
        "url": None,
    }
    assert document["steps"][1] == {
        "name": "seed",
        "uses": "command",
        "note": "runs a command; nothing to list",
        "overview": None,
    }
