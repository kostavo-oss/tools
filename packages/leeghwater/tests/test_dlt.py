"""One test per place leeghwater reaches into dlt: `src/leeghwater/_dlt.py`. DLT-2.

When a dlt upgrade breaks one of these, that is the place to look, and the only one.
"""

import inspect
import logging
import os
import re
from importlib.metadata import requires
from pathlib import Path

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
    """SEC-1."""
    provider = _Canary()
    before = [p.name for p in _dlt.registered_providers()]

    _dlt.register_provider(provider)

    assert [p.name for p in _dlt.registered_providers()] == [*before, "canary"]
    with pytest.raises(DuplicateConfigProviderException):
        _dlt.register_provider(provider)


def test_a_destination_takes_its_config_fields_in_the_call(monkeypatch):
    """DST-6.

    The call wins over dlt's config: tried with the two fields leeghwater sets.
    """
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


def test_every_reach_into_dlt_has_a_canary():
    """DLT-2. A function added to `_dlt.py` gets a test in this file that calls it."""
    reaches = [
        name
        for name, value in vars(_dlt).items()
        if inspect.isfunction(value)
        and value.__module__ == _dlt.__name__
        and not name.startswith("_")
    ]
    here = Path(__file__).read_text(encoding="utf-8")

    assert reaches
    assert [name for name in reaches if f"_dlt.{name}(" not in here] == []


def test_only_the_provider_modules_import_from_inside_dlt():
    """DLT-2.

    `import dlt` is the face dlt documents. `from dlt.common...` is inside it.
    """
    inside = re.compile(r"^\s*(?:from|import)\s+dlt\.", re.MULTILINE)
    source = Path(_dlt.__file__).parent

    importing = sorted(
        file.name
        for file in source.glob("*.py")
        if inside.search(file.read_text(encoding="utf-8"))
    )

    assert importing == ["_dlt.py", "keyvault.py", "secrets.py"]


def _project(requirement: str) -> str:
    name = re.match(r"[A-Za-z0-9_.-]+", requirement)
    assert name, requirement
    return name.group(0).lower()


def test_dlt_is_the_one_dependency_with_an_upper_bound():
    """DLT-3.

    leeghwater is installed on compute it does not own, beside a project's own dlt:
    few dependencies, each with a lower bound. The provider's base class in dlt is why
    dlt alone is capped."""
    needed = requires("leeghwater") or []
    always = [r for r in needed if "extra ==" not in r]
    extra = [r for r in needed if "extra ==" in r]

    assert sorted(map(_project, always)) == ["databricks-sdk", "dlt", "typer"]
    assert [_project(r) for r in always if "<" in r] == ["dlt"]
    assert sorted(map(_project, extra)) == ["azure-identity", "azure-keyvault-secrets"]
    assert all("keyvault" in r and "<" not in r for r in extra)
