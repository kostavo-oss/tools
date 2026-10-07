"""dlt's secrets from secret scopes: `spec/003`. The scopes here are dictionaries."""

import dlt
import pytest
from databricks.sdk.errors import InternalError, PermissionDenied
from dlt.common.configuration.exceptions import ConfigFieldMissingException
from dlt.common.typing import TSecretStrValue

from conftest import FakeWorkspace
from leeghwater import LeeghwaterError
from leeghwater.secrets import (
    DatabricksSecretsProvider,
    PointedSecretsProvider,
    register_pointed_secrets,
    register_secret_scope,
    split_pointer,
)


@dlt.source
def github(access_token: str = dlt.secrets.value, page_size: int = dlt.config.value):
    @dlt.resource
    def issues():
        yield {"token": access_token, "page_size": page_size}

    return issues


@dlt.source
def orders(api_key: str = dlt.secrets.value):
    @dlt.resource
    def rows():
        yield {"key": api_key}

    return rows


def test_a_secret_is_named_by_dlts_path_joined_with_dashes():
    """As dlt's Google provider names one: `providers/google_secrets.py`."""
    name = DatabricksSecretsProvider.get_key_name

    assert name("access_token", "sources", "github") == "sources-github-access_token"
    assert name("access_token") == "access_token"
    assert name("api.key", "sources", "my source") == "sources-mysource-apikey"


def test_an_argument_of_a_real_source_is_filled_from_the_scope(workspace, monkeypatch):
    monkeypatch.setenv("SOURCES__GITHUB__PAGE_SIZE", "50")
    register_secret_scope("ingest", workspace_client=workspace)

    assert list(github()) == [{"token": "tok-from-ingest", "page_size": 50}]


def test_a_scope_is_listed_once_and_only_what_is_there_is_read(workspace, monkeypatch):
    """dlt tries many paths for one value; most are not in the scope. `spec/003`, R6."""
    monkeypatch.setenv("SOURCES__GITHUB__PAGE_SIZE", "50")
    register_secret_scope("ingest", workspace_client=workspace)

    list(github())
    list(github())

    assert workspace.lists == ["ingest"]
    assert workspace.reads == [("ingest", "sources-github-access_token")]


def test_a_value_that_is_not_a_secret_is_never_asked_of_a_scope(workspace):
    """`page_size` is config. It is in no scope, and no scope is asked for it."""
    register_secret_scope("ingest", workspace_client=workspace)

    with pytest.raises(ConfigFieldMissingException) as missing:
        list(github())

    assert "page_size" in str(missing.value)
    assert all("page_size" not in key for _, key in workspace.reads)


def test_a_secret_can_hold_a_whole_section(workspace):
    """The secret `sources-orders` is a piece of TOML with its own heading."""
    register_secret_scope("ingest", workspace_client=workspace)

    assert list(orders()) == [{"key": "key-from-fragment"}]


def test_a_section_without_its_own_heading_lands_at_the_root():
    """dlt merges a fragment at the root of the document, not under the secret's name.

    `dlt/common/configuration/providers/doc.py`, `set_fragment`. So `api_key = "x"` in a
    secret named `sources-orders` is every source's `api_key`, not only orders'.
    """
    scope = FakeWorkspace({"ingest": {"sources-orders": 'api_key = "everyones"\n'}})
    provider = register_secret_scope("ingest", workspace_client=scope)

    assert list(orders()) == [{"key": "everyones"}]
    assert (
        provider.get_value("api_key", TSecretStrValue, None, "sources", "orders")[0]
        is None
    )
    assert provider.get_value("api_key", TSecretStrValue, None)[0] == "everyones"


def test_dlt_secrets_toml_is_read_as_a_whole_file():
    scope = FakeWorkspace(
        {"ingest": {"dlt_secrets_toml": '[sources.orders]\napi_key = "from-the-file"\n'}}
    )
    register_secret_scope("ingest", workspace_client=scope)

    assert list(orders()) == [{"key": "from-the-file"}]


def test_the_environment_wins_over_a_scope(workspace, monkeypatch):
    """The scope is asked after dlt's own providers. `spec/003`, R1."""
    monkeypatch.setenv("SOURCES__GITHUB__ACCESS_TOKEN", "from-the-environment")
    monkeypatch.setenv("SOURCES__GITHUB__PAGE_SIZE", "50")
    register_secret_scope("ingest", workspace_client=workspace)

    assert list(github())[0]["token"] == "from-the-environment"
    assert workspace.reads == []


def test_the_first_scope_that_has_a_secret_answers(monkeypatch):
    monkeypatch.setenv("SOURCES__GITHUB__PAGE_SIZE", "50")
    both = FakeWorkspace(
        {
            "first": {"sources-github-access_token": "from-first"},
            "second": {"sources-github-access_token": "from-second", "other": "x"},
        }
    )
    register_secret_scope("first", workspace_client=both)
    register_secret_scope("second", workspace_client=both)

    assert list(github())[0]["token"] == "from-first"


def test_registering_a_scope_twice_adds_it_once(workspace):
    first = register_secret_scope("ingest", workspace_client=workspace)
    second = register_secret_scope(" ingest ", workspace_client=workspace)

    assert second is first
    assert [p.name for p in dlt.secrets.config_providers].count(first.name) == 1


def test_a_scope_that_does_not_exist_is_an_error_with_its_name(monkeypatch):
    """Without it every secret is reported missing and nothing says why."""
    register_secret_scope("no-such-scope", workspace_client=FakeWorkspace({}))

    with pytest.raises(LeeghwaterError, match="'no-such-scope' does not exist"):
        list(orders())


def test_a_scope_that_refuses_says_which_scope_and_who_asked():
    refused = FakeWorkspace({"ingest": {}}, broken=PermissionDenied("no"))
    register_secret_scope("ingest", workspace_client=refused)

    with pytest.raises(LeeghwaterError) as error:
        list(orders())

    assert "'ingest'" in str(error.value)
    assert "dev@example.com" in str(error.value)
    assert "READ" in str(error.value)


def test_a_missing_a_refused_and_an_empty_key_are_all_not_here():
    scope = FakeWorkspace(
        {"ingest": {"empty": "", "kept": "x"}}, denied={("ingest", "kept")}
    )
    provider = DatabricksSecretsProvider("ingest", workspace_client=scope)

    assert provider._look_vault("not-there", str) is None
    assert provider._look_vault("kept", str) is None
    assert provider._look_vault("empty", str) is None


def test_any_other_error_is_raised_as_it_came():
    class Down(FakeWorkspace):
        def get(self, scope, key):
            raise InternalError("the workspace is down")

    provider = DatabricksSecretsProvider("ingest", workspace_client=Down({"ingest": {}}))

    with pytest.raises(InternalError):
        provider._look_vault("anything", str)


def test_a_scope_needs_a_name():
    with pytest.raises(LeeghwaterError, match="needs a name"):
        DatabricksSecretsProvider("  ")


def test_a_secret_under_another_name_can_be_pointed_at(workspace, monkeypatch):
    """`spec/003`, R7. What is pointed at wins over the scope's own name for it."""
    monkeypatch.setenv("SOURCES__GITHUB__PAGE_SIZE", "50")
    register_pointed_secrets(
        {"sources.github.access_token": "platform-shared/github-token"},
        workspace_client=workspace,
    )
    register_secret_scope("ingest", workspace_client=workspace)

    assert list(github())[0]["token"] == "tok-from-platform"
    assert workspace.reads == [("platform-shared", "github-token")]


def test_a_pointer_at_nothing_is_an_error_that_names_it(workspace):
    register_pointed_secrets(
        {"sources.orders.api_key": "ingest/not-there"}, workspace_client=workspace
    )
    with pytest.raises(LeeghwaterError, match="no secret 'not-there'") as error:
        list(orders())
    assert "sources-github-access_token" in str(error.value)
    assert "tok-from" not in str(error.value)

    register_pointed_secrets(
        {"sources.orders.api_key": "no-such-scope/x"}, workspace_client=workspace
    )
    with pytest.raises(LeeghwaterError, match="'no-such-scope' does not exist"):
        list(orders())


def test_pointing_again_replaces_what_was_pointed_at(workspace):
    register_pointed_secrets({"a.b": "ingest/x"}, workspace_client=workspace)
    again = register_pointed_secrets({"c.d": "ingest/y"}, workspace_client=workspace)

    pointed = [
        p for p in dlt.secrets.config_providers if isinstance(p, PointedSecretsProvider)
    ]
    assert pointed == [again]
    assert again.paths == ["c.d"]


def test_a_pointer_is_a_scope_and_a_key_split_at_the_first_slash():
    assert split_pointer("a.b", "scope/key/with/slashes") == ("scope", "key/with/slashes")
    for wrong in ("no-slash", "/key", "scope/", ""):
        with pytest.raises(LeeghwaterError, match="<scope>/<key>"):
            split_pointer("a.b", wrong)


def test_the_pointed_provider_is_one_per_process_and_registered_once(workspace):
    first = register_pointed_secrets({"a.b": "ingest/x"}, workspace_client=workspace)
    second = register_pointed_secrets({"c.d": "ingest/y"}, workspace_client=workspace)

    names = [p.name for p in dlt.secrets.config_providers]
    assert second is first
    assert names.count(PointedSecretsProvider.NAME) == 1
    assert first.paths == ["c.d"]


def test_no_value_is_in_what_a_provider_says_about_itself(workspace):
    register_secret_scope("ingest", workspace_client=workspace)
    pointed = register_pointed_secrets(
        {"sources.github.access_token": "platform-shared/github-token"},
        workspace_client=workspace,
    )
    list(orders())

    said = " ".join(
        repr(p) + p.name + str(p.locations) for p in dlt.secrets.config_providers
    )
    assert "key-from-fragment" not in said
    assert "tok-from" not in said
    assert "platform-shared/github-token" in str(pointed.locations)
