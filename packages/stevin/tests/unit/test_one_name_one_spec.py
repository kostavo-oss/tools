"""One object, one spec — and no circle of objects — settled before a workspace is asked.

Two files that both said `table: ${catalog}.sales.orders` used to pass
`validate`. The plan then held two `CREATE TABLE IF NOT EXISTS`, the second a
no-op, and the plan after that dropped the first file's columns to make the
table look like the second. Nothing about that needs a workspace to see, so it
is an error where specs are read: at `validate`, and before `plan` reads
anything.

A cycle is the same kind of mistake: the ordering that finds it at `plan` is
text matching over the specs, so `validate` runs it too.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from fake_warehouse import FakeWarehouse
from helpers import col, table
from stevin import api, cli
from stevin.cli import app
from stevin.connect import Connection
from stevin.introspect import Introspector
from stevin.loader import Project
from stevin.model.function import Function
from stevin.model.schema import Schema
from stevin.model.types import Primitive
from stevin.model.view import Relation, View
from stevin.model.volume import Volume
from stevin.planning import PlanningError, plan_tables

runner = CliRunner()

CONFIG = """
version: 1
specs: [tables]
targets:
  dev:
    vars: {catalog: main}
    warehouse_id: abc123
"""

ORDERS = "table: ${catalog}.sales.orders\ncolumns:\n  - {name: id, type: bigint}\n"
#: The same table, written by someone who didn't know the first file was there.
ORDERS_AGAIN = (
    "table: ${catalog}.Sales.ORDERS\ncolumns:\n  - {name: amount, type: double}\n"
)


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "stevin.yml").write_text(CONFIG)
    (tmp_path / "tables").mkdir()
    (tmp_path / "tables" / "orders.yml").write_text(ORDERS)
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def twice(project: Path) -> Path:
    (project / "tables" / "orders_v2.yml").write_text(ORDERS_AGAIN)
    return project


@pytest.fixture
def circle(project: Path) -> Path:
    (project / "tables" / "a.yml").write_text(
        "view: ${catalog}.sales.a\nquery: SELECT * FROM ${catalog}.sales.b\n"
    )
    (project / "tables" / "b.yml").write_text(
        "view: ${catalog}.sales.b\nquery: SELECT * FROM ${catalog}.sales.a\n"
    )
    return project


@pytest.fixture
def warehouse(monkeypatch: pytest.MonkeyPatch) -> FakeWarehouse:
    fake = FakeWarehouse()
    monkeypatch.setattr(
        cli, "_connect", lambda *_args, **_kwargs: Connection(runner=fake)
    )
    return fake


# ---------------------------------------------------------------------------
# two specs, one name
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("twice")
def test_validate_refuses_two_files_naming_one_table() -> None:
    result = runner.invoke(app, ["validate"])
    assert result.exit_code == 1, result.output
    assert "OK" not in result.output
    assert "main.sales.orders" in result.output
    # Both files, so nobody has to go looking for the other one.
    assert "tables/orders.yml" in result.output
    assert "tables/orders_v2.yml" in result.output


def test_validate_refuses_them_among_explicit_paths(twice: Path) -> None:
    files = [
        str(twice / "tables" / "orders.yml"),
        str(twice / "tables" / "orders_v2.yml"),
    ]
    result = runner.invoke(app, ["validate", "-t", "dev", *files])
    assert result.exit_code == 1, result.output
    assert "tables/orders.yml" in result.output
    assert "tables/orders_v2.yml" in result.output


@pytest.mark.usefixtures("twice")
def test_plan_refuses_them_before_it_asks_the_warehouse(warehouse: FakeWarehouse) -> None:
    result = runner.invoke(app, ["plan"])
    assert result.exit_code == 1, result.output
    assert "CREATE TABLE" not in result.output
    assert "tables/orders.yml" in result.output
    assert "tables/orders_v2.yml" in result.output
    assert warehouse.statements == [], "refused on the files alone"


def test_the_library_plan_refuses_them_and_names_both_files(twice: Path) -> None:
    found = Project.load(twice / "stevin.yml")
    fake = FakeWarehouse()
    with pytest.raises(PlanningError) as raised:
        api.plan(found, found.default, Connection(runner=fake))
    said = str(raised.value)
    assert "main.sales.orders" in said
    assert "orders.yml" in said and "orders_v2.yml" in said
    assert fake.statements == []


def test_the_library_validate_says_so_too(twice: Path) -> None:
    found = Project.load(twice / "stevin.yml")
    errors = [d for d in api.validate(found, found.default) if d.severity == "error"]
    assert len(errors) == 1
    assert errors[0].where.endswith("orders_v2.yml")
    assert "orders.yml" in errors[0].message


@pytest.mark.parametrize(
    "pair",
    [
        (table(col("id", "bigint")), table(col("amount", "double"))),
        (table(col("id", "bigint")), View("main.sales.orders", "SELECT 1")),
        (
            Function("main.sales.f", (), Primitive("string"), "'a'"),
            Function("main.sales.f", (), Primitive("string"), "'b'"),
        ),
        (Volume("main.sales.landing"), Volume("main.sales.landing", comment="again")),
        (Schema("main.sales"), Schema("main.sales", comment="again")),
    ],
    ids=["table-table", "table-view", "function-function", "volume-volume", "schemas"],
)
def test_planning_bare_specs_refuses_one_object_described_twice(
    pair: tuple[Relation, Relation],
) -> None:
    """A host that builds its specs in code has no files, so it is told the name."""
    fake = FakeWarehouse()
    with pytest.raises(PlanningError, match="described by two specs"):
        plan_tables(list(pair), Introspector(fake), target="dev", tool_version="0")
    assert fake.statements == []


def test_one_spec_per_name_is_left_alone(project: Path) -> None:
    (project / "tables" / "customers.yml").write_text(
        "table: ${catalog}.sales.customers\ncolumns:\n  - {name: id, type: bigint}\n"
    )
    result = runner.invoke(app, ["validate"])
    assert result.exit_code == 0, result.output
    assert "2 specs OK." in result.output


# ---------------------------------------------------------------------------
# a circle of objects
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("circle")
def test_validate_finds_a_cycle_without_a_workspace() -> None:
    result = runner.invoke(app, ["validate"])
    assert result.exit_code == 1, result.output
    assert "cycle" in result.output
    assert "main.sales.a" in result.output and "main.sales.b" in result.output
    assert "tables/a.yml" in result.output


def test_the_library_validate_finds_it_too(circle: Path) -> None:
    found = Project.load(circle / "stevin.yml")
    errors = [d for d in api.validate(found, found.default) if d.severity == "error"]
    assert [d.where.endswith("a.yml") for d in errors] == [True]
    assert "cycle" in errors[0].message


@pytest.mark.usefixtures("circle", "warehouse")
def test_plan_still_refuses_a_cycle() -> None:
    result = runner.invoke(app, ["plan"])
    assert result.exit_code == 1, result.output
    assert "cycle" in result.output
