"""The live suite's table budget, without a workspace.

The live suite runs in a metastore that is somebody's own, and a run that makes
too many tables fills its quota for everyone. What keeps that from happening is
a counter, a budget and a check for room (`tests/table_budget.py`, called from
`tests/integration/conftest.py`). None of it can be tried against a workspace
without spending what it guards, so it is held to its word here: what counts as
creating a table, who is charged, when a session fails, and when it must not
start.
"""

from __future__ import annotations

import importlib.util
from dataclasses import replace
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from fake_warehouse import FakeWarehouse
from helpers import col, table
from stevin.executor import Executor
from stevin.history import DeltaHistory, MemoryHistory
from stevin.introspect import IntrospectionError, Introspector
from stevin.planning import plan_tables
from stevin.probes import PROBES, Bench, run
from table_budget import (
    FULL_BUDGET,
    SMOKE_BUDGET,
    Created,
    Ledger,
    budget_for,
    created,
    room,
)

# ---------------------------------------------------------------------------
# what counts as creating a table
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("statement", "found"),
    [
        ("CREATE TABLE main.s.t (id INT)", Created("main.s.t")),
        ("create table `main`.`s`.`t` (id int)", Created("main.s.t")),
        (
            "CREATE TABLE IF NOT EXISTS `main`.`s`.`runs` (\n  `id` STRING\n) USING X",
            Created("main.s.runs", guarded=True),
        ),
        (
            "CREATE OR REPLACE TABLE `main`.`s`.`t` AS\nSELECT 1 AS id",
            Created("main.s.t", replaces=True),
        ),
        ("REPLACE TABLE main.s.t (id INT)", Created("main.s.t", replaces=True)),
        ("CREATE TABLE main.s.t AS SELECT * FROM main.s.u", Created("main.s.t")),
        ("CREATE TABLE main.s.t LIKE main.s.u", Created("main.s.t")),
        ("CREATE TABLE main.s.t CLONE main.s.u", Created("main.s.t")),
        ("CREATE TABLE main.s.t DEEP CLONE main.s.u", Created("main.s.t")),
        (
            "CREATE OR REPLACE TABLE `main`.`s`.`t__backup` SHALLOW CLONE `main`.`s`.`t`",
            Created("main.s.t__backup", replaces=True),
        ),
        (
            "CREATE STREAMING TABLE main.s.st AS SELECT id FROM STREAM(main.s.t)",
            Created("main.s.st"),
        ),
        (
            "CREATE OR REFRESH STREAMING TABLE main.s.st AS SELECT 1 AS id",
            Created("main.s.st", replaces=True),
        ),
        (
            "CREATE MATERIALIZED VIEW main.s.mv AS SELECT id FROM main.s.t",
            Created("main.s.mv"),
        ),
        (
            "CREATE EXTERNAL TABLE main.s.t (id INT) LOCATION 's3://b'",
            Created("main.s.t"),
        ),
        (
            "  -- the orders\n/* twice */ CREATE TABLE main.s.t (id INT)",
            Created("main.s.t"),
        ),
        ("CREATE TABLE `main`.`s`.`Odd Name` (id INT)", Created("main.s.odd name")),
    ],
)
def test_a_statement_that_creates_a_table_is_found(
    statement: str, found: Created
) -> None:
    assert created(statement) == found


@pytest.mark.parametrize(
    "statement",
    [
        "CREATE VIEW main.s.v AS SELECT 1 AS id",
        "CREATE OR REPLACE VIEW main.s.v AS SELECT * FROM main.s.t",
        "CREATE FUNCTION main.s.f(x INT) RETURNS INT RETURN x + 1",
        "CREATE OR REPLACE FUNCTION main.s.f(x INT) RETURNS TABLE (id INT) RETURN x",
        "CREATE SCHEMA main.s",
        "CREATE SCHEMA IF NOT EXISTS `main`.`s`",
        "CREATE VOLUME IF NOT EXISTS main.s.landing",
        "CREATE POLICY p ON TABLE main.s.t ROW FILTER main.s.f TO `account users`",
        "CREATE TEMPORARY TABLE t (id INT)",
        # The words, and no table made.
        "GRANT CREATE TABLE ON SCHEMA `main`.`s` TO `account users`",
        "COMMENT ON TABLE main.s.t IS 'made with CREATE TABLE main.s.t (id INT)'",
        "SELECT 'CREATE TABLE main.s.t (id INT)' AS statement",
        "INSERT INTO main.s.log VALUES ('CREATE OR REPLACE TABLE main.s.t')",
        "-- CREATE TABLE main.s.t (id INT)\nSELECT 1",
        "ALTER TABLE main.s.t ADD COLUMNS (replace_table STRING)",
        "DESCRIBE TABLE main.s.create_table",
        "SHOW CREATE TABLE main.s.t",
        "DROP TABLE IF EXISTS main.s.t",
    ],
)
def test_a_statement_that_creates_no_table_is_not_counted(statement: str) -> None:
    assert created(statement) is None
    ledger = Ledger()
    assert ledger.record(statement) is False
    assert ledger.total == 0


# ---------------------------------------------------------------------------
# the ledger
# ---------------------------------------------------------------------------


def test_each_table_is_charged_to_the_test_that_was_running() -> None:
    ledger = Ledger()
    ledger.who = "test_live_apply.py::test_one"
    ledger.record("CREATE TABLE main.s.a (id INT)")
    ledger.record("CREATE OR REPLACE TABLE main.s.a AS SELECT 1 AS id")
    ledger.who = "test_live_seeds.py::test_two"
    with ledger.during("test_live_seeds.py (shared: countries)"):
        ledger.record("CREATE TABLE main.s.b (id INT)")
    ledger.record("SELECT * FROM main.s.b")
    assert ledger.who == "test_live_seeds.py::test_two", "the block hands the name back"
    assert ledger.spent == {
        "test_live_apply.py::test_one": 2,
        "test_live_seeds.py (shared: countries)": 1,
    }
    assert (ledger.total, ledger.replaced) == (3, 1)


def test_if_not_exists_is_counted_once_and_again_after_a_drop() -> None:
    """The history tables are asked for on every apply and made once. A table
    that was dropped in between is made again, and costs again."""
    ledger = Ledger()
    ask = "CREATE TABLE IF NOT EXISTS `main`.`s`.`runs` (`id` STRING) USING DELTA"
    assert [ledger.record(ask) for _ in range(3)] == [True, False, False]
    ledger.record("DROP TABLE IF EXISTS `main`.`s`.`runs`")
    assert ledger.record(ask) is True
    ledger.record("DROP SCHEMA `main`.`s` CASCADE")
    assert ledger.record(ask) is True
    ledger.record("DROP SCHEMA `main`.`s2` CASCADE")
    assert ledger.record(ask) is False, "another schema's drop is not this table's"
    assert ledger.total == 3


def test_the_report_names_the_ten_biggest_spenders_biggest_first() -> None:
    ledger = Ledger(budget=100)
    for index in range(12):
        ledger.who = f"test_{index:02d}"
        for copy in range(index + 1):
            ledger.record(f"CREATE TABLE main.s.t{index}_{copy} (id INT)")
    first, *spenders = ledger.report()
    assert first == "78 of a budget of 100 (0 replaced a table this run had made)"
    assert len(spenders) == 10
    assert spenders[0].split() == ["12", "test_11"]
    assert spenders[-1].split() == ["3", "test_02"]
    assert ledger.over() is None


def test_a_session_over_its_budget_fails_with_one_line() -> None:
    ledger = Ledger(budget=2)
    for name in ("a", "b"):
        ledger.record(f"CREATE TABLE main.s.{name} (id INT)")
    assert ledger.over() is None, "at the budget is within it"
    ledger.record("CREATE TABLE main.s.c (id INT)")
    said = ledger.over()
    assert said is not None and "\n" not in said
    assert "created 3 tables and may create 2" in said


def test_the_budgets_are_the_ones_the_docs_promise() -> None:
    """`docs/testing.md` and the workflow's comment say these numbers."""
    assert (FULL_BUDGET, SMOKE_BUDGET) == (60, 15)
    docs = (Path(__file__).parents[2] / "docs" / "testing.md").read_text("utf-8")
    assert f"at most **{FULL_BUDGET}** tables" in docs
    assert f"at most **{SMOKE_BUDGET}**" in docs


def test_only_a_selection_of_smoke_tests_gets_the_smoke_budget() -> None:
    assert budget_for([True, True]) == SMOKE_BUDGET
    assert budget_for([True, False]) == FULL_BUDGET
    assert budget_for([False]) == FULL_BUDGET
    assert budget_for([]) == FULL_BUDGET, "nothing selected is not a smoke run"


# ---------------------------------------------------------------------------
# what stevin's own statements cost, as the fake warehouse takes them
# ---------------------------------------------------------------------------


class Counting:
    """A runner in front of the fake that counts what succeeded, the way the
    live suite's runner does in front of a warehouse."""

    def __init__(self, fake: FakeWarehouse, ledger: Ledger) -> None:
        self.fake, self.ledger = fake, ledger

    def query(self, statement: str) -> tuple[dict[str, str | None], ...]:
        rows = self.fake.query(statement)
        self.ledger.record(statement)
        return rows


def test_a_rewrite_costs_the_table_its_staging_copy_and_the_replacement() -> None:
    ledger = Ledger()
    runner = Counting(FakeWarehouse(schemas={"main.sales"}), ledger)
    introspector = Introspector(runner)

    def apply(spec: Any) -> None:
        plan = plan_tables([spec], introspector, target="t", tool_version="0")
        assert Executor(runner, introspector, MemoryHistory()).apply(plan).ok

    orders = table(col("id", "bigint"), col("amount", "decimal(10,2)"))
    ledger.who = "create"
    apply(orders)
    ledger.who = "rewrite"
    apply(replace(orders, columns=(orders.columns[0], col("amount", "string"))))
    assert ledger.spent == {"create": 1, "rewrite": 2}
    assert ledger.replaced == 1, "the staging copy is new; the replacement is not"
    ledger.who = "nothing to do"
    apply(replace(orders, columns=(orders.columns[0], col("amount", "string"))))
    assert ledger.total == 3


def test_the_history_tables_cost_three_however_often_they_are_asked_for() -> None:
    class Taking:
        def query(self, statement: str) -> tuple[dict[str, str | None], ...]:
            ledger.record(statement)
            return ()

    ledger = Ledger()
    for _ in range(4):
        DeltaHistory(Taking(), "main.stevin").ensure()
    assert ledger.total == 3


def test_a_refused_statement_costs_nothing() -> None:
    ledger = Ledger()
    fake = FakeWarehouse(refusals={"CREATE TABLE": "QUOTA_EXCEEDED"})
    with pytest.raises(IntrospectionError):
        Counting(fake, ledger).query("CREATE TABLE `main`.`s`.`t` (id INT)")
    assert ledger.total == 0


def test_the_probes_ask_for_no_more_tables_than_the_docs_say() -> None:
    """Every probe, against a runner that takes everything and answers nothing:
    each goes as far as it can, and what it would create is on the record. A
    probe that needs an answer to go on stops short, so this is a floor under
    the real count and a ceiling on nothing — but a probe that starts making a
    table of its own again shows up here."""

    class Taking:
        def __init__(self) -> None:
            self.asked: list[str] = []

        def query(self, statement: str) -> tuple[dict[str, str | None], ...]:
            self.asked.append(statement)
            return ()

    taking = Taking()
    bench = Bench(taking, Introspector(taking), "main.scratch", recoverable=lambda: "m.r")
    list(run(bench, PROBES))
    tables = sorted({found.name for s in taking.asked if (found := created(s))})
    own = [name for name in tables if ".shared_" not in name]
    shared = [name.rsplit(".", 1)[1] for name in tables if ".shared_" in name]
    assert shared == [
        "shared_clustered",
        "shared_plain",
        "shared_policed",
        "shared_replaced",
        "shared_wide",
    ]
    assert len(own) <= 12, own


# ---------------------------------------------------------------------------
# is there room
# ---------------------------------------------------------------------------


def test_a_budget_that_fits_under_the_quota_is_room() -> None:
    assert room(46, 500, 60) is None
    assert room(440, 500, 60) is None, "exactly at the limit still fits"


def test_no_room_is_one_line_with_the_numbers() -> None:
    said = room(441, 500, 60)
    assert said is not None and "\n" not in said
    assert "an estimated 441 of 500" in said
    assert "may create 60 tables" in said
    assert "1 more than fit" in said
    assert "Nothing was created" in said
    # The day this was written for: 510 of 500, with 46 tables really there.
    assert room(510, 500, 15) is not None


# ---------------------------------------------------------------------------
# the live conftest's side of it: the runner that counts, and the quota read
# ---------------------------------------------------------------------------


@pytest.fixture
def live() -> ModuleType:
    """The live suite's conftest, loaded as a module: nothing in it touches a
    workspace until a fixture runs."""
    path = Path(__file__).parents[1] / "integration" / "conftest.py"
    spec = importlib.util.spec_from_file_location("live_conftest", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Quota:
    """A workspace client that only knows its metastore's table quota."""

    def __init__(self, counts: list[int] | None, limit: int = 500) -> None:
        self.counts, self.limit, self.reads = counts, limit, 0

    @property
    def metastores(self) -> Any:
        return self

    @property
    def resource_quotas(self) -> Any:
        return self

    def current(self) -> Any:
        return type("Assignment", (), {"metastore_id": "m-1"})()

    def get_quota(self, **_named: object) -> Any:
        if self.counts is None:
            raise PermissionError("no access to resource quotas")
        count = self.counts[min(self.reads, len(self.counts) - 1)]
        self.reads += 1
        info = type("Info", (), {"quota_count": count, "quota_limit": self.limit})()
        return type("Answer", (), {"quota_info": info})()


def test_the_run_starts_when_the_budget_fits(live: ModuleType) -> None:
    client = _Quota([46])
    runner = live.Counted(client, "w1")
    assert live.no_room(runner, 60) is None
    assert client.reads == 1


def test_the_run_does_not_start_when_it_does_not_fit(
    live: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    client = _Quota([510])
    said = live.no_room(live.Counted(client, "w1"), 15, wait_seconds=0)
    assert said is not None
    assert "510 of 500" in said and "Nothing was created" in said
    assert "the metastore counts 510 tables of 500" in capsys.readouterr().out


def test_a_recount_that_makes_room_lets_the_run_start(
    live: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reading the quota is what asks Unity Catalog to count again."""
    monkeypatch.setattr(live.time, "sleep", lambda _seconds: None)
    client = _Quota([510, 510, 120])
    assert live.no_room(live.Counted(client, "w1"), 60) is None
    assert client.reads == 3


def test_a_quota_that_cannot_be_read_says_so_and_goes_on(
    live: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    assert live.no_room(live.Counted(_Quota(None), "w1"), 60) is None
    said = capsys.readouterr().out
    assert "could not read the metastore's table quota" in said
    assert "no access to resource quotas" in said
    assert "going on" in said


class _Warehouse:
    """A workspace client whose warehouse takes a statement or fails it."""

    def __init__(self, *, fails: bool = False) -> None:
        self.fails = fails

    @property
    def statement_execution(self) -> Any:
        return self

    def execute_statement(self, **_named: object) -> Any:
        from databricks.sdk.service.sql import StatementState

        state = StatementState.FAILED if self.fails else StatementState.SUCCEEDED
        error = type("Error", (), {"message": "QUOTA_EXCEEDED"})() if self.fails else None
        status = type("Status", (), {"state": state, "error": error})()
        return type(
            "Response",
            (),
            {"statement_id": "01ef", "status": status, "manifest": None, "result": None},
        )()


def test_the_suites_runner_counts_what_succeeded(
    live: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    ledger = Ledger()
    ledger.who = "the test that was running"
    monkeypatch.setattr(live, "LEDGER", ledger)
    took = live.Counted(_Warehouse(), "w1")
    took.query("CREATE TABLE `main`.`s`.`t` (id INT)")
    took.query("CREATE VIEW `main`.`s`.`v` AS SELECT 1 AS id")
    with pytest.raises(IntrospectionError, match="QUOTA_EXCEEDED"):
        live.Counted(_Warehouse(fails=True), "w1").query(
            "CREATE TABLE `main`.`s`.`u` (id INT)"
        )
    assert ledger.spent == {"the test that was running": 1}
