# 001 — the runner

**Status:** built, in `src/leeghwater/_app.py` and `_pipeline.py`; tested in
`tests/test_app.py` and `tests/test_pipeline.py`; run as a serverless wheel task on
2026-10-07.

## Words

- A **project** is somebody's dlt project: a Python package with their pipelines in it.
- The **app** is the command line leeghwater gives that project. The project names it as its
  console script, so it has the project's name for it — `ingest` in the examples here.
- A **pipeline** is one thing the app can run, by name.
- A **run** is one call of the app, with its options.

## Why

A job needs an entry point and a developer needs a command. When they are two things, what
was tried on the laptop is not what runs at night. So they are one: the project's console
script, which a wheel task can call as it is.

And where a run loads is not the code's to say. The same code loads into a local file on a
laptop, into one developer's schema in development and into the real one in production. So
the run names those, and leeghwater makes the pipeline from what the run named.

## Requirements

- **R1 — A project makes an app and names it as its console script.** *(owner: "a entry
  point for running in databricks, a cli that people can extend")*

  ```python
  # src/my_ingest/cli.py
  from leeghwater import App

  app = App(pipelines="my_ingest.pipelines", secret_scopes=["ingest"])
  ```

  ```toml
  [project.scripts]
  ingest = "my_ingest.cli:app"
  ```

- **R2 — A pipeline is a function in the project, marked as one, and leeghwater makes its
  dlt pipeline.** Its name is the function's. The app is told where the project's pipelines
  are and imports them itself. *(owner, 2026-10-07: "leeghwater makes it")*

  ```python
  # src/my_ingest/pipelines/github.py
  import leeghwater
  from leeghwater import pipeline


  @pipeline
  def github(since: str = "2024-01-01"):
      p = leeghwater.create_pipeline("github")
      return leeghwater.run(p, github_source(since=since))
  ```

  - `create_pipeline(name, *, schema=None, **more)` is `dlt.pipeline(name, ...)` with the
    destination and the schema the run named, and returns dlt's own pipeline. `schema=` is
    the schema to use when a run names none; a run's `--schema` wins over it. A
    `destination` or a `dataset_name` in the call is refused, with where to say it instead.
    Anything else `dlt.pipeline` takes is passed on.
  - `run(pipeline, data, **more)` is `pipeline.run(data, ...)`: it applies the run's
    `--limit`, prints the load report, raises when a load job failed (R7), and returns dlt's
    load info. Anything else `pipeline.run` takes is passed on.
  - Without an app — in a notebook — both go by the last `prepare()`, and prepare with
    nothing named when there was none (R11).
- **R3 — `ingest run <name>` runs one pipeline.** Before the function is called the process
  is prepared ([002](002-on-databricks.md)) and the secret scopes are in place
  ([003](003-secrets.md)). *(owner)*
- **R4 — A pipeline's parameters are options of its command.** `since` above is
  `ingest run github --since 2024-06-01`, with the type the function gives it, and
  `ingest run github --help` lists them. A parameter is text, a whole or a decimal number, a
  date or a time in ISO format, or a yes or no. A yes or no takes a word — `true`, `1`,
  `yes`, `y`, and their opposites — and is not a flag: a job's parameter comes from a bundle
  variable, and a variable can set a word. A value that doesn't parse is refused with the
  option's name. A parameter of another type, or one named like an option of R5, is refused
  when the app starts, not when the pipeline is run. *(decided)*
- **R5 — Every run takes the same few options,** for what differs between a laptop, a dev
  target and a prod target. None is needed for a first run. *(decided)*

  | Option | What it sets |
  |---|---|
  | `--profile <name>` | Which workspace, on a laptop: a profile from `~/.databrickscfg`. Without it a laptop run loads locally. On Databricks it is refused: the run has an identity already. → [002/R6](002-on-databricks.md#requirements) |
  | `--catalog <name>` | The catalog the Databricks destination loads into. |
  | `--schema <name>` | The schema to load into, used as given. → [002/R10](002-on-databricks.md#requirements) |
  | `--staging-schema <name>` | The schema dlt stages through, by its whole name. → [002/R10](002-on-databricks.md#requirements) |
  | `--warehouse <id>` | The warehouse to load through. → [002/R7](002-on-databricks.md#requirements) |
  | `--secret-scope <name>` | A scope to read secrets from, in place of the app's. May be given more than once. → [003/R3](003-secrets.md#requirements) |
  | `--secret <name>=<scope>/<key>` | Where one secret is, when it isn't under dlt's name. May be given more than once. → [003/R8](003-secrets.md#requirements) |
  | `--limit <n>` | At most `n` pages from each resource; `0`, the default, for all. |
  | `--log-level <level>` | `DEBUG`, `INFO`, `WARNING`, `ERROR` or `CRITICAL`, for dlt. |
  | `--set <key>=<value>` | Any dlt config value for this run, by the name dlt gives it: `--set sources.github.page_size=50`. |

  The catalog and the warehouse also have a default in the app (R1). A `--schema` or a
  `--staging-schema` that is given but empty is refused, not taken for one left out: a
  bundle reference that resolved to nothing is a mistake.

  `--limit` is for a pull-request environment, which runs with `1`: enough for dlt to make
  every table with its real columns. Not with nothing: dlt takes a table's columns from the
  rows it sees, so a source that gives no rows makes no table. It counts pages, not rows:
  it is dlt's `add_limit`.
- **R6 — The same command is a job's entry point.** A wheel task names the project's
  package, the console script, and the words that would be typed. Nothing in the task names
  leeghwater. *(owner; run)*

  ```yaml
  python_wheel_task:
    package_name: my-ingest
    entry_point: ingest
    parameters: ["run", "github", "--catalog", "${var.catalog}"]
  ```

- **R7 — A run ends the way it went.** It prints what was set up
  ([002/R11](002-on-databricks.md#requirements)), then a report of the load. *(decided)*

  - It ends well when the load is done.
  - It ends with an error when the function raises. On Databricks the error is raised and the
    task fails with it *(run)*. On a laptop an error of leeghwater's own is one line and
    exit 1; any other is raised.
  - It ends with an error when a load job failed. dlt raises on that by itself *(dlt)*. A
    project can turn that off (`load.raise_on_failed_jobs`), and dlt then calls the package
    loaded with a table missing; `run()` raises all the same. A green job with a table
    missing is the worst way for a run to end.

  The report, as one block: per load package its id and state; per finished job the table,
  the file format, the size and the seconds it took; per failed job the table and one line of
  why; then the destination, the schema, when it started and ended, and whether it was the
  pipeline's first run.
- **R8 — A pipeline that calls dlt itself fails its run.** `dlt.pipeline(...)` in a
  project's code can't be stopped: it is dlt's call, and nothing in dlt is patched. It also
  gets nothing from the run — no schema, no destination, no limit — because those are set
  on the destination `create_pipeline` makes and nowhere else. So the app counts the loads
  `run()` made during the pipeline function, and **fails the run when there was none**,
  with an error that says why a plain `dlt.pipeline()` is not enough. *(decided; changed
  after a review on 2026-10-07: before, the run's names also reached a plain
  `dlt.pipeline()` through the environment, and `--limit` was silently lost)*
- **R9 — A project adds its own commands,** beside `run`. They are prepared as a pipeline
  is, with the app's own settings, and find the same secrets. *(owner: "a cli that people can
  extend")*

  ```python
  @app.command()
  def backfill(day: str):
      """Load one day again."""
      ...
  ```

- **R10 — Two commands come with the app.** `ingest list` names the project's pipelines and
  their parameters. `ingest doctor` says where this would run and what would be set up,
  checks what can be checked without running a pipeline — the sign-in, each secret scope,
  each pointed-at secret, the warehouse — and changes nothing. It reads names, never a
  value. Both can answer as JSON. *(decided; `doctor` run from a laptop)*
- **R11 — Without an app: `leeghwater.prepare()`.** One call does for a notebook or a script
  what the app does before a run — everything in [002](002-on-databricks.md) and
  [003](003-secrets.md). The app is this call and a command line around it. *(owner: "in
  essence its a package they import")*

  ```python
  import leeghwater

  leeghwater.prepare(secret_scopes=["ingest"], catalog="main", warehouse="<id>")
  p = leeghwater.create_pipeline("github", schema="github")
  leeghwater.run(p, github_source())
  ```

- **R12 — Help and errors are plain text.** A job's log is not a terminal. *(decided)*

## Not in this spec

- **When a pipeline runs, and what runs after it.** A job's schedule and its tasks.
- **Retries.** A job's task has them.
- **Commands inside dlt's own command line.** → [004](004-the-scaffold.md#not-in-this-spec)
- **A wrapper for the rest of dlt.** Two calls are wrapped, because the run has something to
  say in them. Sources, resources, hints and the `dlt` command are dlt's.

## Done when

With a small project of two pipelines, in the tests, with dlt loading into a local database
and no workspace — all of these pass:

- `ingest list` names both, with their parameters, and as JSON.
- `ingest run <name> --<parameter> <value>` runs it and the value arrives typed.
- The same words given as a wheel task would give them run the same pipeline.
- `create_pipeline` takes the destination and the schema from the run, and refuses them in
  the call; `run` applies the limit and returns dlt's load info.
- A pipeline that raises, one whose load job failed with dlt told not to raise, and one that
  called dlt itself and loaded somewhere else, all end with an error.
- A parameter named like an option of every run is refused when the app starts.
- A command the project added runs, and finds a secret from a (stand-in) scope.
- `prepare()` alone, without an app, does the same setting up.

And on a workspace: the same project ran as a serverless wheel task, and a pipeline that
raises failed its task. *(run)*
