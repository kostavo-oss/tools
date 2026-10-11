"""Filling a new column.

The case that needs it: adding a NOT NULL column to a table that has rows. The
column arrives empty, so SET NOT NULL can only fail. `using:` — already "how to
get this column's value from the rest of the row" for rewrites — fills the rows
that are there, in between.

Table `hooks:` — SQL before and after a table's changes — left in 0.4.0: raw SQL
around a change was the door through which transformation logic walked in. A spec
that still says `hooks:` is refused, with the key named.
"""

from dataclasses import replace
from pathlib import Path

import pytest

from helpers import col, plan_against, run, table
from stevin.differ import diff
from stevin.executor import ExecutionError, Executor
from stevin.history import MemoryHistory
from stevin.introspect import Introspector
from stevin.loader import SpecError, load_table
from stevin.model.table import MANAGED_PROPERTY, RowFilter, Table
from stevin.model.types import Field, Mask, Primitive

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


MASKED = replace(
    LIVE,
    columns=(LIVE.columns[0], replace(LIVE.columns[1], mask=Mask("main.security.hide"))),
)
FILTERED = replace(LIVE, row_filter=RowFilter("main.security.by_country", ("country",)))
NO_BACKFILL = (
    "this table has a column mask or row filter. The backfill is an UPDATE that "
    "runs as the applying principal: it fills only the rows that principal can "
    "see, whatever `using:` reads, and it writes a masked column as that principal "
    "sees it, into a column without the mask. Add the column without `using:`"
)


@pytest.mark.parametrize(
    ("live", "using"),
    [
        (MASKED, "upper(country)"),
        (FILTERED, "upper(country)"),
        # Nothing of the table is read, and the rows a filter hides still stay
        # NULL: refused all the same.
        (FILTERED, "'unknown'"),
        (MASKED, "(SELECT max(code) FROM main.ref.countries)"),
    ],
    ids=["a mask", "a row filter", "a constant", "another table"],
)
def test_a_masked_or_filtered_table_is_not_backfilled(live: Table, using: str) -> None:
    """The fill is an UPDATE by the applying principal: it reaches the rows that
    principal can see and reads a masked column as that principal sees it. So
    the step has no SQL, and `apply` runs nothing of the plan."""
    # RULES.md: RW-7.
    desired = replace(live, columns=(*live.columns, region(nullable=False, using=using)))
    fake, plan = plan_against(desired, live, size_bytes=1_000)
    assert [(s.title, s.risk) for s in plan.steps] == [
        ("ADD COLUMN region", "meta"),
        ("BACKFILL region", "rewrite"),
        ("SET NOT NULL", "meta"),
    ]
    backfill = plan.steps[1]
    assert backfill.sql is None
    assert backfill.note == (
        f"{NO_BACKFILL} and without `nullable: false`, and fill it by hand as a "
        "principal that sees every row"
    )
    # The step after it does not send the reader back to `using:`.
    assert plan.steps[2].warnings == ()
    with pytest.raises(ExecutionError, match="can't run"):
        Executor(fake, Introspector(fake), MemoryHistory()).apply(plan)
    assert fake.ddl == []
    assert not any(step.sql and step.sql.startswith("UPDATE") for step in plan.steps)

    # The way out the note gives: the column without `using:` is an ordinary add.
    plain = replace(live, columns=(*live.columns, region()))
    fake, plan = plan_against(plain, live)
    assert [s.title for s in plan.steps] == ["ADD COLUMN region"]
    run(plan, fake)


def test_a_nullable_column_is_told_the_same_without_the_not_null() -> None:
    desired = replace(MASKED, columns=(*MASKED.columns, region(using="upper(country)")))
    _, plan = plan_against(desired, MASKED)
    assert [(s.title, s.sql) for s in plan.steps[1:]] == [("BACKFILL region", None)]
    assert plan.steps[1].note == (
        f"{NO_BACKFILL}, and fill it by hand as a principal that sees every row"
    )


def test_a_mask_set_earlier_in_the_plan_stops_the_backfill_too() -> None:
    """A spec that puts a mask on a column and adds a filled one in the same
    change: by the time the fill would run, the table is masked."""
    desired = replace(MASKED, columns=(*MASKED.columns, region(using="upper(country)")))
    _, plan = plan_against(desired, LIVE)
    titles = [step.title for step in plan.steps]
    assert titles.index("SET MASK") < titles.index("BACKFILL region")
    assert plan.steps[titles.index("BACKFILL region")].sql is None


def test_a_spec_with_hooks_is_refused_with_the_key_named(tmp_path: Path) -> None:
    # RULES.md: SPEC-2.
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
