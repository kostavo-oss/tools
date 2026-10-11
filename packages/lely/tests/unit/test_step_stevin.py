"""The `stevin` plugin, against plan files stevin itself wrote and a fake of
its command line.

`tests/fixtures/stevin-*.json` were recorded by running stevin's CLI against
its own in-memory warehouse (its `tests/screens.py` scenes), so these tests
hold lely to the plan file stevin really writes. `tests/fake_stevin.py` plans
from one of them and applies it; what it assumes of stevin is numbered S1 to S7
there. Each test names the rule of `RULES.md` it holds.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

import pytest
from rich.console import Console

import project
from fakes import FakeStevin, Heard, fixture
from lely.errors import LelyError, Refused
from lely.model import Change, Overview, Plan, PlannedStep, StepPlan
from lely.planfile import normalised
from lely.render import html, markdown, rich
from lely.step import Context, applies, destroys, lists
from lely.steps.stevin import Stevin, changes
from lely.testing import check_overview, check_plan, context


def world(tmp_path: Path, recording: str = "stevin-create.json") -> FakeStevin:
    return FakeStevin.planning(tmp_path / "stevin-world", recording)


def ctx(fake: FakeStevin, tmp_path: Path, **kwargs: Any) -> Context[Stevin.Options]:
    options = Stevin.Options(executable=fake.executable, **kwargs.pop("options", {}))
    return context(options, root=tmp_path, env={}, name="tables", **kwargs)


def planned(fake: FakeStevin, tmp_path: Path) -> StepPlan:
    """A plan as lely keeps it, and as it reads back from a plan file."""
    plan = normalised(Stevin().plan(ctx(fake, tmp_path)))
    fake.clear_calls()
    return plan


def approving(fake: FakeStevin, tmp_path: Path, approved: StepPlan) -> Context[Any]:
    return ctx(fake, tmp_path, approved=approved)


# -- the plan ----------------------------------------------------------------------


def test_a_first_plan_creates_each_table() -> None:
    """STV-2: one change per table, one line per step, each with its risk."""
    result = changes(fixture("stevin-create.json"))
    assert [(c.key, c.action, c.destructive) for c in result] == [
        ("dev.sales.customers", "create", False),
        ("dev.sales.orders", "create", False),
        ("dev.sales.big_orders", "create", False),
    ]
    assert result[0].detail == (
        "CREATE SCHEMA sales  [meta]",
        "CREATE TABLE customers  [meta]",
    )
    dropped = fixture("stevin-destroy.json")
    dropped["tables"][1]["changes"] = [{"kind": "drop_table"}]
    assert [(c.action, c.destructive) for c in changes(dropped)] == [("delete", True)]


def test_a_dropped_column_is_a_destructive_update() -> None:
    """STV-3."""
    assert changes(fixture("stevin-destroy.json")) == (
        Change(
            "dev.sales.orders",
            "update",
            "dev.sales.orders",
            destructive=True,
            detail=("DROP COLUMN address  [destructive]",),
        ),
    )


def test_a_rewrite_is_visible_as_a_rewrite() -> None:
    """STV-2: in the table's own line, and on each step that rewrites. A
    rewrite is not destructive: stevin says so when it loses a column."""
    [orders] = changes(fixture("stevin-rewrite.json"))
    assert (orders.summary, orders.action) == ("dev.sales.orders  rewrite", "update")
    assert not orders.destructive
    assert orders.detail[:2] == (
        "STAGE rewritten data  [rewrite]",
        "REPLACE TABLE  [rewrite]",
    )
    assert "SET NOT NULL order_id  [meta]" in orders.detail
    assert "⚠ fails unless every existing row already has a value" in orders.detail


def test_a_risk_class_lely_doesnt_know_is_destructive(tmp_path: Path) -> None:
    """STV-3: as the bundle plugin reads an action it doesn't know."""
    fake = world(tmp_path)
    fake.told("risk", "irreversible")
    plan = check_plan(Stevin(), ctx(fake, tmp_path))
    assert all(change.destructive for change in plan.changes)
    assert plan.changes[0].detail[:2] == (
        "CREATE SCHEMA sales  [irreversible]",
        "⚠ stevin gives this step the risk class `irreversible`, which lely doesn't "
        "know: it is treated as destructive",
    )
    document = fixture("stevin-create.json")
    del document["steps"][0]["risk"]
    assert changes(document)[0].destructive


def test_a_step_stevin_cant_run_says_so() -> None:
    document = fixture("stevin-destroy.json")
    document["steps"][0]["sql"] = None
    assert changes(document)[0].detail[1] == (
        "⚠ stevin has no statement for this step, and applies no plan that holds one"
    )


def test_a_step_for_a_table_the_file_doesnt_list_is_still_shown() -> None:
    document = fixture("stevin-destroy.json")
    document["tables"] = []
    assert [(c.key, c.destructive) for c in changes(document)] == [
        ("dev.sales.orders", True)
    ]


def test_nothing_to_do_is_no_changes() -> None:
    assert changes(fixture("stevin-empty.json")) == ()


def test_another_plan_format_is_refused() -> None:
    document = fixture("stevin-empty.json")
    document["format_version"] = 2
    with pytest.raises(LelyError, match="plan format 2; lely reads format 1"):
        changes(document)


def test_plans_through_stevins_cli(tmp_path: Path) -> None:
    """STV-1: the command, and stevin's plan file as the payload."""
    fake = world(tmp_path, "stevin-destroy.json")
    step = ctx(fake, tmp_path, target="prod", options={"select": ("sales.*",)})
    plan = check_plan(Stevin(), step)
    assert [c.key for c in plan.changes] == ["dev.sales.orders"]
    recorded = fixture("stevin-destroy.json")
    assert isinstance(plan.payload, dict)
    assert plan.payload["steps"] == recorded["steps"]
    assert plan.payload["tables"] == recorded["tables"]
    [args] = fake.calls
    assert args[:5] == ["plan", "--target", "prod", "--config", "stevin.yml"]
    assert args[-4:] == ["--format", "json", "--select", "sales.*"]


def test_its_own_target_wins(tmp_path: Path) -> None:
    """STV-1."""
    fake = world(tmp_path, "stevin-empty.json")
    Stevin().plan(ctx(fake, tmp_path, target="prod", options={"target": "staging"}))
    assert fake.calls[0][2] == "staging"


def test_a_failing_stevin_is_shown_in_its_own_words(tmp_path: Path) -> None:
    fake = world(tmp_path, "stevin-empty.json")
    fake.told("fail-plan", "Error: sales.orders: can't reach the warehouse")
    with pytest.raises(
        LelyError, match="(?s)`stevin plan` failed.*can't reach the warehouse"
    ):
        Stevin().plan(ctx(fake, tmp_path))


def test_a_missing_stevin_says_how_to_get_it(tmp_path: Path) -> None:
    """STV-1."""
    step = context(Stevin.Options(executable=("no-such-stevin",)), root=tmp_path)
    with pytest.raises(LelyError, match="uv tool install stevin"):
        Stevin().plan(step)


def test_the_fake_fails_loudly_on_what_it_doesnt_know(tmp_path: Path) -> None:
    """The stand-in answers what stevin was read to answer, and nothing else."""
    fake = world(tmp_path)
    for extra in (("drift",), ("plan", "--yes")):
        options = Stevin.Options(executable=(*fake.executable, *extra))
        step = context(options, root=tmp_path, env={})
        with pytest.raises(LelyError, match=r"(?s)exit 2\).*fake stevin: "):
            Stevin().plan(step)


# -- apply -------------------------------------------------------------------------


def test_apply_hands_stevin_the_plan_that_was_approved(tmp_path: Path) -> None:
    """STV-4: the file in the approved plan, not the plan made right before
    the apply, and no plan of stevin's own in between."""
    fake = world(tmp_path)
    approved = planned(fake, tmp_path)
    assert isinstance(approved.payload, dict)
    fresh = dataclasses.replace(
        approved, payload={**approved.payload, "tool_version": "made-again"}
    )
    assert Stevin().apply(approving(fake, tmp_path, approved), fresh) == {}
    assert fake.verbs == ["apply"]
    assert fake.handed == approved.payload
    assert fake.handed["tool_version"] != "made-again"
    assert len(fake.applied) == 5
    [args] = fake.calls
    assert args[2:] == ["--config", "stevin.yml"]  # no --allow-destructive


def test_a_step_that_was_waiting_applies_the_plan_it_was_shown_with(
    tmp_path: Path,
) -> None:
    """STV-9: nothing was approved before it, so the plan made when the step
    is reached is the one that was shown, and the one that runs."""
    fake = world(tmp_path)
    shown = planned(fake, tmp_path)
    Stevin().apply(ctx(fake, tmp_path), shown)
    assert fake.handed == shown.payload


def _another_statement(doc: Any) -> None:
    doc["steps"][3]["sql"] = "DROP TABLE `dev`.`sales`.`customers`"


def _a_step_stevin_would_skip(doc: Any) -> None:
    # stevin skips a step whose change is already true: point one at a change that is
    doc["tables"][0]["changes"].append({"kind": "create_table", "path": ""})
    doc["steps"][3]["change"] = 9


def _set(key: str, value: Any) -> Any:
    def edit(doc: Any) -> None:
        doc["steps"][3][key] = value

    return edit


@pytest.mark.parametrize(
    "edit",
    [
        _another_statement,
        _a_step_stevin_would_skip,
        _set("risk", "feature"),
        _set("title", "SET TAGS, and more"),
        _set("path", "ssn"),
        _set("precheck", "SELECT false"),
        _set("postcheck", "SELECT true"),
        _set("refusal", "Plan again and review the new plan"),
        _set("id", 1),
        _set("change", 0),
        lambda doc: doc.__setitem__("spec_hash", "another"),
        lambda doc: doc["tables"][1].__setitem__("desired", None),
        lambda doc: doc["steps"].append("no step at all"),
    ],
)
def test_a_file_stevin_would_no_longer_run_the_same_is_refused(
    tmp_path: Path, edit: Any
) -> None:
    """STV-5: the same lines in lely's plan, and a file stevin would do
    something else with. stevin is not run, and nothing of the file is in the
    message."""
    fake = world(tmp_path)
    fresh = planned(fake, tmp_path)
    edited = json.loads(json.dumps(fresh.payload))
    edit(edited)
    approved = dataclasses.replace(fresh, payload=edited)
    with pytest.raises(Refused) as refused:
        Stevin().apply(approving(fake, tmp_path, approved), fresh)
    said = str(refused.value)
    assert "no longer what the approved plan holds" in said
    assert said.endswith("Plan again.")
    assert "DROP TABLE" not in said and "another" not in said
    assert fake.calls == []


def test_what_follows_a_tables_data_may_differ(tmp_path: Path) -> None:
    """A table grew, and its restore point moved: the same plan."""
    fake = world(tmp_path)
    fresh = planned(fake, tmp_path)
    grown = json.loads(json.dumps(fresh.payload))
    grown["steps"][1]["est_bytes"] = 10**12
    grown["steps"][1]["undo_hint"] = "RESTORE TABLE x TO VERSION AS OF 12"
    grown["tables"][0]["facts"]["size_bytes"] = 10**12
    approved = dataclasses.replace(fresh, payload=grown)
    Stevin().apply(approving(fake, tmp_path, approved), fresh)
    assert fake.handed == grown


def test_a_file_with_more_steps_than_stevin_would_run_now_is_refused(
    tmp_path: Path,
) -> None:
    """Also when every step that is left is one the file holds."""
    fake = world(tmp_path)
    approved = planned(fake, tmp_path)
    assert isinstance(approved.payload, dict)
    steps = approved.payload["steps"]
    assert isinstance(steps, list)
    fewer = dataclasses.replace(
        approved, payload={**approved.payload, "steps": steps[2:]}
    )
    with pytest.raises(Refused, match=r"5 step\(s\) then, 3 now"):
        Stevin().apply(approving(fake, tmp_path, approved), fewer)
    assert fake.calls == []


def test_a_file_for_another_target_is_refused(tmp_path: Path) -> None:
    """STV-5: and what the file says its target is, is not repeated."""
    fake = world(tmp_path)
    approved = planned(fake, tmp_path)
    prod = ctx(fake, tmp_path, target="prod", approved=approved)
    with pytest.raises(Refused, match="is for another target than `prod`. Plan again"):
        Stevin().apply(prod, approved)
    assert fake.calls == []


def test_an_approved_file_of_another_format_is_refused(tmp_path: Path) -> None:
    """A refusal, not a failure: running it again would not help."""
    fake = world(tmp_path)
    fresh = planned(fake, tmp_path)
    assert isinstance(fresh.payload, dict)
    approved = dataclasses.replace(fresh, payload={**fresh.payload, "format_version": 9})
    with pytest.raises(Refused, match="is not of format 1"):
        Stevin().apply(approving(fake, tmp_path, approved), fresh)
    assert fake.calls == []


def test_a_stale_plan_is_refused_in_stevins_words(tmp_path: Path) -> None:
    """STV-6 (S4): a refusal, not a failure, and it says to plan again."""
    fake = world(tmp_path)
    approved = planned(fake, tmp_path)
    fake.told("moved", "someone added a column by hand")
    with pytest.raises(Refused) as refused:
        Stevin().apply(approving(fake, tmp_path, approved), approved)
    said = str(refused.value)
    assert "stevin refused the plan for step `tables`" in said
    assert "the live tables have changed since this plan was made" in said
    assert said.endswith("Plan again with `lely plan`, and review the new plan.")
    assert fake.applied == []


def test_a_plan_file_of_another_stevin_is_refused_too(tmp_path: Path) -> None:
    """STV-6 (S5): told by stevin's words, also when a terminal wrapped them."""
    fake = world(tmp_path)
    approved = planned(fake, tmp_path)
    fake.told(
        "fail-apply",
        "plan.json: plan format version 9 — this stevin writes and reads version 1. "
        "Re-run\n`stevin plan`.",
    )
    with pytest.raises(Refused, match="stevin refused the plan"):
        Stevin().apply(approving(fake, tmp_path, approved), approved)


def test_a_failing_apply_is_a_failure_in_stevins_words(tmp_path: Path) -> None:
    """STV-7 (S7): not a refusal. What ran before it stays."""
    fake = world(tmp_path)
    approved = planned(fake, tmp_path)
    fake.told("fail-step", "3")
    with pytest.raises(LelyError) as failed:
        Stevin().apply(approving(fake, tmp_path, approved), approved)
    assert not isinstance(failed.value, Refused)
    said = str(failed.value)
    assert "`stevin apply` failed (exit 1)" in said
    assert "Failed at step 3 of 5" in said
    assert "was lely's copy of the approved plan" in said
    assert len(fake.applied) == 2


def test_allow_destructive_goes_to_stevin_only_with_a_destructive_plan(
    tmp_path: Path,
) -> None:
    """STV-8 (S3). The core lets a destructive plan reach `apply` only with
    `--allow-destructive`; `test_running.py` holds that half."""
    fake = world(tmp_path, "stevin-destroy.json")
    approved = planned(fake, tmp_path)
    assert approved.destructive
    Stevin().apply(approving(fake, tmp_path, approved), approved)
    assert fake.calls[0][2:] == ["--config", "stevin.yml", "--allow-destructive"]
    assert fake.applied == ["dev.sales.orders|DROP COLUMN|address"]
    # and stevin holds its own line: without the flag it refuses the same file
    again = world(tmp_path / "again", "stevin-destroy.json")
    kept = planned(again, tmp_path)
    harmless = dataclasses.replace(
        kept,
        changes=tuple(dataclasses.replace(c, destructive=False) for c in kept.changes),
    )
    with pytest.raises(LelyError, match="this plan destroys something"):
        Stevin().apply(approving(again, tmp_path, kept), harmless)
    assert again.applied == []


def test_what_stevin_says_is_passed_on(tmp_path: Path) -> None:
    """STV-12: its own lines, under the step's name, and nothing of the file."""
    fake = world(tmp_path, "stevin-owner.json")
    approved = planned(fake, tmp_path)
    heard = Heard()
    step = dataclasses.replace(approving(fake, tmp_path, approved), log=heard)
    Stevin().apply(step, approved)
    assert heard.lines[0] == "tables: stevin apply"
    assert "tables:   4. SET OWNER [meta] ok" in heard.lines
    assert "jane.doe@example.com" not in "\n".join(heard.lines)


def test_the_plan_names_no_owner(tmp_path: Path) -> None:
    """STV-12: the file holds who owns the table; no rendering of the plan
    does, in a terminal, in a comment or on the page."""
    fake = world(tmp_path, "stevin-owner.json")
    plan = check_plan(Stevin(), ctx(fake, tmp_path))
    assert "jane.doe@example.com" in str(plan.payload)
    [orders] = plan.changes
    assert orders.detail == (
        "CREATE SCHEMA sales  [meta]",
        "CREATE TABLE orders  [meta]",
        "GRANT to analysts  [meta]",
        "SET OWNER  [meta]",
        "⚠ only the owner, its members or MANAGE can change it after this",
    )
    whole = Plan(
        "0", "apply", "dev", project.WORKSPACE, project.SOURCE,
        (PlannedStep("tables", "stevin", "made-from", plan=plan),),
    )  # fmt: skip
    console = Console(record=True, width=200)
    rich.render_plan(whole, console)
    shown = (console.export_text(), markdown.plan_markdown(whole), html.plan_html(whole))
    assert all("SET OWNER" in text for text in shown)
    assert not any("jane.doe" in text for text in shown)


# -- destroy, status ---------------------------------------------------------------


def test_it_plans_applies_and_lists_and_drops_nothing(tmp_path: Path) -> None:
    """STV-10, PLG-11: there is no destroy to call, and no option for one."""
    assert applies(Stevin)
    assert lists(Stevin)
    assert not destroys(Stevin)
    assert Stevin.nothing_to_destroy == (
        "stevin drops nothing on a destroy: a dropped table is its rows. The tables stay."
    )
    assert {f.name for f in dataclasses.fields(Stevin.Options)} == {
        "config",
        "target",
        "select",
        "executable",
    }
    # planned for a destroy, it gives the steps below it nothing and asks nothing
    fake = world(tmp_path)
    assert Stevin().plan(ctx(fake, tmp_path, purpose="destroy")) == StepPlan()
    assert fake.calls == []


def test_the_overview_is_what_the_specs_describe(tmp_path: Path) -> None:
    """STV-11: from `stevin plan`, which reads and changes nothing."""
    fake = world(tmp_path)
    assert Stevin().plan(ctx(fake, tmp_path, purpose="status")) == StepPlan()
    found = check_overview(Stevin(), ctx(fake, tmp_path))
    assert isinstance(found, Overview)
    assert [(i.kind, i.key, i.name, i.deployed) for i in found.items] == [
        ("table", "dev.sales.customers", "customers", False),
        ("table", "dev.sales.orders", "orders", False),
        ("view", "dev.sales.big_orders", "big_orders", False),
    ]
    assert found.notes == ("what stevin's specs describe, as `stevin plan` reads it",)
    assert fake.verbs == ["plan"]
    Stevin().apply(ctx(fake, tmp_path), Stevin().plan(ctx(fake, tmp_path)))
    after = Stevin().overview(ctx(fake, tmp_path))
    assert all(item.deployed for item in after.items)
