"""The seven steps of issue #17, run the way a host program runs them.

Load, resolve, read, connect, plan, apply, ask about drift — with nothing
private, nothing copied out of the CLI, and no subprocess. If any of this needs
an underscore, the SDK is missing something.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import stevin
from fake_warehouse import FakeWarehouse
from stevin.connect import Connection
from stevin.history import MemoryHistory

PROJECT = """\
specs: [tables]
history_schema: main.stevin
targets:
  dev:
    default: true
    vars: {catalog: main}
"""

ORDERS = """\
table: ${catalog}.sales.orders
comment: Order facts
columns:
  - {name: order_id, type: bigint, nullable: false}
  - {name: amount, type: "decimal(18,2)"}
"""


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    (tmp_path / "tables").mkdir()
    (tmp_path / "stevin.yml").write_text(PROJECT)
    (tmp_path / "tables" / "orders.yml").write_text(ORDERS)
    return tmp_path


@pytest.fixture
def fake() -> FakeWarehouse:
    warehouse = FakeWarehouse()
    warehouse.schemas.add("main.sales")
    return warehouse


def test_a_host_plans_and_applies_with_public_names_only(
    project_dir: Path, fake: FakeWarehouse
) -> None:
    project = stevin.Project.find(project_dir / "tables")
    target = project.resolve(project.default)
    connection = Connection(runner=fake)

    plan = stevin.plan(project, target, connection)
    assert not plan.empty
    assert plan.summary.add == 1
    assert plan.highest_risk == "meta"
    assert not plan.is_destructive

    [diff] = plan.diffs
    assert (diff.kind, diff.action) == ("table", "create")
    assert [step.title for step in diff.steps] == ["CREATE TABLE orders"]
    assert diff.risk == "meta"

    run = stevin.apply(
        plan, connection, project=project, target=target, history=MemoryHistory()
    )
    assert run.ok
    assert stevin.plan(project, target, connection).empty, "and it converged"


def test_a_host_can_ask_whether_its_plan_still_holds(
    project_dir: Path, fake: FakeWarehouse
) -> None:
    project = stevin.Project.find(project_dir)
    target = project.resolve(project.default)
    connection = Connection(runner=fake)
    plan = stevin.plan(project, target, connection)
    assert stevin.is_stale(plan, connection) is False

    # Someone else gets there first.
    stevin.apply(
        plan, connection, project=project, target=target, history=MemoryHistory()
    )
    assert stevin.is_stale(plan, connection) is True
    with pytest.raises(stevin.StalePlan) as raised:
        stevin.apply(
            plan, connection, project=project, target=target, history=MemoryHistory()
        )
    assert raised.value.tables == ("main.sales.orders",)


def test_a_destructive_plan_says_what_it_would_destroy(
    project_dir: Path, fake: FakeWarehouse
) -> None:
    project = stevin.Project.find(project_dir)
    target = project.resolve(project.default)
    connection = Connection(runner=fake)
    stevin.apply(
        stevin.plan(project, target, connection),
        connection,
        project=project,
        target=target,
        history=MemoryHistory(),
    )
    # The column goes; the plan that drops it needs saying so out loud.
    (project_dir / "tables" / "orders.yml").write_text(
        "table: ${catalog}.sales.orders\ncomment: Order facts\n"
        "columns:\n  - {name: order_id, type: bigint, nullable: false}\n"
    )
    plan = stevin.plan(project, target, connection)
    assert plan.is_destructive
    with pytest.raises(stevin.DestructiveRefused) as raised:
        stevin.apply(
            plan, connection, project=project, target=target, history=MemoryHistory()
        )
    assert raised.value.tables == ("main.sales.orders",)


def test_select_takes_names_as_well_as_a_predicate(
    project_dir: Path, fake: FakeWarehouse
) -> None:
    (project_dir / "tables" / "customers.yml").write_text(
        "table: ${catalog}.sales.customers\ncolumns:\n  - {name: id, type: bigint}\n"
    )
    project = stevin.Project.find(project_dir)
    target = project.resolve(project.default)
    connection = Connection(runner=fake)
    only = stevin.plan(project, target, connection, select="main.sales.orders")
    assert [diff.table for diff in only.diffs] == ["main.sales.orders"]
    by_predicate = stevin.plan(
        project, target, connection, select=lambda name: name.endswith("customers")
    )
    assert [diff.table for diff in by_predicate.diffs] == ["main.sales.customers"]


@pytest.fixture
def two_tables(project_dir: Path) -> stevin.Project:
    (project_dir / "tables" / "customers.yml").write_text(
        "table: ${catalog}.sales.customers\ncolumns:\n  - {name: id, type: bigint}\n"
    )
    return stevin.Project.find(project_dir)


@pytest.mark.parametrize(
    ("select", "planned"),
    [
        ("orders", ["main.sales.orders"]),
        ("sales.orders", ["main.sales.orders"]),
        ("MAIN.Sales.Orders", ["main.sales.orders"]),
        ("sales.cust*", ["main.sales.customers"]),
        (["orders", "customers"], ["main.sales.customers", "main.sales.orders"]),
        ("sales.*", ["main.sales.customers", "main.sales.orders"]),
    ],
)
def test_select_reads_names_the_way_the_command_line_does(
    two_tables: stevin.Project,
    fake: FakeWarehouse,
    select: str | list[str],
    planned: list[str],
) -> None:
    """The bug: `select="orders"` matched nothing here — only a full name did —
    and came back as an empty plan, where `--select orders` plans the table."""
    target = two_tables.resolve(two_tables.default)
    plan = stevin.plan(two_tables, target, Connection(runner=fake), select=select)
    assert sorted(diff.table for diff in plan.diffs) == planned


@pytest.mark.parametrize("select", ["ordrs", ["orders", "sales.nope*"]])
def test_a_selection_that_matches_nothing_raises(
    two_tables: stevin.Project, fake: FakeWarehouse, select: str | list[str]
) -> None:
    """A typo is not an empty plan: 'nothing to do' would be believed."""
    target = two_tables.resolve(two_tables.default)
    connection = Connection(runner=fake)
    with pytest.raises(stevin.PlanningError, match="matches no spec"):
        stevin.plan(two_tables, target, connection, select=select)
    with pytest.raises(stevin.PlanningError, match="matches no spec"):
        stevin.drift(two_tables, target, connection, select=select)
    with pytest.raises(stevin.PlanningError, match="matches no spec"):
        stevin.adopt(two_tables, target, connection, select=select)
    assert fake.statements == [], "said before the workspace is asked anything"


def test_a_predicate_is_taken_as_it_is(
    two_tables: stevin.Project, fake: FakeWarehouse
) -> None:
    """A host that selects with its own function has its own idea of a match,
    and of what matching nothing means."""
    target = two_tables.resolve(two_tables.default)
    plan = stevin.plan(
        two_tables, target, Connection(runner=fake), select=lambda _name: False
    )
    assert plan.empty


def test_drift_is_the_same_question_asked_differently(
    project_dir: Path, fake: FakeWarehouse
) -> None:
    project = stevin.Project.find(project_dir)
    target = project.resolve(project.default)
    connection = Connection(runner=fake)
    assert not stevin.drift(project, target, connection).empty
    stevin.apply(
        stevin.plan(project, target, connection),
        connection,
        project=project,
        target=target,
        history=MemoryHistory(),
    )
    assert stevin.drift(project, target, connection).empty


def test_validate_needs_no_workspace(project_dir: Path) -> None:
    project = stevin.Project.find(project_dir)
    assert stevin.validate(project, project.default) == ()


def test_apply_without_a_history_schema_just_applies(
    project_dir: Path, fake: FakeWarehouse
) -> None:
    """A project that records nothing still changes tables — and says what it
    could be put back to."""
    (project_dir / "stevin.yml").write_text(
        PROJECT.replace("history_schema: main.stevin\n", "")
    )
    project = stevin.Project.find(project_dir)
    target = project.resolve(project.default)
    connection = Connection(runner=fake)
    plan = stevin.plan(project, target, connection)
    run = stevin.apply(plan, connection, project=project, target=target)
    assert run.ok
    assert "main.sales.orders" in fake.tables
    assert not [name for name in fake.schemas if "stevin" in name], (
        "no bookkeeping schema was made"
    )
    # And it converges: a second apply of a fresh plan has nothing to do.
    assert stevin.plan(project, target, connection).empty


def test_a_plan_survives_being_written_and_read(
    project_dir: Path, fake: FakeWarehouse
) -> None:
    """A host may plan here and apply there; `diff.steps` must survive it."""
    project = stevin.Project.find(project_dir)
    target = project.resolve(project.default)
    plan = stevin.plan(project, target, Connection(runner=fake))
    again = stevin.plan_from_json(stevin.plan_to_json(plan))
    assert [d.table for d in again.diffs] == [d.table for d in plan.diffs]
    assert [s.title for s in again.diffs[0].steps] == ["CREATE TABLE orders"]


def test_a_host_can_import_a_schema_without_writing_anything(
    fake: FakeWarehouse,
) -> None:
    """`import_schema` hands back specs as text; where they go is the host's."""
    fake.schemas.add("main.sales")
    fake.query(
        "CREATE TABLE IF NOT EXISTS `main`.`sales`.`orders` (\n"
        "  `order_id` BIGINT NOT NULL,\n  `amount` DECIMAL(18,2)\n)\nUSING DELTA"
    )
    found = stevin.import_schema(Connection(runner=fake), "main.sales")
    assert [spec.filename for spec in found] == ["orders.yml"]
    [spec] = found.specs
    assert "table: main.sales.orders" in spec.text
    assert spec.relation.name == "main.sales.orders"
    # An owner is a person, not a shape: imported specs leave it out.
    assert "owner:" not in spec.text


def test_import_leaves_out_what_another_tool_manages(fake: FakeWarehouse) -> None:
    fake.schemas.add("main.sales")
    fake.query(
        "CREATE TABLE IF NOT EXISTS `main`.`sales`.`orders` (\n"
        "  `id` BIGINT\n)\nUSING DELTA"
    )
    fake.query("ALTER TABLE `main`.`sales`.`orders` SET TAGS ('domain' = 'sales')")
    handed_over = stevin.Manage(("tags",))
    [spec] = stevin.import_schema(
        Connection(runner=fake), "main.sales", manage=handed_over
    ).specs
    assert "tags:" not in spec.text


def test_a_schema_is_named_catalog_dot_schema(fake: FakeWarehouse) -> None:
    with pytest.raises(stevin.PlanningError, match="catalog.schema"):
        stevin.import_schema(Connection(runner=fake), "sales")


def test_the_databricks_cli_is_found_where_the_sdk_looks(tmp_path: Path) -> None:
    """`DATABRICKS_CLI_PATH` first, then `PATH` — a mise shim is why."""
    real = tmp_path / "databricks"
    real.write_text("#!/bin/bash\nexit 0\n")
    real.chmod(0o755)
    assert stevin.find_cli(environ={"DATABRICKS_CLI_PATH": str(real)}) == str(real)
    assert stevin.find_cli(environ={"PATH": ""}) is None
