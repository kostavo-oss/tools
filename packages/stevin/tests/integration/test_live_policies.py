"""The policies a table is under, against a real workspace.

The offline suite holds stevin to reading ABAC policies into a plan and never
writing one, against a fake that speaks the manual's column names. Only this
says what a workspace answers: in a scratch schema it makes a table, a
row-filter function and — by hand, in SQL, the way whoever owns policies would —
a policy on the schema, and then asks stevin what it sees.

A workspace may refuse `CREATE POLICY`: it takes `MANAGE` on the securable, and
ABAC on the workspace. Then there is nothing to read back, and the test skips
with the workspace's own sentence.

  SHOW POLICIES    https://docs.databricks.com/aws/en/sql/language-manual/sql-ref-syntax-aux-show-policies
  DESCRIBE POLICY  https://docs.databricks.com/aws/en/sql/language-manual/sql-ref-syntax-aux-describe-policy
  CREATE POLICY    https://docs.databricks.com/aws/en/sql/language-manual/sql-ref-syntax-ddl-create-policy
  requirements     https://docs.databricks.com/aws/en/data-governance/unity-catalog/abac/requirements
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass, field, replace
from pathlib import Path

import pytest
from typer.testing import CliRunner

from helpers import col, table
from stevin import cli
from stevin.connect import Connection
from stevin.executor import Executor
from stevin.history import MemoryHistory
from stevin.introspect import IntrospectionError, Introspector, Row, WarehouseRunner
from stevin.manage import EVERYTHING, Manage
from stevin.model.plan import Plan
from stevin.model.table import RowFilter, Table
from stevin.planning import plan_tables
from stevin.render.rich import plan_text
from stevin.sql import quote_ident, quote_literal, quote_qualified

pytestmark = pytest.mark.integration

#: Who the policy is for. Every account has `account users`.
PRINCIPAL = os.environ.get("STEVIN_TEST_PRINCIPAL", "account users")

POLICY = "stevin_it_rows"
COMMENT = "stevin's live suite"


@dataclass
class Noting:
    """A runner that keeps what was sent through it."""

    runner: WarehouseRunner
    statements: list[str] = field(default_factory=list)

    def query(self, statement: str) -> tuple[Row, ...]:
        self.statements.append(statement)
        return self.runner.query(statement)

    @property
    def client(self) -> object:
        return self.runner.client


def orders(schema: str) -> Table:
    return table(col("id", "bigint"), col("region", "string"), name=f"{schema}.orders")


def planned(
    specs: list[Table], introspector: Introspector, manage: Manage = EVERYTHING
) -> Plan:
    return plan_tables(
        specs, introspector, target="integration", tool_version="0.1.0", manage=manage
    )


@pytest.fixture
def governed(
    runner: WarehouseRunner, introspector: Introspector, schema: str
) -> Iterator[str]:
    """A schema with a table of stevin's in it, a row-filter function, and a
    row filter policy on the schema that somebody else wrote. The schema's name.

    The policy is dropped before the schema is: it is defined on the schema,
    and nothing says a `DROP SCHEMA … CASCADE` takes it along.
    """
    plan = planned([orders(schema)], introspector)
    result = Executor(runner, introspector, MemoryHistory()).apply(plan)
    assert result.ok, result.error
    function = quote_qualified(f"{schema}.keep")
    runner.query(f"CREATE FUNCTION {function}(x INT) RETURNS BOOLEAN RETURN x = 1")
    on = f"ON SCHEMA {quote_qualified(schema)}"
    try:
        runner.query(
            f"CREATE POLICY {quote_ident(POLICY)} {on} "
            f"COMMENT {quote_literal(COMMENT)} "
            f"ROW FILTER {function} TO {quote_ident(PRINCIPAL)} "
            "FOR TABLES USING COLUMNS (1)"
        )
    except IntrospectionError as error:
        said = next(line.strip() for line in str(error).splitlines() if line.strip())
        pytest.skip(f"this workspace won't create a policy: {said}")
    try:
        yield schema
    finally:
        runner.query(f"DROP POLICY {quote_ident(POLICY)} {on}")


def test_a_plan_lists_the_policy_with_its_function_and_principals(
    runner: WarehouseRunner, introspector: Introspector, governed: str
) -> None:
    """What the reader rests on, printed as the workspace said it (`-rA` shows
    it): the columns of `SHOW EFFECTIVE POLICIES` and the rows of `DESCRIBE
    POLICY` — and then that stevin reads the same policy out of them."""
    name = f"{governed}.orders"
    shown = runner.query(f"SHOW EFFECTIVE POLICIES ON TABLE {quote_qualified(name)}")
    print(
        "SHOW EFFECTIVE POLICIES columns:", sorted({key for row in shown for key in row})
    )
    for row in shown:
        if POLICY in row.values():
            print("SHOW EFFECTIVE POLICIES row:", row)
    described = runner.query(
        f"DESCRIBE POLICY {quote_ident(POLICY)} ON SCHEMA {quote_qualified(governed)}"
    )
    for row in described:
        print("DESCRIBE POLICY row:", row)

    plan = planned([orders(governed)], introspector)
    assert plan.policies_unread is None
    [diff] = plan.diffs
    assert diff.changes == (), "a policy is no change to the table"
    [policy] = [p for p in diff.facts.policies if p.name == POLICY]
    assert (policy.kind, policy.level, policy.on.lower()) == (
        "row_filter",
        "schema",
        governed.lower(),
    )
    assert policy.comment == COMMENT
    assert (policy.function or "").lower() == f"{governed}.keep".lower()
    assert [who.lower() for who in policy.to] == [PRINCIPAL.lower()]
    assert policy.except_ == ()
    said = plan_text(plan, width=400)
    assert f"policy {POLICY} (row filter, on schema {policy.on}) filters rows" in said


def test_a_spec_with_its_own_row_filter_is_warned_about_the_policy(
    introspector: Introspector, governed: str
) -> None:
    """Planned, not applied: whether Databricks takes a table's own row filter
    under a policy is not stevin's question. That both are there is."""
    filtered = replace(
        orders(governed), row_filter=RowFilter(f"{governed}.keep", ("id",))
    )
    plan = planned([filtered], introspector)
    [diff] = plan.diffs
    [caution] = diff.cautions
    assert f"the row filter policy {POLICY} is in scope of this table too" in caution
    assert plan.summary.warnings >= 1


def test_drift_lists_the_policy_and_reports_no_drift(
    runner: WarehouseRunner,
    governed: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog, _, bare = governed.partition(".")
    (tmp_path / "stevin.yml").write_text(
        "specs: [tables]\n"
        f"targets:\n  it:\n    default: true\n    vars: {{catalog: {catalog}}}\n"
    )
    (tmp_path / "tables").mkdir()
    (tmp_path / "tables" / "orders.yml").write_text(
        f"table: ${{catalog}}.{bare}.orders\n"
        "columns:\n"
        "  - {name: id, type: bigint}\n"
        "  - {name: region, type: string}\n"
    )
    connection = Connection(runner=runner, client=runner.client)
    monkeypatch.setattr(cli, "_connect", lambda *_a, **_k: connection)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("COLUMNS", "400")
    result = CliRunner().invoke(cli.app, ["drift"])
    assert result.exit_code == 0, result.output
    assert f"policy {POLICY} (row filter, on schema " in result.output
    assert "— not stevin's, left untouched" in result.output
    assert "Drift:" not in result.output


def test_handing_policies_over_sends_no_statement_about_them(
    runner: WarehouseRunner, governed: str
) -> None:
    noting = Noting(runner)
    manage = Manage(("policies",))
    plan = planned([orders(governed)], Introspector(noting, manage), manage=manage)
    assert noting.statements, "the table was read"
    assert [s for s in noting.statements if "POLIC" in s.upper()] == []
    [diff] = plan.diffs
    assert diff.facts.policies == ()
    assert plan.policies_unread is None
