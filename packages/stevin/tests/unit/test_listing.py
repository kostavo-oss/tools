"""`stevin list`: what the specs describe for a target, and whether each is there.

For a program that asks what exists because of stevin, without planning: it
reads, compares nothing with its spec and changes nothing.
"""

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from fake_warehouse import FakeSqlError, FakeWarehouse
from helpers import col, table
from stevin import api, cli
from stevin.cli import app
from stevin.connect import Connection
from stevin.loader import Project
from stevin.model.function import Function, Parameter
from stevin.model.schema import Schema
from stevin.model.view import View
from stevin.model.volume import Volume
from stevin.planning import PlanningError
from stevin.typeparser import parse_type

runner = CliRunner()

CONFIG = """
version: 1
specs: [tables]
targets:
  dev:
    vars: {catalog: main}
    warehouse_id: abc123
"""
SPECS = {
    "_schema.yml": "schema: ${catalog}.sales\ncomment: Sales\n",
    "orders.yml": (
        "table: ${catalog}.sales.orders\n"
        "columns:\n"
        "  - {name: order_id, type: bigint}\n"
        "  - {name: email, type: string, mask: '${catalog}.sales.hide'}\n"
    ),
    "customers.yml": (
        "table: ${catalog}.sales.customers\ncolumns:\n  - {name: id, type: bigint}\n"
    ),
    "big_orders.yml": (
        "view: ${catalog}.sales.big_orders\n"
        "query: SELECT order_id FROM ${catalog}.sales.orders\n"
    ),
    "hide.yml": (
        "function: ${catalog}.sales.hide\n"
        "parameters:\n  - {name: v, type: string}\n"
        "returns: string\n"
        "body: \"'***'\"\n"
    ),
    "files.yml": "volume: ${catalog}.sales.files\n",
    "events.yml": (
        "table: ${catalog}.raw.events\ncolumns:\n  - {name: id, type: bigint}\n"
    ),
}

#: A drifted table, a view and the function are there. The customers table, the
#: volume and the whole `raw` schema are not. `legacy` has no spec.
ORDERS = table(col("order_id", "string"), name="main.sales.orders")
LIVE = (
    Schema("main.sales"),
    ORDERS,
    table(col("id", "bigint"), name="main.sales.legacy"),
    View("main.sales.big_orders", "SELECT order_id FROM main.sales.orders"),
    Function(
        "main.sales.hide",
        parameters=(Parameter("v", parse_type("string")),),
        returns=parse_type("string"),
        body="'***'",
    ),
)
EXPECTED = [
    {"name": "main.raw.events", "kind": "table", "exists": False},
    {"name": "main.sales", "kind": "schema", "exists": True},
    {"name": "main.sales.big_orders", "kind": "view", "exists": True},
    {"name": "main.sales.customers", "kind": "table", "exists": False},
    {"name": "main.sales.files", "kind": "volume", "exists": False},
    {"name": "main.sales.hide", "kind": "function", "exists": True},
    {"name": "main.sales.orders", "kind": "table", "exists": True},
]


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "stevin.yml").write_text(CONFIG)
    (tmp_path / "tables").mkdir()
    for name, text in SPECS.items():
        (tmp_path / "tables" / name).write_text(text)
    return tmp_path


@pytest.fixture
def warehouse(monkeypatch: pytest.MonkeyPatch) -> FakeWarehouse:
    fake = FakeWarehouse.of(*LIVE)
    monkeypatch.setattr(cli, "_connect", lambda *_a, **_k: Connection(runner=fake))
    return fake


def listed(project: Path, *args: str) -> dict[str, Any]:
    result = runner.invoke(
        app, ["list", "--json", "--config", str(project / "stevin.yml"), *args]
    )
    assert result.exit_code == 0, result.output
    return json.loads(result.stdout)


def test_it_lists_every_spec_and_whether_its_object_is_there(
    project: Path, warehouse: FakeWarehouse
) -> None:
    """One entry per spec, of every kind: a name, a kind and `exists`. A table
    that differs from its spec is there all the same, and a table no spec
    describes is not listed. What is missing is not an error: the exit is 0."""
    # RULES.md: OWN-10.
    answer = listed(project)
    assert answer["target"] == "dev"
    assert sorted(answer["objects"], key=lambda one: one["name"]) == EXPECTED
    assert set(answer) == {"target", "objects"}


def test_it_reads_and_never_writes(project: Path, warehouse: FakeWarehouse) -> None:
    """Every statement is a read, none is about a policy or one table's whole
    definition, and the warehouse is as it was. A volume that could be made,
    a table that could be claimed, a column that differs: nothing is done."""
    # RULES.md: OWN-10.
    before = dict(warehouse.tables)
    listed(project)
    assert warehouse.statements, "the workspace was asked"
    assert warehouse.ddl == []
    assert all(s.startswith(("SELECT", "DESCRIBE", "SHOW")) for s in warehouse.statements)
    assert not any("SHOW CREATE TABLE" in s for s in warehouse.statements)
    assert not any("POLIC" in s.upper() for s in warehouse.statements)
    assert warehouse.tables == before
    assert not warehouse.tables["main.sales.orders"].managed, "and nothing is claimed"


def test_the_fake_still_refuses_what_it_does_not_know(warehouse: FakeWarehouse) -> None:
    """The listing is held by a warehouse that would say so if it wrote."""
    with pytest.raises(FakeSqlError):
        warehouse.query("LIST EVERYTHING")


def test_a_selection_narrows_it_and_a_typo_is_an_error(
    project: Path, warehouse: FakeWarehouse
) -> None:
    answer = listed(project, "--select", "sales.orders", "-s", "raw.*")
    assert answer["objects"] == [
        {"name": "main.raw.events", "kind": "table", "exists": False},
        {"name": "main.sales.orders", "kind": "table", "exists": True},
    ]
    result = runner.invoke(
        app, ["list", "--config", str(project / "stevin.yml"), "-s", "ordres"]
    )
    assert result.exit_code == 1
    assert "matches no spec" in result.output


def test_the_terminal_says_the_same(project: Path, warehouse: FakeWarehouse) -> None:
    result = runner.invoke(app, ["list", "--config", str(project / "stevin.yml")])
    assert result.exit_code == 0, result.output
    lines = [" ".join(line.split()) for line in result.output.splitlines()]
    assert lines[0] == "dev · 7 objects"
    assert "main.sales.orders table exists" in lines
    assert "main.sales.files volume not there" in lines
    assert "main.raw.events table not there" in lines


def test_the_library_gives_the_same_list(project: Path) -> None:
    found = Project.load(project / "stevin.yml")
    fake = FakeWarehouse.of(*LIVE, Volume("main.sales.files"))
    answer = api.listing(found, found.target("dev"), Connection(runner=fake))
    assert {(one.name, one.kind, one.exists) for one in answer} >= {
        ("main.sales.files", "volume", True),
        ("main.sales", "schema", True),
        ("main.raw.events", "table", False),
    }
    with pytest.raises(PlanningError, match="matches no spec"):
        api.listing(found, found.target("dev"), Connection(runner=fake), select="nope")


def test_a_workspace_that_cannot_be_read_is_a_failure(
    project: Path, warehouse: FakeWarehouse
) -> None:
    warehouse.refusals["information_schema"] = "PERMISSION_DENIED"
    result = runner.invoke(app, ["list", "--config", str(project / "stevin.yml")])
    assert result.exit_code == 1
    assert "PERMISSION_DENIED" in result.output
