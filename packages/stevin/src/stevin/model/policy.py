"""An ABAC policy, as stevin reads one. Never as it writes one: it doesn't.

A policy is defined on a catalog, a schema or a table and reaches every table
below it, so a table can be filtered or masked by something no spec of its own
mentions. stevin reads the policies in scope of the tables it plans, so a
reviewer sees them beside the change — and leaves the writing of them to
Terraform or SQL (docs/DESIGN.md, Scope).

*In scope* is all `SHOW EFFECTIVE POLICIES` promises: the policy is defined on
the table or on a parent of it. Whether it resolves for a given reader depends
on the policy's conditions, the table's tags and who is asking, which
Databricks works out at query time.

References:
  SHOW POLICIES     https://docs.databricks.com/aws/en/sql/language-manual/sql-ref-syntax-aux-show-policies
  DESCRIBE POLICY   https://docs.databricks.com/aws/en/sql/language-manual/sql-ref-syntax-aux-describe-policy
  policies          https://docs.databricks.com/aws/en/data-governance/unity-catalog/abac/policies
"""

from __future__ import annotations

from dataclasses import dataclass

#: The two kinds that reach a table's data. `SHOW POLICIES` documents its
#: `Policy Type` as "for example, ROW_FILTER, COLUMN_MASK, or GRANT"; any other
#: is kept as the workspace spelled it, in lower case.
ROW_FILTER = "row_filter"
COLUMN_MASK = "column_mask"


@dataclass(frozen=True, slots=True)
class Policy:
    """One policy in scope of a table.

    `name`, `kind`, `on`, `level` and `comment` come from `SHOW EFFECTIVE
    POLICIES`; the rest from `DESCRIBE POLICY`, and is empty where that
    couldn't be read — describing a policy takes a privilege on the securable
    it is defined on, which a reader of the table needn't have.
    """

    name: str
    #: `row_filter`, `column_mask`, or whatever else the workspace calls it.
    kind: str
    #: The securable it is defined on, by its full name; empty for a metastore.
    on: str
    #: `catalog`, `schema`, `table` or `metastore`.
    level: str
    #: The function that filters or masks.
    function: str | None = None
    #: Who it applies to, and who is let off.
    to: tuple[str, ...] = ()
    except_: tuple[str, ...] = ()
    #: `WHEN …`: which tables it reaches, as the policy says it.
    when: str | None = None
    #: `MATCH COLUMNS …`: which columns, as the policy says it.
    match_columns: str | None = None
    #: `ON COLUMN …`: the matched column a mask is put on.
    on_column: str | None = None
    comment: str | None = None
