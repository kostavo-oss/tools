"""A function spec is only for a column mask or a row filter.

stevin is not a place for UDFs to accumulate: a function spec exists so the
function a mask or a row filter names is created in the same plan, before the
tables that use it. One that nothing in the project names is refused where
specs are read — at `validate`, and before `plan` asks the workspace anything,
`--select` or not — with its file and line. `import` writes only the functions a
live mask or row filter names, and says which it skipped.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from typer.testing import CliRunner

from fake_warehouse import FakeWarehouse
from helpers import col
from stevin import api, cli
from stevin.cli import app
from stevin.connect import Connection
from stevin.loader import Project, unreferenced_functions
from stevin.model.function import Function, Parameter
from stevin.model.table import Table
from stevin.model.types import Mask, Primitive
from stevin.planning import PlanningError

runner = CliRunner()

CONFIG = """
version: 1
specs: [tables]
targets:
  dev:
    vars: {catalog: main}
    warehouse_id: abc123
"""

CUSTOMERS = """\
table: ${catalog}.sales.customers
columns:
  - {name: customer_id, type: bigint}
  - {name: email, type: string, mask: "${catalog}.Security.Mask_Email"}
  - {name: region, type: string}
row_filter:
  function: ${catalog}.security.by_region
  columns: [region]
"""

ORDERS = "table: ${catalog}.sales.orders\ncolumns:\n  - {name: id, type: bigint}\n"


def function(name: str) -> str:
    return (
        f"function: ${{catalog}}.{name}\n"
        "parameters:\n  - {name: x, type: string}\n"
        "returns: string\nbody: x\n"
    )


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "stevin.yml").write_text(CONFIG)
    tables = tmp_path / "tables"
    tables.mkdir()
    (tables / "customers.yml").write_text(CUSTOMERS)
    (tables / "orders.yml").write_text(ORDERS)
    (tables / "mask_email.yml").write_text(function("security.mask_email"))
    (tables / "by_region.yml").write_text(function("security.by_region"))
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def stray(project: Path) -> Path:
    """A function nothing masks or filters with."""
    (project / "tables" / "order_band.yml").write_text(function("sales.order_band"))
    return project


@pytest.fixture
def warehouse(monkeypatch: pytest.MonkeyPatch) -> FakeWarehouse:
    fake = FakeWarehouse()
    monkeypatch.setattr(
        cli, "_connect", lambda *_args, **_kwargs: Connection(runner=fake)
    )
    return fake


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("project")
def test_functions_a_mask_or_filter_names_are_fine_whatever_the_case() -> None:
    # The mask says `Security.Mask_Email`; the catalog compares names lowercased,
    # and so does this. `${catalog}` has been rendered on both sides.
    result = runner.invoke(app, ["validate"])
    assert result.exit_code == 0, result.output
    assert "4 specs OK" in result.output


@pytest.mark.usefixtures("stray")
def test_validate_refuses_a_function_nothing_names() -> None:
    result = runner.invoke(app, ["validate"])
    assert result.exit_code == 1, result.output
    assert "tables/order_band.yml" in result.output
    assert "main.sales.order_band" in result.output
    assert "a function spec is only for a column mask or row filter" in result.output
    assert "belong to your transformation tool" in result.output
    # The ones a mask and a filter name are not in the complaint.
    assert "mask_email.yml" not in result.output
    assert "by_region.yml" not in result.output


def test_validate_refuses_it_among_explicit_paths(stray: Path) -> None:
    files = [str(stray / "tables" / "order_band.yml")]
    result = runner.invoke(app, ["validate", "-t", "dev", *files])
    assert result.exit_code == 1, result.output
    assert "tables/order_band.yml" in result.output


def test_the_library_validate_says_so_too(stray: Path) -> None:
    found = Project.load(stray / "stevin.yml")
    errors = [d for d in api.validate(found, found.default) if d.severity == "error"]
    assert len(errors) == 1
    assert errors[0].where.endswith("order_band.yml")
    assert "transformation tool" in errors[0].message


def test_the_check_on_its_own(project: Path) -> None:
    found = Project.load(project / "stevin.yml")
    assert unreferenced_functions(found.load_specs(found.default).files) == ()


# ---------------------------------------------------------------------------
# plan — before the warehouse, and before --select
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("stray")
def test_plan_refuses_it_before_it_asks_the_warehouse(warehouse: FakeWarehouse) -> None:
    result = runner.invoke(app, ["plan"])
    assert result.exit_code == 1, result.output
    assert "tables/order_band.yml" in result.output
    assert warehouse.statements == [], "refused on the files alone"


def test_select_does_not_hide_it(stray: Path) -> None:
    found = Project.load(stray / "stevin.yml")
    fake = FakeWarehouse()
    with pytest.raises(PlanningError, match="order_band.yml"):
        api.plan(
            found, found.default, Connection(runner=fake), select="main.sales.orders"
        )
    assert fake.statements == []


# ---------------------------------------------------------------------------
# import
# ---------------------------------------------------------------------------


def test_import_writes_only_the_functions_a_mask_or_filter_names() -> None:
    def function(name: str) -> Function:
        return Function(
            name=name,
            parameters=(Parameter("x", Primitive("string")),),
            returns=Primitive("string"),
            body="'***'",
        )

    people = Table(
        name="main.sales.people",
        columns=(
            col("id", "bigint"),
            replace(col("email", "string"), mask=Mask("main.sales.mask_email")),
        ),
    )
    fake = FakeWarehouse.of(
        function("main.sales.mask_email"), function("main.sales.order_band"), people
    )
    found = api.import_schema(Connection(runner=fake), "main.sales")
    assert [spec.filename for spec in found] == ["people.yml", "mask_email.yml"]
    assert found.skipped == (
        (
            "main.sales.order_band",
            "a SQL function no column mask or row filter here names",
        ),
    )
