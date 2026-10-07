# 002 — on Databricks

**Status:** built, in `src/leeghwater/_prepare.py`, `_where.py` and `_hook.py`; tested in
`tests/test_prepare.py` and `tests/test_hook.py`; run in a serverless wheel task and from a
laptop on 2026-10-07. A notebook and a classic cluster are [to verify](#to-verify).

## Why

The owner's words: the package "handles some of the databricks idiotic things; it knows if
its running in databricks or not". This spec is the list of those things, and what leeghwater
does about each.

## Requirements

- **R1 — It knows where it runs.** On a laptop or on Databricks; and on Databricks, which
  runtime, and whether it is serverless. A project can ask (`leeghwater.where()`). It is read
  from `DATABRICKS_RUNTIME_VERSION`, which is how the Databricks SDK decides too. In a
  serverless wheel task it held `client.2.5` *(run)*; that a cluster holds its runtime's
  version is *to verify*. *(owner; the how is decided)*
- **R2 — Everything happens in `prepare()`, and importing leeghwater does nothing.** The app
  calls it; a notebook calls it itself. A second call with the same arguments changes
  nothing. Importing `leeghwater` does not import dlt. *(decided)*
- **R3 — After `prepare()`, `import dlt` is dltHub's.** On Databricks the import hook that
  comes with Databricks' own `dlt` is taken out for that one import and put back, and what
  Databricks had loaded under the name is dropped. These are the workarounds in dlt's docs
  *(dlt)*. *(owner)*

  **In a serverless wheel task none of it is needed** *(run)*: the hook is there, as
  `dbruntime.PostImportHook.ImportHookFinder`, and so is the folder
  `/databricks/spark/python/dlt`, but that folder is not on the path, and a plain
  `import dlt` at the top of a project's module gets dltHub's. So a project may import dlt
  wherever it likes, and there is no rule about the app's module. The workaround runs there
  all the same and does no harm.

  A notebook and a cluster are where dlt's docs say the name bites; there it is *to verify*.
  When the import comes out as Databricks' own after all, the first lines of the run say so,
  and name the modules that hold it.
- **R4 — Nothing on a cluster is changed.** No init script, no file moved, nothing another
  notebook on the same cluster would notice. In a process where the workaround was needed,
  Databricks' own `dlt` is not importable afterwards. *(decided)*
- **R5 — A run's options are set on the destination, in the call.** `create_pipeline`
  makes dlt's destination factory with the catalog, the warehouse's path, the staging
  layout and the normalization switch the run decided, and gives `dlt.pipeline` the schema;
  what is set in a call is what dlt takes first *(dlt)*. Nothing is written to the
  environment for them, so a later `prepare()` starts from nothing and a plain
  `dlt.pipeline()` gets none of it. The four things dlt or the SDK read from the
  environment go there: `DATABRICKS_CONFIG_PROFILE`, `DLT_PROJECT_DIR`,
  `RUNTIME__LOG_LEVEL`, and what `--set` names. Nothing in dlt is patched. *(decided;
  changed after a review on 2026-10-07, which found the environment channel left state
  behind between calls)*
- **R6 — Where a run loads.** *(owner, 2026-10-07, for the laptop; the rest decided)*

  | Where it runs | It loads into | Secret scopes |
  |---|---|---|
  | A laptop | a local DuckDB file | none is read |
  | A laptop, with `--profile` | that workspace | read, as the developer |
  | Databricks | this workspace | read, as the run's identity |

  The first needs nothing but Python: it tries the source, not the destination. A project
  that loads somewhere else says so once, in the app: `App(destination=...,
  local_destination=...)`; `None` leaves the destination to dlt's own config. A destination
  that the environment already names is left as it is, and the first lines say so.
- **R7 — The warehouse is named, not found.** When the app or the run names one, dlt is
  given it as the `http_path` `/sql/1.0/warehouses/<id>`. When nothing names one, a run
  through the app that loads into Databricks stops before the pipeline is called, and the
  error shows the lines of the job that pass it. dlt would otherwise take "the first one on
  the warehouse's list" *(dlt)*. A warehouse named by `DATABRICKS_WAREHOUSE_ID`, or by an
  `http_path` in dlt's config, counts. `prepare()` alone, which is what a notebook calls,
  says that dlt will choose and goes on: on a cluster dlt takes the cluster. *(decided; run
  from a laptop)*
- **R8 — The project's `config.toml` is read in a job as on a laptop.** dlt looks for `.dlt/`
  in the working directory, which in a job is a home directory on the machine *(run)*. The
  project's wheel carries its `.dlt/config.toml`, and `prepare()` points dlt at it with
  `DLT_PROJECT_DIR` when the working directory has no `.dlt/` of its own and the variable
  isn't set. On a laptop dlt finds the file as it always did. *(decided; dlt for the
  variable; run)*
- **R8a — A `secrets.toml` never rides along.** A wheel with a `secrets.toml` in it is
  refused when a run starts on Databricks, by name, before anything is read from it.
  *(decided)*
- **R9 — One identity, and leeghwater never holds it.** Whoever the Databricks SDK finds —
  the profile on a laptop, the run's own identity on Databricks — is who reads the secrets
  and who loads the data. dlt's Databricks destination makes its own client with the SDK's
  default sign-in *(dlt)*, so `--profile` is handed on as `DATABRICKS_CONFIG_PROFILE` and
  both end up at the same workspace as the same identity. leeghwater reads no token and
  passes none. *(decided; run from a laptop)*
- **R10 — The schemas are named by the run, and used as named.** *(decided; dlt for the two
  settings; run)*
  - A run that names its schema turns dlt's normalizing of the dataset name off
    (`enable_dataset_name_normalization`). A bundle may deploy a schema as `github__anna`;
    normalized, dlt loads into `github_anna`, a schema nobody deployed.
  - dlt stages a merge through `<name>_staging`. For `github__anna` that is
    `github__anna_staging`, while the bundle deployed `github_staging__anna`: dlt would make
    a schema of its own, outside the bundle's grants and its cleanup. `--staging-schema` is
    given to dlt as the layout itself; without a `%s` dlt takes a layout as the whole name.
    A name with `%s` in it is refused.
  - On Databricks a run that names its schema and no staging schema stops, and the error
    shows the lines of the job that pass it.

  Run for real: with `leeghwater_it__anna` and `leeghwater_it_staging__anna`, the load went
  into exactly those two schemas and no third was made.
- **R11 — The first lines of a run say what was set up.** Where it runs and on which
  runtime; the workspace; the destination, the catalog, the schemas and the warehouse; what
  was done about the name `dlt`; where dlt's config was found; where its working files go;
  the scopes that will be read and the secrets pointed at, by name. `doctor` prints the same
  and runs nothing. No value of a secret, and no token.
  → [000/R9](000-what-leeghwater-is.md#what-it-does) *(decided)*
- **R12 — What it is built for, and what it brings.** Python 3.11 and later. dlt 1.30 and
  later, below 2: the secrets provider is a subclass of dlt's `VaultDocProvider`, which dlt
  doesn't promise to keep as it is, and a comment beside the bound says so. Besides dlt: the
  Databricks SDK and typer, with low bounds. Which dlt extras a project installs is the
  project's. *(decided)*

## Not in this spec

- **An init script,** or anything else that changes a cluster. R4.
- **A place for dlt's working files.** dlt picks one itself: under the home directory, and
  in a temporary directory when that can't be written *(dlt)*. In a serverless wheel task
  the home directory was writable *(run)*. They are thrown away with the machine, and dlt
  brings its state back from the destination at the next run.
- **Cluster policies, pools, instance types.** The job's.
- **Which volume dlt stages in.** dlt's own config. It makes a volume named
  `_dlt_staging_load_volume` in the schemas it loads into *(run)*.

## To verify

Not tried on 2026-10-07:

1. **A full load from a serverless job.** On the test workspace the upload to
   `<region>.storage.cloud.databricks.com` was refused from serverless compute: its outbound
   network is limited. Everything before the upload ran. To try on a workspace with ordinary
   outbound access.
2. **A notebook,** through `prepare()`: the name `dlt`, the cluster as the warehouse, the
   working directory.
3. **A job on a classic cluster:** the same, and what `DATABRICKS_RUNTIME_VERSION` holds.
4. **That a non-zero exit fails a wheel task.** An exception does; on Databricks leeghwater
   raises for that reason.
5. **Other serverless environment versions** than the one a new job got that day.

## Done when

In the tests, on a made-up Databricks — the variable set, a stand-in hook in the import
machinery, and a stand-in `dlt` — all of these pass:

- after `prepare()`, `import dlt` gives dltHub's, and a second `prepare()` changes nothing;
- with the hook missing, `prepare()` goes on and says so;
- on a laptop nothing is touched, and the first lines say that;
- a wheel with a `secrets.toml` is refused;
- `DLT_PROJECT_DIR` is set when it should be and left alone when the project set it;
- a run through the app with no warehouse named stops before the pipeline is called;
- a schema named `github__anna` is the dataset dlt is given, unchanged, and the staging
  dataset is the name that was given; a staging name with `%s`, and on Databricks a schema
  without a staging schema, are refused;
- the first lines of a run, and `doctor`, say every item of R11 and no secret.

And on a workspace: the table under [Run on a workspace](README.md#run-on-a-workspace).
