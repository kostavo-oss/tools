# leeghwater

**Your dlt pipeline, the same on your laptop and in a Databricks job.**
One command to run it, its secrets from a secret scope, and the things Databricks asks for
kept out of your code.

[![ci](https://github.com/kostavo-oss/tools/actions/workflows/ci.yml/badge.svg)](https://github.com/kostavo-oss/tools/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/leeghwater.svg)](https://pypi.org/project/leeghwater/)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](https://github.com/kostavo-oss/tools/blob/main/packages/leeghwater/LICENSE)

> **Early.** It has run as a serverless job and from a laptop against a real workspace;
> what was tried and what was not is in
> [Tried, and not yet](https://kostavo-oss.github.io/tools/leeghwater/tried/).

leeghwater is a package your [dlt](https://dlthub.com) project imports. Your sources stay
ordinary dlt code. leeghwater gives the project a command line, and for each run it makes
the dlt pipeline from what the run names: a local file on a laptop, the schema your bundle
deployed in a job.

## Why

A dlt pipeline on Databricks tends to run only on a cluster. Every change is a deploy and
a wait, and the secrets are in one place on a laptop and another in a job. So nobody runs
the pipeline locally, and finding a typo takes ten minutes. With leeghwater the same
command runs the pipeline on a laptop into a local file and unchanged in a job, with its
secrets from one place.

## Quickstart

A project is two files and a line in `pyproject.toml`. This one needs no workspace: on a
laptop a run loads into a local DuckDB file.

```sh
uv init --package my-ingest && cd my-ingest
uv add leeghwater "dlt[duckdb]"
```

The app, which is the project's console script:

```python
# src/my_ingest/cli.py
from leeghwater import App

app = App(pipelines="my_ingest.pipelines")
```

```toml
# pyproject.toml: in place of the script `uv init` wrote
[project.scripts]
ingest = "my_ingest.cli:app"
```

And a pipeline: a function marked `@pipeline`, in the module the app names.

```python
# src/my_ingest/pipelines.py
import dlt
import leeghwater
from leeghwater import pipeline


@dlt.resource
def numbers(upto: int):
    yield [{"n": n} for n in range(upto)]


@pipeline
def example(upto: int = 3):
    """Load a few numbers."""
    p = leeghwater.create_pipeline("example")
    return leeghwater.run(p, numbers(upto))
```

```sh
uv run ingest list                      # the pipelines and their parameters
uv run ingest run example --upto 5      # run one, into example.duckdb
uv run ingest doctor                    # what would be set up, checked, nothing run
```

The same `ingest run example` is the entry point of a Databricks job, where it loads
into the schema the bundle deployed and reads its secrets from a secret scope.

## The docs

How to use it is in the [docs](https://kostavo-oss.github.io/tools/leeghwater/), and only there:

- [A project](https://kostavo-oss.github.io/tools/leeghwater/project/): the app, a pipeline, and why a pipeline calls
  `create_pipeline` and `run` and never `dlt.pipeline()`.
- [Start a project](https://kostavo-oss.github.io/tools/leeghwater/start/) from the template, or add leeghwater to one you have.
- [Where a run loads](https://kostavo-oss.github.io/tools/leeghwater/run/), [the options of every run](https://kostavo-oss.github.io/tools/leeghwater/run/#the-options-of-every-run),
  and [the job](https://kostavo-oss.github.io/tools/leeghwater/run/#in-a-job): the task, why the schemas are passed by reference,
  and when a run ends with an error.
- [Secrets](https://kostavo-oss.github.io/tools/leeghwater/secrets/): from a secret scope by dlt's name, a whole section in one
  secret, a secret under another name, and an Azure Key Vault.
- [A notebook, and commands of your own](https://kostavo-oss.github.io/tools/leeghwater/notebook/).
- [Troubleshooting](https://kostavo-oss.github.io/tools/leeghwater/troubleshooting/).

## Tried, and not yet

On 2026-10-07 a project ran as a serverless job on a workspace, and from a laptop with a
profile: the bundle, the secrets from a scope, a pipeline that fails its task, and from
the laptop a load into Unity Catalog. A full load from a serverless job, a notebook, a
classic cluster and a real Azure Key Vault have not been tried.

[Tried, and not yet](https://kostavo-oss.github.io/tools/leeghwater/tried/) is the
record: what held, what did not, and why.

## When not to use it

- **Lakeflow Connect has a connector for your source** and it does what you need.
- **dlt runs somewhere else** — Airflow, GitHub Actions — and only loads into Databricks.
  dlt does that alone.
- **The data needs Spark to move it.** dlt is Python on one machine, and leeghwater
  doesn't change that.

leeghwater is a library for one kind of code, dlt ingestion. It will not:

- deploy, schedule, or order one pipeline after another. That is a job's, and a bundle's;
- add a file format for pipelines, or patch anything in dlt;
- make, change or rotate secrets. That is the Databricks CLI's, and caland's;
- change tables, or set table properties and clustering. dlt's own `databricks_adapter`
  does the second, in your source;
- change anything on a cluster: no init script, no file outside the run's own
  directories.

## When you no longer need it

When dlt reads Databricks secret scopes by itself and runs in a job with nothing around
it — the right `dlt` imported, the bundle's schema names used as they are — use dlt
alone. Today dlt has no provider for secret scopes, and its Databricks
page gives workarounds for the import.

## Where it fits

leeghwater is one of the [Kostavo tools](https://github.com/kostavo-oss/tools): small tools for the ugly gaps on
Databricks, one gap each. Its gap is the pipeline that only runs on a cluster: every
change a deploy and a wait, and the secrets in one place on a laptop and another in a job.
Each works alone. Kostavo is the company behind them: it builds
[a governance platform for Databricks workspaces](https://kostavo.com), and the tools are
complete without it.

Community project, not affiliated with or endorsed by Databricks or dltHub.

## Named after

Jan Adriaanszoon Leeghwater — the millwright who drained the Beemster with windmills, dry in 1612. He moved water from where it lay to where it was wanted.

## License

[Apache-2.0](https://github.com/kostavo-oss/tools/blob/main/packages/leeghwater/LICENSE).
