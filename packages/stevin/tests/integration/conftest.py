"""Fixtures for the live suite.

Every test here runs against a real workspace in a schema created for the run and
dropped afterwards. Without credentials the whole suite skips, so a fork, a
laptop and CI all stay green.

Credentials come from the Databricks SDK's unified auth — DATABRICKS_HOST and a
token, a `~/.databrickscfg` profile named by DATABRICKS_CONFIG_PROFILE, OAuth.
Also set DATABRICKS_WAREHOUSE_ID, and optionally STEVIN_TEST_CATALOG (default
`main`): every test creates and drops its own schema there.

**A run has a table budget.** The metastore the suite runs in is somebody's own,
and its table quota is counted with an estimate that only comes down slowly
(`tests/table_budget.py` says why). So every statement goes through one runner
that counts the tables it creates, the session prints the total and its biggest
spenders and fails when it is over the budget, and it does not start at all
when the budget does not fit under the quota. A test that only reads a table
shares one with the others in its module (`shared_schema`); a test that changes
a table's shape, or must start from nothing, gets a schema of its own
(`schema`).
"""

from __future__ import annotations

import os
import time
import uuid
from collections.abc import Generator, Iterator
from contextlib import contextmanager

import pytest

from stevin.introspect import Introspector, Row, WarehouseRunner
from stevin.sql import quote_ident, quote_qualified
from table_budget import Ledger, budget_for, room

#: What this session has created so far. One for the whole session: the budget
#: is the session's.
LEDGER = Ledger()


class Counted(WarehouseRunner):
    """The suite's runner: a `WarehouseRunner` that counts the tables it makes.

    Everything a live test sends goes through the `runner` fixture — a test's
    own statements, stevin's apply, the history tables, a probe — so this is
    the one place a table can be counted, with the test that was running.
    """

    def query(self, statement: str) -> tuple[Row, ...]:
        rows = super().query(statement)
        # After it succeeded: a refused statement created nothing.
        LEDGER.record(statement)
        return rows


def pytest_collection_finish(session: pytest.Session) -> None:
    """Pick the budget from what was selected: `smoke` alone has a smaller one."""
    LEDGER.budget = budget_for(
        item.get_closest_marker("smoke") is not None
        for item in session.items
        if item.get_closest_marker("integration") is not None
    )


def pytest_runtest_logstart(nodeid: str) -> None:
    LEDGER.who = nodeid.removeprefix("tests/integration/")


@pytest.hookimpl(wrapper=True)
def pytest_fixture_setup(
    fixturedef: pytest.FixtureDef[object], request: pytest.FixtureRequest
) -> Generator[None, object, object]:
    """Charge what a shared fixture creates to the fixture, not to whichever
    test happened to ask for it first."""
    if fixturedef.scope == "function":
        return (yield)
    module = request.node.nodeid.removeprefix("tests/integration/") or "session"
    with LEDGER.during(f"{module} (shared: {fixturedef.argname})"):
        return (yield)


def pytest_terminal_summary(terminalreporter: pytest.TerminalReporter) -> None:
    if not LEDGER.total:
        return
    terminalreporter.section("tables this run created")
    for line in LEDGER.report():
        terminalreporter.write_line(line)
    if over := LEDGER.over():
        terminalreporter.write_line(over, red=True, bold=True)


def pytest_sessionfinish(session: pytest.Session) -> None:
    """A run over its budget fails, whatever its tests did."""
    if LEDGER.over() and session.exitstatus == pytest.ExitCode.OK:
        session.exitstatus = pytest.ExitCode.TESTS_FAILED


@pytest.fixture(scope="session")
def warehouse_id() -> str:
    value = os.environ.get("DATABRICKS_WAREHOUSE_ID")
    if not value:
        pytest.skip("DATABRICKS_WAREHOUSE_ID is not set")
    return value


@pytest.fixture(scope="session")
def catalog() -> str:
    return os.environ.get("STEVIN_TEST_CATALOG", "main")


@pytest.fixture(scope="session")
def runner(warehouse_id: str) -> WarehouseRunner:
    from databricks.sdk import WorkspaceClient

    # Not a check for DATABRICKS_HOST: a profile is just as good, and requiring
    # the variable would skip the whole suite for anyone who uses one.
    try:
        client = WorkspaceClient()
    except Exception as error:  # the SDK raises ValueError when nothing is configured
        pytest.skip(f"no Databricks workspace configured: {error}")
    return Counted(client, warehouse_id)


#: How long a test schema may live before it can only be a leak. A schema a
#: module shares lives as long as the module runs, and the whole suite is given
#: 90 minutes by its workflow.
STALE_AFTER = "2 HOURS"


@pytest.fixture(scope="session", autouse=True)
def sweep(runner: WarehouseRunner, catalog: str) -> None:
    """Drop the schemas a killed run left behind, then see that there is room.

    Every test drops its own schema when it finishes, but a cancelled CI run
    never gets to. What is left keeps its tables, and Unity Catalog counts those
    against the metastore's quota (500 by default), so a few cancelled runs are
    enough to make every later run fail with QUOTA_EXCEEDED. This sweeps them
    first.
    https://docs.databricks.com/aws/en/data-governance/unity-catalog/index.html

    Then, before any test creates anything, the quota is read. When this run's
    budget does not fit under it the whole session stops, with one error that
    says the numbers: sixty-eight tests failing one by one on the 501st table
    said the same thing less clearly, and left the metastore full.
    """
    try:
        stale = runner.query(
            f"SELECT schema_name FROM {quote_ident(catalog)}."
            "information_schema.schemata WHERE schema_name LIKE 'stevin_it_%' "
            f"AND created < current_timestamp() - INTERVAL {STALE_AFTER}"
        )
    except Exception as error:  # noqa: BLE001 - a sweep must never fail the suite
        print(f"could not look for stale test schemas: {error}")
        stale = ()
    for row in stale:
        name = row["schema_name"]
        if not name:
            continue
        print(f"dropping the stale test schema {catalog}.{name}")
        try:
            runner.query(f"DROP SCHEMA {quote_qualified(f'{catalog}.{name}')} CASCADE")
        except Exception as error:  # noqa: BLE001
            print(f"  could not drop it: {error}")
    full = no_room(runner, LEDGER.budget)
    if full is not None:
        # Not a failure of anything this suite tests, and every table it makes
        # would fail the same way: say it once, clearly, and stop the session.
        pytest.exit(full, returncode=pytest.ExitCode.TESTS_FAILED)


def quota(runner: WarehouseRunner) -> tuple[int, int] | None:
    """The metastore's table quota as `(estimate, limit)`, or None when this
    workspace or this principal can't say.

    Reading it is also what asks Unity Catalog to count again: "Unity Catalog
    updates the quota count only during resource creation. The count might be
    out of date if only delete operations have been performed."
    https://docs.databricks.com/aws/en/data-governance/unity-catalog/resource-quotas
    """
    metastore = runner.client.metastores.current().metastore_id
    if metastore is None:
        return None
    found = runner.client.resource_quotas.get_quota(
        parent_securable_type="metastore",
        parent_full_name=metastore,
        quota_name="table-quota",
    ).quota_info
    if found is None or found.quota_count is None or found.quota_limit is None:
        return None
    return found.quota_count, found.quota_limit


def no_room(
    runner: WarehouseRunner, budget: int, *, wait_seconds: float = 30
) -> str | None:
    """Why this run must not start, or None when its budget fits or nobody can say.

    The quota count only goes up by itself, so a suite that creates and drops
    hundreds of tables in a day meets QUOTA_EXCEEDED on a metastore that is
    nearly empty: 510 of 500, with 46 tables actually there. A read triggers a
    recount, and the recount is asynchronous — counts are "accurate to within
    30 minutes of the last create operation" — so this reads a few times before
    it gives up. When the quota cannot be read at all, it says so and the run
    goes on: a workspace that won't tell is not a reason to test nothing.
    """
    deadline = time.monotonic() + wait_seconds
    while True:
        try:
            found = quota(runner)
        except Exception as error:  # noqa: BLE001 - a read must never fail the suite
            found, why = None, str(error)
        else:
            why = "the workspace gave no count"
        if found is None:
            print(
                f"could not read the metastore's table quota ({why}): going on "
                f"without knowing whether {budget} more tables fit"
            )
            return None
        estimate, limit = found
        print(
            f"the metastore counts {estimate} tables of {limit}; "
            f"this run may create {budget}"
        )
        full = room(estimate, limit, budget)
        if full is None or time.monotonic() > deadline:
            return full
        time.sleep(10)


@contextmanager
def scratch_schema(
    runner: WarehouseRunner, catalog: str, *, keeps_dropped: bool = False
) -> Generator[str]:
    """A schema of the suite's own, dropped with everything in it.

    Dropped is not gone: a dropped table stays recoverable with `UNDROP` for
    seven days by default, and it still counts against the metastore's table
    quota while it does — which is how a metastore holding 46 tables comes to
    refuse the 501st. A test's tables are worth nothing a second after it ends,
    so unless `keeps_dropped`, the schema keeps none of them.
    https://docs.databricks.com/aws/en/sql/language-manual/sql-ref-syntax-ddl-undrop-table
    """
    name = f"stevin_it_{uuid.uuid4().hex[:8]}"
    full = f"{catalog}.{name}"
    runner.query(f"CREATE SCHEMA {quote_qualified(full)}")
    if not keeps_dropped:
        try:
            runner.query(
                f"ALTER SCHEMA {quote_qualified(full)} SET RETAIN DROPPED TO 0 HOURS"
            )
        except Exception as error:  # noqa: BLE001 - older workspaces may not have it
            print(f"could not turn off the recovery period for {full}: {error}")
    try:
        yield full
    finally:
        runner.query(f"DROP SCHEMA {quote_qualified(full)} CASCADE")


@pytest.fixture
def schema(runner: WarehouseRunner, catalog: str) -> Iterator[str]:
    """An empty schema for one test, dropped when the test finishes.

    For a test that changes a table's shape or has to start from nothing. A
    test that only reads asks for `shared_schema`, and makes fewer tables.
    """
    with scratch_schema(runner, catalog) as full:
        yield full


@pytest.fixture(scope="module")
def shared_schema(runner: WarehouseRunner, catalog: str) -> Iterator[str]:
    """One schema for a whole module, dropped when the module finishes.

    Where the tables several tests only read are made once, by a module-scoped
    fixture that asks for this. Whatever a test puts here it names for itself,
    because the others see it: nothing in a shared schema may depend on which
    test ran first, so `-k` on one test finds what it needs.
    """
    with scratch_schema(runner, catalog) as full:
        yield full


@pytest.fixture
def recoverable_schema(runner: WarehouseRunner, catalog: str) -> Iterator[str]:
    """A schema that keeps what it drops — for the one test about `UNDROP`.

    The other schemas turn the recovery period off, so the suite stops filling
    the metastore's table quota with tables nobody can see. `UNDROP` is the one
    thing that needs that period, so this schema keeps the default seven days:
    it makes one table, in a full run.
    """
    with scratch_schema(runner, catalog, keeps_dropped=True) as full:
        yield full


@pytest.fixture
def introspector(runner: WarehouseRunner) -> Introspector:
    return Introspector(runner)
