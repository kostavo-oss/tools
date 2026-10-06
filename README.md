# stevin

**Safe plan/apply migrations for Unity Catalog tables and schemas.**
Describe the tables you want in YAML or SQL, see what it takes to get a live catalog
there — which changes are free, which rewrite 400 GB, which destroy something — and
then apply it.

[![ci](https://github.com/kostavo-oss/stevin/actions/workflows/ci.yml/badge.svg)](https://github.com/kostavo-oss/stevin/actions/workflows/ci.yml)
[![Docs](https://img.shields.io/badge/docs-stevin-1f9e9a.svg)](https://kostavo-oss.github.io/stevin/)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

> **Terraform for your platform, Asset Bundles for your code, stevin for your data model.**

> **Status: alpha.** Every milestone in the design is built — plan, apply (rewrites
> included), drift, the GitHub Action, and governance (tags, grants, masks, row filters,
> views, SQL functions). It is tested offline against a fake warehouse, and every
> assumption it makes about Databricks is checked by a live suite against a real
> workspace. Try it on a dev catalog before production.

## Named after

Simon Stevin (1548–1620), engineer and mathematician: he designed sluices and introduced
decimal notation. Precision before action — which is what a plan is.

Up to 0.2.0a4 stevin was called `deltaplan`. That command and a `deltaplan.yml` still
work — [coming from deltaplan](https://kostavo-oss.github.io/stevin/installation/#coming-from-deltaplan)
says what changed and what didn't.

## Install

> **Not on PyPI under this name yet.** The first release as `stevin` is being prepared.
> Until this notice is gone, do not install a `stevin` from PyPI — it is not ours. Install
> it from GitHub, or under the name its releases have so far, `deltaplan`:
>
> ```sh
> uv tool install git+https://github.com/kostavo-oss/stevin   # stevin, as it is on main
> uv tool install --prerelease allow deltaplan                # the last release, 0.2.0a4
> ```

Once it is released:

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
**[Get started →](https://kostavo-oss.github.io/stevin/getting-started/)** is those ten
minutes on your own workspace, every step shown;
**[the tour →](https://kostavo-oss.github.io/stevin/tour/)** takes one project from
nothing to a reviewed pull request. The [docs](https://kostavo-oss.github.io/stevin/)
have the spec format, the commands and the safety model, and
[`docs/DESIGN.md`](docs/DESIGN.md) is the source of truth.

## What it is for

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
  [details](https://kostavo-oss.github.io/stevin/bundles/). Without a bundle, a
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
everything — [the list](https://kostavo-oss.github.io/stevin/formats/) says which.

## The plan

![A stevin plan: a rename, a widening, a backfilled NOT NULL column, a nested field, a CHECK and a grant, each with its numbered, risk-labelled steps](https://kostavo-oss.github.io/stevin/assets/screens/tour-plan-change.svg)

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
- uses: kostavo-oss/stevin@v0
  with:
    target: prod        # comments the plan on the pull request
```

Plan on pull requests, apply on merge, catch drift nightly — see
[the CI guide](https://kostavo-oss.github.io/stevin/ci/).

## Where it fits

stevin is one of the [Kostavo tools](https://github.com/kostavo-oss) for Databricks.
Each does one job and none needs another: Terraform sets up the platform, an Asset
Bundle deploys the code, and stevin changes the data model — the part of a deploy that
can't simply be run again.

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

See [CONTRIBUTING.md](CONTRIBUTING.md) for the architecture and the house rules.

## License

Apache-2.0 — see [LICENSE](LICENSE).
