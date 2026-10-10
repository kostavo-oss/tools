"""Applying a plan made by a project that hands something to another tool.

The bug this pins: `plan` read live state through the project's `manage` and
`apply` read it through the default, so the two readings differed by exactly
what had been handed over — and every apply refused itself as stale, forever,
on every project with a `manage:` block. Nothing was moving; the two sides were
looking at different things.

The fix is that the plan carries what it was made under, so a check can't
disagree with the plan it is checking.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from fake_warehouse import FakeWarehouse
from helpers import col, table
from stevin import api
from stevin.connect import Connection
from stevin.history import MemoryHistory
from stevin.introspect import Introspector
from stevin.manage import MANAGEABLE, Manage
from stevin.model.plan import Plan
from stevin.model.table import MANAGED_PROPERTY, Grant, RowFilter, Table
from stevin.model.types import Mask
from stevin.planning import plan_tables
from stevin.render.json import dumps, loads

NAME = "main.sales.orders"
MANAGED = ((MANAGED_PROPERTY, "true"),)


def live_table() -> Table:
    """A table carrying everything a project might hand to another tool.

    The handoff has to hide something that is really there, or the test proves
    nothing: this is that something.
    """
    return replace(
        table(
            col("id", "bigint", comment="the key"),
            replace(col("email", "string"), mask=Mask("main.sales.hide")),
            name=NAME,
            properties=MANAGED,
        ),
        comment="written by the data contract",
        tags=(("domain", "sales"),),
        grants=(Grant("analysts", ("SELECT",)),),
        row_filter=RowFilter("main.sales.only_mine", ("id",)),
        owner="someone@example.com",
    )


def spec() -> Table:
    """The same table as a spec says it: shape only."""
    return table(col("id", "bigint"), col("email", "string"), name=NAME)


def planned(manage: Manage, fake: FakeWarehouse, desired: Table | None = None) -> Plan:
    return plan_tables(
        [desired or spec()],
        Introspector(fake, manage),
        target="dev",
        tool_version="0",
        manage=manage,
    )


@pytest.mark.parametrize("aspect", sorted(MANAGEABLE))
def test_a_plan_is_not_stale_the_moment_it_is_made(aspect: str) -> None:
    fake = FakeWarehouse.of(live_table())
    manage = Manage((aspect,))
    plan = planned(manage, fake)
    assert api.is_stale(plan, Connection(runner=fake)) is False, (
        f"handing over {aspect} must not make a fresh plan look stale"
    )


def test_a_project_that_hands_something_over_can_apply() -> None:
    """The bug, end to end: plan, then apply, on a project with a handoff."""
    fake = FakeWarehouse.of(live_table())
    manage = Manage(("grants", "tags", "masks", "comments"))
    desired = replace(spec(), columns=(*spec().columns, col("region", "string")))
    plan = planned(manage, fake, desired)
    assert not plan.empty, "there is a column to add"
    result = api.apply(plan, Connection(runner=fake), history=MemoryHistory())
    assert result.ok, result.error
    assert "region" in fake.tables[NAME].column_names
    # And what was handed over is exactly where it was.
    assert fake.tables[NAME].grants == live_table().grants
    assert fake.tables[NAME].tags == live_table().tags


def test_a_plan_another_version_saved_is_stale_and_says_so() -> None:
    """What a plan holds changes between versions, and with it the fingerprint.
    No table moved, so no table can be named: `is_stale` has to say what `apply`
    will do, and `apply` has to say why."""
    from stevin.executor import StalePlan, stale_tables

    fake = FakeWarehouse.of(live_table())
    desired = replace(spec(), columns=(*spec().columns, col("region", "string")))
    made = planned(Manage(), fake, desired)
    other = replace(made, state_fingerprint="as-another-version-read-it")

    connection = Connection(runner=fake)
    assert stale_tables(other, connection.introspector(other.manage)) == ()
    assert api.is_stale(other, connection) is True
    with pytest.raises(StalePlan, match="saved by another version") as refused:
        api.apply(other, connection, history=MemoryHistory())
    assert "have changed" not in str(refused.value)
    assert "region" not in fake.tables[NAME].column_names, "and nothing ran"


def test_the_handoff_travels_with_the_plan_file() -> None:
    """A plan applied somewhere else has to be read the same way there."""
    fake = FakeWarehouse.of(live_table())
    manage = Manage(("grants", "tags"))
    plan = loads(dumps(planned(manage, fake, replace(spec(), comment="Orders"))))
    assert plan.manage == manage
    assert api.is_stale(plan, Connection(runner=fake)) is False
    assert api.apply(plan, Connection(runner=fake), history=MemoryHistory()).ok


def test_a_plan_from_a_version_that_had_no_handoff_manages_everything() -> None:
    """The JSON plan file is a wire format: an older one still applies."""
    import json

    fake = FakeWarehouse.of(live_table())
    document = json.loads(dumps(planned(Manage(), fake, replace(spec(), comment="O"))))
    del document["not_managed"]
    plan = loads(json.dumps(document))
    assert plan.manage == Manage(), "no record means it managed everything"
    assert api.apply(plan, Connection(runner=fake), history=MemoryHistory()).ok


def test_a_table_that_really_moved_is_still_refused() -> None:
    """The check still does its job: this is not a way to make it quiet."""
    from stevin.executor import StalePlan

    fake = FakeWarehouse.of(live_table())
    manage = Manage(("grants",))
    plan = planned(manage, fake, replace(spec(), comment="Orders"))
    fake.query("ALTER TABLE `main`.`sales`.`orders` ADD COLUMNS (`extra` STRING)")
    with pytest.raises(StalePlan):
        api.apply(plan, Connection(runner=fake), history=MemoryHistory())
