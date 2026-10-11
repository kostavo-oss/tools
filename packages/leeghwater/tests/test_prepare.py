"""What `prepare()` sets up, on a laptop and on a made-up Databricks: PRE, DBX, DST."""

import logging
import os
import sys

import dlt
import pytest

from conftest import FakeWorkspace
from leeghwater import LeeghwaterError, prepare
from leeghwater._prepare import current, prepare_process, prepare_run
from leeghwater.secrets import DatabricksSecretsProvider


def _scopes() -> list[str]:
    return [
        provider.scope
        for provider in dlt.secrets.config_providers
        if isinstance(provider, DatabricksSecretsProvider)
    ]


def test_on_a_laptop_it_loads_locally_and_reads_no_scope(workspace):
    """DST-1."""
    setup = prepare(secret_scopes=["ingest"], workspace_client=workspace)

    assert setup.destination == "duckdb"
    assert _scopes() == []
    assert workspace.lists == []
    said = "\n".join(setup.lines())
    assert "a laptop" in said
    assert "no secret scope is read on a laptop without --profile" in said
    assert "nothing to do off Databricks" in said


def test_with_a_profile_a_laptop_loads_into_the_workspace(workspace):
    """PRE-4, DBX-5, DST-1."""
    setup = prepare(profile="dev", secret_scopes=["ingest"], workspace_client=workspace)

    assert setup.destination == "databricks"
    assert os.environ["DATABRICKS_CONFIG_PROFILE"] == "dev"
    assert _scopes() == ["ingest"]
    assert "profile dev" in "\n".join(setup.lines())


def _workspace_line(setup) -> str | None:
    found = [line for line in setup.lines() if line.split()[0] == "workspace"]
    return found[0].split(None, 1)[1] if found else None


def test_a_profile_is_named_only_when_the_run_uses_it(workspace, monkeypatch):
    """PRE-7. The variable is the user's own, set for any tool that reads it: it does
    not decide where a run loads, and the first lines do not say that it did."""
    neither = prepare(secret_scopes=["ingest"], workspace_client=workspace)

    assert (neither.profile, _workspace_line(neither)) == (None, None)
    assert "  note: pipelines load into duckdb, here; give --profile to load" in (
        "\n".join(neither.lines())
    )

    monkeypatch.setenv("DATABRICKS_CONFIG_PROFILE", "mine")
    unused = prepare(secret_scopes=["ingest"], workspace_client=workspace)

    assert unused.destination == "duckdb"
    assert (_scopes(), workspace.lists) == ([], [])
    assert (unused.profile, _workspace_line(unused)) == (None, None)
    said = "\n".join(unused.lines())
    assert "secret scopes    none read" in said
    assert (
        "  note: pipelines load into duckdb, here; the profile in"
        " DATABRICKS_CONFIG_PROFILE (mine) is not used: give --profile to load into a"
        " workspace"
    ) in said
    assert os.environ["DATABRICKS_CONFIG_PROFILE"] == "mine"

    given = prepare(profile="dev", secret_scopes=["ingest"], workspace_client=workspace)

    assert given.destination == "databricks"
    assert (given.profile, _workspace_line(given)) == ("dev", "profile dev")
    assert "mine" not in "\n".join(given.lines())

    # A run that has its profile and loads elsewhere is not told to give one.
    elsewhere = prepare(profile="dev", destination="duckdb", workspace_client=workspace)

    assert elsewhere.notes == ["pipelines load into duckdb"]
    assert _workspace_line(elsewhere) == "profile dev"


def test_a_profile_in_the_environment_is_named_when_the_run_loads_with_it(monkeypatch):
    """PRE-7. An app whose laptop runs load into Databricks leaves the sign-in to the
    SDK, which reads the variable: `databricks/sdk/config.py`, the `profile` attribute
    with `env="DATABRICKS_CONFIG_PROFILE"`.
    https://docs.databricks.com/aws/en/dev-tools/auth/unified-auth"""
    monkeypatch.setenv("DATABRICKS_CONFIG_PROFILE", "mine")
    setup = prepare(local_destination="databricks", warehouse="abc123")

    assert (setup.profile, _workspace_line(setup)) == ("mine", "profile mine")
    assert "is not used" not in "\n".join(setup.lines())

    # A run that leaves the destination to dlt's config claims neither.
    setup = prepare(local_destination=None)

    assert (setup.profile, _workspace_line(setup)) == (None, None)
    assert "mine" not in "\n".join(setup.lines())


def test_a_catalog_and_a_warehouse_are_named_only_when_the_run_loads_into_databricks(
    workspace,
):
    """PRE-8. An app names its catalog and its warehouse once, for every run. A load
    into DuckDB goes into no catalog and through no warehouse."""
    labels = ("catalog", "warehouse")
    named = dict(catalog="main", warehouse="abc123")

    def lines(setup) -> dict[str, str]:
        said = (line.split(None, 1) for line in setup.lines() if "note:" not in line)
        return {label: value for label, value in said if label in labels}

    for local in (prepare(**named), prepare(**named, local_destination=None)):
        assert (local.catalog, local.warehouse, local.http_path) == (None, None, None)
        assert lines(local) == {}
        assert "main" not in "\n".join(local.lines())
        assert "abc123" not in "\n".join(local.lines())

    loads = prepare(**named, profile="dev", workspace_client=workspace)

    assert (loads.catalog, loads.warehouse) == ("main", "abc123")
    assert lines(loads) == {"catalog": "main", "warehouse": "abc123"}

    # With its profile, and loading elsewhere: the scopes are read, and no warehouse.
    elsewhere = prepare(
        **named, profile="dev", destination="duckdb", workspace_client=workspace
    )

    assert (elsewhere.catalog, elsewhere.warehouse, lines(elsewhere)) == (None, None, {})


def test_on_databricks_it_loads_into_databricks_and_reads_the_scopes(
    on_databricks, workspace
):
    """DST-1."""
    setup = prepare(
        secret_scopes=["ingest", "platform-shared"], workspace_client=workspace
    )

    assert setup.destination == "databricks"
    assert _scopes() == ["ingest", "platform-shared"]
    said = "\n".join(setup.lines())
    assert "serverless" in said
    assert "ingest, platform-shared" in said


def test_a_profile_is_refused_on_databricks(on_databricks):
    """DBX-5."""
    with pytest.raises(LeeghwaterError, match="--profile is for a laptop"):
        prepare(profile="dev")


VAULT = "https://kv-ingest.vault.azure.net"


def _providers() -> list[str]:
    return [provider.name for provider in dlt.secrets.config_providers]


def _dlt_level() -> int:
    from dlt.common import logger

    return logger.LOGGER.level


def test_a_second_call_changes_nothing(on_databricks, workspace, tmp_path, monkeypatch):
    """PRE-2. Everything a call can leave is asked for, and asked for again."""
    _project(tmp_path, monkeypatch, "wheel_twice", {"config.toml": "x = 1\n"})
    arguments = dict(
        project="wheel_twice",
        secret_scopes=["ingest"],
        secrets={"a.b": "ingest/x"},
        key_vaults=[VAULT],
        key_vault_client=object(),
        catalog="main",
        schema="github__anna",
        staging_schema="github_staging__anna",
        warehouse="abc123",
        log_level="ERROR",
        limit=2,
        config={"sources.orders.page_size": "50"},
        workspace_client=workspace,
    )
    first = prepare(**arguments)
    environment = dict(os.environ)
    providers = _providers()

    second = prepare(**arguments)

    assert dict(os.environ) == environment
    assert _providers() == providers
    assert second.lines() == first.lines()
    assert second.as_dict() == first.as_dict()
    assert _dlt_level() == logging.ERROR
    assert dlt.config["sources.orders.page_size"] == 50


def test_a_later_call_leaves_nothing_of_an_earlier_one(workspace, tmp_path, monkeypatch):
    """PRE-3. The earlier call sets all a call can set, and the later one nothing."""
    package = _project(
        tmp_path,
        monkeypatch,
        "wheel_before",
        {"config.toml": "[sources.orders]\nregion = 'eu'\n"},
    )
    alone = prepare()
    environment, providers, level = dict(os.environ), _providers(), _dlt_level()

    first = prepare(
        project="wheel_before",
        profile="dev",
        secret_scopes=["ingest"],
        secrets={"sources.github.access_token": "platform-shared/github-token"},
        key_vaults=[VAULT],
        key_vault_client=object(),
        schema="s",
        staging_schema="t",
        warehouse="w",
        log_level="ERROR",
        limit=2,
        config={"sources.orders.page_size": "50"},
        workspace_client=workspace,
    )
    assert (first.destination, first.schema, first.limit) == ("databricks", "s", 2)
    assert {
        name: os.environ[name]
        for name in (
            "DATABRICKS_CONFIG_PROFILE",
            "DLT_PROJECT_DIR",
            "RUNTIME__LOG_LEVEL",
            "SOURCES__ORDERS__PAGE_SIZE",
        )
    } == {
        "DATABRICKS_CONFIG_PROFILE": "dev",
        "DLT_PROJECT_DIR": str(package),
        "RUNTIME__LOG_LEVEL": "ERROR",
        "SOURCES__ORDERS__PAGE_SIZE": "50",
    }
    assert len(_providers()) == len(providers) + 3
    assert _dlt_level() == logging.ERROR
    assert dlt.config["sources.orders.region"] == "eu"

    second = prepare()

    assert dict(os.environ) == environment
    assert _providers() == providers
    assert _scopes() == []
    assert second.as_dict() == alone.as_dict()
    assert second.lines() == alone.lines()
    assert "profile dev" not in "\n".join(second.lines())
    assert _dlt_level() == level
    assert dlt.config.get("sources.orders.page_size") is None
    assert dlt.config.get("sources.orders.region") is None
    assert current() is second


def test_a_later_call_with_other_settings_has_only_its_own(workspace, monkeypatch):
    """PRE-3. What the environment held before leeghwater set it is put back as it was,
    and what somebody set after leeghwater did is theirs."""
    monkeypatch.setenv("DATABRICKS_CONFIG_PROFILE", "mine")
    monkeypatch.setenv("SOURCES__ORDERS__PAGE_SIZE", "7")
    other = FakeWorkspace({"platform-shared": {"sources-orders-api_key": "from-other"}})

    prepare(
        profile="dev",
        secret_scopes=["ingest"],
        log_level="ERROR",
        config={"sources.orders.page_size": "50", "sources.orders.region": "eu"},
        workspace_client=workspace,
    )
    assert os.environ["SOURCES__ORDERS__PAGE_SIZE"] == "50"
    os.environ["SOURCES__ORDERS__REGION"] = "set by hand since"

    second = prepare(
        profile="prod",
        secret_scopes=["platform-shared"],
        config={"sources.orders.window": "3"},
        workspace_client=other,
    )

    assert os.environ["DATABRICKS_CONFIG_PROFILE"] == "prod"
    assert os.environ["SOURCES__ORDERS__PAGE_SIZE"] == "7"
    assert os.environ["SOURCES__ORDERS__WINDOW"] == "3"
    assert os.environ["SOURCES__ORDERS__REGION"] == "set by hand since"
    assert "RUNTIME__LOG_LEVEL" not in os.environ
    assert _dlt_level() != logging.ERROR
    assert _scopes() == ["platform-shared"]
    assert (second.profile, second.log_level) == ("prod", None)
    assert second.config == ["sources.orders.window"]
    # The scope is read with the later call's client, not the earlier one's.
    assert dlt.secrets["sources.orders.api_key"] == "from-other"
    assert workspace.lists == [] and other.lists == ["platform-shared"]

    prepare()
    assert os.environ["DATABRICKS_CONFIG_PROFILE"] == "mine"


def test_a_call_that_is_refused_leaves_no_setup_of_an_earlier_one(workspace):
    """PRE-6. Half of an earlier call and half of a refused one is no setup to load by."""
    providers = _providers()
    prepare(profile="dev", secret_scopes=["ingest"], workspace_client=workspace)

    with pytest.raises(LeeghwaterError, match="--log-level is one of"):
        prepare(profile="prod", config={"sources.orders.page_size": "50"}, log_level="x")

    with pytest.raises(LeeghwaterError, match="Nothing has prepared this process"):
        current()
    assert _scopes() == []

    prepare()
    assert "DATABRICKS_CONFIG_PROFILE" not in os.environ
    assert "SOURCES__ORDERS__PAGE_SIZE" not in os.environ
    assert _providers() == providers


def test_no_destination_leaves_it_to_dlt():
    """DST-2."""
    assert prepare(local_destination=None).destination is None


def test_a_schema_is_given_to_dlt_as_it_is(on_databricks):
    """DST-3, DST-6. No normalized name, and no derived staging name."""
    setup = prepare(schema="github__anna", staging_schema="github_staging__anna")

    assert (setup.schema, setup.staging_schema) == (
        "github__anna",
        "github_staging__anna",
    )
    assert "DATASET_NAME" not in os.environ


def test_on_databricks_a_schema_needs_its_staging_schema(on_databricks):
    """DST-7."""
    with pytest.raises(LeeghwaterError, match="without --staging-schema") as error:
        prepare(schema="github__anna")

    assert "github__anna_staging" in str(error.value)
    assert "${resources.schemas." in str(error.value)


def test_locally_a_schema_alone_is_enough():
    """DST-7."""
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
    """APP-7, DST-7."""
    with pytest.raises(LeeghwaterError, match=message):
        prepare(**arguments)


def test_a_warehouse_is_kept_as_its_id_and_its_path(on_databricks):
    """DST-4."""
    setup = prepare(warehouse="abc123")

    assert setup.warehouse == "abc123"
    assert setup.http_path == "/sql/1.0/warehouses/abc123"


def test_a_run_through_the_app_stops_without_a_warehouse(on_databricks):
    """DST-5. dlt would take the first warehouse on the workspace's list."""
    with pytest.raises(LeeghwaterError, match="No SQL warehouse is named"):
        prepare_run(prepare_process(), require_warehouse=True)


def test_a_notebook_is_told_that_dlt_will_choose(on_databricks):
    """DST-5."""
    assert "no warehouse is named" in "\n".join(prepare().lines())


def test_a_warehouse_named_another_way_counts(on_databricks, monkeypatch):
    """DST-5."""
    monkeypatch.setenv("DATABRICKS_WAREHOUSE_ID", "from-the-sdk")
    by_sdk = prepare_run(prepare_process(), require_warehouse=True)
    monkeypatch.delenv("DATABRICKS_WAREHOUSE_ID")
    monkeypatch.setenv("DESTINATION__DATABRICKS__CREDENTIALS__HTTP_PATH", "/sql/x")
    by_dlt = prepare_run(prepare_process(), require_warehouse=True)

    assert "from-the-sdk" in by_sdk.http_path
    assert "/sql/x" in by_dlt.http_path


def test_locally_no_warehouse_is_asked_for():
    """DST-5."""
    assert prepare_run(prepare_process(), require_warehouse=True).warehouse is None


def test_a_catalog_and_any_config_value_reach_dlt(on_databricks):
    """PRE-4."""
    setup = prepare(catalog="main", config={"sources.orders.page_size": "50"})

    assert setup.catalog == "main"
    assert dlt.config["sources.orders.page_size"] == 50
    assert setup.config == ["sources.orders.page_size"]


def test_the_log_level_is_dlts_and_stays_after_dlt_makes_its_logger_again():
    """PRE-4."""
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
    """PRE-4, DBX-7. In a job the working directory is not the project."""
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
    """DBX-7."""
    _project(tmp_path, monkeypatch, "wheel_b", {"config.toml": "x = 1\n"})
    (tmp_path / ".dlt").mkdir()

    prepare(project="wheel_b")

    assert "DLT_PROJECT_DIR" not in os.environ


def test_a_project_dir_that_was_set_is_left(tmp_path, monkeypatch):
    """DBX-7."""
    _project(tmp_path, monkeypatch, "wheel_c", {"config.toml": "x = 1\n"})
    monkeypatch.setenv("DLT_PROJECT_DIR", "/somewhere/else")

    prepare(project="wheel_c")

    assert os.environ["DLT_PROJECT_DIR"] == "/somewhere/else"


def test_a_wheel_with_a_secrets_toml_is_refused_on_databricks(
    tmp_path, monkeypatch, on_databricks
):
    """DBX-8, SEC-9. Refused by name, before anything is read from it."""
    _project(tmp_path, monkeypatch, "wheel_d", {"secrets.toml": 'token = "t0p-s3cret"\n'})

    with pytest.raises(LeeghwaterError, match="carries a secrets.toml") as error:
        prepare(project="wheel_d")

    assert "t0p-s3cret" not in str(error.value)


def test_a_project_that_is_not_installed_is_no_error():
    """DBX-7."""
    assert prepare(project="no_such_project_anywhere").destination == "duckdb"


def test_the_first_lines_say_everything_and_no_secret(on_databricks, workspace):
    """PRE-5, SEC-9."""
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
