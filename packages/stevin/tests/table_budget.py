"""What a live run costs a workspace in tables, counted as the suite sends them.

Unity Catalog allows a metastore a number of tables (500 by default) and counts
them with an estimate that goes up when a table is created and comes down
later: a dropped table is not taken off at once. A suite that makes a hundred
tables a run therefore fills a metastore that holds almost nothing, and then
nobody can create a table in it, the owner included.
https://docs.databricks.com/aws/en/data-governance/unity-catalog/resource-quotas

So the live suite has a budget. Every statement it sends goes through one
runner, and this counts the ones that create a table, by the test that sent
them. The session says the total at its end and fails when it is over the
budget; before it starts it reads the metastore's estimate and does not start
when the budget would not fit.

Nothing here talks to a workspace: `tests/integration/conftest.py` does that
and calls this, and `tests/unit/test_table_budget.py` holds it to its word.
"""

from __future__ import annotations

import re
from collections.abc import Generator, Iterable
from contextlib import contextmanager
from dataclasses import dataclass, field

#: The most tables a full live run may create. A reading of the suite counts 59.
FULL_BUDGET = 60

#: The most a run of only the `smoke` tests may create. A reading counts 13.
SMOKE_BUDGET = 15

_PART = r"(?:`(?:[^`]|``)+`|[A-Za-z_][A-Za-z0-9_]*)"
_NAME = rf"{_PART}(?:\s*\.\s*{_PART})*"

#: A statement that makes a table, a streaming table or a materialized view.
#: Anchored at the start: a statement that only contains the words (a comment,
#: a literal, `GRANT CREATE TABLE ON SCHEMA`) is not one.
_CREATES = re.compile(
    r"(?:CREATE\s+(?P<replace>OR\s+REPLACE\s+|OR\s+REFRESH\s+)?(?:EXTERNAL\s+)?"
    r"(?:TABLE|MATERIALIZED\s+VIEW|STREAMING\s+TABLE)"
    r"|(?P<bare>REPLACE)\s+TABLE)"
    rf"\s+(?P<guard>IF\s+NOT\s+EXISTS\s+)?(?P<name>{_NAME})",
    re.IGNORECASE,
)
_DROPS_TABLE = re.compile(
    rf"DROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?(?P<name>{_NAME})", re.IGNORECASE
)
_DROPS_SCHEMA = re.compile(
    rf"DROP\s+(?:SCHEMA|DATABASE)\s+(?:IF\s+EXISTS\s+)?(?P<name>{_NAME})", re.IGNORECASE
)
_LEADING_COMMENT = re.compile(r"\s*(?:--[^\n]*(?:\n|$)|/\*.*?\*/)", re.DOTALL)


@dataclass(frozen=True, slots=True)
class Created:
    """One statement that creates a table: which table, and how it says so."""

    name: str
    #: `CREATE OR REPLACE` or `REPLACE`: a table of that name may be there.
    replaces: bool = False
    #: `IF NOT EXISTS`: creates nothing when the table is there.
    guarded: bool = False


def _bare(statement: str) -> str:
    """The statement without the comments and the space in front of it."""
    while found := _LEADING_COMMENT.match(statement):
        statement = statement[found.end() :]
    return statement.lstrip()


def _named(name: str) -> str:
    """A name the way two spellings of it compare equal."""
    return re.sub(r"\s*\.\s*", ".", name).replace("`", "").casefold()


def created(statement: str) -> Created | None:
    """The table a statement creates, or None when it creates none.

    Counted: `CREATE TABLE` in every form (`AS SELECT`, `LIKE`, `CLONE`,
    `SHALLOW CLONE`), `CREATE OR REPLACE TABLE`, `REPLACE TABLE`, a streaming
    table and a materialized view. Not counted: a view, a function, a schema, a
    volume, a policy, a temporary table, and any statement that only mentions
    one of these.
    """
    found = _CREATES.match(_bare(statement))
    if found is None:
        return None
    return Created(
        _named(found["name"]),
        replaces=bool(found["replace"] or found["bare"]),
        guarded=bool(found["guard"]),
    )


@dataclass(slots=True)
class Ledger:
    """What a session has spent so far, and who spent it.

    `who` is the test that is running: the conftest sets it. A statement is
    recorded after it succeeded, so a refused `CREATE TABLE` costs nothing here,
    as it costs nothing there.
    """

    budget: int = FULL_BUDGET
    who: str = "before the first test"
    spent: dict[str, int] = field(default_factory=dict)
    #: Of the total, the statements that replaced a table this session made.
    #: Whether Unity Catalog counts those is not known, so they are counted.
    replaced: int = 0
    _made: set[str] = field(default_factory=set)

    def record(self, statement: str) -> bool:
        """Count a statement that ran. True when it created a table."""
        text = _bare(statement)
        if dropped := _DROPS_TABLE.match(text):
            self._made.discard(_named(dropped["name"]))
            return False
        if dropped := _DROPS_SCHEMA.match(text):
            inside = _named(dropped["name"]) + "."
            self._made = {name for name in self._made if not name.startswith(inside)}
            return False
        found = created(text)
        if found is None:
            return False
        known = found.name in self._made
        if found.guarded and known:
            # `CREATE TABLE IF NOT EXISTS` for a table this session made: the
            # history tables are asked for on every apply and made once.
            return False
        if found.replaces and known:
            self.replaced += 1
        self._made.add(found.name)
        self.spent[self.who] = self.spent.get(self.who, 0) + 1
        return True

    @contextmanager
    def during(self, who: str) -> Generator[None]:
        """Charge what is created in this block to `who`: a shared fixture."""
        before, self.who = self.who, who
        try:
            yield
        finally:
            self.who = before

    @property
    def total(self) -> int:
        return sum(self.spent.values())

    def biggest(self, count: int = 10) -> list[tuple[str, int]]:
        """The biggest spenders, the biggest first; ties in the order they ran."""
        return sorted(self.spent.items(), key=lambda entry: -entry[1])[:count]

    def over(self) -> str | None:
        """The one line that fails a session, or None when it kept to its budget."""
        if self.total <= self.budget:
            return None
        return (
            f"over the table budget: this run created {self.total} tables and may "
            f"create {self.budget}. Cut what the biggest spenders make, or raise "
            "the budget in tests/table_budget.py and say why."
        )

    def report(self) -> list[str]:
        """What a session prints at its end."""
        lines = [
            f"{self.total} of a budget of {self.budget} "
            f"({self.replaced} replaced a table this run had made)"
        ]
        lines += [f"{count:4d}  {who}" for who, count in self.biggest()]
        return lines


def budget_for(smoke: Iterable[bool]) -> int:
    """The budget of a selection: the smoke budget when every live test in it
    is a smoke test, the full one otherwise. `-k` on one test gets the full
    budget, because nothing says how much one test may make."""
    flags = list(smoke)
    return SMOKE_BUDGET if flags and all(flags) else FULL_BUDGET


def room(estimate: int, limit: int, budget: int) -> str | None:
    """Why a run must not start, or None when its budget fits.

    `estimate` is the metastore's own count, which is what a `CREATE TABLE` is
    refused by: it can be far above what the catalogs hold.
    """
    if estimate + budget <= limit:
        return None
    return (
        f"no room for a live run: the metastore's table quota stands at an "
        f"estimated {estimate} of {limit}, and this run may create {budget} "
        f"tables, which is {estimate + budget - limit} more than fit. Nothing was "
        "created. Unity Catalog takes dropped tables off its estimate later: "
        "wait for it to come down."
    )
