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

> **Alpha.** Every release so far is a pre-release, and the spec format may still change
> before the first stable one. Try it on a dev catalog before production. The
> [changelog](https://github.com/kostavo-oss/tools/blob/main/packages/stevin/CHANGELOG.md)
> says what each release changed and what to do about it.

## Why

Every workspace has tables that nobody's pipeline owns: the table a notebook appends
to, the lookup table, the table another system writes into. Someone made each once, with
a `CREATE TABLE` in a notebook, and changing one is another notebook, run by hand, once
per environment. Who may see them is set the same way.

stevin keeps those tables, and the access around them, as specs in git. A change is a
plan in a pull request: which changes are metadata only, which rebuild the table, which
destroy something. A change made by hand shows up as drift. dbt, Lakeflow or SQLMesh own
what they build, and stevin leaves that alone.

Unity Catalog is the state: there is no state file. A table holds data, so a change is
an `ALTER` wherever Delta allows one and never a drop and a recreate, which is
[why Terraform is not the tool for tables](https://kostavo-oss.github.io/tools/stevin/next-to-other-tools/#why-not-terraform-for-the-tables).

## Install

```sh
uvx --prerelease allow stevin --version      # run it once, nothing installed
uv tool install --prerelease allow stevin    # or keep it
```

Every release so far is a pre-release, which installers skip unless asked: hence the
flag. `pip install --pre stevin` works too.

## Quickstart

```sh
mkdir crm-tables && cd crm-tables
stevin import main.crm    # a spec per table, and a stevin.yml with one target
stevin plan               # what it would do; nothing is touched
stevin apply              # the same plan: shown, asked about, then run
```

Then change a table by editing its spec, and `stevin apply` again.

![A stevin plan: a rename, a widening, a backfilled NOT NULL column, a nested field, a CHECK and a grant, each with its numbered, risk-labelled steps](https://kostavo-oss.github.io/tools/stevin/assets/screens/tour-plan-change.svg)

In CI, the Action comments the plan on a pull request:

```yaml
- uses: kostavo-oss/tools/packages/stevin@stevin-v0
  with:
    target: prod        # comments the plan on the pull request
```

## The docs

How to use it is in the [docs](https://kostavo-oss.github.io/tools/stevin/), and only
there:

- [Get started](https://kostavo-oss.github.io/tools/stevin/getting-started/): those ten
  minutes on your own workspace, every step shown. [A tour](https://kostavo-oss.github.io/tools/stevin/tour/)
  takes one project from nothing to a reviewed pull request.
- [Writing a spec](https://kostavo-oss.github.io/tools/stevin/spec/), in
  [YAML or SQL](https://kostavo-oss.github.io/tools/stevin/formats/), and
  [every kind of change](https://kostavo-oss.github.io/tools/stevin/features/) with its
  spec and its plan.
- [Commands](https://kostavo-oss.github.io/tools/stevin/cli/), and stevin
  [as a library](https://kostavo-oss.github.io/tools/stevin/sdk/).
- [The safety model](https://kostavo-oss.github.io/tools/stevin/safety/): what stevin
  touches, what a step may cost, and what `apply` promises.
- [In CI](https://kostavo-oss.github.io/tools/stevin/ci/): plan on pull requests, apply
  on merge, catch drift nightly. [From a job](https://kostavo-oss.github.io/tools/stevin/running-from-a-job/)
  where CI cannot reach the workspace.
- [With an Asset Bundle](https://kostavo-oss.github.io/tools/stevin/bundles/),
  [next to dbt, dlt, Lakeflow and Terraform](https://kostavo-oss.github.io/tools/stevin/next-to-other-tools/),
  [tables your notebooks write](https://kostavo-oss.github.io/tools/stevin/tables-your-notebooks-write/),
  and [three access recipes](https://kostavo-oss.github.io/tools/stevin/access-recipes/).
- [How it works](https://kostavo-oss.github.io/tools/stevin/how-it-works/): the
  pipeline, the model, what a plan holds, how ownership is known.

What must be true of the code is in
[RULES.md](https://github.com/kostavo-oss/tools/blob/main/packages/stevin/RULES.md),
why it is so in
[DECISIONS.md](https://github.com/kostavo-oss/tools/blob/main/packages/stevin/DECISIONS.md),
and how to contribute in
[CONTRIBUTING.md](https://github.com/kostavo-oss/tools/blob/main/packages/stevin/CONTRIBUTING.md).

## How it is tested

Offline, against a fake warehouse that interprets the SQL stevin sends. And by a live
suite that runs what stevin assumes about Databricks against a real workspace: it has
settled most of those assumptions and not all of them. `stevin verify` runs the same
assumptions in a workspace of your own.

[How it is tested](https://kostavo-oss.github.io/tools/stevin/testing/) says what each
layer proves and lists what is still open.

## What it will not do

The scope is closed. stevin does not:

- manage ABAC policies. Those are written in Terraform or SQL, and stevin reads them;
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
  names. Both left in 0.4.0.

A request for one of these is a snippet in your own repository, not a feature.
[Next to other tools](https://kostavo-oss.github.io/tools/stevin/next-to-other-tools/)
draws the line per tool.

## When you no longer need it

When an Asset Bundle has a table resource that plans changes to a live table — which
are free, which rewrite it, which destroy something — use that. Today a bundle declares
schemas and volumes, and no tables.

## Where it fits

stevin is one of the [Kostavo tools](https://github.com/kostavo-oss/tools): small tools
for the ugly gaps on Databricks, one gap each. Its gap is the table nobody's pipeline
owns: the table a notebook appends to, the lookup table, the table another system
writes into, and who may see them. Each works alone. Kostavo is the company behind
them: it builds
[a governance platform for Databricks workspaces](https://kostavo.com), and the tools
are complete without it.

Community project, not affiliated with or endorsed by Databricks.

## Named after

Simon Stevin (1548–1620), engineer and mathematician: he designed sluices and introduced
decimal notation. Precision before action, which is what a plan is.

Up to 0.2.0a4 stevin was called `deltaplan`. That command and a `deltaplan.yml` still
work: [coming from deltaplan](https://kostavo-oss.github.io/tools/stevin/installation/#coming-from-deltaplan)
says what changed and what didn't.

## License

[Apache-2.0](https://github.com/kostavo-oss/tools/blob/main/packages/stevin/LICENSE).
