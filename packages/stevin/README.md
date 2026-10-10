# stevin

**Safe plan/apply migrations for Unity Catalog tables and schemas.**
Describe the tables you want in YAML or SQL, see what it takes to get a live catalog
there — which changes are free, which rewrite 400 GB, which destroy something — and
then apply it.

[![ci](https://github.com/kostavo-oss/tools/actions/workflows/ci.yml/badge.svg)](https://github.com/kostavo-oss/tools/actions/workflows/ci.yml)
[![Docs](https://img.shields.io/badge/docs-stevin-1f9e9a.svg)](https://kostavo-oss.github.io/tools/stevin/)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](https://github.com/kostavo-oss/tools/blob/main/packages/stevin/LICENSE)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

Every workspace has tables that nobody's pipeline owns: the table a notebook appends
to, the lookup table, the table another system writes into. Someone made each once, with
a `CREATE TABLE` in a notebook, and changing one is another notebook, run by hand, once
per environment. stevin keeps those tables, and the access around them, as specs in git:
a change is a plan in a pull request, and a change made by hand shows up as drift.

> **Status: alpha.** Every milestone in the design is built — plan, apply (rewrites
> included), drift, the GitHub Action, and governance (tags, grants, masks, row filters,
> views). On `main` and in no release yet: tables another tool owns are reported as
> theirs (`owned_elsewhere`, dbt's manifest, dlt's schemas), a governance-only spec says
> who may see such a table, and a table's shape can come from an ODCS data contract
> (`from_contract`). SQL hooks and standalone SQL functions are removed on `main` and
> leave with 0.4.0 — the
> [changelog](https://github.com/kostavo-oss/tools/blob/main/packages/stevin/CHANGELOG.md) says why and
> what to do. It is tested offline against a fake warehouse, and a live suite
> runs what it assumes about Databricks against a real workspace. That suite has settled
> most of those assumptions and not all of them: loading reference data (`seed:`) has
> never run on a workspace, for one.
> [How it is tested](https://kostavo-oss.github.io/tools/stevin/testing/) says what each layer
> proves and lists what is still open, and `stevin verify` runs the same assumptions in a
> workspace of your own. Try it on a dev catalog before production.

## Named after

Simon Stevin (1548–1620), engineer and mathematician: he designed sluices and introduced
decimal notation. Precision before action — which is what a plan is.

Up to 0.2.0a4 stevin was called `deltaplan`. That command and a `deltaplan.yml` still
work — [coming from deltaplan](https://kostavo-oss.github.io/tools/stevin/installation/#coming-from-deltaplan)
says what changed and what didn't.

## Install

```sh
uvx --prerelease allow stevin --version      # run it once, nothing installed
uv tool install --prerelease allow stevin    # or keep it
```

Every release so far is a pre-release, which installers skip unless asked — hence the
flag. `pip install --pre stevin` works too.

## Quickstart

```sh
mkdir crm-tables && cd crm-tables
stevin import main.crm    # a spec per table, and a stevin.yml with one target
stevin plan               # what it would do; nothing is touched
stevin apply              # the same plan — shown, asked about, then run
```

Then change a table by editing its spec, and `stevin apply` again.
**[Get started →](https://kostavo-oss.github.io/tools/stevin/getting-started/)** is those ten
minutes on your own workspace, every step shown;
**[the tour →](https://kostavo-oss.github.io/tools/stevin/tour/)** takes one project from
nothing to a reviewed pull request. The [docs](https://kostavo-oss.github.io/tools/stevin/)
have the spec format, the commands and the safety model, and
[`docs/DESIGN.md`](https://github.com/kostavo-oss/tools/blob/main/packages/stevin/docs/DESIGN.md) is the
source of truth.

## What it is for

- **The tables and access your transformation tool doesn't own.** dbt, Lakeflow or
  SQLMesh own what they build. stevin owns what they read and what they leave to a
  setup job: the tables notebooks and external systems write into, lookup tables,
  filtered views, and who may see what — grants, column masks, row filters. It never
  touches what another tool built —
  [where the line is, per tool](https://kostavo-oss.github.io/tools/stevin/next-to-other-tools/)
  and [three access recipes](https://kostavo-oss.github.io/tools/stevin/access-recipes/)
  — and it runs from CI at deploy time, or
  [from a job](https://kostavo-oss.github.io/tools/stevin/running-from-a-job/) where
  CI can't reach the workspace.
- **What another tool owns stays theirs.** `stevin.yml` says which tables another tool
  owns (`owned_elsewhere:`), a dbt `manifest.json` says it for dbt, and a schema that
  holds dlt's `_dlt_loads` and `_dlt_version` tables is dlt's. A plan reports those
  tables as theirs — "dbt's", "dlt's", "the data-science team's" — and not as
  unmanaged. A spec for a table dbt builds is refused.
- **Access for a table stevin doesn't make.** A governance-only spec has no column
  types: it puts tags, grants, a row filter, an owner and column masks on a table dlt
  or a notebook team makes, and says nothing about its shape. The table is never
  claimed, reshaped or dropped.
- **A table's shape from a data contract.** `from_contract:` points a spec at an
  [ODCS](https://bitol-io.github.io/open-data-contract-standard/) contract. The columns,
  types, keys and descriptions come from the contract, and the spec adds what a contract
  doesn't say: clustering, properties, grants, a row filter, masks —
  [how a contract is read](https://kostavo-oss.github.io/tools/stevin/spec/#shape-from-a-data-contract).
- **Unity Catalog is the state.** There is no state file to store, lock or repair.
  stevin reads the live catalog — `information_schema` and the tables' own definitions —
  every time it plans, and the one thing it has to remember, that it made a table, is a
  property on that table.
- **Plans that know there is data in the table.** A change is an `ALTER TABLE` wherever
  Delta allows one, never a drop and a recreate. The plan says which changes are
  metadata-only, which need a table feature switched on first (a rename needs column
  mapping), and which rebuild the table — with its size, and with the data, the
  identity and the history kept.
- **Destructive changes are flagged, never implied.** Dropping a column or a table is a
  step marked `destructive`, and `apply` refuses it without `--allow-destructive`. Only
  tables stevin made can ever be dropped; everything else in the schema is reported as
  unmanaged and left alone. A plan that has gone stale is refused.
- **Next to an Asset Bundle, if you have one.** Your `databricks.yml` already has the
  targets, the workspaces, the variables and often the schema. stevin asks the
  Databricks CLI what they resolve to, names things the way a deploy would, and leaves
  what the bundle declares to the bundle —
  [details](https://kostavo-oss.github.io/tools/stevin/bundles/). Without a bundle, a
  `stevin.yml` says the same things.

Also: nested types are first class — struct, array and map fields diff by path
(`address.element.zip`), renames and comments included — and the plan is a data
structure, so the terminal, the pull-request comment and the JSON file all show the
same one.

## The spec

```yaml
table: ${catalog}.sales.orders
comment: Order facts
cluster_by: [order_date]
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
```

Or as SQL — the same model, read with [sqlglot](https://github.com/tobymao/sqlglot):

```sql
CREATE TABLE ${catalog}.sales.customers (
  customer_id BIGINT NOT NULL,
  name        STRING,
  CONSTRAINT customers_pk PRIMARY KEY (customer_id)
)
CLUSTER BY AUTO;
```

A project can mix both. SQL specs support what sqlglot can parse; YAML supports
everything — [the list](https://kostavo-oss.github.io/tools/stevin/formats/) says which.

## The plan

![A stevin plan: a rename, a widening, a backfilled NOT NULL column, a nested field, a CHECK and a grant, each with its numbered, risk-labelled steps](https://kostavo-oss.github.io/tools/stevin/assets/screens/tour-plan-change.svg)

## Why not Terraform?

Terraform is the right tool for the platform — workspaces, catalogs, warehouses,
permissions — and stevin doesn't try to be it. Tables are a different kind of thing,
because a table holds data.

- **Replace means drop.** When Terraform can't change something in place it replaces
  the resource: destroy, then create. For a cluster that costs a restart; for a managed
  table it costs the rows. stevin has no replace. A change is an `ALTER`, or a rebuild
  that keeps the data, or — when it really is a drop — a step that says `destructive`
  and won't run until you allow it.
- **The catalog is the only copy of the truth.** Terraform keeps a state file, and a
  table that already exists has to be imported into it before Terraform will manage it.
  stevin has none: it reads Unity Catalog every time, a table somebody altered by hand
  shows up as drift, and adopting an existing table is writing a spec for it —
  `stevin import` does.
- **Delta has rules a general tool doesn't model.** Renaming a column needs column
  mapping; `int` to `bigint` needs type widening; a struct becoming an array needs the
  table rebuilt. stevin plans each as the separate, numbered step it is, and tells you
  how much a rebuild rebuilds before it starts.

## What it will not do

The scope is closed. stevin does not:

- manage ABAC policies. Those are written in Terraform or SQL;
- create catalogs, external tables, governed-tag definitions, groups or service
  principals. Those are the platform's, and Terraform's;
- decide who may have what. It has no rules, no approvals and no policy engine: it puts
  in place what a spec says;
- check data quality or service levels;
- manage materialized views and streaming tables. Those are their pipeline's;
- shape a table another tool builds, or detect a Lakeflow pipeline's tables by itself;
- run from a notebook. It applies from CI, or as a job task where CI can't reach the
  workspace;
- run SQL of your own around a change, or keep SQL functions that no mask or row filter
  names. Both leave with 0.4.0.

A request for one of these is a snippet in your own repository, not a feature.
[Next to other tools](https://kostavo-oss.github.io/tools/stevin/next-to-other-tools/)
draws the line per tool.

## When you no longer need it

When an Asset Bundle has a table resource that plans changes to a live table — which
are free, which rewrite it, which destroy something — use that. Today a bundle declares
schemas and volumes, and no tables.

## Commands

```sh
stevin validate -t dev             # spec lint, no connection needed
stevin import main.sales -o tables # live tables -> YAML specs
stevin apply -t dev                # plan, show, ask, run
stevin plan -t dev [-o plan.json] [--select sales.orders] [--format rich|md|json]
stevin show plan.json -f md        # render a saved plan, no warehouse needed
stevin apply plan.json [--allow-destructive]   # run a reviewed plan, as CI does
stevin drift -t dev                # exit code 2 on drift, for CI
stevin force-unlock -t dev
```

## In CI

```yaml
- uses: kostavo-oss/tools/packages/stevin@stevin-v0
  with:
    target: prod        # comments the plan on the pull request
```

Plan on pull requests, apply on merge, catch drift nightly — see
[the CI guide](https://kostavo-oss.github.io/tools/stevin/ci/).

## Where it fits

stevin is one of the [Kostavo tools](https://github.com/kostavo-oss/tools): small tools
for the ugly gaps on Databricks, one gap each. Its gap is the table nobody's pipeline
owns: the table a notebook appends to, the lookup table, the table another system
writes into, and who may see them. Each works alone. Kostavo is the company behind
them: it builds
[a governance platform for Databricks workspaces](https://kostavo.com), and the tools
are complete without it.

Community project, not affiliated with or endorsed by Databricks.

## Development

stevin uses [mise](https://mise.jdx.dev) + the Astral stack
([uv](https://docs.astral.sh/uv/), [ruff](https://docs.astral.sh/ruff/),
[ty](https://docs.astral.sh/ty/)).

```sh
mise install     # pinned Python + uv
uv sync          # .venv with deps and dev tools

mise run check   # lint + format check + types + unit tests
mise run test    # uv run pytest tests/unit
mise run docs    # preview the docs at localhost:8000
```

See [CONTRIBUTING.md](https://github.com/kostavo-oss/tools/blob/main/packages/stevin/CONTRIBUTING.md) for
the architecture and the house rules.

## License

Apache-2.0 — see [LICENSE](https://github.com/kostavo-oss/tools/blob/main/packages/stevin/LICENSE).
