"""Filling a new column.

The case that needs it: adding a NOT NULL column to a table that has rows. The
column arrives empty, so SET NOT NULL can only fail. `using:` — already "how to
get this column's value from the rest of the row" for rewrites — fills the rows
that are there, in between.

Table `hooks:` — SQL before and after a table's changes — left in 0.4.0: raw SQL
around a change was the door through which transformation logic walked in. A spec
that still says `hooks:` is refused, with the key named.
"""

from pathlib import Path

import pytest

from helpers import col, plan_against, run, table
from stevin.differ import diff
from stevin.introspect import Introspector
from stevin.loader import SpecError, load_table
from stevin.model.table import MANAGED_PROPERTY
from stevin.model.types import Field, Primitive

NAME = "main.sales.orders"
MANAGED = ((MANAGED_PROPERTY, "true"),)
LIVE = table(col("id", "bigint"), col("country", "string"), name=NAME, properties=MANAGED)


def region(*, nullable: bool = True, using: str | None = None) -> Field:
    return Field("region", Primitive("string"), nullable=nullable, using=using)


def test_a_not_null_column_is_added_filled_then_constrained() -> None:
    desired = table(
        *LIVE.columns,
        region(nullable=False, using="coalesce(country, 'unknown')"),
        name=NAME,
    )
    fake, plan = plan_against(desired, LIVE, size_bytes=1_000)
    assert [(s.title, s.risk) for s in plan.steps] == [
        ("ADD COLUMN region", "meta"),
        ("BACKFILL region", "rewrite"),
        ("SET NOT NULL", "meta"),
    ]
    assert plan.steps[1].sql == (
        "UPDATE `main`.`sales`.`orders` SET `region` = coalesce(country, 'unknown') "
        "WHERE `region` IS NULL"
    )
    # Filled first, so the NOT NULL step no longer warns that it will fail.
    assert plan.steps[2].warnings == ()
    run(plan, fake)
    after = Introspector(fake).table(NAME)
    assert after is not None and diff(desired, after.table) == ()


def test_without_using_the_plan_says_what_is_missing() -> None:
    desired = table(*LIVE.columns, region(nullable=False), name=NAME)
    _, plan = plan_against(desired, LIVE)
    assert "give the column a `using:` expression" in plan.steps[1].warnings[0]


def test_a_nullable_column_can_be_backfilled_too() -> None:
    desired = table(*LIVE.columns, region(using="upper(country)"), name=NAME)
    _, plan = plan_against(desired, LIVE)
    assert [s.title for s in plan.steps] == ["ADD COLUMN region", "BACKFILL region"]


def test_a_new_table_has_nothing_to_backfill() -> None:
    desired = table(col("id", "bigint"), region(nullable=False, using="'x'"), name=NAME)
    _, plan = plan_against(desired)
    assert "BACKFILL" not in " ".join(s.title for s in plan.steps)


def test_a_spec_with_hooks_is_refused_with_the_key_named(tmp_path: Path) -> None:
    path = tmp_path / "orders.yml"
    path.write_text(
        "table: ${catalog}.sales.orders\n"
        "columns: [{name: id, type: bigint}]\n"
        "hooks:\n"
        "  before: DELETE FROM ${catalog}.sales.orders WHERE id IS NULL\n"
    )
    with pytest.raises(SpecError, match="unknown key 'hooks'") as caught:
        load_table(path, {"catalog": "main"})
    assert "orders.yml:3" in str(caught.value)
