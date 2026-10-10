"""`create_pipeline` and `run`, a run's dlt pipeline made by leeghwater: the RUN rules."""

import dlt
import duckdb
import pytest

import leeghwater
from leeghwater import LeeghwaterError, RunFailed, prepare


@dlt.resource
def pages():
    yield [{"id": 1}, {"id": 2}]
    yield [{"id": 3}]
    yield [{"id": 4}]


def _count(database: str, table: str) -> int:
    with duckdb.connect(database, read_only=True) as connection:
        return connection.sql(f"select count(*) from {table}").fetchone()[0]


def test_the_pipeline_is_dlts_own_with_what_the_run_named():
    """RUN-1."""
    prepare(schema="shop__anna", staging_schema="shop_staging__anna")

    pipeline = leeghwater.create_pipeline("orders")

    assert isinstance(pipeline, dlt.Pipeline)
    assert pipeline.dataset_name == "shop__anna"
    assert pipeline.destination.destination_type.endswith("duckdb")


def test_the_run_wins_over_the_schema_in_the_code():
    """RUN-1."""
    prepare(schema="asked")

    assert leeghwater.create_pipeline("orders", schema="default").dataset_name == "asked"


def test_the_schema_in_the_code_is_for_a_run_that_names_none():
    """RUN-1."""
    prepare()

    assert leeghwater.create_pipeline("orders", schema="shop").dataset_name == "shop"
    assert leeghwater.create_pipeline("plain").dataset_name == "plain_dataset"


def test_without_prepare_it_refuses():
    """RUN-3."""
    with pytest.raises(LeeghwaterError, match="call leeghwater.prepare"):
        leeghwater.create_pipeline("orders")


def test_a_setup_can_be_given_instead_of_the_last_one():
    """RUN-3."""
    prepare(schema="last")
    other = prepare(schema="other")
    prepare(schema="last")

    assert leeghwater.create_pipeline("orders", setup=other).dataset_name == "other"


def test_what_the_run_named_is_set_on_the_destination_itself(on_databricks):
    """DST-3, DST-4, DST-6. In the call, where dlt takes it first; no environment."""
    from leeghwater._pipeline import _destination

    setup = prepare(
        catalog="main",
        schema="shop__anna",
        staging_schema="shop_staging__anna",
        warehouse="w1",
    )

    config = _destination(setup).config_params

    assert config["credentials"] == {
        "catalog": "main",
        "http_path": "/sql/1.0/warehouses/w1",
    }
    assert config["staging_dataset_name_layout"] == "shop_staging__anna"
    assert config["enable_dataset_name_normalization"] is False
    assert not any(k.startswith("DESTINATION") for k in __import__("os").environ)


def test_what_the_run_did_not_name_is_left_to_dlts_config(on_databricks):
    """DST-3."""
    from leeghwater._pipeline import _destination

    config = _destination(prepare(warehouse="w1")).config_params

    assert config == {"credentials": {"http_path": "/sql/1.0/warehouses/w1"}}


def test_no_destination_leaves_it_to_dlt(monkeypatch):
    """DST-2."""
    monkeypatch.setenv("DESTINATION_TYPE", "duckdb")
    prepare(local_destination=None)

    pipeline = leeghwater.create_pipeline("orders", schema="shop")

    assert pipeline.destination.destination_type.endswith("duckdb")


@pytest.mark.parametrize("argument", ["destination", "dataset_name"])
def test_what_is_the_runs_to_say_is_refused_in_the_call(argument):
    """RUN-2."""
    prepare()
    with pytest.raises(LeeghwaterError, match=f"takes no {argument}"):
        leeghwater.create_pipeline("orders", **{argument: "mine"})


def test_other_arguments_of_dlt_pipeline_are_passed_on():
    """RUN-2."""
    prepare()
    pipeline = leeghwater.create_pipeline("orders", dev_mode=True)

    assert pipeline.dev_mode is True


def test_duckdb_cannot_have_a_schema_named_like_its_file():
    """RUN-9."""
    prepare()
    with pytest.raises(LeeghwaterError, match="both named 'orders'"):
        leeghwater.create_pipeline("orders", schema="orders")


def test_run_loads_reports_and_returns_dlts_load_info(capsys):
    """RUN-4, RUN-6."""
    prepare()
    info = leeghwater.run(leeghwater.create_pipeline("orders", schema="shop"), pages())

    assert info.dataset_name == "shop"
    assert "done    pages" in capsys.readouterr().out
    assert _count("orders.duckdb", "shop.pages") == 4


def test_a_limit_is_so_many_pages_from_each_resource():
    """RUN-5. dlt's `add_limit` counts what a resource yields, not rows."""
    setup = prepare(limit=1)

    leeghwater.run(leeghwater.create_pipeline("orders", schema="shop"), pages())

    assert _count("orders.duckdb", "shop.pages") == 2
    assert "1 page(s) from each resource" in "\n".join(setup.lines())


def test_a_limit_needs_something_dlt_can_limit():
    """RUN-5."""
    prepare(limit=1)

    with pytest.raises(LeeghwaterError, match="--limit needs a dlt source or resource"):
        leeghwater.run(leeghwater.create_pipeline("orders"), [{"id": 1}])
    with pytest.raises(LeeghwaterError, match="--limit is 0 for everything"):
        prepare(limit=-1)


def test_arguments_of_pipeline_run_are_passed_on():
    """RUN-4."""
    prepare()
    pipeline = leeghwater.create_pipeline("orders", schema="shop")

    leeghwater.run(pipeline, [{"id": 1}], table_name="by_hand")

    assert _count("orders.duckdb", "shop.by_hand") == 1


def test_a_failed_load_job_is_raised_even_when_dlt_was_told_not_to(monkeypatch, capsys):
    """RUN-7."""
    prepare()
    monkeypatch.setenv("LOAD__RAISE_ON_FAILED_JOBS", "false")
    pipeline = leeghwater.create_pipeline("orders", schema="shop")
    leeghwater.run(pipeline, pages())
    with pipeline.sql_client() as client:
        client.execute_sql("DROP TABLE pages")
        client.execute_sql(
            "CREATE TABLE pages (id DATE, _dlt_load_id VARCHAR, _dlt_id VARCHAR)"
        )

    with pytest.raises(RunFailed, match="1 load job.s. failed, for: pages"):
        leeghwater.run(pipeline, pages())

    assert "FAILED  pages: " in capsys.readouterr().out
