# leeghwater

**Your dlt pipeline, the same on your laptop and in a Databricks job.**
One command to run it, its secrets from a secret scope, and the things Databricks asks for
kept out of your code.

[![ci](https://github.com/kostavo-oss/leeghwater/actions/workflows/ci.yml/badge.svg)](https://github.com/kostavo-oss/leeghwater/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/leeghwater.svg)](https://pypi.org/project/leeghwater/)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

> **Early.** It has run as a serverless job and from a laptop against a real workspace;
> what was tried and what was not is under [Tried, and not yet](#tried-and-not-yet).

leeghwater is a package your [dlt](https://dlthub.com) project imports. Your sources stay
ordinary dlt code. leeghwater gives the project a command line, and for each run it makes
the dlt pipeline from what the run names: a local file on a laptop, the schema your bundle
deployed in a job.

## A project is two files

The app, which is the project's console script:

```python
# src/my_ingest/cli.py
from leeghwater import App

app = App(pipelines="my_ingest.pipelines", secret_scopes=["ingest"])
```

```toml
# pyproject.toml
[project.scripts]
ingest = "my_ingest.cli:app"
```

And a pipeline: a function marked `@pipeline`, anywhere in the package the app names.

```python
# src/my_ingest/pipelines/github.py
from datetime import date

import dlt
import leeghwater
from leeghwater import pipeline


@dlt.source
def github_source(since: date, access_token: str = dlt.secrets.value): ...


@pipeline
def github(since: date = date(2024, 1, 1)):
    """Load GitHub issues."""
    p = leeghwater.create_pipeline("github")
    return leeghwater.run(p, github_source(since=since))
```

`create_pipeline` and `run` stand in for `dlt.pipeline()` and `pipeline.run()`, and a
pipeline never calls those two itself. Where a run loads, into which schema and through
which staging schema is the run's to say, not the code's: `create_pipeline` sets them on
the dlt destination it makes, and a plain `dlt.pipeline()` gets none of it. What you get
back is dlt's own pipeline and dlt's own load info, and anything else the two dlt calls
take is passed on.

```sh
ingest list                                  # the pipelines and their parameters
ingest run github --since 2024-06-01         # run one
ingest doctor                                # what would be set up, checked, nothing run
```

## Start a project

[vierlingh](https://github.com/kostavo-oss/vierlingh) is the way to start: a copier
template for a data product — dlt to land the data, run by leeghwater; dbt to shape it; one
job; the schemas as bundle resources; every task behind `mise run`.

```sh
uvx copier copy gh:kostavo-oss/vierlingh my-product
```

To add leeghwater to a project you have: `uv add leeghwater`, write the two files above, and
pass the schemas' deployed names from the bundle as shown under [In a job](#in-a-job).

## Where a run loads

| Where you run it | It loads into | Secrets come from |
|---|---|---|
| A laptop | a local DuckDB file, `<pipeline>.duckdb` | the environment, `.dlt/secrets.toml` |
| A laptop, with `--profile <name>` | that workspace, as you | the same, then the secret scopes |
| Databricks | this workspace, as the run's identity | the environment, then the secret scopes |

The first row needs nothing but Python and `dlt[duckdb]`. It tries your source, not the
destination: DuckDB ignores what is Databricks' own, such as table properties.

A project that loads somewhere else says so once, in the app:
`App(..., destination=..., local_destination=...)`.

## The options of every run

A pipeline's own parameters are options of its command: `since` above is `--since`, with
the type the function gives it. Text, whole and decimal numbers, dates and times in ISO
format, and yes or no as a word (`--full true`), so a bundle variable can set it.

Every run also takes these:

| Option | What it sets |
|---|---|
| `--profile <name>` | Load into a workspace from a laptop, with a profile from `~/.databrickscfg`. Refused on Databricks. |
| `--catalog <name>` | The catalog to load into. |
| `--schema <name>` | The schema to load into, used exactly as given. |
| `--staging-schema <name>` | The schema dlt stages through, by its whole name. |
| `--warehouse <id>` | The SQL warehouse to load through. |
| `--secret-scope <name>` | A secret scope to read, in place of the app's. May be repeated. |
| `--secret <name>=<scope>/<key>` | Where one secret is, when it isn't under dlt's name. May be repeated. |
| `--key-vault <url>` | An Azure Key Vault to read, after the scopes. May be repeated. |
| `--limit <n>` | At most `n` pages from each resource; `0`, the default, for all. |
| `--log-level <level>` | `DEBUG`, `INFO`, `WARNING`, `ERROR` or `CRITICAL`, for dlt. |
| `--set <key>=<value>` | Any dlt config value, by dlt's name: `--set sources.github.page_size=50`. |

The schema, staging schema, catalog and warehouse are set on the destination that
`create_pipeline` makes, in the call, which is what dlt takes first. `--set` and
`--log-level` go to dlt as config, the way an environment variable does. Nothing in dlt is
patched.

A pull-request environment runs with `--limit 1`: enough for dlt to make every table with
its real columns. Not with nothing: dlt takes a table's columns from the rows it sees, so a
source that gives no rows makes no table.

## In a job

The same command is the job's entry point. Nothing in the task names leeghwater.

```yaml
python_wheel_task:
  package_name: my-ingest
  entry_point: ingest
  parameters:
    - run
    - github
    - --catalog
    - ${var.catalog}
    - --schema
    - ${resources.schemas.github.name}
    - --staging-schema
    - ${resources.schemas.github_staging.name}
    - --warehouse
    - ${var.warehouse_id}
```

### Why the schemas are passed by reference

A bundle names your schemas, and a target may change the name it deploys: a prefix, or a
suffix per developer, such as `github__anna`. Left alone, dlt gets this wrong twice:

- it normalizes a dataset name, and `github__anna` becomes `github_anna`: a schema nobody
  deployed;
- it derives its staging dataset as `<name>_staging`, so `github__anna_staging`, while the
  bundle deployed `github_staging__anna`. dlt then makes a schema of its own, outside the
  bundle's grants and its cleanup.

`--schema` turns the normalizing off for the run, and `--staging-schema` gives dlt the
staging schema's whole name. On Databricks a run that names a schema and no staging schema
stops, and says which line of the job is missing. That holds for a pipeline that never
merges too: a staging schema that is there and unused costs nothing, one that is missing
costs a schema nobody governs.

### A run ends the way it went

A run prints what was set up, then a report of the load. It ends with an error when:

- the pipeline raises;
- a load job failed. dlt raises on that by itself; a project that turned that off
  (`load.raise_on_failed_jobs`) still gets a failed run;
- a run into Databricks names no warehouse. dlt would otherwise load through the first
  warehouse on the workspace's list;
- the pipeline made no load with `leeghwater.run()`: a plain `dlt.pipeline()` loads
  wherever dlt's own config says, with no schema, catalog or limit from the run.

A serverless job retries a failed task once by itself unless the task sets
`disable_auto_optimization: true`: set it, so a load is retried when you say so, with
`max_retries`.

## Secrets

A source asks dlt for a secret: `access_token: str = dlt.secrets.value`. dlt looks in the
environment, then in `.dlt/secrets.toml`, then in the secret scopes the app or the run
names. Three ways to give it one, and when to use each:

1. **By dlt's name, in a scope.** The path dlt asks for, joined with `-`:

   ```sh
   databricks secrets put-secret ingest sources-github-access_token
   ```

   The default. One secret per value, and no code.

2. **A whole section in one secret.** A secret named `sources-github` (or `sources`,
   `destination-<name>`, `destination`, `dlt_secrets_toml`) is read as a piece of
   `secrets.toml`. It must spell out its own heading:

   ```toml
   [sources.github]
   access_token = "..."
   ```

   Without the heading its values are found as every source's. Use it when a source has
   several secrets that change together.

3. **A secret that exists under another name.** Point at it, as `<scope>/<key>`:

   ```python
   app = App(..., secrets={"sources.github.access_token": "platform-shared/github-token"})
   ```

   or per run, so dev and prod can differ in the bundle:
   `--secret sources.github.access_token=platform-shared/github-token`.
   Use it when somebody else fills the scope.

4. **An Azure Key Vault**, for a team whose secrets live there and not in a scope. Needs
   the extra, `uv add "leeghwater[keyvault]"`, and a vault named in the app or per run:

   ```python
   app = App(..., key_vaults=["https://kv-ingest.vault.azure.net"])
   ```

   A vault is asked after the scopes. Its secrets are named like a scope's, with dashes
   where a Key Vault allows no underscore: `sources-github-access-token`. Whoever
   `DefaultAzureCredential` finds reads it: `az login` on a laptop; a service principal's
   variables or a managed identity elsewhere. A Databricks job has no identity in Azure by
   itself, so there a vault is reachable only through a service principal whose secret
   comes from somewhere else — in practice a Databricks scope — and only when the job's
   network reaches `vault.azure.net`. A Key Vault-backed Databricks scope needs none of
   this: it is a scope, read as in 1.

A scope or a vault is listed once in a run and only the secrets that are there are read.
Only values a source marks as secret are looked up. No value is printed, logged, written to
a file or put in the environment. To make, change or rotate a secret, use the Databricks
CLI or the Azure portal.

In a job a secret is read through `dbutils`, so Databricks redacts it: if your own code
prints one, the job's output shows `[REDACTED]`.

## In a notebook, or without an app

```python
import leeghwater

setup = leeghwater.prepare(secret_scopes=["ingest"], catalog="main", warehouse="<id>")
print("\n".join(setup.lines()))

p = leeghwater.create_pipeline("github", schema="github")
leeghwater.run(p, github_source())
```

`prepare()` is everything the app does before a run, and returns what it decided;
`create_pipeline` and `run` go by the last `prepare()`, or by a `setup=` you pass them.
Importing `leeghwater` changes nothing and does not import dlt.

## Commands of your own

```python
@app.command()
def backfill(day: str):
    """Load one day again."""
    ...
```

`ingest backfill 2024-06-01` is prepared as a pipeline is, with the app's own settings, and
finds the same secrets.

## Troubleshooting

- **Deleting the DuckDB file does not start a pipeline over.** dlt keeps a pipeline's state
  outside the database, under `~/.dlt/pipelines/<name>/`. Delete that folder too.
- **`import dlt` gives Delta Live Tables.** Databricks has a module of its own named `dlt`.
  In a serverless job a plain `import dlt` gets the right one. In a notebook or on a
  cluster, call `leeghwater.prepare()` before `import dlt`. The first lines of a run say
  what was done about the name.
- **The pipeline and its schema have the same name, and DuckDB refuses.** DuckDB names its
  database after the file, `<pipeline>.duckdb`, and can't tell a schema of that name from
  it. Locally, give the schema another name or leave it out.
- **A load from a job is refused a connection to `…storage.cloud.databricks.com`.** dlt
  uploads its files to a volume before it copies them into a table. A workspace whose
  serverless compute has a limited outbound network refuses that upload.
- **`ingest doctor`** says where a run would load and checks the sign-in, each secret scope
  and the warehouse, without running anything. `--json` for a machine.

## Tried, and not yet

On 2026-10-07 a project made by `leeghwater init` was deployed to a workspace as a bundle
and run, and the same project was run from a laptop with a profile.

Held, for real:

- a bundle made from the former `leeghwater init` validates, deploys and destroys, and the
  job's entry point is the project's own command;
- the job is told the deployed names of the bundle's schemas, and finds the `config.toml`
  its wheel carries;
- a pipeline that raises fails its task;
- a secret scope is read as the job's identity and from a laptop, and a secret is redacted
  in the job's output;
- from a laptop, a load into Unity Catalog; and with schemas named with two underscores, a
  load into exactly those, with no third schema made.

Not yet:

- **a full load from a serverless job.** The workspace it was tried on limits the outbound
  network of serverless compute, and dlt's upload to storage was refused. Everything before
  the upload ran;
- a notebook and a classic cluster, which is where the name `dlt` is said to bite;
- the job's `ingest` task with leeghwater installed from PyPI, which 0.1.0 makes possible.

## Where it fits

> **Terraform for your platform, Asset Bundles for your code, stevin for your data model.**

leeghwater is one of the [Kostavo tools](https://github.com/kostavo-oss) for Databricks.
It is a library for one kind of code, dlt ingestion, and not a layer of its own: it deploys
nothing and schedules nothing. The bundle it writes is deployed by the Databricks CLI, or
by lely.

When not to use it: when Lakeflow Connect has a connector for your source; when dlt runs
somewhere else and only loads into Databricks; when the data needs Spark to move it.

## Named after

Jan Adriaanszoon Leeghwater — the millwright who drained the Beemster with windmills, dry in 1612. He moved water from where it lay to where it was wanted.

Community project, not affiliated with or endorsed by Databricks or dltHub.

## License

[Apache-2.0](LICENSE).
