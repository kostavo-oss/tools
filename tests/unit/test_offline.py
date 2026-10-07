"""The unit suite can't find a real Databricks CLI or workspace.

Hiding `databricks` from `PATH` was not enough: `DATABRICKS_CLI_PATH` is looked
at first, and a host and a token in the environment — or a DEFAULT profile in
`~/.databrickscfg` — are all the Databricks SDK needs to reach a workspace from
a test that only meant to see "not connected".
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest

from helpers import fake_databricks, offline_environment
from stevin.bundle import find_cli
from stevin.connect import Connection, NotConnected

if TYPE_CHECKING:
    from databricks.sdk import WorkspaceClient


def a_configured_laptop(tmp_path: Path) -> dict[str, str]:
    """Everything a developer's shell can hold that finds the real thing."""
    profiles = tmp_path / "databrickscfg"
    profiles.write_text(
        "[DEFAULT]\nhost = https://adb-1.azuredatabricks.net\ntoken = dapi-real\n"
    )
    on_path = fake_databricks(tmp_path / "on-path", "{}\n")
    named = fake_databricks(tmp_path / "named", "{}\n").split(os.pathsep)[0]
    return {
        "PATH": on_path,
        "DATABRICKS_CLI_PATH": str(Path(named) / "databricks"),
        "DATABRICKS_HOST": "https://adb-1.azuredatabricks.net",
        "DATABRICKS_TOKEN": "dapi-real",
        "DATABRICKS_CONFIG_PROFILE": "DEFAULT",
        "DATABRICKS_CONFIG_FILE": str(profiles),
        "DATABRICKS_WAREHOUSE_ID": "abc123",
        "HOME": str(tmp_path),
    }


def test_nothing_that_finds_the_real_thing_is_left(tmp_path: Path) -> None:
    laptop = a_configured_laptop(tmp_path)
    assert find_cli(environ=laptop) is not None, "the laptop does have a CLI"
    offline = offline_environment(laptop, tmp_path / "nowhere")
    assert [name for name in offline if name.startswith("DATABRICKS_")] == [
        "DATABRICKS_CONFIG_FILE"
    ]
    assert not Path(offline["DATABRICKS_CONFIG_FILE"]).exists()
    assert offline["HOME"] == laptop["HOME"], "the rest is left as it was"
    assert find_cli(environ=offline) is None


def test_a_configured_laptop_is_not_connected_in_a_unit_test(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The Databricks SDK itself, asked for a client with the laptop's
    environment after the fixture's treatment: it finds no host and no
    credentials, and nothing is sent anywhere."""
    laptop = a_configured_laptop(tmp_path)
    for name, value in offline_environment(laptop, tmp_path / "nowhere").items():
        monkeypatch.setenv(name, value)
    with pytest.raises(NotConnected, match="can't connect"):
        Connection(warehouse_id="w1")
    with pytest.raises(NotConnected, match="no SQL warehouse"):
        Connection(client=cast("WorkspaceClient", object()))


def test_every_unit_test_runs_that_way() -> None:
    """The fixture is on: what this very test can see is the treated environment."""
    assert [name for name in os.environ if name.upper().startswith("DATABRICKS_")] == [
        "DATABRICKS_CONFIG_FILE"
    ]
    assert not Path(os.environ["DATABRICKS_CONFIG_FILE"]).exists()
    assert find_cli() is None
