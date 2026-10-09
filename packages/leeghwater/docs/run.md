# Where a run loads

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
