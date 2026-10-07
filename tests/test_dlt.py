"""One test per place leeghwater reaches into dlt: `src/leeghwater/_dlt.py`.

When a dlt upgrade breaks one of these, that is the place to look, and the only one.
"""

import logging
import os

import dlt
import pytest
from dlt.common.configuration.exceptions import DuplicateConfigProviderException
from dlt.common.configuration.providers import EnvironProvider

from leeghwater import _dlt


def test_the_config_locations_follow_dlt_project_dir(tmp_path, monkeypatch):
    (tmp_path / "elsewhere" / ".dlt").mkdir(parents=True)
    (tmp_path / "elsewhere" / ".dlt" / "config.toml").write_text("[sources]\nx = 1\n")
    assert dlt.config.get("sources.x") is None

    monkeypatch.setenv("DLT_PROJECT_DIR", str(tmp_path / "elsewhere"))
    _dlt.reload_config_locations()

    assert _dlt.settings_dir() == str(tmp_path / "elsewhere" / ".dlt")
    assert dlt.config["sources.x"] == 1


def test_the_data_dir_is_where_dlt_keeps_its_files():
    assert _dlt.data_dir() == os.environ["DLT_DATA_DIR"]


def test_a_changed_log_level_is_taken_up(monkeypatch):
    from dlt.common import logger

    monkeypatch.setenv("RUNTIME__LOG_LEVEL", "ERROR")
    _dlt.apply_log_level()

    assert logger.LOGGER.level == logging.ERROR


def test_a_config_value_by_its_dotted_name(monkeypatch):
    monkeypatch.setenv("DESTINATION__DATABRICKS__CREDENTIALS__HTTP_PATH", "/sql/x")

    assert _dlt.config_value("destination.databricks.credentials.http_path") == "/sql/x"
    assert _dlt.config_value("destination.databricks.credentials.catalog") is None


class _Canary(EnvironProvider):
    @property
    def name(self) -> str:
        return "canary"


def test_a_provider_is_registered_after_dlts_own_and_once():
    provider = _Canary()
    before = [p.name for p in _dlt.registered_providers()]

    _dlt.register_provider(provider)

    assert [p.name for p in _dlt.registered_providers()] == [*before, "canary"]
    with pytest.raises(DuplicateConfigProviderException):
        _dlt.register_provider(provider)


def test_a_destination_takes_its_config_fields_in_the_call(monkeypatch):
    """The call wins over dlt's config: tried with the two fields leeghwater sets."""
    monkeypatch.setenv("DESTINATION__STAGING_DATASET_NAME_LAYOUT", "from_env")

    factory = _dlt.destination(
        "duckdb",
        staging_dataset_name_layout="named",
        enable_dataset_name_normalization=False,
    )
    pipeline = dlt.pipeline("canary", destination=factory, dataset_name="shop__anna")
    pipeline.run([{"id": 1}], table_name="rows")
    client = pipeline.destination_client()

    assert client.config.staging_dataset_name_layout == "named"
    assert client.config.enable_dataset_name_normalization is False
    assert client.sql_client.dataset_name == "shop__anna"
    assert client.sql_client.staging_dataset_name == "named"


def test_failed_jobs_are_read_from_each_package():
    info = dlt.pipeline("canary", destination="duckdb").run(
        [{"id": 1}], table_name="rows"
    )

    assert _dlt.failed_jobs(info) == []
    assert info.load_packages[0].jobs["completed_jobs"]
