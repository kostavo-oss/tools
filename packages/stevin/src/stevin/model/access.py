"""Who may see a table, and through what — as stevin reads it. Never written.

Three things decide what a reader gets from a table, and they are kept in three
places: the privileges granted on it or on a parent of it, what narrows a read
(the table's row filter, its column masks, the ABAC policies in scope), and the
owner. `Access` holds the three for one table, so they can be read top to
bottom.

It is a list of what is granted and what is in scope. `LIMITS` says what that
leaves out, and goes wherever the report goes.

References:
  table_privileges  https://docs.databricks.com/aws/en/sql/language-manual/information-schema/table_privileges
  privileges        https://docs.databricks.com/aws/en/data-governance/unity-catalog/manage-privileges/privileges
"""

from __future__ import annotations

from dataclasses import dataclass

from stevin.model.policy import Policy
from stevin.model.table import RowFilter
from stevin.model.types import Mask

#: Where a privilege is granted, nearest first.
LEVELS = ("table", "schema", "catalog")

#: What the report is, and what it is not. Printed under it, and in its JSON.
LISTS = "This lists what is granted and what is in scope. It does not:"
LIMITS = (
    "evaluate a policy's condition for a given reader",
    "resolve who is in a group",
    "run a query as someone else",
    "list USE CATALOG and USE SCHEMA, which a reader needs as well",
)


@dataclass(frozen=True, slots=True)
class Held:
    """One privilege a principal holds on a table, and where it is granted."""

    principal: str
    privilege: str
    #: `table` for the table's own; `schema` or `catalog` for an inherited one.
    #: Anything else is what the workspace said, in lower case.
    level: str
    #: The securable it is granted on, by its full name; empty where the
    #: workspace named a level stevin doesn't know.
    on: str

    @property
    def inherited(self) -> bool:
        return self.level != "table"


@dataclass(frozen=True, slots=True)
class Access:
    """What is granted on one table, what narrows a read of it, and its owner."""

    table: str
    owner: str | None = None
    grants: tuple[Held, ...] = ()
    row_filter: RowFilter | None = None
    #: Each masked column, and its mask.
    masks: tuple[tuple[str, Mask], ...] = ()
    #: The ABAC policies in scope: defined on the table or on a parent of it.
    policies: tuple[Policy, ...] = ()
    #: Why they couldn't be read, in the workspace's words. None when they
    #: were read.
    policies_unread: str | None = None

    @property
    def principals(self) -> tuple[str, ...]:
        """Everyone a privilege is granted to, by name."""
        return tuple(sorted({held.principal for held in self.grants}))

    def held_by(self, principal: str) -> tuple[tuple[str, str, tuple[str, ...]], ...]:
        """One principal's privileges, by where each is granted, nearest first:
        `(level, on, privileges)`."""
        found: dict[tuple[str, str], list[str]] = {}
        for held in self.grants:
            if held.principal == principal:
                found.setdefault((held.level, held.on), []).append(held.privilege)
        return tuple(
            (level, on, tuple(sorted(set(privileges))))
            for (level, on), privileges in sorted(
                found.items(), key=lambda item: (_rank(item[0][0]), item[0])
            )
        )

    @property
    def narrowed(self) -> bool:
        """Whether anything read here narrows what a reader sees."""
        return bool(self.row_filter or self.masks or self.policies)


def _rank(level: str) -> int:
    return LEVELS.index(level) if level in LEVELS else len(LEVELS)
