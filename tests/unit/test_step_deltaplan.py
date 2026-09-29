"""The `deltaplan` step, against plan files deltaplan itself wrote.

`tests/fixtures/deltaplan-*.json` were recorded by running deltaplan's CLI
against its own fake warehouse (its `tests/screens.py` scenes), so these tests
hold sluis to the plan file deltaplan really writes.
"""

import json
import sys
from pathlib import Path

import pytest

from fakes import FIXTURES, fixture
from sluis.errors import SluisError
from sluis.model import Change
from sluis.steps.deltaplan import Deltaplan, changes
from sluis.testing import check_plan, context

FAKE = str(Path(__file__).parent.parent / "fake_deltaplan.py")


def test_a_first_plan_creates_each_table() -> None:
    result = changes(fixture("deltaplan-create.json"))
    assert [(c.key, c.action, c.destructive) for c in result] == [
        ("dev.sales.customers", "create", False),
        ("dev.sales.orders", "create", False),
        ("dev.sales.big_orders", "create", False),
    ]
    assert result[0].detail == ("CREATE SCHEMA sales", "CREATE TABLE customers")


def test_a_dropped_column_is_a_destructive_update() -> None:
    assert changes(fixture("deltaplan-destroy.json")) == (
        Change(
            "dev.sales.orders",
            "update",
            "dev.sales.orders",
            destructive=True,
            detail=("DROP COLUMN  [destructive]",),
        ),
    )


def test_nothing_to_do_is_no_changes() -> None:
    assert changes(fixture("deltaplan-empty.json")) == ()


def test_another_plan_format_is_refused() -> None:
    document = fixture("deltaplan-empty.json")
    document["format_version"] = 2
    with pytest.raises(SluisError, match="plan format 2; sluis reads format 1"):
        changes(document)


def test_plans_through_deltaplans_cli(tmp_path: Path) -> None:
    calls = tmp_path / "calls.jsonl"
    options = Deltaplan.Options(
        executable=(sys.executable, FAKE, str(FIXTURES / "deltaplan-destroy.json")),
        select=("sales.*",),
    )
    ctx = context(
        options, target="prod", root=tmp_path, env={"FAKE_DELTAPLAN_CALLS": str(calls)}
    )
    plan = check_plan(Deltaplan(), ctx)
    assert [c.key for c in plan.changes] == ["dev.sales.orders"]
    assert plan.payload == fixture("deltaplan-destroy.json")
    [args] = [json.loads(line) for line in calls.read_text().splitlines()]
    assert args[:5] == ["plan", "--target", "prod", "--config", "deltaplan.yml"]
    assert args[-2:] == ["--select", "sales.*"]


def test_its_own_target_wins(tmp_path: Path) -> None:
    calls = tmp_path / "calls.jsonl"
    options = Deltaplan.Options(
        target="staging",
        executable=(sys.executable, FAKE, str(FIXTURES / "deltaplan-empty.json")),
    )
    Deltaplan().plan(
        context(
            options,
            target="prod",
            root=tmp_path,
            env={"FAKE_DELTAPLAN_CALLS": str(calls)},
        )
    )
    assert json.loads(calls.read_text())[2] == "staging"


def test_a_failing_deltaplan_is_shown_in_its_own_words(tmp_path: Path) -> None:
    options = Deltaplan.Options(
        executable=(sys.executable, FAKE, str(FIXTURES / "deltaplan-empty.json"))
    )
    ctx = context(options, root=tmp_path, env={"FAKE_DELTAPLAN_FAIL": "1"})
    with pytest.raises(
        SluisError, match="(?s)`deltaplan plan` failed.*can't reach the warehouse"
    ):
        Deltaplan().plan(ctx)


def test_a_missing_deltaplan_says_how_to_get_it(tmp_path: Path) -> None:
    ctx = context(Deltaplan.Options(executable=("no-such-deltaplan",)), root=tmp_path)
    with pytest.raises(SluisError, match="uv tool install deltaplan"):
        Deltaplan().plan(ctx)
