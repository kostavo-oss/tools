# Tried, and not yet

What has run against a real workspace, and what has not. This page is the one record of
it. Everything else leeghwater does is held by its tests, against stand-ins: a made-up
Databricks, a secret scope that is a dictionary, a local DuckDB file.

The runs below were made on 2026-10-07, the day before the first release, with
leeghwater installed from a wheel beside the project's own. leeghwater is on PyPI since
0.1.0 of 2026-10-08, and no release from PyPI has been run in a job.

## 2026-10-07: a serverless job, and a laptop with a profile

On one test workspace. A project with a bundle was deployed to a development target and
run as a job of serverless wheel tasks, and the same project was run from a laptop with
a profile. The project was written by `leeghwater init`, a command leeghwater had that
day and no longer has: a project now starts from
[data-product-template](https://github.com/kostavo-oss/data-product-template). A
throwaway scope, secret, job and schemas were made and removed again.

| What | Held? |
|---|---|
| The bundle validates, deploys and destroys | yes |
| The job's entry point is the project's console script, with the words of the command as its parameters | yes |
| `DATABRICKS_RUNTIME_VERSION` says where it runs; on serverless it held `client.2.5` | yes |
| The job is told the deployed names of the bundle's schemas (`dev_<user>_…`) by reference | yes |
| The `.dlt/config.toml` the wheel carries is found from a job's working directory, which is a home directory on the machine | yes |
| dlt's working files can be written: the home directory is writable | yes |
| A pipeline that raises fails its task | yes |
| A plain `import dlt` in a serverless wheel task is dltHub's dlt | yes |
| A scope is listed and read as the job's identity, and a real source gets its secret | yes |
| A secret read through `dbutils` is redacted in the task's output | yes |
| A secret read through the SDK's secrets API is redacted in the task's output | **no**: it was printed as it is |
| From a laptop with a profile: `doctor`, the scope, and a load into Unity Catalog | yes |
| Schemas named with two underscores are loaded into as named, through the named staging schema, and no third schema is made | yes |
| A load from the serverless job into Unity Catalog | **no, not on this workspace** |

**What did not hold, and why.** dlt's Databricks destination uploads its files to a
volume before it copies them into a table, and the upload goes to
`<region>.storage.cloud.databricks.com`. From this workspace's serverless compute that
connection is refused: its outbound network is limited to a list of hosts. Everything
before the upload ran, and the same load from a laptop works.

What the run showed besides:

- **The name `dlt`.** In a serverless wheel task the import hook is there, as
  `dbruntime.PostImportHook.ImportHookFinder`, and so is Databricks' own `dlt`, at
  `/databricks/spark/python/dlt`. That folder is not on the path, so a plain `import dlt`
  gets dltHub's. With the hook taken out for the import, as leeghwater does, it is
  dltHub's too.
- **A failed task is run again.** A serverless task that failed was run a second time
  without being asked. `disable_auto_optimization: true` on the task turns that off.
- **pyarrow.** dlt loads into Databricks from parquet files and needs pyarrow to write
  them. A Databricks runtime has it and a laptop does not: a project that loads into a
  workspace from a laptop depends on `dlt[databricks,parquet]`.
- **The volume.** dlt makes a volume named `_dlt_staging_load_volume` in the schema it
  loads into, and uploads to it.

## Not yet

- **A full load from a serverless job**, on a workspace whose serverless compute can
  reach its storage.
- **A notebook**, through `prepare()`: the name `dlt`, the cluster as the warehouse, the
  working directory. A notebook and a cluster are where dlt's docs say the name bites.
- **A job on a classic cluster**: the same, and what `DATABRICKS_RUNTIME_VERSION` holds
  there.
- **That a non-zero exit fails a wheel task.** An exception does, which is why
  leeghwater raises its errors on Databricks.
- **Other serverless environment versions** than the one a new job got that day.
- **A real Azure Key Vault.** The Key Vault provider is tested against a stand-in
  client.
- **leeghwater from PyPI in a job.** Every release came after the run.
