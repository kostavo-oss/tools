"""The dlt pipeline of a run, made and run by leeghwater. `spec/001`, R2.

A project's pipeline calls these two, and never `dlt.pipeline()` or `pipeline.run()`.
Where a run loads, into which schema and through which staging schema is the run's to say,
and only pipelines made here get it: a plain `dlt.pipeline()` loads wherever dlt's own
config says, and the app fails a run that made no pipeline here.
"""

from typing import Any

import typer

from leeghwater import _prepare
from leeghwater._errors import LeeghwaterError, RunFailed
from leeghwater._report import load_report

# How many loads `run` has made in this process: the app's check that a pipeline used it.
_runs = 0

_THE_RUNS = {
    "destination": "Where a pipeline loads is the run's to say: a local database on a"
    " laptop, Databricks in a job or with --profile. To load somewhere else, make the App"
    " with destination=... or local_destination=...",
    "dataset_name": "The schema is the run's to say (--schema). For the schema to use"
    " when a run names none, give create_pipeline(..., schema=...).",
}


def create_pipeline(
    pipeline_name: str,
    *,
    schema: str | None = None,
    setup: _prepare.Setup | None = None,
    **pipeline: Any,
) -> Any:
    """Make the dlt pipeline for this run: `dlt.pipeline(...)`, with what the run decided.

    The destination and the schema come from the run, not from this call. Anything else
    `dlt.pipeline` takes is passed on as it is.
    https://dlthub.com/docs/api_reference/dlt/pipeline/__init__#pipeline

    Args:
        pipeline_name: dlt's name for the pipeline. Its state is kept under this name.
        schema: The schema to load into when the run names none. `--schema` wins over it.
        setup: What a run decided. Default: the last `prepare()` in this process.
        **pipeline: Other arguments of `dlt.pipeline`, e.g. `staging` or `dev_mode`.
    """
    for name, why in _THE_RUNS.items():
        if name in pipeline:
            raise LeeghwaterError(f"create_pipeline() takes no {name}. {why}")
    setup = setup or _prepare.current()
    import dlt

    dataset = setup.schema or schema
    if dataset:
        if setup.destination == "duckdb" and dataset == pipeline_name:
            # DuckDB names its database after the file, and the file after the pipeline.
            raise LeeghwaterError(
                f"The pipeline and its schema are both named '{dataset}', and DuckDB"
                f" can't tell the schema from the database file {pipeline_name}.duckdb."
                " Locally, give the schema another name, or leave it out: dlt then loads"
                f" into '{pipeline_name}_dataset'."
            )
        pipeline["dataset_name"] = dataset
    if setup.destination:
        pipeline["destination"] = _destination(setup)
    return dlt.pipeline(pipeline_name, **pipeline)


def _destination(setup: _prepare.Setup) -> Any:
    """The destination factory for a run, with what the run named set in the call."""
    from leeghwater import _dlt

    config: dict[str, Any] = {}
    if setup.schema:
        # A name the bundle deployed is used as it is: `spec/002`, R10.
        config["enable_dataset_name_normalization"] = False
    if setup.staging_schema:
        # Without a `%s`, dlt takes the layout as the whole name.
        config["staging_dataset_name_layout"] = setup.staging_schema
    if setup.loads_into_databricks:
        credentials = {}
        if setup.catalog:
            credentials["catalog"] = setup.catalog
        if setup.warehouse:
            credentials["http_path"] = f"/sql/1.0/warehouses/{setup.warehouse}"
        if credentials:
            # The rest — host, sign-in — dlt takes from the Databricks SDK's default.
            config["credentials"] = credentials
    return _dlt.destination(setup.destination, **config)


def run(pipeline: Any, data: Any, **run: Any) -> Any:
    """Run a load, report it, and fail when a load job failed. Returns dlt's load info.

    This is `pipeline.run(data, ...)`, and anything it takes is passed on.
    https://dlthub.com/docs/api_reference/dlt/pipeline/pipeline#run

    A run's `--limit` is applied here, with dlt's `add_limit`: at most that many pages
    from each resource.
    """
    global _runs
    setup = _prepare.current()
    if setup.limit:
        if not hasattr(data, "add_limit"):
            raise LeeghwaterError(
                "--limit needs a dlt source or resource to limit, and run() was given a"
                f" {type(data).__name__}."
            )
        data = data.add_limit(setup.limit)

    load_info = pipeline.run(data, **run)
    _runs += 1

    typer.echo(load_report(load_info))
    raise_on_failed_jobs(load_info)
    return load_info


def runs_so_far() -> int:
    return _runs


def raise_on_failed_jobs(load_info: Any) -> None:
    """dlt raises on a failed load job by itself (`dlt/load/configuration.py`).

    This is for a project that turned that off: a green job with a table missing is the
    worst way for a run to end.
    """
    from leeghwater import _dlt

    failed = _dlt.failed_jobs(load_info)
    if failed:
        tables = ", ".join(sorted({job.job_file_info.table_name for job in failed}))
        raise RunFailed(f"{len(failed)} load job(s) failed, for: {tables}.")
