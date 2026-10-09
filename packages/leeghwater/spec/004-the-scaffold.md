# 004 — the scaffold

**Status:** superseded on 2026-10-07. It was built as `leeghwater init` and run on a
workspace; the owner then decided that starting a project is a Databricks Asset Bundle
template's job, in a repository of its own, with dlt and dbt both. `init` and its files left
leeghwater that day; the files went to the template's draft. What is below is what was
learned, kept for that template.

## Why

Between "dlt works on my laptop" and "it runs every night on Databricks" stand a wheel, an
entry point, a bundle, a job, and a config file that has to end up inside the wheel. None is
hard and all of them are easy to get slightly wrong. The owner: "it should also be able to
scaffold a job to get people started".

## Requirements

- **R1 — `leeghwater init <name>` writes a project that runs.** Run as
  `uvx leeghwater init my-ingest`, before anything is installed. *(owner; the command's name
  and home are decided)*
- **R2 — What it writes.** *(decided)*

  ```
  my-ingest/
    pyproject.toml              the project, its console script, and the rule that puts
                                .dlt/config.toml into the wheel
    databricks.yml              the bundle, with a dev and a prod target
    resources/schemas.yml       the schema the job loads into, and its staging schema
    resources/ingest.job.yml    one job with one wheel task: ingest run example
    .dlt/config.toml            dlt's config, where dlt looks for it
    .gitignore                  .dlt/secrets.toml stays out
    src/my_ingest/cli.py        the app
    src/my_ingest/pipelines/example.py
    README.md                   run it here, deploy it, give it a secret
  ```

  The project depends on `leeghwater` and on `dlt[databricks,parquet]`. `parquet` because
  dlt loads into Databricks from parquet files and needs pyarrow to write them: a runtime
  has it, a laptop doesn't *(run)*. `dlt[duckdb]` is in the project's dev group, for a run
  on a laptop.
- **R3 — The first run needs nothing but Python.** `uv sync`, then
  `uv run ingest run example`. The example pipeline loads rows it makes itself, into a local
  DuckDB file, so it works before there is a workspace, a source or a secret. Beside it, as
  a comment, how a source asks for a secret. *(decided)*
- **R4 — The job is a serverless wheel task.** Its parameters are the words of R3, with the
  catalog and the warehouse taken from the bundle's variables, so dev and prod differ in the
  bundle and nowhere else. The warehouse is a variable without a default unless `init` was
  given one: `databricks bundle deploy --var warehouse_id=<id>`. A secret scope is passed
  only when `init` was given one: a first run should not need a scope to exist. *(decided;
  run)*

  The task turns serverless' own retry off (`disable_auto_optimization`). Left on, a task
  that failed was run a second time without being asked *(run)*; a load is retried when the
  project says so, with `max_retries`.
- **R5 — The schemas are the bundle's, and the job is told their deployed names.** The
  bundle declares the schema and the staging schema as resources, and the job passes each by
  reference, not by a name typed twice:

  ```yaml
  parameters:
    - run
    - example
    - --schema
    - ${resources.schemas.my_ingest.name}
    - --staging-schema
    - ${resources.schemas.my_ingest_staging.name}
  ```

  Whatever a target does to a schema's name, the job loads into the schema that was
  deployed, and dlt makes none of its own
  ([002/R10](002-on-databricks.md#requirements)). In a development target the bundle
  deployed `dev_<user>_my_ingest`, and that is the name the job got. *(decided; run)*
- **R6 — It deploys as any bundle does:** `databricks bundle deploy -t dev`, then
  `databricks bundle run ingest -t dev`. No leeghwater command deploys or runs a job, and
  lely works on the project because it is a bundle. *(decided; run with the Databricks CLI)*
- **R7 — It asks for a name and nothing else.** Everything else has a default and an option
  (`--dir`, `--package`, `--catalog`, `--secret-scope`, `--warehouse-id`), so it runs
  without a terminal — for an agent, or in a script. *(decided)*
- **R8 — It overwrites nothing.** In a folder that has files, it writes what is missing and
  leaves the rest, naming each file it wrote and each it left. That is also how it is added
  to a dlt project that exists. *(decided)*
- **R9 — What it writes is tried, not read.** The repository's tests make a project with it,
  build the wheel, look inside it for `config.toml` and for no `secrets.toml`, run the
  example pipeline into a local database from the project and from the unpacked wheel in
  another folder, and run the linter over what was written. *(decided)*
- **R10 — What it writes is short.** Every file is one a person would have written, with a
  line of comment where a choice was made. No file of leeghwater's own beside dlt's and the
  bundle's. *(decided)*

## Not in this spec

- **Deploying.** R6.
- **A workflow for the project's CI.**
- **A second job, a job per pipeline, a schedule.** The job file is short enough to copy.
- **Jobs on a classic cluster, and notebooks.** After
  [002, To verify](002-on-databricks.md#to-verify).
- **A `lely.yml`.** lely needs none for a project that is only a bundle.
- **Sources.** `dlt init` adds dlt's verified sources to a project, and still does.
- **`dlt databricks init`,** the same command inside dlt's own, through its hook for plugins.
  It needs dlt and leeghwater installed first, which is not when a scaffold is wanted. A
  later addition if it is asked for.

## Done when

R9's checks pass in CI — they do. And a person who has never seen the tool gets from
`uvx leeghwater init` to a job that has run on their workspace by following the written
README and nothing else: not yet, because `leeghwater` is not on PyPI, and a full load from
a job is still [to verify](002-on-databricks.md#to-verify).
