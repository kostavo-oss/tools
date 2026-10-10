"""`apply` against a real workspace: does the executor's machinery hold up?

The offline suite already asserts that a plan converges (`test_convergence.py`)
and that the executor skips, resumes and refuses (`test_executor.py`), against a
fake that implements stevin's own reading of the manual. What only a real
warehouse can tell us is whether the statements are accepted at all — including
the history and lock SQL, which the fake never sees.

What the module shares, to make fewer tables: the three history tables are made
once, in the module's schema, and every apply here records into them; one
applied plan serves the two tests that only look at what an apply left; and one
rewrite serves the two tests that look at what a rewrite did. A test that
changes a table has a table, and a schema, of its own.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from dataclasses import replace as with_fields

import pytest

from helpers import col, table
from stevin.differ import diff
from stevin.executor import ExecutionError, ExecutionResult, Executor
from stevin.history import DeltaHistory, MemoryHistory
from stevin.introspect import Introspector, Row, WarehouseRunner
from stevin.model.plan import Plan, TableDiff, TableFacts, fingerprint
from stevin.model.table import Grant, Table
from stevin.model.types import Field, Primitive, Struct
from stevin.planner import build_plan, create_table_sql
from stevin.planning import plan_tables
from stevin.sql import quote_literal, quote_qualified

pytestmark = pytest.mark.integration

#: A principal to grant to. Every account has `account users`.
PRINCIPAL = os.environ.get("STEVIN_TEST_PRINCIPAL", "account users")


def plan_for(
    desired: Table, introspector: Introspector, target: str = "integration"
) -> Plan:
    live = introspector.table(desired.name)
    live_table = live.table if live else None
    return build_plan(
        [
            TableDiff(
                desired.name,
                diff(desired, live_table),
                TableFacts(
                    desired.name,
                    exists=live_table is not None,
                    properties=live_table.properties if live_table else (),
                    size_bytes=live.size_bytes if live else None,
                    features=live.features if live else (),
                ),
                # A rewrite needs both sides: without them the planner can only
                # classify the change, not rebuild the table.
                desired=desired,
                live=live_table,
            )
        ],
        target=target,
        tool_version="0.1.0",
        spec_hash="spec",
        state_fingerprint=fingerprint([live_table]),
    )


def executor(runner: WarehouseRunner, history: str) -> Executor:
    """An executor that records into the history tables in `history`."""
    return Executor(
        runner=runner,
        introspector=Introspector(runner),
        history=DeltaHistory(runner, history),
    )


@pytest.fixture(scope="module")
def history(shared_schema: str) -> str:
    """The schema this module's applies record into: the module's own.

    `runs`, `steps` and `lock` are three tables, and an executor asks for them
    with `CREATE TABLE IF NOT EXISTS` on every apply. In a schema per test that
    was three tables for each of six tests; here it is three.
    """
    return shared_schema


ORIGINAL = (
    col("order_id", "bigint", nullable=False),
    col("amount", "decimal(10,2)"),
    col("cust_id", "string"),
    col("address", "struct<street:string>"),
    col("legacy_flag", "boolean"),
)


def desired_for(schema: str) -> Table:
    return table(
        col("order_id", "bigint", nullable=False),
        col("amount", "decimal(18,2)"),  # widening -> enables typeWidening
        col("customer_ref", "string", renamed_from="cust_id"),  # -> columnMapping
        col("address", "struct<street:string,zip:string>"),  # nested add
        col("shipped_at", "timestamp", comment="When it left"),
        name=f"{schema}.orders",
        comment="Order facts, one row per order",
        cluster_by=("order_id",),
        tags=(("domain", "sales"),),
        properties=(("delta.enableChangeDataFeed", "true"),),
    )


@dataclass(frozen=True)
class Applied:
    """A plan that ran, and what the executor said of it."""

    desired: Table
    plan: Plan
    result: ExecutionResult


@pytest.fixture(scope="module")
def applied(runner: WarehouseRunner, history: str) -> Applied:
    """A table brought to its spec by one apply. Two tests read what that left:
    neither changes the table, so they share it."""
    introspector = Introspector(runner)
    runner.query(create_table_sql(table(*ORIGINAL, name=f"{history}.orders")))
    desired = desired_for(history)
    plan = plan_for(desired, introspector)
    assert plan.steps
    result = executor(runner, history).apply(plan, allow_destructive=True)
    return Applied(desired, plan, result)


@pytest.mark.smoke
def test_apply_converges_and_records_what_it_did(
    runner: WarehouseRunner, introspector: Introspector, applied: Applied, history: str
) -> None:
    desired, plan, result = applied.desired, applied.plan, applied.result
    assert result.ok, result.error
    assert len(result.ran) == len(plan.steps)

    live = introspector.table(desired.name)
    assert live is not None
    assert diff(desired, live.table) == (), "re-planning after apply must be empty"

    # The history tables exist and hold this run.
    runs = runner.query(
        f"SELECT status FROM {quote_qualified(f'{history}.runs')} "
        f"WHERE run_id = {quote_literal(result.run_id)}"
    )
    assert [row["status"] for row in runs] == ["succeeded"]
    steps = runner.query(
        f"SELECT step_id, status FROM {quote_qualified(f'{history}.steps')} "
        f"WHERE run_id = {quote_literal(result.run_id)}"
    )
    assert len(steps) == len(plan.steps)
    assert {row["status"] for row in steps} == {"succeeded"}

    # And the lock was handed back.
    assert DeltaHistory(runner, history).lock_holder("integration") is None


def test_a_plan_that_already_ran_is_refused(
    runner: WarehouseRunner, applied: Applied, history: str
) -> None:
    """Refused before a step runs, so the table the other test reads is left
    as the first apply made it."""
    assert applied.result.ok, applied.result.error
    with pytest.raises(ExecutionError, match="changed since this plan was made"):
        executor(runner, history).apply(applied.plan, allow_destructive=True)


def test_a_held_lock_stops_a_second_run(
    runner: WarehouseRunner, introspector: Introspector, schema: str, history: str
) -> None:
    """The lock is the target's, and this test has a target of its own: the
    history tables are the module's, and a lock left held here must not stop
    the applies of the other tests."""
    target = "integration-held"
    runner.query(create_table_sql(table(*ORIGINAL, name=f"{schema}.orders")))
    plan = plan_for(desired_for(schema), introspector, target)

    held = DeltaHistory(runner, history)
    held.ensure()
    assert held.acquire_lock(target, "someone-else", 60)
    try:
        with pytest.raises(ExecutionError, match="locked by run someone-else"):
            executor(runner, history).apply(plan, allow_destructive=True)
    finally:
        unlocked = held.force_unlock(target)
    assert unlocked == "someone-else"
    assert executor(runner, history).apply(plan, allow_destructive=True).ok


@dataclass(frozen=True)
class Rewritten:
    """What one rewrite did to one table: the plan, and the table afterwards."""

    name: str
    spec: Table
    plan: Plan
    result: ExecutionResult
    #: Planned again after the rewrite: every change still wanted.
    left: tuple[tuple[str, str], ...]
    live: Table
    rows: tuple[Row, ...]
    staging_left: bool


@pytest.fixture(scope="module")
def rewritten(runner: WarehouseRunner, shared_schema: str, history: str) -> Rewritten:
    """One table, rewritten once, for the two tests about a rewrite.

    A rewrite makes three tables in the metastore's count: the table, the
    staging copy, and the replacement. One asks what became of the data and
    the other what became of the tags, the grants and the owner, so the table
    carries both and is rewritten once. Both tests only read what is kept here.
    """
    introspector = Introspector(runner)
    name = f"{shared_schema}.rewritten"
    quoted = quote_qualified(name)
    original = with_fields(
        table(
            col("order_id", "bigint", nullable=False),
            Field(
                "amount",
                col("amount", "decimal(10,2)").type,
                comment="Gross",
                tags=(("pii", "no"),),
            ),
            col("address", "struct<street:string,old_zip:string>"),
            col("lines", "array<struct<sku:string,qty:int>>"),
            Field("old_name", Primitive("string"), tags=(("pii", "name"),)),
            name=name,
            tags=(("domain", "sales"),),
            grants=(Grant(PRINCIPAL, ("SELECT",)),),
        ),
        owner=PRINCIPAL,
    )

    def planned(spec: Table) -> Plan:
        return plan_tables([spec], introspector, target="integration", tool_version="0")

    made = Executor(runner, introspector, MemoryHistory()).apply(planned(original))
    assert made.ok, made.error
    runner.query(
        f"INSERT INTO {quoted} VALUES "
        "(1, 10.50, named_struct('street', 'High St', 'old_zip', '1234'), "
        "array(named_struct('sku', 'A', 'qty', 2)), 'x')"
    )
    # Set by someone else, and never named by the spec below.
    runner.query(f"ALTER TABLE {quoted} SET TAGS ('unmanaged' = 'yes')")
    runner.query(f"ALTER TABLE {quoted} ALTER COLUMN old_name SET TAGS ('team' = 'crm')")

    spec = with_fields(
        original,
        columns=(
            original.columns[0],
            # A cast, and not a widening.
            Field("amount", Primitive("string"), comment="Gross", tags=(("pii", "no"),)),
            Field(
                "address",
                Struct(
                    (
                        Field("street", Primitive("string")),
                        Field("zip", Primitive("string"), renamed_from="old_zip"),
                        Field("country", Primitive("string")),  # new, so NULL
                    )
                ),
            ),
            col("lines", "array<struct<sku:string,qty:string>>"),  # element cast
            Field(
                "new_name",
                Primitive("string"),
                tags=(("pii", "name"),),
                renamed_from="old_name",
            ),
        ),
        comment="Rewritten",
    )
    plan = planned(spec)
    result = executor(runner, history).apply(plan)
    # Said here, with the step's own error: a rewrite that stopped leaves a
    # table the reads below can't make sense of.
    assert result.ok, result.error
    again = planned(spec)
    live = introspector.table(name)
    assert live is not None
    return Rewritten(
        name=name,
        spec=spec,
        plan=plan,
        result=result,
        left=tuple((c.kind, c.path) for d in again.diffs for c in d.changes),
        live=live.table,
        rows=runner.query(
            "SELECT order_id, amount, address.street, address.zip, address.country, "
            f"lines[0].qty AS qty FROM {quoted}"
        ),
        staging_left=introspector.table(f"{name}__deltaplan_rewrite") is not None,
    )


@pytest.mark.smoke
def test_a_rewrite_converts_the_data_it_moves(rewritten: Rewritten) -> None:
    """The one thing no fake can check: that the projection means what we think.

    A rewrite stages the converted data, replaces the table from it, and drops the
    staging table. Here there are actual rows in it, so a cast that silently
    produced NULLs — or a struct rebuilt by position — shows up.
    """
    titles = [step.title for step in rewritten.plan.steps]
    assert titles[:2] == ["STAGE rewritten data", "REPLACE TABLE"], titles
    assert [step.risk for step in rewritten.plan.steps][:2] == ["rewrite", "rewrite"]
    assert rewritten.result.ok, rewritten.result.error
    assert rewritten.left == (), "the new table must match the spec"

    assert len(rewritten.rows) == 1, "the rewrite must not lose or duplicate rows"
    row = rewritten.rows[0]
    assert row["order_id"] == "1"
    assert row["amount"] == "10.50"
    assert row["street"] == "High St"
    assert row["zip"] == "1234", "the renamed field keeps its value"
    assert row["country"] is None, "a new field starts empty"
    assert row["qty"] == "2"

    # The staging table is cleaned up.
    assert not rewritten.staging_left


def test_a_rewrite_that_converts_nothing_is_one_statement(
    runner: WarehouseRunner, introspector: Introspector, schema: str, history: str
) -> None:
    """A table reads itself and is replaced in one go — the data written once.

    Repartitioning rebuilds a table without changing a single value, so there is
    nothing a staging copy could catch. Verified here on real rows: the
    statement is accepted, every row survives it, and no staging table is made.
    https://docs.databricks.com/aws/en/tables/partitions
    """
    name = f"{schema}.events"
    columns = (
        col("id", "bigint", nullable=False),
        col("day", "date"),
        col("region", "string"),
    )
    live_table = with_fields(table(*columns, name=name), partitioned_by=("region",))
    runner.query(create_table_sql(live_table))
    runner.query(
        f"INSERT INTO {quote_qualified(name)} SELECT id, "
        "date_add(DATE'2026-01-01', CAST(id % 5 AS INT)), "
        "CASE WHEN id % 2 = 0 THEN 'eu' ELSE 'us' END FROM range(100)"
    )

    desired = with_fields(table(*columns, name=name), partitioned_by=("day",))
    plan = plan_for(desired, introspector)
    assert [step.title for step in plan.steps][0] == "REPLACE TABLE"
    assert not any("__deltaplan_rewrite" in (step.sql or "") for step in plan.steps), (
        "nothing is converted, so nothing is staged"
    )
    assert f"FROM {quote_qualified(name)}" in (plan.steps[0].sql or "")
    assert executor(runner, history).apply(plan).ok

    [row] = runner.query(
        "SELECT count(*) AS rows, count(DISTINCT day) AS days, "
        f"count(DISTINCT region) AS regions FROM {quote_qualified(name)}"
    )
    assert (row["rows"], row["days"], row["regions"]) == ("100", "5", "2")
    live = introspector.table(name)
    assert live is not None
    assert live.table.partitioned_by == ("day",)
    assert diff(desired, live.table) == (), "the table must match the spec"


def test_a_table_is_renamed_with_its_data(
    runner: WarehouseRunner, introspector: Introspector, schema: str, history: str
) -> None:
    """Settles the TODO(verify) in the planner's rename: RENAME TO takes a fully
    qualified name in the same schema, and the rows go with the table.
    https://docs.databricks.com/aws/en/sql/language-manual/sql-ref-syntax-ddl-alter-table
    """
    from dataclasses import replace

    old = table(col("id", "bigint"), name=f"{schema}.order_facts")
    runner.query(create_table_sql(old))
    runner.query(f"INSERT INTO {quote_qualified(old.name)} VALUES (1), (2)")

    new = replace(
        table(col("id", "bigint"), name=f"{schema}.orders"), renamed_from=old.name
    )
    plan = plan_tables([new], introspector, target="integration", tool_version="0.1.0")
    assert plan.steps[0].title == "RENAME TABLE"
    assert executor(runner, history).apply(plan).ok

    rows = runner.query(f"SELECT count(*) AS n FROM {quote_qualified(new.name)}")
    assert rows[0]["n"] == "2"
    assert introspector.table(old.name) is None
    again = plan_tables([new], introspector, target="integration", tool_version="0.1.0")
    assert again.empty


def test_a_rewrite_keeps_what_a_replace_keeps(rewritten: Rewritten) -> None:
    """The plan no longer puts back a table's tags, grants and owner, because a
    replace keeps them (verified 2026-09-20) — so this asserts they are still
    there afterwards, including the ones the spec doesn't name. A renamed
    column's tags do stay behind on the old name, and those the plan puts back.
    https://docs.databricks.com/aws/en/database-objects/tags
    """
    titles = [step.title for step in rewritten.plan.steps]
    assert "REPLACE TABLE" in titles
    assert "SET TAGS" not in titles, "a replace keeps the table's tags"
    assert not any(title.startswith("GRANT") for title in titles)
    assert "SET OWNER" not in titles
    assert rewritten.result.ok, rewritten.result.error

    assert rewritten.left == (), "the spec is satisfied"
    live = rewritten.live
    assert dict(live.tags) == {"domain": "sales", "unmanaged": "yes"}
    assert live.owner == PRINCIPAL
    assert live.grants == (Grant(PRINCIPAL, ("SELECT",)),)
    by_name = {column.name: column for column in live.columns}
    assert dict(by_name["amount"].tags) == {"pii": "no"}, "kept through a cast"
    assert dict(by_name["new_name"].tags) == {"pii": "name", "team": "crm"}
    assert by_name["amount"].comment == "Gross"
    assert rewritten.rows[0]["amount"] == "10.50"


def test_a_project_that_hands_grants_over_can_still_apply(
    runner: WarehouseRunner, introspector: Introspector, schema: str
) -> None:
    """The live half of the stale-plan bug: `plan` and `apply` must read the
    workspace the same way, or they differ by whatever was handed over.

    The table is granted something no spec mentions, which is the state a
    handoff hides — and the state that made every apply refuse itself.
    """
    from stevin import api
    from stevin.connect import Connection
    from stevin.manage import Manage

    principal = PRINCIPAL
    manage = Manage(("grants",))
    name = f"{schema}.orders"
    runner.query(create_table_sql(table(col("id", "bigint"), name=name)))
    runner.query(f"GRANT SELECT ON TABLE {quote_qualified(name)} TO `{principal}`")

    desired = table(col("id", "bigint"), col("region", "string"), name=name)
    plan = plan_tables(
        [desired],
        Introspector(runner, manage),
        target="integration",
        tool_version="0.1.0",
        manage=manage,
    )
    assert not plan.empty
    assert api.is_stale(plan, Connection(runner=runner)) is False
    assert api.apply(plan, Connection(runner=runner), history=MemoryHistory()).ok, (
        "a plan made with a handoff has to be appliable"
    )

    live = introspector.table(name)
    assert live is not None and "region" in live.table.column_names
    assert live.table.grants, "and the grant nobody declared is still there"


def test_apply_without_a_history_schema_writes_nothing_beside_the_table(
    runner: WarehouseRunner, introspector: Introspector, schema: str
) -> None:
    """A project that records nothing leaves nothing behind but its table.

    The lock, the resume and the record are what a history schema buys; a host
    deploying into many catalogs may not want three Delta tables of bookkeeping
    in each of them. This checks the catalog afterwards, which is the only way
    to know stevin kept that promise.
    """
    from stevin import api
    from stevin.connect import Connection
    from stevin.history import NoHistory

    name = f"{schema}.orders"
    desired = table(col("id", "bigint", nullable=False), col("amount", "int"), name=name)
    result = api.apply(
        plan_for(desired, introspector), Connection(runner=runner), history=NoHistory()
    )
    assert result.ok, result.error

    live = introspector.table(name)
    assert live is not None and diff(desired, live.table) == ()
    catalog = schema.split(".")[0]
    # The scratch schemas of this suite are named stevin_it_…, this test's own among
    # them: they are not what is looked for.
    left = runner.query(
        f"SELECT schema_name FROM {quote_qualified(f'{catalog}.information_schema')}"
        ".schemata WHERE lower(schema_name) LIKE 'stevin%'"
        " AND lower(schema_name) NOT LIKE 'stevin_it_%'"
    )
    assert left == (), "no history schema was created anywhere"
    tables = runner.query(
        f"SELECT table_name FROM {quote_qualified(f'{catalog}.information_schema')}"
        f".tables WHERE table_schema = {quote_literal(schema.split('.')[1])}"
    )
    assert [row["table_name"] for row in tables] == ["orders"], (
        "and nothing beside the table the spec describes"
    )


def test_a_function_that_reads_a_table_is_created_after_it(
    runner: WarehouseRunner, introspector: Introspector, schema: str
) -> None:
    """A fresh schema has to converge in one apply.

    A row filter that consults a lookup table is the ordinary way to write
    row-level security, and Databricks resolves a function's body when the
    function is created — so the table has to exist first. Nothing but a real
    workspace proves the order stevin chose is the order that works.
    https://docs.databricks.com/aws/en/sql/language-manual/sql-ref-syntax-ddl-create-sql-function
    """
    from stevin import api
    from stevin.connect import Connection
    from stevin.history import NoHistory
    from stevin.model.function import Function, Parameter

    lookup = table(col("mailbox", "string"), name=f"{schema}.mailbox_access")
    reads_it = Function(
        name=f"{schema}.mailbox_filter",
        parameters=(Parameter("val", Primitive("string")),),
        returns=Primitive("boolean"),
        body=(
            f"EXISTS (SELECT 1 FROM {quote_qualified(lookup.name)} a "
            "WHERE a.mailbox = val)"
        ),
    )
    plan = plan_tables(
        [reads_it, lookup],  # written the wrong way round on purpose
        introspector,
        target="integration",
        tool_version="0.1.0",
    )
    assert [diff.table for diff in plan.diffs if diff.changes] == [
        lookup.name,
        reads_it.name,
    ]
    result = api.apply(plan, Connection(runner=runner), history=NoHistory())
    assert result.ok, result.error

    live = introspector.schema(*schema.split("."))
    assert live.get(lookup.name) is not None
    assert live.get_function(reads_it.name) is not None
