"""`stevin access`: who may see a table, and through what.

Three things decide what a reader gets from a table — the privileges on it and
on its parents, what narrows a read, and the owner — and they are kept in three
places. These hold the report to reading all three for one table, to saying of
each privilege where it is granted, to saying what it could not read and what
it is not, and to writing nothing.

What they can't hold it to is what a workspace answers. The fake lists a
schema's `SELECT` for each table with `inherited_from = SCHEMA`, as a workspace
did on 2026-10-10 (`tests/integration/test_live_access.py` and the probe
*table_privileges says where an inherited grant comes from*); `CATALOG` is the
manual's.
https://docs.databricks.com/aws/en/sql/language-manual/information-schema/table_privileges
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from syrupy.assertion import SnapshotAssertion
from typer.testing import CliRunner

import stevin
from fake_warehouse import FakeWarehouse
from helpers import col, table
from stevin import api, cli
from stevin.access import AccessError
from stevin.connect import Connection
from stevin.introspect import Introspector, Row
from stevin.manage import Manage
from stevin.model.access import LIMITS, LISTS, Access, Held
from stevin.model.policy import Policy
from stevin.model.schema import Schema
from stevin.model.table import Grant, RowFilter
from stevin.model.types import Mask
from stevin.model.view import View
from stevin.render.access import access_text, access_to_dict, dumps, loads

NAME = "main.sales.customers"

#: The table's own: a grant each for two groups, a mask, a row filter, an owner.
CUSTOMERS = replace(
    table(
        col("id", "bigint"),
        replace(col("email", "string"), mask=Mask("main.security.mask_email")),
        col("region", "string"),
        name=NAME,
        grants=(Grant("analysts", ("MODIFY",)), Grant("etl", ("SELECT", "MODIFY"))),
    ),
    owner="crm-team",
    row_filter=RowFilter("main.security.by_region", ("region",)),
)
#: The schema's: `analysts` reads everything in it. `USE SCHEMA` stays there.
SALES = Schema("main.sales", grants=(Grant("analysts", ("USE SCHEMA", "SELECT")),))
#: The catalog's, which stevin never writes.
EVERYONE = (Grant("account users", ("SELECT", "USE CATALOG")),)

MASK_PII = Policy(
    "mask_pii",
    "column_mask",
    "main.sales",
    "schema",
    function="main.governance.redact",
    to=("account users",),
    except_=("data_admins",),
    match_columns="has_tag('pii') AS c",
    on_column="c",
)
REFUSAL = "[INSUFFICIENT_PERMISSIONS] no READ METADATA on main.sales"

CONFIG = (
    "specs: [tables]\ntargets:\n  dev:\n    default: true\n    vars: {catalog: main}\n"
)


def warehouse(*policies: Policy) -> FakeWarehouse:
    fake = FakeWarehouse.of(CUSTOMERS, SALES).under(*policies)
    fake.catalog_grants["main"] = EVERYONE
    return fake


def read(fake: FakeWarehouse, name: str = NAME) -> Access:
    return api.access(Connection(runner=fake), name)


def held(report: Access, principal: str) -> list[tuple[str, str, tuple[str, ...]]]:
    return list(report.held_by(principal))


# ---------------------------------------------------------------------------
# grants: the table's own, and what it inherits
# ---------------------------------------------------------------------------


def test_a_grant_on_the_table_is_the_tables_own() -> None:
    report = read(warehouse())
    assert held(report, "etl") == [("table", NAME, ("MODIFY", "SELECT"))]
    assert not any(h.inherited for h in report.grants if h.principal == "etl")


def test_a_grant_on_the_schema_is_inherited_from_the_schema() -> None:
    report = read(warehouse())
    assert Held("analysts", "SELECT", "schema", "main.sales") in report.grants
    # What a table can't hold stays with the schema: the workspace doesn't
    # list it for the table, and neither does the report.
    assert "USE SCHEMA" not in {h.privilege for h in report.grants}


def test_a_grant_on_the_catalog_is_inherited_from_the_catalog() -> None:
    report = read(warehouse())
    assert held(report, "account users") == [("catalog", "main", ("SELECT",))]


def test_a_principal_with_both_has_each_under_where_it_is_granted() -> None:
    """Nearest first: the table's own, then the schema's."""
    report = read(warehouse())
    assert held(report, "analysts") == [
        ("table", NAME, ("MODIFY",)),
        ("schema", "main.sales", ("SELECT",)),
    ]
    said = access_text(report)
    assert "      MODIFY          the table's own" in said
    assert "      SELECT          inherited from schema main.sales" in said


def test_the_same_privilege_twice_is_listed_twice() -> None:
    """A workspace lists a `SELECT` on the table and one on the schema as two
    rows; revoking one leaves the other, so the report keeps both."""
    fake = warehouse()
    fake.query("GRANT SELECT ON TABLE `main`.`sales`.`customers` TO `analysts`")
    assert held(read(fake), "analysts") == [
        ("table", NAME, ("MODIFY", "SELECT")),
        ("schema", "main.sales", ("SELECT",)),
    ]


def test_principals_are_listed_by_name() -> None:
    assert read(warehouse()).principals == ("account users", "analysts", "etl")


def test_a_table_nobody_was_granted_says_so() -> None:
    fake = FakeWarehouse.of(table(col("id", "bigint"), name="main.ops.lonely"))
    report = read(fake, "main.ops.lonely")
    assert report.grants == ()
    said = access_text(report)
    assert "· nothing on the table, and nothing inherited" in said
    assert "· nothing: no row filter, no mask, no policy in scope" in said
    assert "  owner unknown" in said


def test_a_level_stevin_does_not_know_is_kept_as_the_workspace_said_it() -> None:
    """`inherited_from` is documented as "the ancestor relation"; a value other
    than the three known ones is shown, and placed nowhere."""

    class Answering:
        def query(self, statement: str) -> tuple[Row, ...]:  # noqa: ARG002
            return (
                {
                    "grantee": "auditors",
                    "privilege_type": "ALL_PRIVILEGES",
                    "inherited_from": "METASTORE",
                },
            )

    [only] = Introspector(Answering()).privileges(NAME)
    assert only == Held("auditors", "ALL PRIVILEGES", "metastore", "")
    assert "inherited from metastore" in access_text(Access(NAME, grants=(only,)))


def test_grants_are_asked_of_this_table_only_with_every_name_quoted() -> None:
    fake = warehouse()
    read(fake)
    [asked] = [s for s in fake.statements if "table_name = " in s]
    assert asked == (
        "SELECT grantee, privilege_type, inherited_from "
        "FROM `main`.information_schema.table_privileges "
        "WHERE table_schema = 'sales' AND table_name = 'customers'"
    )


def test_the_reader_asks_for_grants_whatever_the_project_manages() -> None:
    """`grants: false` keeps handed-over grants out of plans, through one gate.
    The report's read doesn't go through it: it changes nothing, and a team
    whose grants another tool sets is who needs to see them."""
    # RULES.md: ACC-7.
    fake = warehouse()
    handed = Introspector(fake, Manage(("grants",)))
    assert {held.principal for held in handed.privileges(NAME)} == {
        "account users",
        "analysts",
        "etl",
    }
    # The plan's own read of the same table still asks nothing.
    live = handed.table(NAME)
    assert live is not None and live.table.grants == ()


# ---------------------------------------------------------------------------
# what narrows a read
# ---------------------------------------------------------------------------


def test_the_row_filter_the_mask_and_the_policy_are_shown() -> None:
    report = read(warehouse(MASK_PII))
    assert report.row_filter == RowFilter("main.security.by_region", ("region",))
    assert report.masks == (("email", Mask("main.security.mask_email")),)
    assert report.policies == (MASK_PII,)
    assert report.narrowed
    said = access_text(report, width=400)
    assert "· row filter main.security.by_region on region" in said
    assert "· mask on email with main.security.mask_email" in said
    assert (
        "· policy mask_pii (column mask, on schema main.sales) masks columns matching "
        "has_tag('pii') AS c with main.governance.redact, for account users except "
        "data_admins"
    ) in said


def test_a_mask_says_the_columns_it_reads() -> None:
    masked = Access(NAME, masks=(("email", Mask("main.s.f", ("region", "id"))),))
    assert "· mask on email with main.s.f, using region and id" in access_text(masked)


def test_the_owner_is_shown() -> None:
    report = read(warehouse())
    assert report.owner == "crm-team"
    assert "  owner crm-team" in access_text(report)


def test_policies_that_could_not_be_read_are_said_once() -> None:
    """A refusal is not a failed report: the grants, the filter and the mask are
    still there, and one line says what is missing, in the workspace's words."""
    fake = warehouse(MASK_PII)
    fake.refusals["SHOW EFFECTIVE POLICIES"] = REFUSAL
    report = read(fake)
    assert report.policies == ()
    assert report.policies_unread == f"FAILED: {REFUSAL}"
    assert report.principals == ("account users", "analysts", "etl")
    said = access_text(report, width=400)
    assert said.count("policies could not be read") == 1
    assert f"⚠ policies could not be read: FAILED: {REFUSAL}" in said
    assert "(the report is otherwise complete)" in said
    assert "manage:" not in said
    assert "· row filter main.security.by_region on region" in said


def test_without_a_filter_or_a_mask_unread_policies_are_not_called_nothing() -> None:
    bare = Access(NAME, policies_unread="FAILED: no")
    said = access_text(bare)
    assert "· no row filter and no mask on the table" in said
    assert "no policy in scope" not in said


# ---------------------------------------------------------------------------
# what it is not, and what it can't report on
# ---------------------------------------------------------------------------


def test_the_report_says_what_it_is_not() -> None:
    said = access_text(read(warehouse()))
    assert LISTS in said
    for limit in LIMITS:
        assert f"· {limit}" in said
    assert access_to_dict(read(warehouse()))["does_not"] == list(LIMITS)
    wanted = ("policy's condition", "who is in a group", "as someone else")
    assert all(any(word in limit for limit in LIMITS) for word in wanted)


def test_it_writes_nothing() -> None:
    # RULES.md: ACC-7.
    fake = warehouse(MASK_PII)
    read(fake)
    assert fake.ddl == []


def test_a_table_that_does_not_exist_is_an_error() -> None:
    with pytest.raises(AccessError, match=r"there is no table main\.sales\.nope"):
        read(warehouse(), "main.sales.nope")


def test_a_schema_that_does_not_exist_is_an_error() -> None:
    with pytest.raises(AccessError, match=r"there is no schema main\.nowhere"):
        read(warehouse(), "main.nowhere.customers")


def test_a_view_is_said_to_be_a_view() -> None:
    fake = warehouse()
    fake.views["main.sales.big"] = View("main.sales.big", "SELECT 1")
    with pytest.raises(AccessError, match="main.sales.big is a view"):
        read(fake, "main.sales.big")


def test_a_name_that_is_not_three_parts_is_refused() -> None:
    with pytest.raises(AccessError, match="catalog.schema.table"):
        read(warehouse(), "sales.customers")


def test_a_name_is_read_in_lower_case() -> None:
    assert read(warehouse(), "Main.Sales.Customers").table == NAME


# ---------------------------------------------------------------------------
# rendered, and as data
# ---------------------------------------------------------------------------


def test_the_report_in_a_terminal(snapshot: SnapshotAssertion) -> None:
    assert access_text(read(warehouse(MASK_PII))) == snapshot


def test_json_round_trips() -> None:
    report = read(warehouse(MASK_PII))
    assert loads(dumps(report)) == report
    unread = replace(report, policies=(), policies_unread="FAILED: no")
    assert loads(dumps(unread)) == unread


def test_text_that_is_not_a_report_is_refused() -> None:
    with pytest.raises(AccessError, match="not an access report"):
        loads('{"table": "main.sales.customers"}')


def test_the_library_exports_the_verb_and_its_result() -> None:
    report = stevin.access(Connection(runner=warehouse()), NAME)
    assert isinstance(report, stevin.Access)
    assert stevin.access_text(report) == access_text(report)
    assert stevin.access_to_json(report) == dumps(report)


# ---------------------------------------------------------------------------
# the command
# ---------------------------------------------------------------------------


@pytest.fixture
def at(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FakeWarehouse:
    """A directory with no project in it, and the warehouse the command reads."""
    fake = warehouse(MASK_PII)
    monkeypatch.setattr(cli, "_connect", lambda *_a, **_k: Connection(runner=fake))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("COLUMNS", "400")
    return fake


def test_the_command_prints_the_report_and_exits_zero(at: FakeWarehouse) -> None:
    result = CliRunner().invoke(cli.app, ["access", NAME])
    assert result.exit_code == 0, result.output
    assert result.output == access_text(read(at), width=400)
    assert at.ddl == []


def test_the_command_gives_the_same_as_json(at: FakeWarehouse) -> None:
    result = CliRunner().invoke(cli.app, ["access", NAME, "--json"])
    assert result.exit_code == 0, result.output
    assert loads(result.output) == read(at)
    data = json.loads(result.output)
    assert data["owner"] == "crm-team"
    assert {
        "principal": "analysts",
        "privilege": "SELECT",
        "level": "schema",
        "on": "main.sales",
        "inherited": True,
    } in data["grants"]
    assert data["row_filter"] == {
        "function": "main.security.by_region",
        "columns": ["region"],
    }
    assert data["masks"] == [
        {"column": "email", "function": "main.security.mask_email", "using_columns": []}
    ]
    assert [p["name"] for p in data["policies"]] == ["mask_pii"]
    assert data["does_not"] == list(LIMITS)


def test_the_command_fails_for_a_table_that_is_not_there(at: FakeWarehouse) -> None:
    result = CliRunner().invoke(cli.app, ["access", "main.sales.nope"])
    assert result.exit_code == 1
    assert "there is no table main.sales.nope" in result.output


def test_the_command_wants_three_parts(at: FakeWarehouse) -> None:
    result = CliRunner().invoke(cli.app, ["access", "customers"])
    assert result.exit_code == 1
    assert "Give the table as catalog.schema.table" in result.output
    assert at.statements == []


def test_a_variable_is_the_targets(at: FakeWarehouse, tmp_path: Path) -> None:
    (tmp_path / "stevin.yml").write_text(CONFIG)
    result = CliRunner().invoke(cli.app, ["access", "${catalog}.sales.customers"])
    assert result.exit_code == 0, result.output
    assert result.output.startswith(f"{NAME}   access")


def test_a_variable_nobody_defined_is_an_error(at: FakeWarehouse, tmp_path: Path) -> None:
    (tmp_path / "stevin.yml").write_text(CONFIG)
    result = CliRunner().invoke(cli.app, ["access", "${nope}.sales.customers"])
    assert result.exit_code == 1
    assert "undefined variable ${nope}" in result.output


def test_a_variable_without_a_project_is_an_error(at: FakeWarehouse) -> None:
    result = CliRunner().invoke(cli.app, ["access", "${catalog}.sales.customers"])
    assert result.exit_code == 1
    assert "there is no stevin.yml here" in result.output


def test_the_command_reads_grants_and_policies_whatever_the_project_hands_over(
    at: FakeWarehouse, tmp_path: Path
) -> None:
    """`manage:` is about what stevin plans and changes. The report only reads,
    and shows what another tool put there: the same answer as without it."""
    plain = CliRunner().invoke(cli.app, ["access", NAME])
    handed = CONFIG + "manage:\n  grants: false\n  policies: false\n  masks: false\n"
    (tmp_path / "stevin.yml").write_text(handed)
    result = CliRunner().invoke(cli.app, ["access", NAME])
    assert result.exit_code == 0, result.output
    assert result.output == plain.output
    assert "SELECT          inherited from schema main.sales" in result.output
    assert "policy mask_pii (column mask, on schema main.sales)" in result.output
    assert "not read" not in result.output
    assert at.ddl == []


def test_a_refusal_is_said_once_in_a_project_that_hands_policies_over(
    at: FakeWarehouse, tmp_path: Path
) -> None:
    (tmp_path / "stevin.yml").write_text(CONFIG + "manage:\n  policies: false\n")
    at.refusals["SHOW EFFECTIVE POLICIES"] = REFUSAL
    result = CliRunner().invoke(cli.app, ["access", NAME])
    assert result.exit_code == 0, result.output
    assert result.output.count("policies could not be read") == 1
    assert "inherited from schema main.sales" in result.output


def test_the_command_says_once_that_policies_could_not_be_read(
    at: FakeWarehouse,
) -> None:
    at.refusals["SHOW EFFECTIVE POLICIES"] = REFUSAL
    result = CliRunner().invoke(cli.app, ["access", NAME])
    assert result.exit_code == 0, result.output
    assert result.output.count("policies could not be read") == 1
