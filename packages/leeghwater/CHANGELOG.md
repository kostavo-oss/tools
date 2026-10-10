# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

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
