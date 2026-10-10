"""Who may see a table, against a real workspace.

The offline suite holds `stevin access` to its report against a fake that lists
a schema's grant for each table with `inherited_from = SCHEMA`. Only this says
a workspace does: in a scratch schema it grants `SELECT` on the schema, makes a
table with a grant and a row filter of its own, has somebody else's row filter
policy on the schema, and asks stevin who may see the table.

The tests here only read, so they share one schema and one table: the fixture
is made once for the module, and one table is what the module costs.

Nothing here prints or compares a report as the workspace gave it. The table's
owner is whoever ran the suite, and a catalog may grant to people by name: the
report is cut down to the one group and the one policy this file made before
anything is asserted on it, so a failure can't put a name in a public log.

A workspace may refuse `CREATE POLICY`: it takes `MANAGE` on the securable, and
ABAC on the workspace. Then the test skips with the workspace's own sentence.

  table_privileges  https://docs.databricks.com/aws/en/sql/language-manual/information-schema/table_privileges
  row filters       https://docs.databricks.com/aws/en/tables/row-and-column-filters
  CREATE POLICY     https://docs.databricks.com/aws/en/sql/language-manual/sql-ref-syntax-ddl-create-policy
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from dataclasses import dataclass, field, replace
from pathlib import Path

import pytest
from typer.testing import CliRunner

from helpers import col, table
from stevin import api, cli
from stevin.connect import Connection
from stevin.executor import Executor
from stevin.history import MemoryHistory
from stevin.introspect import IntrospectionError, Introspector, Row, WarehouseRunner
from stevin.model.access import LIMITS, Access, Held
from stevin.model.table import Grant, RowFilter
from stevin.planning import plan_tables
from stevin.render.access import access_text, loads
from stevin.sql import quote_ident, quote_literal, quote_qualified

pytestmark = pytest.mark.integration

#: Who the grants and the policy are for. Every account has `account users`.
PRINCIPAL = os.environ.get("STEVIN_TEST_PRINCIPAL", "account users")

POLICY = "stevin_it_access"


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


def ours(report: Access) -> Access:
    """The report, cut down to what this file made: the one group's grants, the
    one policy, and no owner's name."""
    return replace(
        report,
        owner="the owner" if report.owner else None,
        grants=tuple(h for h in report.grants if h.principal == PRINCIPAL),
        policies=tuple(p for p in report.policies if p.name == POLICY),
    )


@pytest.fixture(scope="module")
def governed(runner: WarehouseRunner, shared_schema: str) -> Iterator[str]:
    """A schema that grants `SELECT` to a group, with one table in it that has a
    grant and a row filter of its own, and a row filter policy on the schema
    that somebody else wrote. The table's name.

    Made once for the module: every test here reads it and none changes it.

    The policy is dropped before the schema is: it is defined on the schema,
    and nothing says a `DROP SCHEMA … CASCADE` takes it along.
    """
    schema, introspector = shared_schema, Introspector(runner)
    name = f"{schema}.orders"
    orders = table(
        col("id", "bigint"),
        col("region", "string"),
        name=name,
        grants=(Grant(PRINCIPAL, ("MODIFY",)),),
    )
    plan = plan_tables([orders], introspector, target="integration", tool_version="0")
    result = Executor(runner, introspector, MemoryHistory()).apply(plan)
    assert result.ok, result.error
    on = f"ON SCHEMA {quote_qualified(schema)}"
    runner.query(f"GRANT SELECT {on} TO {quote_ident(PRINCIPAL)}")
    runner.query(f"GRANT USE SCHEMA {on} TO {quote_ident(PRINCIPAL)}")
    keep = quote_qualified(f"{schema}.keep")
    runner.query(
        f"CREATE FUNCTION {keep}(region STRING) RETURNS BOOLEAN RETURN region IS NOT NULL"
    )
    runner.query(f"ALTER TABLE {quote_qualified(name)} SET ROW FILTER {keep} ON (region)")
    every = quote_qualified(f"{schema}.every")
    runner.query(f"CREATE FUNCTION {every}(x INT) RETURNS BOOLEAN RETURN x = 1")
    try:
        runner.query(
            f"CREATE POLICY {quote_ident(POLICY)} {on} "
            f"COMMENT {quote_literal('stevin live suite')} "
            f"ROW FILTER {every} TO {quote_ident(PRINCIPAL)} "
            "FOR TABLES USING COLUMNS (1)"
        )
    except IntrospectionError as error:
        said = next(line.strip() for line in str(error).splitlines() if line.strip())
        pytest.skip(f"this workspace won't create a policy: {said}")
    try:
        yield name
    finally:
        runner.query(f"DROP POLICY {quote_ident(POLICY)} {on}")


@pytest.mark.smoke
def test_the_report_says_what_is_inherited_and_what_is_the_tables_own(
    runner: WarehouseRunner, governed: str
) -> None:
    """What the reader rests on is printed as the workspace said it (`-rA` shows
    it) — the group's rows only — and then the report is read out of it."""
    catalog, schema, short = governed.split(".")
    for row in runner.query(
        "SELECT grantee, privilege_type, inherited_from "
        f"FROM {quote_ident(catalog)}.information_schema.table_privileges "
        f"WHERE table_schema = {quote_literal(schema)} "
        f"AND table_name = {quote_literal(short)} "
        f"AND grantee = {quote_literal(PRINCIPAL)}"
    ):
        print("table_privileges row:", row)

    noting = Noting(runner)
    report = ours(api.access(Connection(runner=noting, client=runner.client), governed))
    written = [
        s for s in noting.statements if not s.startswith(("SELECT", "SHOW", "DESCRIBE"))
    ]
    assert written == [], "the report only reads"

    assert report.table == governed.lower()
    assert report.owner == "the owner"
    assert Held(PRINCIPAL, "MODIFY", "table", governed.lower()) in report.grants
    assert Held(PRINCIPAL, "SELECT", "schema", f"{catalog}.{schema}") in report.grants
    # The schema's SELECT is not the table's, and USE SCHEMA is not a table's at all.
    own = {h.privilege for h in report.grants if not h.inherited}
    assert own == {"MODIFY"}
    assert "USE SCHEMA" not in {h.privilege for h in report.grants}

    assert report.row_filter == RowFilter(f"{catalog}.{schema}.keep", ("region",))
    assert report.masks == ()
    assert report.policies_unread is None
    [policy] = report.policies
    assert (policy.kind, policy.level, policy.on.lower()) == (
        "row_filter",
        "schema",
        f"{catalog}.{schema}",
    )
    assert (policy.function or "").lower() == f"{catalog}.{schema}.every"
    assert [who.lower() for who in policy.to] == [PRINCIPAL.lower()]

    said = access_text(report, width=400)
    assert "  owner the owner" in said
    assert f"    {PRINCIPAL}\n" in said
    assert "MODIFY  the table's own" in said
    assert f"SELECT  inherited from schema {catalog}.{schema}" in said
    assert f"· row filter {catalog}.{schema}.keep on region" in said
    assert f"· policy {POLICY} (row filter, on schema {policy.on}) filters rows" in said
    for limit in LIMITS:
        assert f"· {limit}" in said


def test_the_command_reads_the_same_as_json(
    runner: WarehouseRunner,
    governed: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`--json`, because it is printed once, whole: a report that printed half
    and then failed would have the owner in it."""
    connection = Connection(runner=runner, client=runner.client)
    monkeypatch.setattr(cli, "_connect", lambda *_a, **_k: connection)
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(cli.app, ["access", governed, "--json"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["does_not"] == list(LIMITS)
    report = ours(loads(result.stdout))
    assert report == ours(api.access(connection, governed))
    assert {(h.privilege, h.level) for h in report.grants} == {
        ("MODIFY", "table"),
        ("SELECT", "schema"),
    }
    assert [p.name for p in report.policies] == [POLICY]


def test_a_table_that_is_not_there_is_the_usual_error(
    runner: WarehouseRunner,
    shared_schema: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schema = shared_schema
    connection = Connection(runner=runner, client=runner.client)
    monkeypatch.setattr(cli, "_connect", lambda *_a, **_k: connection)
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(cli.app, ["access", f"{schema}.nope"])
    assert result.exit_code == 1
    assert f"there is no table {schema}.nope" in result.output
