# 000 — what leeghwater is

**Status:** agreed. The direction is the owner's, of 2026-10-06; the first line and the
Kostavo line are *(decided)*.

How a requirement is marked is in [the README](README.md#how-a-spec-is-written).

## In one line

> **Your dlt pipeline, the same on your laptop and in a Databricks job.**
> One command to run it, its secrets from a secret scope, and the things Databricks asks for
> kept out of your code.

*(decided)*

The definition, for whoever builds it: leeghwater is a Python package that a dlt project
imports. It gives the project a command line that runs its pipelines, it makes the dlt
pipeline for each run from what the run names, it reads dlt's secrets from Databricks secret
scopes, and it prepares the process for dlt wherever it runs. A second command writes such a
project, with a job to run it.

## Why it exists

dlt runs well on Databricks once you know six things. None of them is in one place.

1. **The name.** On Databricks `import dlt` can meet Databricks' own `dlt` — Delta Live
   Tables — and the import hook that comes with it. dlt's docs give two workarounds and call
   one of them fragile. *(dlt)* In a serverless wheel task it turned out not to bite *(run)*;
   a notebook and a cluster are where the docs say it does.
2. **The secrets.** dlt reads secrets from the environment, from `secrets.toml`, and from the
   vaults of Google, AWS and Airflow. A Databricks team keeps its secrets in secret scopes,
   and dlt has no provider for those. *(dlt)*
3. **The warehouse.** Away from a notebook's own cluster, dlt's Databricks destination takes
   `DATABRICKS_WAREHOUSE_ID`, or else "the first one on the warehouse's list". *(dlt)*
4. **The files.** dlt looks for `.dlt/config.toml` in the working directory. In a job that
   is a home directory on the machine, not the project. *(dlt; run)*
5. **The job.** `dlt deploy` knows GitHub Actions and Airflow. Nothing writes the wheel, the
   entry point and the job. *(dlt)*
6. **The names.** A bundle names the schemas, and a target may deploy one under another name
   than the one written down: with a prefix, or as `github__anna`. dlt normalizes a dataset
   name and would make that `github_anna`; and it derives its staging dataset as
   `<name>_staging`, a schema the bundle never made and so never grants or cleans up. Both
   have a setting, and neither is on by default. *(dlt)*

So every team writes the same wrapper: a `main.py` that reads its own arguments, copies
`dbutils.secrets` into environment variables, and builds the pipeline by hand. It works on
Databricks and nowhere else, so what runs at night is not what ran on the laptop. leeghwater
is that wrapper, written once and tested. A project that uses it is two files: a dlt source,
and an entry point of a few lines.

## Where it stands

- **Beside dlt.** Sources, resources, `secrets.toml`, dlt's config and the `dlt` command all
  work as dlt documents them. What leeghwater makes is dlt's own `Pipeline`, and what it
  returns is dlt's own load info. *(owner: "fit it nicely with dlt")*
- **Between the project and two calls of dlt.** A project's pipeline calls
  `leeghwater.create_pipeline` and `leeghwater.run` in place of `dlt.pipeline` and
  `pipeline.run`. Those two calls are where the destination and the schema names are said,
  and they are the run's to say. *(owner, 2026-10-07)*
- **The first Kostavo tool that is imported.** stevin, lely and caland are run. leeghwater is
  a dependency of somebody's project, and is installed on Databricks compute it doesn't own.
  That asks for few dependencies with low bounds, and for an import that changes nothing
  ([002/R2](002-on-databricks.md#requirements)). *(decided)*
- **Not a deploy tool.** The scaffold writes an Asset Bundle. The Databricks CLI deploys it,
  or lely does. *(decided)*
- **Not a scheduler.** When a pipeline runs, what runs after it and what happens when it
  fails are a job's to say. *(decided)*

### When not to use it

- **Lakeflow Connect has a connector for your source** and it does what you need.
- **dlt runs somewhere else** — Airflow, GitHub Actions — and only loads *into* Databricks.
  dlt does that alone.
- **The data needs Spark to move it.** dlt is Python on one machine, and leeghwater doesn't
  change that.

## Who it is for

A developer or a data team on Databricks that writes its ingestion in Python with dlt, wants
to build it on a laptop and run it as a Databricks job, and keeps its secrets in secret
scopes. *(owner: "developers in databricks, to build and run ingestion within databricks")*

## What it does

- **R1 — A package a project imports.** *(owner)*
- **R2 — One command line for a project's pipelines,** the same on a laptop and as a job's
  entry point. → [001](001-the-runner.md) *(owner)*
- **R3 — That command line is the project's to extend.**
  → [001/R9](001-the-runner.md#requirements) *(owner)*
- **R4 — It knows whether it runs on Databricks,** and does there what Databricks needs.
  → [002](002-on-databricks.md) *(owner)*
- **R5 — dlt's secrets from Databricks secret scopes.** → [003](003-secrets.md) *(owner)*
- **R6 — A scaffold:** a project, and a job to run it. Moved to a bundle template, a
  repository of its own. → [004](004-the-scaffold.md) *(owner, 2026-10-07)*
- **R7 — Help for coding agents.** → [005](005-for-agents.md) *(owner: "maybe")*
- **R8 — dlt stays dlt.** leeghwater goes through what dlt offers for it: a registered config
  provider, the config dlt reads from the environment, and the arguments of `dlt.pipeline`.
  It patches nothing in dlt. *(owner; the how is decided)*
- **R9 — It says what it did.** Whatever leeghwater sets up for a run is printed when the run
  starts, and by `doctor` without running anything.
  → [002/R11](002-on-databricks.md#requirements) *(decided)*
- **R10 — No secret's value is printed, logged, written to a file or put in the
  environment.** → [003/R9](003-secrets.md#requirements) *(decided)*
- **R11 — The README says whose it isn't:** a community project, not affiliated with or
  endorsed by Databricks or dltHub. *(decided)*

## What it does not do

- deploy, schedule, or order one pipeline after another
- add a file format for pipelines
- make, change or rotate secrets — that is the Databricks CLI's, and caland's
- change tables — that is stevin's
- set table properties or clustering for a project: dlt's own `databricks_adapter` does, in
  the project's source
- make dlt distributed
- change anything on a cluster: no init script, no file outside the run's own directories

## Phases

1. **Run** — the runner ([001](001-the-runner.md)), what it knows about Databricks
   ([002](002-on-databricks.md)) and secrets ([003](003-secrets.md)). **Built.**
2. **Start** — the scaffold ([004](004-the-scaffold.md)). Built, then moved to a bundle
   template of its own on the owner's word.
3. **For agents** — the skills ([005](005-for-agents.md)). Not built.

Outside the phases: the first release. Publishing waits for the owner's word, as for lely.

## Done when

The README opens with the line above, installs with `uv add`, and carries the disclaimer of R11. All three hold.
