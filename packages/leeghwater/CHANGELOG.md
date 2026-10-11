# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.1] - 2026-10-11

### Fixed

- **The first lines no longer name a profile the run does not use.** With
  `DATABRICKS_CONFIG_PROFILE` set in the shell and no `--profile`, a run on a laptop
  loads locally, as before, and its first lines and `doctor` said
  `workspace  profile <name>` all the same. That line is gone, `doctor --json` gives
  `"profile": null`, and the note says
  `the profile in DATABRICKS_CONFIG_PROFILE (<name>) is not used: give --profile to load into a workspace`.
  Where a run loads does not change.
- **The first lines no longer name a catalog and a warehouse the run does not use.** A
  run that loads locally showed the `catalog` and the `warehouse` the app or the run
  names, though it loads into no catalog and through no warehouse. Those lines are shown
  only for a run that loads into Databricks, and `doctor --json` gives null for
  `catalog`, `warehouse` and `http_path` otherwise. Where a run loads and what `doctor`
  checks do not change.
- A run that was given `--profile` and loads somewhere other than Databricks is no
  longer told to give `--profile`.

## [0.2.0] - 2026-10-11

### Added

- **`leeghwater.where()`** says where the process runs: on a laptop or on Databricks,
  and on which runtime. The function was there and could not be imported by that name.

### Changed

- **`doctor` checks what a run would read, wherever it would load.** A Key Vault is
  checked on a laptop without `--profile` too, where `doctor` used to check nothing. The
  sign-in and the secret scopes are checked for every run that reads a scope, also one
  that loads somewhere other than Databricks. When there is nothing to check it says
  `nothing to check: this run reads no workspace and no key vault`.
- **Every command's help is plain text.** The help of `run`, of a pipeline, of `list`
  and of `doctor` was drawn in boxes, which a job's log shows as box characters.

### Fixed

- A secret scope that is named and also pointed into with `--secret` is listed once in a
  run. It was listed twice, once for each.

- **A later `prepare()` starts from nothing.** A second call in one process, as in a
  notebook, kept what the first had set: its secret scopes and Key Vaults stayed
  registered with dlt, its profile, log level and `--set` values stayed in the
  environment, and a bare `prepare()` after `prepare(profile="dev")` said `profile dev`
  while it loaded locally. Now a call first takes back what the one before it set: the
  environment variables go back to what they held, and the scopes and vaults it
  registered are taken out of dlt.
- A `prepare()` that is refused leaves no setup behind. `create_pipeline` and `run` used
  to go on with the setup of the call before it.

## [0.1.1] - 2026-10-10

### Changed

- **leeghwater lives in `kostavo-oss/tools`**, one repository for the four Kostavo
  tools. The package and its name on PyPI are what they were. The links on PyPI point at
  the new place, and the docs are at `kostavo-oss.github.io/tools/leeghwater/`. From
  this release on a tag is `leeghwater-v<version>`.
- **The README says why leeghwater exists, when not to use it, and when you no longer
  need it**: the day dlt reads Databricks secret scopes by itself and runs in a job with
  nothing around it.
- typer 0.17.5 or newer, as for the other Kostavo tools: older typers mis-declare the
  `--json` flag. Found by the new lowest-dependencies CI job.

### Fixed

- A pipeline's parameter may be called `name`, `function` or `self`: `ingest run` failed
  with `TypeError: App._run_command() got multiple values for argument 'name'`, because
  the app's own method took arguments by those names.
- A parameter before a `/` in the pipeline's function is given by its place, not by
  name: it failed the run with a `TypeError` too.
- A parameter keeps its capitals with a typer before 0.21: `Since` was handed on as
  `since`, which the function does not take, and `Schema` was taken for the run's
  `--schema`.
- A parameter called `help` is refused when the app starts, as one named like an option
  of every run is: it took `--help` from its command.

## [0.1.0] — 2026-10-08

The first release. Run against a workspace on 2026-10-07; what was tried and what was not
is in `spec/README.md`.

### Added

- `App`: a project's command line, the same on a laptop and as a job's entry point, with
  `run`, `list`, `doctor` and the project's own commands.
- `@pipeline`: marks a function as a pipeline; its parameters become options.
- `create_pipeline()` and `run()`: the dlt pipeline of a run, made from what the run names
  (set on the destination, in the call), and a load that is reported, limited by
  `--limit`, and fails when a load job failed. A pipeline that makes no load with `run()`
  fails its run.
- `prepare()`: sets the process up for dlt, for a notebook or a script.
- `leeghwater.secrets`: dlt config providers that read Databricks secret scopes.
- `leeghwater.keyvault`: a dlt config provider that reads an Azure Key Vault, as the
  `keyvault` extra; `--key-vault` and `App(key_vaults=...)`.
