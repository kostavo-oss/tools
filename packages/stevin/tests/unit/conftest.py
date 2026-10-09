"""Offline tests stay offline.

stevin asks the Databricks CLI what a bundle resolves to, and the Databricks
SDK finds a workspace by itself from the environment and `~/.databrickscfg`. A
machine with a CLI, a token or a DEFAULT profile would answer differently from
one without — and from CI — and could reach a real workspace from a unit test.
So the unit suite hides all of it (`helpers.offline_environment`), and the
tests that want a CLI put a stub on PATH themselves. The live suite, which has
both a CLI and a workspace, doesn't.
"""

import os

import pytest

from helpers import offline_environment


@pytest.fixture(autouse=True)
def _without_databricks(
    monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> None:
    nowhere = tmp_path_factory.getbasetemp() / "no-databrickscfg"
    offline = offline_environment(dict(os.environ), nowhere)
    for name in os.environ.keys() - offline.keys():
        monkeypatch.delenv(name)
    for name, value in offline.items():
        if os.environ.get(name) != value:
            monkeypatch.setenv(name, value)
