# leeghwater

**Your dlt pipeline, the same on your laptop and in a Databricks job.**
One command to run it, its secrets from a secret scope, and the things Databricks asks for
kept out of your code.

!!! note "Early"

    It has run as a serverless job and from a laptop against a real workspace. What was
    tried and what was not is in [Tried, and not yet](tried.md).

```sh
uv add leeghwater
uv run ingest run example
```

A dlt pipeline on Databricks tends to run only on a cluster. Every change is a deploy and
a wait, and the secrets are in one place on a laptop and another in a job. So nobody runs
the pipeline locally, and finding a typo takes ten minutes. leeghwater runs the same
pipeline on a laptop and in a job, with its secrets from one place.

A project is two files: an app, and a pipeline that makes its dlt pipeline with
`leeghwater.create_pipeline` and runs it with `leeghwater.run`. On a laptop that loads into
a local DuckDB file; the same command is the entry point of a Databricks job.

Read on: [a project](project.md), [where a run loads](run.md) and the options of every
run, [secrets](secrets.md), [a notebook and commands of your own](notebook.md),
[troubleshooting](troubleshooting.md), and [what was tried for real](tried.md).

## Where it fits

leeghwater is one of the [Kostavo tools](https://kostavo-oss.github.io/tools/): small
tools for the ugly gaps on Databricks, one gap each. Its gap is the pipeline that only
runs on a cluster. Each works alone.
[Why the tools exist](https://kostavo-oss.github.io/tools/why/) has the rules they keep,
and the README says
[when not to use it](https://github.com/kostavo-oss/tools/tree/main/packages/leeghwater#when-not-to-use-it)
and when you no longer need it.

## Named after

Jan Adriaanszoon Leeghwater — the millwright who drained the Beemster with windmills, dry in 1612. He moved water from where it lay to where it was wanted.

---

Community project, not affiliated with or endorsed by Databricks or dltHub.
