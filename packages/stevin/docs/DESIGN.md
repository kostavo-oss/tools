# stevin — design

`stevin` (designed under the working name `deltaplan`). Declarative, Terraform-style `plan` / `apply` for Databricks SQL (Unity Catalog, Delta) tables.

This is the design the tool was built from, kept as it was written. Where the code has
since gone another way, the sentence is corrected in place and marked **(since)**; what
the design never had is listed in [Since the design](#since-the-design) at the end.

## Goals

- Desired state in YAML → diff against live Unity Catalog → reviewable plan → safe apply.
- Rich plan output: per table, per column, nested struct changes as a tree, numbered steps, risk labels, size/cost hints.
- Delta-aware planning: knows which changes are metadata-only, which need a table feature, which need a rewrite.
- Safe by default: never touches what it does not manage, never destroys without an explicit flag.
- Free, Python-native, Apache-2.0. Fits next to Databricks Asset Bundles and CI.

## Scope (2026-10-09)

**(since)** Settled by the owner on 2026-10-09: stevin puts in place
the tables and access that your transformation tool doesn't own. dbt, Lakeflow or SQLMesh
own what they build. stevin owns what they read and what they leave to a setup job: the
tables notebooks and external systems write into, lookup tables, and who may see what —
grants, column masks, row filters and ABAC policies. It never touches what another tool
built, and it runs at deploy time from CI (a lely step or the Action), never as a job.

What that means for the shape of the tool:

- **Stays:** managed Delta tables (the engine), schemas, managed volumes, seeds, `using:`
  backfills, grants, tags, owner, properties, column masks, row filters, `import`,
  `adopt`, `drift`, `plan --clone`, the history and lock tables, the Action, bundle
  targets, `manage:`, SQL specs, `ui`.
- **Leaves in 0.4.0:** views, pre/post `hooks:`, and SQL functions as a thing of their
  own — a function spec stays valid only when a column mask, a row filter or a policy
  names it. These were the parts that made stevin a second transformation tool. Each
  removal is a pull request of its own after this note; the changelog says what a user
  has to do.
- **Comes:** ABAC policies as a spec kind (`policy:`), additive like masks and filters,
  built only after a live probe with a governed tag holds; and an *owned elsewhere* map
  — a list in `stevin.yml`, dbt's manifest, and dlt's own `_dlt_*` tables in a schema —
  so `plan` refuses a spec that would *shape* what another tool builds, and `drift`
  names the owner. A spec for such a table may still say who may see it — tags,
  grants, masks, row filters, owner — and stevin puts that in place without ever
  claiming or reshaping the table. That is how PII in dlt's landing tables and dbt's
  models is governed without a post-hook or a setup job.
- **Seeds stay on one condition:** they have never run on a workspace. They pass the
  live suite before 0.4.0, or they leave with it.

Not in this scope, and not planned: catalogs; external tables; governed-tag definitions
(account-level — Terraform's); groups and service principals; ABAC `GRANT`/`DENY`
policies, metastore- and table-level policies; rules about who may have what, approvals,
a policy engine; quality checks, SLAs or data contracts; materialized views and streaming
tables (reported as their pipeline's, never managed); detecting a Lakeflow pipeline's
tables; SQLMesh beyond the owned-elsewhere list; a bundle job task or a notebook entry
point.

## Non-goals (v1)

- Views, grants, masks, row filters, volumes, functions (later milestones). **(since)**
  All of these are built: views, grants, column masks, row filters, SQL functions,
  schemas and managed volumes are specs like tables are. **Changed 2026-10-09, by the
  owner:** views and standalone SQL functions leave again in 0.4.0; grants, masks, row
  filters, schemas and volumes stay. See [Scope](#scope-2026-10-09).
- Data backfills beyond simple pre/post SQL hooks. **(since)** A `using:` expression
  backfills a new `NOT NULL` column, and a `seed:` loads reference data; anything
  larger still belongs in a pipeline. **Changed 2026-10-09, by the owner:** the hooks
  leave in 0.4.0; `using:` and `seed:` stay, seeds on the condition in
  [Scope](#scope-2026-10-09).
- ~~Parsing SQL DDL as the source of truth.~~ **Changed 2026-09-18, by the owner:**
  a spec may be a `.sql` `CREATE` statement, parsed with sqlglot into the same model
  as YAML. SQL specs support exactly what sqlglot parses into structure; YAML stays
  the complete format. See `docs/formats.md` and `stevin.features`.
- Non-Delta formats.

## Pipeline

```
spec (YAML) ─┐
             ├─> differ ─> changes ─> planner ─> plan (JSON) ─> renderer
live (UC) ───┘                                        │
                                                      └─> executor ─> history
```

1. **Loader** — YAML → frozen dataclasses. Validation at this edge only. Variables per target (`${catalog}`). **(since)** Not Pydantic or msgspec: a hand-written validator over the YAML node tree, so every error carries `file:line:column`. A `.sql` spec is read by `sqlspec.py` (sqlglot) into the same model.
2. **Introspector** — live state from `information_schema`, `DESCRIBE DETAIL`, `DESCRIBE HISTORY` and `SHOW CREATE TABLE` into the same dataclasses. Type strings are parsed into the type tree. **(since)** `DESCRIBE TABLE EXTENDED` is not used; identity, generated and default columns are read from `SHOW CREATE TABLE`, because `information_schema.columns` doesn't report them.
3. **Differ** — pure function `(desired, actual) -> list[Change]`.
4. **Planner** — pure function `list[Change] -> Plan`. Expands changes into ordered steps, inserts prerequisite steps, classifies risk, resolves dependencies.
5. **Renderer** — Rich CLI, Markdown (PR comments), JSON. All from the same plan object. **(since)** And HTML: one page, served on localhost by `stevin ui`.
6. **Executor** — runs steps on a SQL warehouse (Statement Execution API via `databricks-sdk`). Precheck → SQL → postcheck → history row. **(since)** The per-step precheck and postcheck queries became `differ.is_applied()`, which asks the model whether a change is already true of the live table; `precheck` survives as a precondition guard (`SET NOT NULL` on a column that still holds nulls).

Differ and planner do no I/O. Everything outside loader, introspector and executor must be unit-testable without a workspace.

## Domain model

Frozen, slotted dataclasses. Tuples, not lists, so everything is hashable.

```python
DataType = Primitive | Decimal | Array | Map | Struct

Primitive(name)
Decimal(precision, scale)
Array(element, contains_null=True)
Map(key, value)
Struct(fields: tuple[Field, ...])
Field(name, type, nullable=True, comment=None, renamed_from=None)  # hints: compare=False

Column  = Field at top level
Table(name, columns, comment, cluster_by, properties, tags, constraints)
```

**(since)** A table also carries grants, a row filter, an owner, partitioning, a seed and
hooks, and a column a mask, an identity, a generation expression or a default. Beside
`Table` there are `View`, `Function`, `Schema` and `Volume`; `Relation` is any of the five.
**(2026-10-09)** `View` and the hooks leave in 0.4.0, a `Policy` comes, and `Function`
stays for what masks, filters and policies name.

- **Change** (semantic, rendered): `path` (e.g. `address.element.zip`), `kind`, `before`, `after`.
- **Step** (executable): `id`, `sql`, `risk`, `precheck`, `postcheck`, `est_bytes`, `undo_hint`.
- **Plan**: tool version, target, spec hash, state fingerprint, changes, steps.

Paths follow Databricks nested syntax: struct `a.b`, array `a.element.b`, map `m.key` / `m.value`.

## Spec format

```yaml
table: ${catalog}.sales.orders
comment: Order facts
cluster_by: [order_date]
tags: {domain: sales}
properties:
  delta.enableChangeDataFeed: "true"
columns:
  - name: order_id
    type: bigint
    nullable: false
  - name: customer_ref
    type: string
    renamed_from: cust_id
  - name: address
    type:
      struct:
        - {name: street, type: string}
        - {name: zip, type: string}
constraints:
  - primary_key: [order_id]
```

- Types accepted as string (`struct<street:string,zip:string>`) or nested YAML. Nested form allows per-field comments and `renamed_from`.
- `renamed_from` is ignored once the old name is gone and the new one exists; `validate` warns that it can be removed.
- Unknown keys are an error.

## Ownership

There is no state file; Unity Catalog is the state.

- Tables created by the tool get the property `deltaplan.managed = true`.
- Only managed tables can ever become drop candidates.
- Anything else is reported as **unmanaged** and left untouched.
- Per-schema mode: `additive` (never drop, default) or `strict`. **(since)** `stevin.yml` has a per-schema `schemas:` map, and a target's `mode` is the default for schemas it doesn't list.
- `import` generates specs from existing tables and marks them managed on first apply.
- Features seen on a live table that the model does not cover are shown as "unmanaged feature, left untouched" — never diffed away.

## Step classification

| Class | Examples | Behaviour |
|---|---|---|
| `meta` | add column, comment, tags, properties, constraints, add nested field | Runs directly |
| `feature` | rename/drop column → column mapping; int→bigint → type widening | Planner inserts `SET TBLPROPERTIES` step; warns about streaming readers |
| `rewrite` | incompatible type change, kind change (struct→array), partitioning | `CREATE OR REPLACE TABLE … AS SELECT`; shows table size; records restore point. **(since)** Staged in two statements — the converted data into a staging table, then the table replaced from it — so the expensive step can be repeated and checked before the table is touched |
| `destructive` | drop column, drop table | Requires `--allow-destructive` |

Nested-field rules to verify against current Databricks docs and encode as tests: add nested field (meta), rename/drop nested (feature), widen nested (feature), reorder (meta, opt-in diff), `SET NOT NULL` on nested (unsupported → rewrite or error), map key change (rewrite).

> **Verified live (2026-09-19), two of these differ:** `SET NOT NULL` and `DROP NOT NULL` on a struct's field are ordinary `ALTER`s (meta), and a map key widens in place like any other field — only a key change that isn't a widening is a rewrite. `tests/integration/test_live_assumptions.py` and `test_live_round_trip.py` hold the evidence.

## Failure model

DDL is not transactional across statements. No rollback promise.

- Every step is idempotent via precheck/postcheck. **(since)** Via `differ.is_applied()`, as above.
- `apply` resumes from the history table.
- Before any rewrite: record Delta version (`delta_version_before`) so `RESTORE` is one command. Optional `SHALLOW CLONE`.
- Stale plan protection: `apply` recomputes the state fingerprint and refuses if it differs.

## History and locking

Delta tables in a dedicated schema (configurable).

- `runs`: run_id, plan_hash, target, user, tool_version, status, started_at, ended_at
- `steps`: run_id, step_id, table, sql, status, started_at, ended_at, error, delta_version_before
- `lock`: conditional `UPDATE … WHERE holder IS NULL`, check affected rows. TTL + `force-unlock`. **(since)** The update is confirmed by reading the row back rather than by its affected-row count, and it also takes a lock whose TTL has run out. `apply` takes the lock before it checks the plan is not stale.

**(since)** The history schema is optional. A project that names none applies anyway: no lock, no resume, no record, and the restore points are on the run's result instead.

## CLI

```
stevin validate            # spec lint, no connection needed
stevin import <schema>     # live tables -> YAML specs
stevin plan -t <target> [-o plan.json] [--format rich|md|json]
stevin apply plan.json [--allow-destructive]
stevin drift -t <target>   # exit code != 0 on drift, for CI
stevin force-unlock
```

**(since)** Thirteen commands. The six above, and:

```
stevin apply [-t <target>]   # no plan file: plan, show, ask, run
stevin show plan.json        # render a saved plan, no warehouse
stevin ui [plan.json]        # the plan as a page on localhost
stevin adopt [<name>…]       # drift, written back into the spec files
stevin doctor                # check the setup; changes nothing
stevin verify --schema <s>   # run the Databricks assumptions in a scratch schema
stevin schema spec|project   # the JSON Schema editors use
stevin version
```

`plan`, `apply`, `ui` take `--select`; `plan`, `show` and `drift` also render `html`;
`drift` exits 2 on drift and 1 on failure. [Commands](cli.md) is the reference.

## Plan output (target look)

```
sales.orders   ~ update  (412 GB)
  ~ amount  DECIMAL(10,2) → (18,2)
    1. enable typeWidening        [feature]
    2. ALTER COLUMN TYPE          [meta]
  ~ address
    + zip STRING
    3. ADD COLUMN address.zip     [meta]
  → customer_ref (was cust_id)
    4. enable columnMapping       [feature]
       ⚠ breaks streaming readers
    5. RENAME COLUMN              [meta]
  - legacy_flag
    6. DROP COLUMN                [destructive]

Plan: 0 add, 1 change, 0 destroy · 6 steps · 0 rewrites · 1 warning
```

## Testing

- Unit: differ and planner with golden plan snapshots. No workspace needed.
- Integration: real workspace, ephemeral schema per run, nightly in CI. Marked `@pytest.mark.integration`, skipped without credentials.
- Every discovered Databricks limitation becomes a test.

**(since)** Two layers sit between those: a fake warehouse that interprets stevin's own
SQL, so plan → apply → re-plan is asserted offline, and transcripts of what a workspace
answered, replayed offline (built; none recorded yet). The Databricks assumptions are a
list of probes (`probes.py`) that the live suite and `stevin verify` both run.
[Testing](testing.md) says what each layer proves.

## Milestones

1. **Read-only**: domain model, type parser, loader, introspector, differ, planner (classification only), Rich renderer, `validate`, `import`, `plan`.
2. **Apply (meta)**: executor, history, locking, fingerprint check, resume.
3. **Feature + rewrite**: prerequisite steps, rewrites, restore points, `--allow-destructive`.
4. **CI**: Markdown renderer, GitHub Action, `drift`.
5. **Governance**: tags on columns, masks, row filters, grants, views.

Open-source after milestone 1.

**(since)** All five are built.

## Stack

Python ≥ 3.11 · uv · src layout · typer + rich · databricks-sdk · PyYAML · pytest (+ syrupy for snapshots) · ruff · pyright · GitHub Actions · Apache-2.0.

**(since)** `ty` instead of pyright, `sqlglot` for SQL specs, and `mise` to pin Python and uv.

## Since the design

What the tool has that this page never planned, a line each. The user-facing pages are
the reference for all of it.

- **A project file.** `stevin.yml`: targets with their variables, profile, warehouse and
  mode, where the specs are, the history schema, and `manage:` — what the project
  leaves to another tool.
- **SQL specs.** A spec may be a `CREATE` statement in a `.sql` file. It supports exactly
  what sqlglot parses into structure; YAML is the complete format ([formats](formats.md)).
- **More than tables.** Views, SQL functions, schemas and managed volumes; grants,
  column tags, masks, row filters and owners. Functions, schemas and volumes are never
  dropped: nothing on them records that stevin made them. **(2026-10-09)** Views and
  standalone functions leave in 0.4.0 — see [Scope](#scope-2026-10-09).
- **One order over the objects.** Functions, tables and views are planned as one graph,
  each after what it names; a cycle is an error, found at `validate`. Two specs for one
  name are an error too. **(2026-10-09)** With views gone the graph is functions and
  tables.
- **Asset Bundles.** A project can take its targets and variables from a
  `databricks.yml`, resolved by asking the Databricks CLI. What a bundle declares is the
  bundle's: stevin doesn't create or manage it ([bundles](bundles.md)).
- **Seeds, hooks and backfills.** Reference data kept beside the spec; SQL before and
  after an apply; `using:` to fill a new required column. **(2026-10-09)** The hooks
  leave in 0.4.0.
- **The way back.** `adopt` writes live state into the spec file that describes it, by
  editing the YAML text, so comments and `${var}` survive.
- **Ownership claims.** A spec for a table stevin didn't create plans a visible claim
  before anything else.
- **A library.** Every command is a function in `stevin.api`; `import stevin` is a
  supported way in ([as a library](sdk.md)).
- **A GitHub Action**, a JSON Schema for editors, `doctor`, `verify`, and the `ui` page.
- **The name.** Built and first released as `deltaplan`; `stevin` from 0.3.0a1. The
  names written onto tables — `deltaplan.managed`, `deltaplan.seed` and the two
  suffixes — did not change.
