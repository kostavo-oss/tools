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
        source=Source(
            "4b825dc642cb6eb9a060e54bf8d69288fbee4904", dirty=True, root="deploy"
        ),
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
        "format_version": 4,
        "tool_version": document["tool_version"],
        "kind": "apply",
        "target": "dev",
        "workspace": {
            "host": "https://dbc-example.cloud.databricks.com",
            "identity": "jane@example.com",
        },
        "source": {
            "tree": "4b825dc642cb6eb9a060e54bf8d69288fbee4904",
            "dirty": True,
            "root": "deploy",
        },
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
        "This plan file is format 1; this lely reads format 4. Run `lely plan` again."
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
        ["app"],  # `model` had nothing to do: it didn't run
        ["notify"],
        ["backfill"],
    )
    assert document["refused"] == []
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


# -- found in review ---------------------------------------------------------------


def test_a_step_that_isnt_ready_cant_hold_changes(tmp_path: Path) -> None:
    """A skipped step shows no changes, so a file that marks one skipped and
    leaves its changes in would hide what it then lets through."""
    document = planfile.plan_to_json(planned(tmp_path, "destroy"))
    app = document["steps"][1]
    assert app["plan"]["changes"]
    app["skipped"] = "nothing deployed"
    with pytest.raises(PlanFileError) as caught:
        planfile.plan_from_json(document)
    assert str(caught.value) == (
        "step `app` is skipped and holds changes; lely writes no such plan. "
        "Run `lely plan` again."
    )
    app["skipped"] = None
    app["waits_for"] = ["model.version"]
    with pytest.raises(PlanFileError, match="step `app` is waiting and holds changes"):
        planfile.plan_from_json(document)


def test_a_file_nested_too_deep_is_not_a_plan_file() -> None:
    with pytest.raises(PlanFileError, match="Not a plan file"):
        planfile.loads("[" * 100_000)


def test_a_refused_step_is_listed_as_refused_not_failed() -> None:
    result = Result(
        "apply",
        "dev",
        project.WORKSPACE,
        (
            StepResult("app", "bundle", "done"),
            StepResult("notify", "command", "refused", "plan again"),
            StepResult("backfill", "bundle.run", "not started"),
        ),
        "refused",
        "plan again",
    )
    document = planfile.result_to_json(result)
    assert (document["ran"], document["failed"], document["refused"]) == (
        ["app"],
        [],
        ["notify"],
    )


# -- found in the second review ------------------------------------------------------


def test_a_plan_names_its_target(tmp_path: Path) -> None:
    """The Databricks CLI would read an empty target as "the default one"; the
    command line refuses one, and so does a plan file."""
    document = planfile.plan_to_json(planned(tmp_path))
    for empty in ("", "  "):
        document["target"] = empty
        with pytest.raises(PlanFileError, match="`target` is empty"):
            planfile.plan_from_json(document)


def test_a_plan_file_is_read_strictly(tmp_path: Path) -> None:
    """A key lely doesn't write, or a flag that isn't one, is a file lely
    didn't write. `"dirty": "false"` used to read as true."""
    good = planfile.plan_to_json(planned(tmp_path))

    def refused(edit: Any, message: str) -> None:
        document = json.loads(json.dumps(good))
        edit(document)
        with pytest.raises(PlanFileError, match=message):
            planfile.plan_from_json(document)

    refused(lambda d: d.update(extra=1), "unknown keys extra")
    refused(lambda d: d["steps"][0].update(note="x"), "step `model`: unknown keys note")
    refused(lambda d: d["source"].update(dirty="false"), "`dirty` must be true or false")
    refused(lambda d: d["steps"][1].update(every_deploy=1), "`every_deploy` must be")
    refused(lambda d: d["steps"][1]["inputs"][0].update(known="yes"), "`known` must be")
    refused(
        lambda d: d["steps"][1]["plan"]["changes"][0].update(destructive="no"),
        "`destructive` must be",
    )
    refused(
        lambda d: d["steps"][1]["plan"]["changes"][0].update(extra=1),
        "unknown keys extra",
    )
    refused(lambda d: d["steps"].append(d["steps"][0]), "two steps share a name")


def test_a_number_too_long_to_read_is_not_a_plan_file() -> None:
    with pytest.raises(PlanFileError, match="Not a plan file"):
        planfile.loads('{"format_version": ' + "9" * 5000 + "}")


def test_what_isnt_json_is_refused_with_its_reason() -> None:
    import datetime

    for value, said in (
        ({1: "a"}, "a key that isn't text"),
        ({"when": datetime.date(2026, 10, 5)}, "holds a date, which isn't JSON"),
        ({"n": float("nan")}, "holds nan, which isn't JSON"),
        ({"s": {1, 2}}, "holds a set"),
    ):
        with pytest.raises(PlanFileError, match=said):
            planfile.step_plan_to_json(StepPlan(payload=cast(Any, value)))


def test_a_plan_is_made_plain_so_it_reads_back_equal() -> None:
    plan = StepPlan(
        changes=(Change("k", "run", "", detail=cast(Any, ["a"])),),
        outputs={"names": cast(Any, ("a", "b")), "token": Secret("t0k")},
        payload=cast(Any, {"rows": (1, 2)}),
    )
    plain = planfile.normalised(plan)
    assert plain.outputs["names"] == ["a", "b"]
    assert plain.payload == {"rows": [1, 2]}
    assert plain.changes == (Change("k", "run", "k", detail=("a",)),)
    back = planfile.step_plan_from_json(
        json.loads(json.dumps(planfile.step_plan_to_json(plain)))
    )
    assert back == plain


# -- found in the third review -------------------------------------------------------


def test_an_output_shaped_like_the_secret_marker_is_refused() -> None:
    """It would read back from a plan file as a secret — and a secret is never
    compared, so the value could move without the plan going stale."""
    for value in ({"$secret": True, "id": 14}, {"nested": {"$secret": True}}):
        with pytest.raises(PlanFileError, match="how a plan file marks a secret"):
            planfile.normalised(StepPlan(outputs={"made": cast(Any, value)}))
    # and only exactly the marker reads back as one
    back = planfile.step_plan_from_json({"outputs": {"a": {"$secret": True, "id": 1}}})
    assert back.outputs["a"] == {"$secret": True, "id": 1}
    assert isinstance(
        planfile.step_plan_from_json({"outputs": {"a": {"$secret": True}}}).outputs["a"],
        Secret,
    )


def test_a_number_python_wont_write_is_refused_when_it_is_planned() -> None:
    """An integer of thousands of digits: every later step — comparing it,
    showing it, writing it — would end in a `ValueError`."""
    with pytest.raises(PlanFileError, match="a number too long to write"):
        planfile.normalised(StepPlan(outputs={"n": 10**5000}))
    assert planfile.normalised(StepPlan(outputs={"n": 2**70})).outputs == {"n": 2**70}


def test_what_is_nested_too_deep_is_refused_not_a_traceback() -> None:
    deep: Any = []
    for _ in range(100_000):
        deep = [deep]
    with pytest.raises(PlanFileError, match="nested too deep"):
        planfile.normalised(StepPlan(payload=deep))


def test_a_change_is_one_thing_however_it_was_handed_over() -> None:
    """A plugin that passes `destructive=1`, or one line of detail as a string,
    used to get a plan lely wrote and then refused to read — or a detail of
    single letters."""
    change = Change(
        "k", "update", "k", destructive=cast(Any, 1), detail=cast(Any, "one line")
    )
    assert change == Change("k", "update", "k", destructive=True, detail=("one line",))
    plan = StepPlan((change, Change("j", "update", "j", destructive=cast(Any, None))))
    document = json.loads(json.dumps(planfile.step_plan_to_json(plan)))
    assert planfile.step_plan_from_json(document) == plan


def test_a_plan_that_names_a_tree_names_its_project(tmp_path: Path) -> None:
    document = planfile.plan_to_json(planned(tmp_path))
    del document["source"]["root"]
    with pytest.raises(PlanFileError, match="a `tree` needs a `root`"):
        planfile.plan_from_json(document)
    document["source"] = {"tree": None, "dirty": False, "root": None}  # outside git
    assert planfile.plan_from_json(document).source == Source()


# -- found in the fourth review ------------------------------------------------------


def test_what_a_file_says_of_a_steps_state_is_what_lely_reads(tmp_path: Path) -> None:
    """`state` is there for whoever reads the JSON — in a pull request's diff,
    say. A file that calls a step skipped, and lely then runs it, told its
    reader something else than it told lely."""
    document = planfile.plan_to_json(planned(tmp_path))
    app = document["steps"][1]
    assert app["state"] == "ready" and app["plan"]["changes"]
    app["state"] = "skipped"
    with pytest.raises(PlanFileError) as caught:
        planfile.plan_from_json(document)
    assert str(caught.value) == (
        "step `app`: `state` says 'skipped', and the rest of the step says it is "
        "ready; lely writes no such plan. Run `lely plan` again."
    )
    app["state"] = "waiting"
    with pytest.raises(PlanFileError, match="`state` says 'waiting'"):
        planfile.plan_from_json(document)
    del app["state"]  # a file from before lely wrote it says nothing false
    planfile.plan_from_json(document)


def test_where_a_plan_was_made_is_read_strictly_too(tmp_path: Path) -> None:
    good = planfile.plan_to_json(planned(tmp_path))

    def refused(edit: Any, message: str) -> None:
        document = json.loads(json.dumps(good))
        edit(document)
        with pytest.raises(PlanFileError, match=message):
            planfile.plan_from_json(document)

    refused(lambda d: d["source"].update(commit="abc"), "`source`: unknown keys commit")
    refused(lambda d: d["workspace"].update(o="1"), "`workspace`: unknown keys o")
    # left out, `dirty` would read as a clean checkout
    refused(lambda d: d["source"].pop("dirty"), "`dirty` must be true or false")


def test_a_kind_of_text_or_number_is_the_text_or_number_it_is() -> None:
    """A member of an enum, a `numpy.float64`: equal to the plain value, and
    not the same kind — so a plan read back from its file was refused for a
    value that hadn't changed."""
    import enum

    class Mode(enum.StrEnum):
        FAST = "fast"

    class Level(enum.IntEnum):
        HIGH = 3

    class Metric(float):
        pass

    class Name(str):
        __slots__ = ()

    plan = StepPlan(
        outputs=cast(
            Any,
            {
                "mode": Mode.FAST,
                "level": Level.HIGH,
                "score": Metric(0.5),
                "names": [Name("a"), {"deep": Mode.FAST}],
                "flag": True,
            },
        )
    )
    plain = planfile.normalised(plan)
    assert plain.outputs == {
        "mode": "fast",
        "level": 3,
        "score": 0.5,
        "names": ["a", {"deep": "fast"}],
        "flag": True,
    }
    names = cast(Any, plain.outputs["names"])
    kinds = [
        type(plain.outputs["mode"]),
        type(plain.outputs["level"]),
        type(plain.outputs["score"]),
        type(names[0]),
        type(names[1]["deep"]),
        type(plain.outputs["flag"]),
    ]
    assert kinds == [str, int, float, str, str, bool]
    back = planfile.step_plan_from_json(
        json.loads(json.dumps(planfile.step_plan_to_json(plain)))
    )
    assert back == plain


def test_what_a_run_removed_is_listed_in_the_result_as_the_terminal_lists_it() -> None:
    """It is no longer in the overview — nothing is deployed to list — and the
    JSON left it out where the terminal showed it."""
    overview = Overview((Item("job", "jobs.bar", "job bar", True, "1001"),))
    happened = {"jobs.bar": "changed", "jobs.gone": "deleted"}
    document = planfile.overview_to_json(overview, happened)
    assert document is not None
    assert [(item["key"], item["happened"]) for item in document["items"]] == [
        ("jobs.bar", "changed"),
        ("jobs.gone", "deleted"),
    ]
    assert document["items"][1] == {
        "kind": "",
        "key": "jobs.gone",
        "name": "",
        "deployed": False,
        "id": None,
        "url": None,
        "happened": "deleted",
    }
    listed = planfile.overview_to_json(overview)
    assert listed is not None and len(listed["items"]) == 1  # a status: no run to tell


# -- a plugin's own view (007/R2, 002/R8) -----------------------------------------------


def test_a_steps_view_is_kept_with_its_plan() -> None:
    """Made when the step is planned, so the page for a plan file needs no
    plugin, no project and no workspace — and is the same on any machine."""
    plan = StepPlan(
        changes=(Change("jobs.bar", "create", "jobs.bar"),),
        view="<table><tr><td>jobs.bar</td></tr></table>",
    )
    document = json.loads(json.dumps(planfile.step_plan_to_json(plan)))
    assert document["view"] == "<table><tr><td>jobs.bar</td></tr></table>"
    assert planfile.step_plan_from_json(document) == plan
    assert planfile.step_plan_from_json({"changes": []}).view is None
    with pytest.raises(PlanFileError, match="`view` must be a string"):
        planfile.step_plan_from_json({"view": ["<p>"]})
    with pytest.raises(Exception, match="A plan's `view` is HTML, as text"):
        StepPlan(view=cast(Any, 5))


# -- a run's record (007/R6) ------------------------------------------------------------


def a_result() -> Result:
    overview = Overview(
        (
            Item("job", "jobs.bar", "job bar", True, "1001", "https://x/1"),
            Item("job", "jobs.new", "new", False),
        ),
        ("as seen by jane",),
    )
    return Result(
        "apply",
        "dev",
        project.WORKSPACE,
        (
            StepResult("model", "lookup", "nothing", "nothing to do"),
            StepResult(
                "app",
                "bundle",
                "done",
                "",
                (Change("jobs.bar", "create", "jobs.bar", detail=("tasks",)),),
                overview,
                {"jobs.bar": "created", "jobs.gone": "deleted"},
            ),
            StepResult("notify", "command", "failed", "boom"),
            StepResult("warm", "command", "not started"),
        ),
        "failed",
        "step `notify` failed:\nboom",
    )


def test_a_runs_record_reads_back_as_the_run() -> None:
    """Written when the run was asked to, and read back only to be shown: a
    record, not state."""
    result = a_result()
    document = json.loads(json.dumps(planfile.result_to_json(result)))
    assert document["result_format"] == 1 and planfile.is_result(document)
    assert planfile.result_from_json(document) == result
    assert not planfile.is_result(
        planfile.plan_to_json(Plan("0", "apply", "d", project.WORKSPACE, Source(), ()))
    )


def test_a_run_that_never_started_has_a_record_too() -> None:
    """It may not have known its workspace, or its target."""
    stopped: dict[str, Any] = {
        "result_format": 1,
        "kind": "destroy",
        "target": None,
        "workspace": None,
        "outcome": "refused",
        "message": "Not approved. Nothing was run.",
        "ran": [],
        "failed": [],
        "refused": [],
        "not_started": [],
        "rolled_back": [],
        "steps": [],
    }
    result = planfile.result_from_json(stopped)
    assert (result.kind, result.target, result.outcome) == ("destroy", "?", "refused")
    assert str(result.workspace) == "? as ?" and result.steps == ()


def test_a_record_is_read_as_strictly_as_a_plan() -> None:
    good = planfile.result_to_json(a_result())

    def refused(edit: Any, message: str) -> None:
        document = json.loads(json.dumps(good))
        edit(document)
        with pytest.raises(PlanFileError, match=message):
            planfile.result_from_json(document)

    refused(lambda d: d.update(result_format=2), "format 2; this lely reads format 1")
    refused(lambda d: d.update(extra=1), "the result file: unknown keys extra")
    refused(lambda d: d.update(kind="plan"), "`kind` must be apply or destroy")
    refused(lambda d: d.update(outcome="fine"), "`outcome` must be done, failed or")
    refused(lambda d: d["steps"][1].update(outcome="ok"), "step `app`: `outcome` must")
    refused(lambda d: d["steps"][1].update(note="x"), "step `app`: unknown keys note")
    refused(
        lambda d: d["steps"][1]["overview"]["items"][0].update(deployed="yes"),
        "`deployed` must be true or false",
    )
    refused(
        lambda d: d["steps"][1]["changes"][0].update(action="explode"), "action must be"
    )


# -- found in the sixth review ---------------------------------------------------------


def test_a_record_tells_one_story(tmp_path: Path) -> None:
    """How a run ended is said in three places: its `outcome`, each step's
    own, and the lists of names. A file where they disagree was edited — and
    showed a run that failed as "Applied", in green."""
    good = planfile.result_to_json(a_result())

    def refused(edit: Any, message: str) -> None:
        document = json.loads(json.dumps(good))
        edit(document)
        with pytest.raises(PlanFileError, match=message):
            planfile.result_from_json(document)

    refused(lambda d: d.update(outcome="done"), "`outcome` says done, and its")
    refused(
        lambda d: d.update(outcome="done", message=""),
        "`outcome` says done, and its steps say otherwise",
    )
    refused(lambda d: d.update(outcome="refused"), "`outcome` says refused")
    refused(lambda d: d.update(ran=[]), "`ran` doesn't name the steps")
    refused(lambda d: d.update(failed=[]), "`failed` doesn't name the steps")
    refused(lambda d: d.update(not_started="warm"), "`not_started` doesn't name")
    refused(lambda d: d.update(rolled_back=["app"]), "`rolled_back` is never anything")
    refused(lambda d: d["steps"].append(d["steps"][0]), "two steps share a name")

    def all_done(document: Any) -> None:  # the steps changed, and not the rest
        for step in document["steps"]:
            step["outcome"] = "done"

    refused(all_done, "`outcome` says failed, and its steps say otherwise")

    def unfinished(document: Any) -> None:
        document.update(outcome="done", message="", failed=[], ran=["app", "notify"])
        document["steps"][2]["outcome"] = "done"

    refused(unfinished, "`outcome` says done, and its steps say otherwise")

    # found when the fixes were reviewed: each of these still read, and showed green
    def no_steps_left(document: Any) -> None:
        document.update(outcome="done", steps=[], ran=[], failed=[], not_started=[])

    refused(no_steps_left, "`outcome` says done, and its `message` says what went wrong")

    def lists_left_out(document: Any) -> None:
        for key in ("ran", "failed", "refused", "not_started"):
            del document[key]

    refused(lists_left_out, "`ran` doesn't name the steps")
    refused(lambda d: d.pop("rolled_back"), "`rolled_back` is never anything")

    def two_stopped_it(document: Any) -> None:
        document["steps"][3]["outcome"] = "refused"
        document.update(outcome="refused", refused=["warm"], not_started=[])

    refused(two_stopped_it, "more than one step failed or was refused")


def test_a_view_has_its_size_in_a_file_too() -> None:
    """The limit was held where a plugin hands a view over, and not where one
    is read: a hand-written plan file brought twenty megabytes of it."""
    with pytest.raises(PlanFileError, match="its view is 1000001 characters"):
        planfile.step_plan_from_json({"view": "x" * 1_000_001})
    assert planfile.step_plan_from_json({"view": "x" * 1_000_000}).view is not None


def test_a_plan_nested_too_deep_to_write_is_said() -> None:
    deep: Any = "x"
    for _ in range(100_000):
        deep = [deep]
    plan = Plan(
        "0",
        "apply",
        "dev",
        project.WORKSPACE,
        Source(),
        (PlannedStep("app", "bundle", "h", StepPlan(payload=deep)),),
    )
    with pytest.raises(PlanFileError, match="nested too deep to write down"):
        planfile.dumps(plan)
