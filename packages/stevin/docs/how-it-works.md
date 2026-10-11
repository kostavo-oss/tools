# How it works

How stevin gets from a spec to a plan and from a plan to a change. For how to use it,
start at [Writing a spec](spec.md) and [Commands](cli.md); what it promises a user is
the [safety model](safety.md).

## The pipeline

```
spec (YAML, SQL) ────┐
                     ├─> differ ─> changes ─> planner ─> plan ─> renderer
live (Unity Catalog) ┘                                    │
                                                          └─> executor ─> history
```

1. **Specs are read** into the model by `loader.py`, which validates by hand so that
   every error names its file, line and column. A `.sql` spec is read by `sqlspec.py`
   with sqlglot, into the same model. Variables such as `${catalog}` are filled in per
   target. A shape may come from a data contract (`contract.py`), and targets from a
   Databricks Asset Bundle (`bundle.py`, which asks the Databricks CLI).
2. **Live state is read** into the same model by `introspect.py`: `information_schema`
   per schema, and per table `DESCRIBE DETAIL` and `SHOW CREATE TABLE`, the second for
   identity, generated and default columns. Only the tables a spec describes are read
   in full, several at a time, and for those also the ABAC policies in scope. The other
   tables of a schema get a light read: enough to list them and see whose they are.
3. **The differ** (`differ.py`) is a pure function from a desired and a live object to
   changes. A change says what differs and not how to fix it. What the live object has
   and the spec does not mention is not a change: it is reported as unmanaged.
4. **`planning.py`** sees both sides at once. It refuses two specs for one name, orders
   the objects so that each comes after what it names, and decides what happens to the
   live tables no spec describes.
5. **The planner** (`planner.py`) is a pure function from changes to ordered steps. It
   writes the SQL, gives every step a risk class, and puts what a change needs first in
   a step of its own. What it needs to know about a live table is handed to it.
6. **`render/`** shows the one plan object in a terminal, as Markdown for a pull-request
   comment, as JSON, and as one HTML page that `stevin ui` serves on localhost.
7. **The executor** (`executor.py`) runs a plan's steps on a SQL warehouse, through the
   Statement Execution API, and `history.py` records the run.

Three things change a workspace and nothing else does: the executor changes the objects
a plan names, `history.py` writes stevin's own three tables, and `stevin verify`
(`probes.py`) makes and drops a scratch schema. Each of the fifteen commands is a
function in `stevin.api`; `cli.py` parses arguments and prints.

## The model

Frozen, slotted dataclasses that hold tuples, in `src/stevin/model/`.

```text
DataType = Primitive | Decimal | Char | Varchar | Array | Map | Struct
Field(name, type, nullable, comment, tags, mask, identity, generated, default)
Table(name, columns, comment, cluster_by, cluster_auto, partitioned_by, properties,
      tags, constraints, grants, row_filter)
Relation = Table | View | Function | Schema | Volume
```

A column is a `Field` at the top level. A field and a table also carry what only a spec
can say, which does not count when two are compared: `renamed_from`, `using`, a seed,
an owner, what to remove, and the contract a shape comes from. A `Policy` is an ABAC
policy as it was read; it is never written.

## What a plan holds

A plan is data: every rendering, the plan file and `apply` use the same object.

- A **change** has a `table`, a `kind` such as `add_column`, a `path`, and `before` and
  `after`. A path follows Databricks' nested syntax: `address.zip` in a struct,
  `lines.element.sku` in an array, `m.key` and `m.value` in a map.
- A **step** is one statement: `id`, `table`, `title`, `risk`, the `change` it
  implements, `path`, `sql`, a `precheck` with its `refusal`, a `postcheck` with its
  `failure`, `est_bytes`, `undo_hint`, `warnings` and a `note`. A step stevin could not
  write has no `sql`, and its note says what it needs.
- A **table's diff** has its changes and steps, the `desired` and the `live` object,
  the facts read about the live table (properties, size, Delta version, table features,
  policies in scope), what is `unmanaged` on it, `notes` and `cautions`.
- A **plan** has `tool_version`, `target`, `spec_hash`, `state_fingerprint`, `diffs`,
  `steps`, `unmanaged_tables`, `orphaned_tables`, `owned_tables` and `not_managed`.

The state fingerprint is a digest of every live object the plan was made from, with the
policies in scope of each. Any difference makes the plan stale. The plan file is the
plan as JSON, with every planned object written out, also one that does not change:
`apply` computes the fingerprint again over the same objects.

## How ownership is known

There is no state file. That stevin made a table or a view is a property on it,
`deltaplan.managed = true`, set by the statement that creates it.

| The live table | What a plan does |
|---|---|
| Has a spec and the marker | Diffs it. |
| Has a spec and no marker | Plans a claim, a step that sets the marker, and diffs it. |
| No spec, no marker | Reports it as unmanaged. Never touches it. |
| No spec, the marker, an `additive` schema | Reports it as orphaned. It stays. |
| No spec, the marker, a `strict` schema | Plans a `DROP`, a destructive step. |
| Another tool owns it | Reports it as theirs, whatever marker it has. |

A schema's mode is in `stevin.yml`: a `schemas:` map, then the target's `mode`, then
`additive`. Who owns a table is known from `owned_elsewhere:`, from a dbt manifest, and
from dlt's `_dlt_loads` and `_dlt_version` tables in a schema (`owned.py`):
[whose tables are whose](spec.md#whose-tables-are-whose). Schemas, volumes and
functions carry no marker, so they are never dropped.

## What apply does

1. It refuses a plan with a destructive step unless told `--allow-destructive`, and a
   plan with a step that has no SQL.
2. With a history schema it looks for an unfinished run of the same plan and takes the
   lock for the target, with a conditional `UPDATE` that it confirms by reading back.
3. It reads again every object the plan was made from, and on a fresh run refuses when
   the fingerprint differs. A resumed run skips that check and the steps that are done.
4. For each step: it skips the step when its change is already true of the live object,
   renews the lock, records the table's Delta version before a rewrite or a destructive
   step, runs the precheck, the statement and the postcheck, and records the outcome.
5. It stops at the first step that fails, and releases the lock.

The history is three Delta tables in the `history_schema` a project names: `runs`
(`run_id`, `plan_hash`, `target`, `user`, `tool_version`, `status`, `started_at`,
`ended_at`), `steps` (`run_id`, `step_id`, `table_name`, `sql`, `status`, `started_at`,
`ended_at`, `error`, `delta_version_before`) and `lock` (`id`, `holder`, `acquired_at`,
`expires_at`). [Without a history schema](safety.md#without-a-history-schema) there is
no lock, no resume and no record.

What must be true of all this, with the tests that hold it, is in
[RULES.md](https://github.com/kostavo-oss/tools/blob/main/packages/stevin/RULES.md), and
why in
[DECISIONS.md](https://github.com/kostavo-oss/tools/blob/main/packages/stevin/DECISIONS.md).
