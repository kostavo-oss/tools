# Why not Liquibase or Flyway

Liquibase and Flyway are the tools most teams know for changing a database from git.
Both work with Databricks. So the fair question before you pick stevin is why you would
not use one of them. This page answers it, and says when you should.

## Two ways to change a table

**A migration tool runs the steps you wrote.** You write each change as a file: a
changeset in Liquibase, a versioned script in Flyway. The tool runs the files in order
and writes down which ones ran, in a table of its own: `DATABASECHANGELOG` for
Liquibase, `flyway_schema_history` for Flyway. The next run skips what is written down.

**stevin works out the steps.** You write what the table should be. stevin reads what
the table is in Unity Catalog, compares the two and plans the `ALTER` statements that
close the gap.

The same change, a new column, in both:

=== "Liquibase"

    ```yaml
    databaseChangeLog:
      - changeSet:
          id: 42
          author: you
          changes:
            - addColumn:
                tableName: orders
                columns:
                  - column: {name: region, type: string}
    ```

=== "stevin"

    ```yaml
    table: ${catalog}.sales.orders
    columns:
      - {name: order_id, type: bigint, nullable: false}
      - {name: region, type: string}    # the new line
    ```

The first file is a step. The second is the table. That difference is small on the day
you write it and large a year later.

## What follows from it

- **A migration tool knows what it ran, not what is there.** Its record is a list of
  files. When a notebook writes with `mergeSchema` and adds a column, or someone gives a
  grant by hand, the record still says everything is in order. Both tools have a way
  to compare a database with an earlier picture of it, but that is a separate command
  you have to run and read.
  stevin has no record to go stale: every plan starts from the live table, and
  [`stevin drift`](cli.md#drift) lists what was changed outside git.
- **A table that already exists needs a baseline.** A migration tool starts from an
  empty history, so a table that was made before the tool arrived has to be written up
  or marked as done. In stevin, [`stevin import`](cli.md#import) writes a spec for each
  table, and that spec is the whole adoption.
- **The steps are yours to get right.** A rename on a Delta table needs column mapping
  switched on first. A change from `int` to `bigint` needs type widening. A struct that
  becomes an array needs the table rebuilt. A migration tool runs what you wrote, so
  knowing this is your job, for every change, in every script. stevin plans each as its
  own numbered step and labels it: metadata only, a rewrite, or destructive.
- **Nothing tells a safe step from a costly one.** To a migration tool every statement
  is a statement. stevin says before it runs which steps rebuild the table and how big
  the table is, and refuses a step that destroys data unless you pass
  `--allow-destructive`. [The safety model](safety.md) has the list.
- **Access is raw SQL.** Grants, tags, column masks and row filters have no change type
  of their own in either tool, so they are `GRANT` and `ALTER` statements you write, and
  write again to take back. In a stevin spec they are part of the table: add a line and
  the plan grants, remove it and the plan shows what is left unmanaged.
- **Every environment replays the whole history.** A new catalog gets every step since
  the first, including the three that undid each other. A spec makes the table as it is
  meant to be now.
- **It is another runtime.** Both tools run on Java. That is nothing in a Java shop and
  one more thing to install and patch next to a Python stack. stevin is a Python package
  and a single command.

## What Liquibase and Flyway do on Databricks

Checked in their documentation on 2026-10-12. Both move fast, so read their pages
before you decide.

| | Liquibase | Flyway |
|---|---|---|
| Databricks support | An open-source extension and a commercial one | Named as *Databricks Lakehouse (Unity Catalog)*, with the advanced features in preview |
| Its own record | `DATABASECHANGELOG` | `flyway_schema_history` |
| Delta-specific steps | `optimizeTable`, `vacuumTable`, `analyzeTable`, `alterTableProperties` and more; volumes, `cloneTable` and `restoreTable` in the commercial one | Plain SQL scripts |
| Grants, tags, masks, row filters | Not among the change types: written as SQL | Written as SQL |

Liquibase's own page lists what it does not support on Databricks, such as
`addUniqueConstraint` and `createSequence`, and notes that a generated changelog leaves
out a table's format and partition columns.

## When a migration tool is the better choice

stevin is narrow on purpose, and there is real work it will not do.

- **You need to change data, not only shape.** Fixing rows, splitting a column with
  logic of your own, loading data as part of a release: a migration tool runs any SQL
  in order. stevin runs no SQL of yours around a change. It has a `using:` expression
  to fill a new column, and that is all.
- **You manage more than Databricks.** One tool and one way of working across Postgres,
  SQL Server and Databricks is worth a lot. stevin knows Unity Catalog and nothing else.
- **You need a signed-off list of every statement.** Some audits want each change as a
  numbered, reviewed, immutable file. That is what a changeset is. stevin keeps a
  [history](cli.md#history) of every run and every statement it sent, but the reviewed
  thing is the spec and the plan, not a script.
- **You want views, functions and procedures as code.** stevin keeps views for access
  and the functions a mask or a row filter names. General SQL objects belong to your
  transformation tool or to a migration tool.
- **Your team already runs one and it works.** A tool people know beats a tool that is
  better on paper.

## Together

The two do not exclude each other. A team can keep a migration tool for data fixes and
one-off scripts and give stevin the tables' shape and access. What does not work is two
tools changing the same table's columns: the migration tool's record and the live table
drift apart on the first stevin apply. Pick one owner per table, as
[next to other tools](next-to-other-tools.md) says for every other pair.

## In one line

Use a migration tool when the steps are what you want to review. Use stevin when the
table is.
