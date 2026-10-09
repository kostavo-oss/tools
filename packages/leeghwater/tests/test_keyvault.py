"""dlt's secrets from an Azure Key Vault: `spec/003`, R12. The vault is a dictionary."""

from types import SimpleNamespace

import dlt
import pytest
from azure.core.exceptions import (
    ClientAuthenticationError,
    HttpResponseError,
    ResourceNotFoundError,
)
from dlt.common.configuration.exceptions import ConfigFieldMissingException

from leeghwater import LeeghwaterError, prepare
from leeghwater.keyvault import KeyVaultSecretsProvider, register_key_vault, secret_name
from leeghwater.secrets import register_secret_scope


class FakeVault:
    """A stand-in for `azure.keyvault.secrets.SecretClient`.

    It answers as the SDK does: a listing gives properties with a `name`, a secret that
    isn't there is a `ResourceNotFoundError`, a refused one an `HttpResponseError` 403.
    """

    def __init__(self, secrets, *, denied=(), list_error=None):
        self.secrets = secrets
        self.denied = set(denied)
        self.list_error = list_error
        self.lists = 0
        self.reads: list[str] = []

    def list_properties_of_secrets(self):
        self.lists += 1
        if self.list_error:
            raise self.list_error
        return [SimpleNamespace(name=name) for name in self.secrets]

    def get_secret(self, name):
        self.reads.append(name)
        if name in self.denied:
            error = HttpResponseError("Forbidden")
            error.status_code = 403
            raise error
        if name not in self.secrets:
            raise ResourceNotFoundError("not there")
        return SimpleNamespace(name=name, value=self.secrets[name])


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


VAULT = "https://kv-ingest.vault.azure.net"


@pytest.fixture
def vault():
    return FakeVault(
        {
            "sources-github-access-token": "tok-from-vault",
            "sources-orders": '[sources.orders]\napi_key = "key-from-vault"\n',
        }
    )


def test_a_secret_is_named_without_underscores():
    """A Key Vault allows letters, digits and dashes, and nothing else."""
    assert (
        secret_name("access_token", "sources", "github") == "sources-github-access-token"
    )
    assert secret_name("dlt_secrets_toml") == "dlt-secrets-toml"
    assert secret_name("api.key", "sources", "my source") == "sources-mysource-apikey"


def test_an_argument_of_a_real_source_is_filled_from_the_vault(vault, monkeypatch):
    monkeypatch.setenv("SOURCES__GITHUB__PAGE_SIZE", "50")
    register_key_vault(VAULT, client=vault)

    assert list(github()) == [{"token": "tok-from-vault", "page_size": 50}]
    assert vault.lists == 1
    assert vault.reads == ["sources-github-access-token"]


def test_a_section_in_one_secret(vault):
    register_key_vault(VAULT, client=vault)

    assert list(orders()) == [{"key": "key-from-vault"}]


def test_a_scope_is_asked_before_a_vault(vault, workspace, monkeypatch):
    """The order is the order of registration: scopes first, then vaults."""
    monkeypatch.setenv("SOURCES__GITHUB__PAGE_SIZE", "50")
    register_secret_scope("ingest", workspace_client=workspace)
    register_key_vault(VAULT, client=vault)

    assert list(github())[0]["token"] == "tok-from-ingest"
    assert vault.reads == []


def test_a_missing_and_a_refused_secret_are_not_here():
    vault = FakeVault({"kept": "x"}, denied={"kept"})
    provider = KeyVaultSecretsProvider(VAULT, client=vault)

    assert provider._look_vault("not-there", str) is None
    assert provider._look_vault("kept", str) is None
    assert provider._look_vault("not_a_vault_name", str) is None
    assert vault.reads == ["not-there", "kept"]


def test_nobody_signed_in_is_said_in_plain_words():
    vault = FakeVault({}, list_error=ClientAuthenticationError("no credential"))
    register_key_vault(VAULT, client=vault)

    with pytest.raises(LeeghwaterError, match="az login"):
        list(orders())


@pytest.mark.parametrize(
    ("status", "message"), [(403, "Key Vault Secrets User"), (404, "no Key Vault at")]
)
def test_a_vault_that_refuses_or_is_not_there_names_itself(status, message):
    error = HttpResponseError("no")
    error.status_code = status
    register_key_vault(VAULT, client=FakeVault({}, list_error=error))

    with pytest.raises(LeeghwaterError, match=message) as raised:
        list(orders())
    assert VAULT in str(raised.value)


def test_a_vault_with_nothing_for_dlt_leaves_dlts_own_error(vault):
    register_key_vault(VAULT, client=FakeVault({}))

    with pytest.raises(ConfigFieldMissingException) as missing:
        list(orders())
    assert VAULT in str(missing.value)


def test_a_vault_needs_an_address():
    with pytest.raises(LeeghwaterError, match="named by its address"):
        KeyVaultSecretsProvider("kv-ingest")


def test_registering_a_vault_twice_adds_it_once(vault):
    first = register_key_vault(VAULT, client=vault)
    second = register_key_vault(VAULT + "/", client=vault)

    assert second is first
    assert [p.name for p in dlt.secrets.config_providers].count(first.name) == 1


def test_prepare_names_the_vaults_and_reads_them_on_a_laptop_too(vault):
    """A vault needs no workspace: a laptop without --profile may read one."""
    setup = prepare(key_vaults=[VAULT], key_vault_client=vault)

    assert setup.key_vaults == [VAULT]
    assert "key vaults" in "\n".join(setup.lines())
    assert list(orders()) == [{"key": "key-from-vault"}]
    assert "key-from-vault" not in "\n".join(setup.lines())


def test_no_value_is_in_what_the_provider_says_about_itself(vault):
    provider = register_key_vault(VAULT, client=vault)
    list(orders())

    said = repr(provider) + provider.name + str(provider.locations)
    assert "key-from-vault" not in said
    assert "tok-from" not in said
