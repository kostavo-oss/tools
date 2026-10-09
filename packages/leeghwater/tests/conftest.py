import os
from types import SimpleNamespace

import pytest
from databricks.sdk.errors import PermissionDenied, ResourceDoesNotExist


@pytest.fixture(autouse=True)
def clean_process(tmp_path, monkeypatch):
    """Every test starts in an empty folder, and leaves dlt and the environment alone.

    leeghwater works by setting environment variables and registering config providers,
    so a test that didn't put them back would decide the next one.
    """
    before = dict(os.environ)
    monkeypatch.chdir(tmp_path)
    os.environ["DLT_DATA_DIR"] = str(tmp_path / "dlt-data")
    for name in ("DATABRICKS_RUNTIME_VERSION", "DATABRICKS_CONFIG_PROFILE"):
        os.environ.pop(name, None)
    yield
    os.environ.clear()
    os.environ.update(before)

    import dlt  # noqa: F401
    from dlt.common.configuration.container import Container
    from dlt.common.configuration.specs.pluggable_run_context import PluggableRunContext
    from dlt.common.pipeline import PipelineContext

    from leeghwater import _prepare

    _prepare._current = None
    context = Container()[PluggableRunContext]
    context.reload_providers()
    context.initialize_runtime()
    Container()[PipelineContext].deactivate()


@pytest.fixture
def on_databricks(monkeypatch):
    """A made-up Databricks: the one variable leeghwater reads to know where it runs."""
    monkeypatch.setenv("DATABRICKS_RUNTIME_VERSION", "client.2.5")


class FakeWorkspace:
    """A stand-in for `databricks.sdk.WorkspaceClient`: scopes as dictionaries.

    It answers as the SDK does off Databricks: `dbutils.secrets.get` gives the value as
    text, and a scope or a key that isn't there is a `ResourceDoesNotExist`.
    https://docs.databricks.com/api/workspace/secrets
    """

    def __init__(self, scopes, *, denied=(), user="dev@example.com", broken=None):
        self.scopes = scopes
        self.denied = set(denied)
        self.broken = broken
        self.lists: list[str] = []
        self.reads: list[tuple[str, str]] = []
        self.secrets = self
        self.dbutils = SimpleNamespace(secrets=SimpleNamespace(get=self.get))
        self.current_user = SimpleNamespace(me=lambda: SimpleNamespace(user_name=user))
        self.warehouses = SimpleNamespace(get=self._warehouse)

    def list_secrets(self, scope):
        self.lists.append(scope)
        if self.broken:
            raise self.broken
        if scope not in self.scopes:
            raise ResourceDoesNotExist(f"Scope {scope} does not exist!")
        return [SimpleNamespace(key=key) for key in self.scopes[scope]]

    def get(self, scope, key):
        self.reads.append((scope, key))
        if (scope, key) in self.denied:
            raise PermissionDenied("no READ")
        if key not in self.scopes.get(scope, {}):
            raise ResourceDoesNotExist(f"Secret {key} does not exist!")
        return self.scopes[scope][key]

    def _warehouse(self, warehouse_id):
        if warehouse_id != "abc123":
            raise ResourceDoesNotExist(f"Warehouse {warehouse_id} does not exist")
        return SimpleNamespace(name="ingest", state=SimpleNamespace(value="RUNNING"))


@pytest.fixture
def workspace():
    return FakeWorkspace(
        {
            "ingest": {
                "sources-github-access_token": "tok-from-ingest",
                "sources-orders": '[sources.orders]\napi_key = "key-from-fragment"\n',
                "empty": "",
            },
            "platform-shared": {"github-token": "tok-from-platform"},
        }
    )
