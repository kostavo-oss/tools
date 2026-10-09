"""What `prepare()` sets up, on a laptop and on a made-up Databricks. `spec/002`."""

import logging
import os
import sys

import dlt
import pytest

from leeghwater import LeeghwaterError, prepare
from leeghwater._prepare import prepare_process, prepare_run
from leeghwater.secrets import DatabricksSecretsProvider


def _scopes() -> list[str]:
    return [
        provider.scope
        for provider in dlt.secrets.config_providers
        if isinstance(provider, DatabricksSecretsProvider)
    ]


def test_on_a_laptop_it_loads_locally_and_reads_no_scope(workspace):
    setup = prepare(secret_scopes=["ingest"], workspace_client=workspace)

    assert setup.destination == "duckdb"
    assert _scopes() == []
    assert workspace.lists == []
    said = "\n".join(setup.lines())
    assert "a laptop" in said
    assert "no secret scope is read on a laptop without --profile" in said
    assert "nothing to do off Databricks" in said


def test_with_a_profile_a_laptop_loads_into_the_workspace(workspace):
    setup = prepare(profile="dev", secret_scopes=["ingest"], workspace_client=workspace)

    assert setup.destination == "databricks"
    assert os.environ["DATABRICKS_CONFIG_PROFILE"] == "dev"
    assert _scopes() == ["ingest"]
    assert "profile dev" in "\n".join(setup.lines())


def test_on_databricks_it_loads_into_databricks_and_reads_the_scopes(
    on_databricks, workspace
):
    setup = prepare(
        secret_scopes=["ingest", "platform-shared"], workspace_client=workspace
    )

    assert setup.destination == "databricks"
    assert _scopes() == ["ingest", "platform-shared"]
    said = "\n".join(setup.lines())
    assert "serverless" in said
    assert "ingest, platform-shared" in said


def test_a_profile_is_refused_on_databricks(on_databricks):
    with pytest.raises(LeeghwaterError, match="--profile is for a laptop"):
        prepare(profile="dev")


def test_a_second_call_changes_nothing(on_databricks, workspace):
    """`spec/002`, R2."""
    arguments = dict(
        secret_scopes=["ingest"],
        secrets={"a.b": "ingest/x"},
        catalog="main",
        schema="github__anna",
        staging_schema="github_staging__anna",
        warehouse="abc123",
        workspace_client=workspace,
    )
    first = prepare(**arguments)
    environment = dict(os.environ)
    providers = [provider.name for provider in dlt.secrets.config_providers]

    second = prepare(**arguments)

    assert dict(os.environ) == environment
    assert [provider.name for provider in dlt.secrets.config_providers] == providers
    assert second.lines() == first.lines()


def test_a_later_call_decides_again_from_scratch():
    """Nothing from an earlier call is kept: there is no state but the last Setup."""
    first = prepare(profile="dev", schema="s", staging_schema="t", warehouse="w", limit=2)
    assert (first.destination, first.schema, first.limit) == ("databricks", "s", 2)

    second = prepare()

    assert (second.destination, second.schema, second.staging_schema) == (
        "duckdb",
        None,
        None,
    )
    assert (second.warehouse, second.limit) == (None, 0)


def test_no_destination_leaves_it_to_dlt():
    assert prepare(local_destination=None).destination is None


def test_a_schema_is_given_to_dlt_as_it_is(on_databricks):
    """`spec/002`, R12 and R13: no normalized name, and no derived staging name."""
    setup = prepare(schema="github__anna", staging_schema="github_staging__anna")

    assert (setup.schema, setup.staging_schema) == (
        "github__anna",
        "github_staging__anna",
    )
    assert "DATASET_NAME" not in os.environ


def test_on_databricks_a_schema_needs_its_staging_schema(on_databricks):
    with pytest.raises(LeeghwaterError, match="without --staging-schema") as error:
        prepare(schema="github__anna")

    assert "github__anna_staging" in str(error.value)
    assert "${resources.schemas." in str(error.value)


def test_locally_a_schema_alone_is_enough():
    assert prepare(schema="github__anna").schema == "github__anna"


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ({"schema": "s", "staging_schema": "s_%s"}, "a %s in it"),
        ({"schema": "s", "staging_schema": " "}, "--staging-schema is empty"),
        ({"schema": ""}, "--schema is empty"),
        ({"log_level": "LOUD"}, "--log-level is one of"),
        ({"config": {"a..b": "1"}}, "not a dlt config name"),
    ],
)
def test_what_is_refused(arguments, message):
    with pytest.raises(LeeghwaterError, match=message):
        prepare(**arguments)


def test_a_warehouse_is_kept_as_its_id_and_its_path(on_databricks):
    setup = prepare(warehouse="abc123")

    assert setup.warehouse == "abc123"
    assert setup.http_path == "/sql/1.0/warehouses/abc123"


def test_a_run_through_the_app_stops_without_a_warehouse(on_databricks):
    """`spec/002`, R7: dlt would take the first warehouse on the workspace's list."""
    with pytest.raises(LeeghwaterError, match="No SQL warehouse is named"):
        prepare_run(prepare_process(), require_warehouse=True)


def test_a_notebook_is_told_that_dlt_will_choose(on_databricks):
    assert "no warehouse is named" in "\n".join(prepare().lines())


def test_a_warehouse_named_another_way_counts(on_databricks, monkeypatch):
    monkeypatch.setenv("DATABRICKS_WAREHOUSE_ID", "from-the-sdk")
    by_sdk = prepare_run(prepare_process(), require_warehouse=True)
    monkeypatch.delenv("DATABRICKS_WAREHOUSE_ID")
    monkeypatch.setenv("DESTINATION__DATABRICKS__CREDENTIALS__HTTP_PATH", "/sql/x")
    by_dlt = prepare_run(prepare_process(), require_warehouse=True)

    assert "from-the-sdk" in by_sdk.http_path
    assert "/sql/x" in by_dlt.http_path


def test_locally_no_warehouse_is_asked_for():
    assert prepare_run(prepare_process(), require_warehouse=True).warehouse is None


def test_a_catalog_and_any_config_value_reach_dlt(on_databricks):
    setup = prepare(catalog="main", config={"sources.orders.page_size": "50"})

    assert setup.catalog == "main"
    assert dlt.config["sources.orders.page_size"] == 50
    assert setup.config == ["sources.orders.page_size"]


def test_the_log_level_is_dlts_and_stays_after_dlt_makes_its_logger_again():
    from dlt.common import logger

    from leeghwater import _dlt

    prepare(log_level="debug")

    assert os.environ["RUNTIME__LOG_LEVEL"] == "DEBUG"
    assert logger.LOGGER.level == logging.DEBUG
    _dlt.apply_log_level()
    assert logger.LOGGER.level == logging.DEBUG


def _project(tmp_path, monkeypatch, name, files):
    package = tmp_path / "site" / name
    (package / ".dlt").mkdir(parents=True)
    (package / "__init__.py").write_text("")
    for file, text in files.items():
        (package / ".dlt" / file).write_text(text)
    monkeypatch.syspath_prepend(str(tmp_path / "site"))
    return package


def test_a_wheels_config_is_found_where_the_working_directory_has_none(
    tmp_path, monkeypatch
):
    """`spec/002`, R5: in a job the working directory is not the project."""
    package = _project(
        tmp_path,
        monkeypatch,
        "wheel_a",
        {"config.toml": "[sources.orders]\npage_size = 7\n"},
    )

    setup = prepare(project="wheel_a.pipelines")

    assert os.environ["DLT_PROJECT_DIR"] == str(package)
    assert dlt.config["sources.orders.page_size"] == 7
    assert setup.config_dir == str(package / ".dlt")
    assert "wheel_a" not in sys.modules


def test_a_config_in_the_working_directory_is_left_to_dlt(tmp_path, monkeypatch):
    _project(tmp_path, monkeypatch, "wheel_b", {"config.toml": "x = 1\n"})
    (tmp_path / ".dlt").mkdir()

    prepare(project="wheel_b")

    assert "DLT_PROJECT_DIR" not in os.environ


def test_a_project_dir_that_was_set_is_left(tmp_path, monkeypatch):
    _project(tmp_path, monkeypatch, "wheel_c", {"config.toml": "x = 1\n"})
    monkeypatch.setenv("DLT_PROJECT_DIR", "/somewhere/else")

    prepare(project="wheel_c")

    assert os.environ["DLT_PROJECT_DIR"] == "/somewhere/else"


def test_a_wheel_with_a_secrets_toml_is_refused_on_databricks(
    tmp_path, monkeypatch, on_databricks
):
    """`spec/002`, R5a. Refused by name, before anything is read from it."""
    _project(tmp_path, monkeypatch, "wheel_d", {"secrets.toml": 'token = "t0p-s3cret"\n'})

    with pytest.raises(LeeghwaterError, match="carries a secrets.toml") as error:
        prepare(project="wheel_d")

    assert "t0p-s3cret" not in str(error.value)


def test_a_project_that_is_not_installed_is_no_error():
    assert prepare(project="no_such_project_anywhere").destination == "duckdb"


def test_the_first_lines_say_everything_and_no_secret(on_databricks, workspace):
    """`spec/002`, R9, and `spec/003`, R8."""
    setup = prepare(
        secret_scopes=["ingest"],
        secrets={"sources.github.access_token": "platform-shared/github-token"},
        catalog="main",
        schema="github__anna",
        staging_schema="github_staging__anna",
        warehouse="abc123",
        log_level="INFO",
        workspace_client=workspace,
    )
    assert dlt.secrets["sources.github.access_token"] == "tok-from-platform"

    said = "\n".join(setup.lines())

    for expected in (
        "Databricks, serverless, runtime client.2.5",
        "as the run's own identity",
        "databricks",
        "main",
        "github__anna",
        "github_staging__anna",
        "abc123",
        "dlt was imported already, and it is dltHub's",
        "dlt's config",
        "dlt's files",
        "INFO",
        "ingest",
        "sources.github.access_token is platform-shared/github-token",
    ):
        assert expected in said
    assert "tok-from" not in said
    assert "tok-from" not in str(setup.as_dict())
    assert "tok-from-platform" not in os.environ.values()
