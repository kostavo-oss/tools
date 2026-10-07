import os

import dlt

import leeghwater
from leeghwater import pipeline


@dlt.resource
def rows():
    yield [{"id": 1}]


@pipeline
def raises():
    raise RuntimeError("the source is down")


@pipeline
def fails_quietly():
    """A project that told dlt not to raise on a failed load job."""
    os.environ["LOAD__RAISE_ON_FAILED_JOBS"] = "false"
    p = leeghwater.create_pipeline("fails_quietly", schema="shop")
    leeghwater.run(p, rows())
    # Break the table behind dlt's back, so the next load job fails at the destination.
    with p.sql_client() as client:
        client.execute_sql("DROP TABLE rows")
        client.execute_sql(
            "CREATE TABLE rows (id DATE, _dlt_load_id VARCHAR, _dlt_id VARCHAR)"
        )
    return leeghwater.run(p, rows())


@pipeline
def calls_dlt_itself():
    """A pipeline written the way every dlt example on the web is written."""
    return dlt.pipeline("own", destination="duckdb", dataset_name="mine").run(rows())


@pipeline
def returns_nothing():
    leeghwater.run(leeghwater.create_pipeline("returns_nothing"), rows())


@pipeline
def runs_nothing():
    return "done"


@pipeline
def reads_config():
    print("page_size is", dlt.config["sources.orders.page_size"])
    leeghwater.run(leeghwater.create_pipeline("reads_config"), rows())
