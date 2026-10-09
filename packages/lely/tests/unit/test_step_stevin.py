"""The `stevin` plugin's plan half, against plan files stevin itself wrote.

Parked: the owner takes this plugin up separately. It plans, and says before
anything runs that it can't apply yet.

`tests/fixtures/stevin-*.json` were recorded by running stevin's CLI
against its own fake warehouse (its `tests/screens.py` scenes), so these tests
hold lely to the plan file stevin really writes.
"""

import json
import sys
from pathlib import Path

import pytest

from fakes import FIXTURES, fixture
from lely.errors import LelyError
from lely.model import Change
from lely.steps.stevin import Stevin, changes
from lely.testing import check_plan, context

FAKE = str(Path(__file__).parent.parent / "fake_stevin.py")


def test_a_first_plan_creates_each_table() -> None:
    result = changes(fixture("stevin-create.json"))
    assert [(c.key, c.action, c.destructive) for c in result] == [
        ("dev.sales.customers", "create", False),
        ("dev.sales.orders", "create", False),
        ("dev.sales.big_orders", "create", False),
    ]
    assert result[0].detail == ("CREATE SCHEMA sales", "CREATE TABLE customers")


def test_a_dropped_column_is_a_destructive_update() -> None:
    assert changes(fixture("stevin-destroy.json")) == (
        Change(
            "dev.sales.orders",
            "update",
            "dev.sales.orders",
            destructive=True,
            detail=("DROP COLUMN  [destructive]",),
        ),
    )


def test_nothing_to_do_is_no_changes() -> None:
    assert changes(fixture("stevin-empty.json")) == ()


def test_another_plan_format_is_refused() -> None:
    document = fixture("stevin-empty.json")
    document["format_version"] = 2
    with pytest.raises(LelyError, match="plan format 2; lely reads format 1"):
        changes(document)


def test_plans_through_stevins_cli(tmp_path: Path) -> None:
    calls = tmp_path / "calls.jsonl"
    options = Stevin.Options(
        executable=(sys.executable, FAKE, str(FIXTURES / "stevin-destroy.json")),
        select=("sales.*",),
    )
    ctx = context(
        options, target="prod", root=tmp_path, env={"FAKE_STEVIN_CALLS": str(calls)}
    )
    plan = check_plan(Stevin(), ctx)
    assert [c.key for c in plan.changes] == ["dev.sales.orders"]
    assert plan.payload == fixture("stevin-destroy.json")
    [args] = [json.loads(line) for line in calls.read_text().splitlines()]
    assert args[:5] == ["plan", "--target", "prod", "--config", "stevin.yml"]
    assert args[-2:] == ["--select", "sales.*"]


def test_its_own_target_wins(tmp_path: Path) -> None:
    calls = tmp_path / "calls.jsonl"
    options = Stevin.Options(
        target="staging",
        executable=(sys.executable, FAKE, str(FIXTURES / "stevin-empty.json")),
    )
    Stevin().plan(
        context(
            options,
            target="prod",
            root=tmp_path,
            env={"FAKE_STEVIN_CALLS": str(calls)},
        )
    )
    assert json.loads(calls.read_text())[2] == "staging"


def test_a_failing_stevin_is_shown_in_its_own_words(tmp_path: Path) -> None:
    options = Stevin.Options(
        executable=(sys.executable, FAKE, str(FIXTURES / "stevin-empty.json"))
    )
    ctx = context(options, root=tmp_path, env={"FAKE_STEVIN_FAIL": "1"})
    with pytest.raises(
        LelyError, match="(?s)`stevin plan` failed.*can't reach the warehouse"
    ):
        Stevin().plan(ctx)


def test_a_missing_stevin_says_how_to_get_it(tmp_path: Path) -> None:
    ctx = context(Stevin.Options(executable=("no-such-stevin",)), root=tmp_path)
    with pytest.raises(LelyError, match="uv tool install stevin"):
        Stevin().plan(ctx)


def test_it_can_plan_and_cant_apply_yet(tmp_path: Path) -> None:
    from lely.step import applies, destroys, lists

    assert not applies(Stevin)
    assert not destroys(Stevin)
    assert not lists(Stevin)
    with pytest.raises(LelyError, match="can plan and can't apply yet"):
        Stevin().apply(context(Stevin.Options(), root=tmp_path), check_plan_stub())


def check_plan_stub():  # a plan to hand to `apply`; it never looks at it
    from lely.model import StepPlan

    return StepPlan()
