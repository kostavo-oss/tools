from leeghwater._where import where


def test_a_laptop_is_where_the_variable_is_not_set():
    here = where({})

    assert not here.on_databricks
    assert here.runtime is None
    assert not here.serverless
    assert "laptop" in here.describe()


def test_a_cluster_and_serverless_are_told_apart_by_the_runtime():
    cluster = where({"DATABRICKS_RUNTIME_VERSION": "16.4"})
    serverless = where({"DATABRICKS_RUNTIME_VERSION": "client.2.5"})

    assert cluster.on_databricks and not cluster.serverless
    assert serverless.on_databricks and serverless.serverless
    assert "16.4" in cluster.describe()
    assert "serverless" in serverless.describe()


def test_it_reads_the_process_environment_when_given_none(on_databricks):
    assert where().on_databricks


def test_importing_leeghwater_does_not_import_dlt():
    """`spec/002`, R2: on Databricks an early `import dlt` gets the wrong module."""
    import subprocess
    import sys

    code = "import sys, leeghwater; print('dlt' in sys.modules)"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)

    assert out.stdout.strip() == "False", out.stderr
