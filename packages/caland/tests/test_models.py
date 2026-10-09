from __future__ import annotations

import pytest

from caland.domain import (
    SOURCE_BUNDLE,
    SOURCE_PROFILE,
    Scope,
    Workspace,
    perm_rank,
)


def test_perm_rank_orders_permissions():
    assert perm_rank("READ") < perm_rank("WRITE") < perm_rank("MANAGE")
    assert perm_rank("nonsense") == 0


@pytest.mark.parametrize(
    ("backend", "is_kv"), [("DATABRICKS", False), ("AZURE_KEYVAULT", True)]
)
def test_scope_backend_flags(backend, is_kv):
    assert Scope("s", backend).is_keyvault is is_kv


def test_workspace_label_strips_scheme():
    ws = Workspace("prod", "https://x.cloud.databricks.com/")
    assert ws.label == "prod  ·  x.cloud.databricks.com"


def test_profile_workspace_name_and_source():
    ws = Workspace(profile="prod", host="https://prod.cloud.databricks.com")
    assert ws.source == SOURCE_PROFILE
    assert ws.name == "prod"
    assert ws.source_label == "~/.databrickscfg"


def test_bundle_workspace_name_source_and_default_marker():
    ws = Workspace(
        host="https://dab.cloud.databricks.com",
        source=SOURCE_BUNDLE,
        target="acme",
        default=True,
    )
    assert ws.name == "acme"  # no profile -> falls back to the bundle target
    assert ws.host_label == "dab.cloud.databricks.com"
    assert ws.source_label == "databricks.yml  ·  default"
