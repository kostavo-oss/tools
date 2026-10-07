import dlt

from leeghwater._report import _reason, _size, failed_jobs, is_load_info, load_report


@dlt.resource
def rows():
    yield [{"id": 1}, {"id": 2}]


def test_a_report_names_each_job_and_where_it_went():
    info = dlt.pipeline("report", destination="duckdb", dataset_name="shop").run(rows())

    report = load_report(info)

    assert is_load_info(info)
    assert failed_jobs(info) == []
    assert "load report" in report
    assert ": loaded" in report
    assert "done    rows" in report
    assert "insert_values" in report
    assert "schema       shop" in report
    assert "dlt.destinations.duckdb" in report
    assert "first run    yes" in report


def test_a_second_run_is_not_a_first_run():
    pipeline = dlt.pipeline("report_twice", destination="duckdb", dataset_name="shop")
    pipeline.run(rows())

    assert "first run" not in load_report(pipeline.run(rows()))


def test_sizes_read_like_sizes():
    assert _size(150) == "150 B"
    assert _size(2048) == "2.0 kB"
    assert _size(5 * 1024 * 1024) == "5.0 MB"
    assert _size(None) == "?"


def test_a_failed_job_is_one_line_not_a_traceback():
    message = (
        "Traceback (most recent call last):\n"
        '  File "x.py", line 1, in run\n'
        "_duckdb.ConversionException: Conversion Error: no cast\n"
        "\nThe above exception was the direct cause of the following exception:\n\n"
        "Traceback (most recent call last):\n"
        "dlt.destinations.exceptions.DatabaseTerminalException: Conversion Error: no"
        " cast\n"
        "\nLINE 3: (1);\n         ^\n"
    )

    assert _reason(message) == (
        "dlt.destinations.exceptions.DatabaseTerminalException: Conversion Error: no cast"
    )
    assert _reason("the table is gone") == "the table is gone"
    assert _reason(None) == "dlt gave no reason"
